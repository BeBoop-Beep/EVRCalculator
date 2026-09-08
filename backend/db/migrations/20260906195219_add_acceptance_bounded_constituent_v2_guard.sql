SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '20s';

CREATE FUNCTION public.get_pokemon_cards_constituent_routes_v2(
  p_set_ids uuid[], p_start_date date, p_end_date date
)
RETURNS TABLE(set_id uuid, window_start date, window_end date, backend text, reason text)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = ''
AS $function$
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
  END IF;
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;
  RETURN QUERY
  WITH requested AS (
    SELECT DISTINCT u.id FROM unnest(p_set_ids) AS u(id) WHERE u.id IS NOT NULL
  ), assessed AS (
    SELECT r.id,
      coalesce(a.status='complete' AND a.missing_side=0 AND a.mismatches=0
        AND a.old_rows=a.v2_rows AND a.start_date<=a.end_date
        AND e.set_id IS NULL, false) AS approved,
      greatest(p_start_date,a.start_date) AS accepted_start,
      least(p_end_date,a.end_date) AS accepted_end,
      CASE WHEN e.set_id IS NOT NULL THEN 'explicit_legacy_exception'
           ELSE 'no_passing_acceptance' END AS fallback_reason
    FROM requested r
    LEFT JOIN public.pokemon_set_market_constituent_v2_acceptance a ON a.set_id=r.id
    LEFT JOIN public.pokemon_set_market_constituent_legacy_exceptions_v2 e ON e.set_id=r.id
  ), routes AS (
    SELECT a.id,p_start_date AS first_day,p_end_date AS last_day,
      'legacy'::text AS engine,
      CASE WHEN a.approved THEN 'outside_validated_dates' ELSE a.fallback_reason END AS why
    FROM assessed a WHERE NOT a.approved OR a.accepted_start>a.accepted_end
    UNION ALL
    SELECT a.id,a.accepted_start,a.accepted_end,'v2','passing_acceptance_window'
    FROM assessed a WHERE a.approved AND a.accepted_start<=a.accepted_end
    UNION ALL
    SELECT a.id,p_start_date,a.accepted_start-1,'legacy','before_validated_window'
    FROM assessed a WHERE a.approved AND a.accepted_start<=a.accepted_end
      AND p_start_date<a.accepted_start
    UNION ALL
    SELECT a.id,a.accepted_end+1,p_end_date,'legacy','after_validated_window'
    FROM assessed a WHERE a.approved AND a.accepted_start<=a.accepted_end
      AND a.accepted_end<p_end_date
  )
  SELECT r.id,r.first_day,r.last_day,r.engine,r.why
  FROM routes r ORDER BY r.id,r.first_day;
END;
$function$;

CREATE FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(
  p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,
  card_variant_id uuid,source text,captured_at date)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = ''
SET "TimeZone" = 'America/Phoenix'
AS $function$
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
  END IF;
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;
  -- Legacy contract: NULL means unrestricted; an empty array selects no cards.
  IF p_card_ids IS NOT NULL AND cardinality(p_card_ids)=0 THEN
    RETURN;
  END IF;
  RETURN QUERY
  WITH routes AS MATERIALIZED (
    SELECT * FROM public.get_pokemon_cards_constituent_routes_v2(p_set_ids,p_start_date,p_end_date)
  ), v2_groups AS MATERIALIZED (
    SELECT r.window_start,r.window_end,array_agg(r.set_id ORDER BY r.set_id) AS ids
    FROM routes r WHERE r.backend='v2' GROUP BY r.window_start,r.window_end
  ), legacy_groups AS MATERIALIZED (
    SELECT r.window_start,r.window_end,array_agg(r.set_id ORDER BY r.set_id) AS ids
    FROM routes r WHERE r.backend='legacy' GROUP BY r.window_start,r.window_end
  ), combined AS (
    SELECT c.* FROM v2_groups g
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_shadow(
      g.ids,g.window_start,g.window_end,p_card_ids) c
    UNION ALL
    SELECT c.* FROM legacy_groups g
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_legacy_shadow(
      g.ids,g.window_start,g.window_end,p_card_ids) c
  )
  SELECT c.canonical_card_id,c.set_id,c.market_date,c.market_price,c.card_variant_id,c.source,c.captured_at
  FROM combined c ORDER BY c.market_date,c.canonical_card_id,c.set_id;
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_constituent_routes_v2(uuid[],date,date) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(uuid[],date,date,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_constituent_routes_v2(uuid[],date,date) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(uuid[],date,date,uuid[]) TO service_role;

INSERT INTO public.price_storage_v2_migration_audit(phase,details)
SELECT 'constituent_guard_staged_20260906',jsonb_build_object(
  'production_changed',false,'raw_history_deleted',false,
  'empty_card_filter_legacy_rows',0,'empty_card_filter_previous_v2_rows',237,
  'hybrid_definition_before',pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[])'::regprocedure),
  'public_definition_before',pg_get_functiondef('public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[])'::regprocedure),
  'v2_definition_hash',md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure)),
  'legacy_definition_hash',md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_legacy_shadow(uuid[],date,date,uuid[])'::regprocedure))
);
