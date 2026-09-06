CREATE TABLE IF NOT EXISTS public.pokemon_market_explorer_variant_merge_ledger (
    predecessor_variant_id uuid PRIMARY KEY REFERENCES public.card_variants(id) ON DELETE RESTRICT,
    successor_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'merged' CHECK (status IN ('merged','reverted')),
    merge_reason text NOT NULL DEFAULT 'vintage_edition_predecessor',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    merged_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (predecessor_variant_id <> successor_variant_id)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_market_explorer_variant_merge_ledger_successor
    ON public.pokemon_market_explorer_variant_merge_ledger(successor_variant_id)
    WHERE status = 'merged';

ALTER TABLE public.pokemon_market_explorer_variant_merge_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_explorer_variant_merge_ledger FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pokemon_market_explorer_variant_merge_ledger TO service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_variant_authority(p_set_ids uuid[] DEFAULT NULL::uuid[])
RETURNS TABLE(canonical_card_id uuid, legacy_card_id uuid, card_variant_id uuid, set_id uuid, card_name text, card_number text, rarity text, edition text, printing_type text, special_type text, image_url text, identity_basis text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
WITH canonical_scope AS (
    SELECT canonical.*
    FROM public.pokemon_canonical_cards canonical
    WHERE public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)
      AND (p_set_ids IS NULL OR cardinality(p_set_ids) = 0
           OR canonical.set_id = ANY(p_set_ids))
), candidates AS (
    SELECT canonical.id canonical_card_id, link.legacy_card_id,
           canonical.set_id,
           'explicit_legacy_identity_link'::text identity_basis,
           0 identity_rank
    FROM canonical_scope canonical
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = canonical.id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'parent_pokemon_tcg_api_id', 1
    FROM canonical_scope canonical
    JOIN public.cards card
      ON card.set_id = canonical.set_id
     AND card.pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'variant_pokemon_tcg_api_id', 2
    FROM canonical_scope canonical
    JOIN public.card_variants matched
      ON matched.pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id
    JOIN public.cards card
      ON card.id = matched.card_id AND card.set_id = canonical.set_id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'normalized_name_number_fallback', 3
    FROM canonical_scope canonical
    JOIN public.cards card
      ON card.set_id = canonical.set_id
     AND lower(regexp_replace(trim(card.name), '[[:space:]]+', ' ', 'g')) =
         lower(regexp_replace(trim(canonical.name), '[[:space:]]+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(card.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(canonical.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(canonical.printed_number, '')), '/', 1), '^0+', ''))
), resolved AS (
    SELECT DISTINCT ON (canonical_card_id)
           canonical_card_id, legacy_card_id, set_id, identity_basis
    FROM candidates
    ORDER BY canonical_card_id, identity_rank, legacy_card_id
)
SELECT resolved.canonical_card_id, resolved.legacy_card_id, variant.id,
       resolved.set_id, canonical.name,
       coalesce(canonical.number, canonical.printed_number, legacy.card_number),
       canonical.rarity, variant.edition, variant.printing_type,
       variant.special_type,
       coalesce(variant.image_small_url, canonical.image_small_url,
                legacy.image_small_url),
       resolved.identity_basis
FROM resolved
JOIN public.pokemon_canonical_cards canonical
  ON canonical.id = resolved.canonical_card_id
JOIN public.cards legacy ON legacy.id = resolved.legacy_card_id
JOIN public.card_variants variant ON variant.card_id = resolved.legacy_card_id
WHERE NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_variant_merge_ledger retired
    WHERE retired.predecessor_variant_id = variant.id
      AND retired.status = 'merged'
);
$function$;

CREATE OR REPLACE FUNCTION public.merge_pokemon_card_variant_price_observations(
    p_predecessor_variant_id uuid,
    p_successor_variant_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
AS $function$
DECLARE
    v_pred_card uuid;
    v_succ_card uuid;
    v_pred_edition text;
    v_succ_edition text;
    v_pred_printing text;
    v_succ_printing text;
    v_pred_special text;
    v_succ_special text;
    v_existing_successor uuid;
    v_conflicts bigint := 0;
    v_pred_wins bigint := 0;
    v_succ_wins bigint := 0;
    v_deleted_successor bigint := 0;
    v_deleted_predecessor bigint := 0;
    v_moved bigint := 0;
BEGIN
    IF p_predecessor_variant_id IS NULL OR p_successor_variant_id IS NULL OR p_predecessor_variant_id = p_successor_variant_id THEN
        RAISE EXCEPTION 'predecessor and successor must be distinct non-null variant ids';
    END IF;

    SELECT card_id, edition, printing_type, special_type
      INTO v_pred_card, v_pred_edition, v_pred_printing, v_pred_special
      FROM public.card_variants
     WHERE id = p_predecessor_variant_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'predecessor variant % not found', p_predecessor_variant_id; END IF;

    SELECT card_id, edition, printing_type, special_type
      INTO v_succ_card, v_succ_edition, v_succ_printing, v_succ_special
      FROM public.card_variants
     WHERE id = p_successor_variant_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'successor variant % not found', p_successor_variant_id; END IF;

    IF v_pred_card <> v_succ_card THEN
        RAISE EXCEPTION 'predecessor/successor card_id mismatch: % vs %', v_pred_card, v_succ_card;
    END IF;
    IF NULLIF(trim(coalesce(v_pred_edition,'')), '') IS NOT NULL THEN
        RAISE EXCEPTION 'predecessor % is not generic edition=NULL/empty (edition=%)', p_predecessor_variant_id, v_pred_edition;
    END IF;
    IF v_succ_edition NOT IN ('1st-edition','unlimited') THEN
        RAISE EXCEPTION 'successor % edition % is not an approved explicit edition', p_successor_variant_id, v_succ_edition;
    END IF;
    IF coalesce(v_pred_printing,'') <> coalesce(v_succ_printing,'')
       OR coalesce(v_pred_special,'') <> coalesce(v_succ_special,'') THEN
        RAISE EXCEPTION 'predecessor/successor printing identity mismatch';
    END IF;

    SELECT successor_variant_id INTO v_existing_successor
      FROM public.pokemon_market_explorer_variant_merge_ledger
     WHERE predecessor_variant_id = p_predecessor_variant_id
       AND status = 'merged';
    IF FOUND THEN
        IF v_existing_successor <> p_successor_variant_id THEN
            RAISE EXCEPTION 'predecessor % already retired to different successor %', p_predecessor_variant_id, v_existing_successor;
        END IF;
        RETURN jsonb_build_object('status','already_merged','predecessorVariantId',p_predecessor_variant_id,'successorVariantId',p_successor_variant_id,'movedRows',0);
    END IF;

    WITH conflicts AS (
        SELECT p.id pred_id, s.id succ_id,
               CASE WHEN p.created_at > s.created_at OR (p.created_at = s.created_at AND p.id > s.id)
                    THEN 'predecessor' ELSE 'successor' END winner
        FROM public.card_variant_price_observations p
        JOIN public.card_variant_price_observations s
          ON s.card_variant_id = p_successor_variant_id
         AND s.condition_id = p.condition_id
         AND s.source IS NOT DISTINCT FROM p.source
         AND s.captured_at IS NOT DISTINCT FROM p.captured_at
        WHERE p.card_variant_id = p_predecessor_variant_id
    )
    SELECT count(*), count(*) FILTER (WHERE winner='predecessor'), count(*) FILTER (WHERE winner='successor')
      INTO v_conflicts, v_pred_wins, v_succ_wins
      FROM conflicts;

    WITH conflicts AS (
        SELECT p.id pred_id, s.id succ_id,
               CASE WHEN p.created_at > s.created_at OR (p.created_at = s.created_at AND p.id > s.id)
                    THEN 'predecessor' ELSE 'successor' END winner
        FROM public.card_variant_price_observations p
        JOIN public.card_variant_price_observations s
          ON s.card_variant_id = p_successor_variant_id
         AND s.condition_id = p.condition_id
         AND s.source IS NOT DISTINCT FROM p.source
         AND s.captured_at IS NOT DISTINCT FROM p.captured_at
        WHERE p.card_variant_id = p_predecessor_variant_id
    )
    DELETE FROM public.card_variant_price_observations o
     USING conflicts c
     WHERE c.winner='predecessor' AND o.id=c.succ_id;
    GET DIAGNOSTICS v_deleted_successor = ROW_COUNT;

    WITH conflicts AS (
        SELECT p.id pred_id, s.id succ_id,
               CASE WHEN p.created_at > s.created_at OR (p.created_at = s.created_at AND p.id > s.id)
                    THEN 'predecessor' ELSE 'successor' END winner
        FROM public.card_variant_price_observations p
        JOIN public.card_variant_price_observations s
          ON s.card_variant_id = p_successor_variant_id
         AND s.condition_id = p.condition_id
         AND s.source IS NOT DISTINCT FROM p.source
         AND s.captured_at IS NOT DISTINCT FROM p.captured_at
        WHERE p.card_variant_id = p_predecessor_variant_id
    )
    DELETE FROM public.card_variant_price_observations o
     USING conflicts c
     WHERE c.winner='successor' AND o.id=c.pred_id;
    GET DIAGNOSTICS v_deleted_predecessor = ROW_COUNT;

    UPDATE public.card_variant_price_observations
       SET card_variant_id = p_successor_variant_id
     WHERE card_variant_id = p_predecessor_variant_id;
    GET DIAGNOSTICS v_moved = ROW_COUNT;

    RETURN jsonb_build_object(
        'status','merged_observations',
        'predecessorVariantId',p_predecessor_variant_id,
        'successorVariantId',p_successor_variant_id,
        'conflicts',v_conflicts,
        'predecessorWins',v_pred_wins,
        'successorWins',v_succ_wins,
        'deletedSuccessorLosers',v_deleted_successor,
        'deletedPredecessorLosers',v_deleted_predecessor,
        'movedRows',v_moved
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.retire_pokemon_card_variant_predecessor(
    p_predecessor_variant_id uuid,
    p_successor_variant_id uuid,
    p_merge_reason text DEFAULT 'vintage_edition_predecessor'
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
AS $function$
DECLARE
    v_pred_card uuid;
    v_succ_card uuid;
    v_existing_successor uuid;
    v_sensitive_refs bigint := 0;
    v_observations bigint := 0;
    v_rollups bigint := 0;
    v_intervals bigint := 0;
    v_metrics bigint := 0;
    v_top_hits bigint := 0;
BEGIN
    SELECT card_id INTO v_pred_card FROM public.card_variants WHERE id=p_predecessor_variant_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'predecessor variant % not found', p_predecessor_variant_id; END IF;
    SELECT card_id INTO v_succ_card FROM public.card_variants WHERE id=p_successor_variant_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'successor variant % not found', p_successor_variant_id; END IF;
    IF v_pred_card <> v_succ_card THEN RAISE EXCEPTION 'predecessor/successor card_id mismatch'; END IF;

    SELECT successor_variant_id INTO v_existing_successor
      FROM public.pokemon_market_explorer_variant_merge_ledger
     WHERE predecessor_variant_id=p_predecessor_variant_id AND status='merged';
    IF FOUND THEN
        IF v_existing_successor <> p_successor_variant_id THEN
            RAISE EXCEPTION 'predecessor already retired to a different successor';
        END IF;
        RETURN jsonb_build_object('status','already_retired','predecessorVariantId',p_predecessor_variant_id,'successorVariantId',p_successor_variant_id);
    END IF;

    SELECT count(*) INTO v_observations FROM public.card_variant_price_observations WHERE card_variant_id=p_predecessor_variant_id;
    IF v_observations <> 0 THEN
        RAISE EXCEPTION 'predecessor % still has % source observations; merge observations first', p_predecessor_variant_id, v_observations;
    END IF;

    SELECT
      (SELECT count(*) FROM public.user_card_holdings WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.simulation_input_cards WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.simulation_card_variant_pull_rates WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.simulation_card_variant_exclusions WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.graded_card_variants WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.sealed_product_composition_card_components WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.pokemon_card_chase_efficiency_rows WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.pokemon_canonical_card_market_prices_latest WHERE card_variant_id=p_predecessor_variant_id) +
      (SELECT count(*) FROM public.card_variant_external_identities WHERE card_variant_id=p_predecessor_variant_id)
      INTO v_sensitive_refs;
    IF v_sensitive_refs <> 0 THEN
        RAISE EXCEPTION 'predecessor % has % non-derived references; refusing retirement', p_predecessor_variant_id, v_sensitive_refs;
    END IF;

    DELETE FROM public.card_variant_price_monthly_rollups WHERE card_variant_id=p_predecessor_variant_id;
    GET DIAGNOSTICS v_rollups = ROW_COUNT;
    DELETE FROM public.pokemon_card_variant_market_price_intervals WHERE card_variant_id=p_predecessor_variant_id;
    GET DIAGNOSTICS v_intervals = ROW_COUNT;
    DELETE FROM public.card_variant_market_metrics_latest WHERE card_variant_id=p_predecessor_variant_id;
    GET DIAGNOSTICS v_metrics = ROW_COUNT;
    DELETE FROM public.card_market_top_hits_by_edition_latest WHERE card_variant_id=p_predecessor_variant_id;
    GET DIAGNOSTICS v_top_hits = ROW_COUNT;

    INSERT INTO public.pokemon_market_explorer_variant_merge_ledger(
        predecessor_variant_id, successor_variant_id, status, merge_reason, metadata, merged_at, updated_at
    ) VALUES (
        p_predecessor_variant_id, p_successor_variant_id, 'merged', coalesce(nullif(p_merge_reason,''),'vintage_edition_predecessor'),
        jsonb_build_object('retirementMode','ledger','cardVariantRowPreserved',true), clock_timestamp(), clock_timestamp()
    )
    ON CONFLICT (predecessor_variant_id) DO UPDATE
       SET successor_variant_id=excluded.successor_variant_id,
           status='merged', merge_reason=excluded.merge_reason,
           metadata=excluded.metadata, updated_at=clock_timestamp();

    RETURN jsonb_build_object(
        'status','retired',
        'predecessorVariantId',p_predecessor_variant_id,
        'successorVariantId',p_successor_variant_id,
        'deletedRollups',v_rollups,
        'deletedIntervals',v_intervals,
        'deletedMetrics',v_metrics,
        'deletedTopHits',v_top_hits,
        'cardVariantRowPreserved',true
    );
END;
$function$;

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
AS $function$
DECLARE
    v_metrics jsonb;
    v_hits jsonb;
    v_set_edition jsonb;
BEGIN
    v_metrics := public.refresh_card_variant_market_metrics_latest();
    v_hits := public.refresh_card_market_top_hits_by_edition_latest();
    v_set_edition := public.refresh_set_market_metrics_by_edition_latest();
    RETURN jsonb_build_object('cardMetrics',v_metrics,'topHitsByEdition',v_hits,'setMetricsByEdition',v_set_edition);
END;
$function$;

CREATE OR REPLACE FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
SET work_mem TO '64MB'
AS $function$
DECLARE
    v_expected_coverage integer;
    v_actual_coverage integer;
    v_bad_through integer;
    v_deleted bigint := 0;
    v_inserted bigint := 0;
    v_updated_coverage bigint := 0;
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN RAISE EXCEPTION 'p_set_ids required'; END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date > p_end_date THEN RAISE EXCEPTION 'valid date range required'; END IF;

    SELECT cardinality(array_agg(DISTINCT x)) INTO v_expected_coverage FROM unnest(p_set_ids) x;
    SELECT count(*) INTO v_actual_coverage FROM public.pokemon_market_explorer_card_daily_coverage WHERE set_id=ANY(p_set_ids);
    IF v_actual_coverage <> v_expected_coverage THEN
        RAISE EXCEPTION 'repair projection requires existing coverage for every set: expected %, found %', v_expected_coverage, v_actual_coverage;
    END IF;
    SELECT count(*) INTO v_bad_through FROM public.pokemon_market_explorer_card_daily_coverage WHERE set_id=ANY(p_set_ids) AND computed_through < p_end_date;
    IF v_bad_through <> 0 THEN
        RAISE EXCEPTION 'repair end date % exceeds computed_through for % sets', p_end_date, v_bad_through;
    END IF;

    DELETE FROM public.pokemon_market_explorer_card_daily_states
     WHERE set_id=ANY(p_set_ids) AND market_date BETWEEN p_start_date AND p_end_date;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    INSERT INTO public.pokemon_market_explorer_card_daily_states(market_date,card_variant_id,set_id,market_price)
    SELECT q.market_date, i.card_variant_id, i.set_id, i.market_price
      FROM public.pokemon_market_date_quality q
      JOIN public.pokemon_card_variant_market_price_intervals i
        ON i.set_id=ANY(p_set_ids)
       AND i.valid_from <= q.market_date
       AND (i.valid_to IS NULL OR q.market_date < i.valid_to)
     WHERE q.tcg='pokemon'
       AND q.status IN ('READY','LEGACY_VERIFIED')
       AND q.market_date BETWEEN p_start_date AND p_end_date;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    WITH stats AS (
        SELECT set_id, min(market_date) first_market_date, count(*) row_count
        FROM public.pokemon_market_explorer_card_daily_states
        WHERE set_id=ANY(p_set_ids)
        GROUP BY set_id
    )
    UPDATE public.pokemon_market_explorer_card_daily_coverage c
       SET first_market_date=s.first_market_date,
           row_count=s.row_count,
           refreshed_at=clock_timestamp()
      FROM stats s
     WHERE c.set_id=s.set_id;
    GET DIAGNOSTICS v_updated_coverage = ROW_COUNT;

    RETURN jsonb_build_object('deletedRows',v_deleted,'insertedRows',v_inserted,'coverageRowsUpdated',v_updated_coverage,'startDate',p_start_date,'endDate',p_end_date);
END;
$function$;

CREATE OR REPLACE FUNCTION public.invalidate_pokemon_market_explorer_query_cache_scoped(p_set_ids uuid[])
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
AS $function$
DECLARE
    v_era_ids text[];
    v_set_text text[];
    v_affected bigint := 0;
    v_generation bigint;
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN RAISE EXCEPTION 'p_set_ids required'; END IF;
    SELECT array_agg(DISTINCT x::text) INTO v_set_text FROM unnest(p_set_ids) x;
    SELECT array_agg(DISTINCT era_id::text) INTO v_era_ids FROM public.sets WHERE id=ANY(p_set_ids) AND era_id IS NOT NULL;

    UPDATE public.pokemon_market_explorer_query_cache q
       SET status='stale', build_token=NULL, build_started_at=NULL, build_expires_at=NULL, updated_at=clock_timestamp()
     WHERE q.asset='cards'
       AND q.status IN ('ready','building')
       AND (
          EXISTS (SELECT 1 FROM jsonb_array_elements_text(coalesce(q.normalized_spec->'setIds','[]'::jsonb)) s WHERE s = ANY(v_set_text))
          OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(coalesce(q.normalized_spec->'eraIds','[]'::jsonb)) e WHERE e = ANY(coalesce(v_era_ids,ARRAY[]::text[])))
          OR (
              jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
              AND jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=0
          )
       );
    GET DIAGNOSTICS v_affected = ROW_COUNT;

    UPDATE public.pokemon_market_explorer_cache_state
       SET repair_generation=repair_generation+1, updated_at=clock_timestamp()
     WHERE asset='cards'
     RETURNING repair_generation INTO v_generation;

    RETURN jsonb_build_object('affectedCacheRows',v_affected,'cardsRepairGeneration',v_generation,'setIds',to_jsonb(v_set_text),'eraIds',to_jsonb(coalesce(v_era_ids,ARRAY[]::text[])));
END;
$function$;

REVOKE ALL ON FUNCTION public.merge_pokemon_card_variant_price_observations(uuid,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.retire_pokemon_card_variant_predecessor(uuid,uuid,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.merge_pokemon_card_variant_price_observations(uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.retire_pokemon_card_variant_predecessor(uuid,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition() TO service_role;
GRANT EXECUTE ON FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date) TO service_role;
GRANT EXECUTE ON FUNCTION public.invalidate_pokemon_market_explorer_query_cache_scoped(uuid[]) TO service_role;
