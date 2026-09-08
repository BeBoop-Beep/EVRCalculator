SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $check$
BEGIN
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'cab2e26e26e61a0fdddc1c2cafe17028' THEN
    RAISE EXCEPTION 'V2 reader changed since inspection; revalidate before installing routing guard';
  END IF;
END;
$check$;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(
  p_set_ids uuid[], p_start_date date, p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
  canonical_card_id uuid, set_id uuid, market_date date,
  market_price numeric, card_variant_id uuid, source text, captured_at date
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ''
SET "TimeZone" = 'America/Phoenix'
AS $function$
DECLARE
  v_reader_verified boolean;
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
  END IF;
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;

  -- NULL means unrestricted. An explicitly empty filter means no cards,
  -- matching the original public constituent contract.
  IF p_card_ids IS NOT NULL AND cardinality(p_card_ids)=0 THEN
    RETURN;
  END IF;

  -- Acceptance is tied to the actual tested implementation, not its name.
  -- A subsequent reader change falls back to raw until independently accepted.
  v_reader_verified := md5(pg_get_functiondef(
    'public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure
  )) = 'cab2e26e26e61a0fdddc1c2cafe17028';

  RETURN QUERY
  WITH requested AS MATERIALIZED (
    SELECT DISTINCT u.requested_set_id
    FROM unnest(p_set_ids) AS u(requested_set_id)
    WHERE u.requested_set_id IS NOT NULL
  ), approved AS MATERIALIZED (
    SELECT r.requested_set_id, a.start_date, a.end_date
    FROM requested r
    JOIN public.pokemon_set_market_constituent_v2_acceptance a
      ON a.set_id=r.requested_set_id
    WHERE v_reader_verified
      AND a.status='complete'
      AND a.missing_side=0
      AND a.mismatches=0
      AND a.old_rows=a.v2_rows
      AND a.start_date IS NOT NULL
      AND a.end_date IS NOT NULL
      AND a.start_date<=a.end_date
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_set_market_constituent_legacy_exceptions_v2 e
        WHERE e.set_id=r.requested_set_id
      )
  ), v2_segments AS MATERIALIZED (
    SELECT a.requested_set_id,
           greatest(p_start_date,a.start_date) AS from_date,
           least(p_end_date,a.end_date) AS through_date
    FROM approved a
    WHERE a.start_date<=p_end_date AND a.end_date>=p_start_date
  ), legacy_segments AS MATERIALIZED (
    -- Unaccepted sets retain their existing reader in full.
    SELECT r.requested_set_id, p_start_date AS from_date, p_end_date AS through_date
    FROM requested r
    WHERE NOT EXISTS(SELECT 1 FROM approved a WHERE a.requested_set_id=r.requested_set_id)
    UNION ALL
    -- Before and after the tested range, use legacy, with no overlap.
    SELECT a.requested_set_id,p_start_date,least(p_end_date,a.start_date-1)
    FROM approved a WHERE p_start_date<a.start_date
    UNION ALL
    SELECT a.requested_set_id,greatest(p_start_date,a.end_date+1),p_end_date
    FROM approved a WHERE p_end_date>a.end_date
  ), result_rows AS (
    -- Bounded per-set calls avoid the pathological all-set expansion observed
    -- when feeding the V2 SQL function a large multi-set array.
    SELECT v.*
    FROM v2_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) v
    UNION ALL
    SELECT l.*
    FROM legacy_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_legacy_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) l
  )
  SELECT r.canonical_card_id,r.set_id,r.market_date,r.market_price,
         r.card_variant_id,r.source,r.captured_at
  FROM result_rows r
  ORDER BY r.market_date,r.canonical_card_id,r.set_id;
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(uuid[],date,date,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(uuid[],date,date,uuid[]) TO service_role;
COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(uuid[],date,date,uuid[]) IS 'Candidate compatibility guard: exact accepted sets/dates only; legacy exceptions retained; NULL and empty card filters distinguished; stable globally ordered output. No production reader switched by this migration.';

INSERT INTO public.price_storage_v2_migration_audit(phase,details)
VALUES ('guarded_constituent_reader_candidate_created',jsonb_build_object(
  'production_reader_switched',false,
  'destructive_cleanup_started',false,
  'confirmed_empty_filter_legacy_rows',0,
  'confirmed_empty_filter_pre_guard_production_rows',237,
  'tested_v2_definition_md5','cab2e26e26e61a0fdddc1c2cafe17028',
  'legacy_exception_sets',(SELECT count(*) FROM public.pokemon_set_market_constituent_legacy_exceptions_v2),
  'full_history_exact_sets',(SELECT count(*) FROM public.pokemon_set_market_constituent_v2_acceptance WHERE status='complete' AND mismatches=0 AND missing_side=0 AND old_rows=v2_rows)
));