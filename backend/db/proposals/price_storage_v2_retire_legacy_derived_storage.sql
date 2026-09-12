-- PROPOSAL ONLY -- DO NOT APPLY BEFORE A FRESH POST-2026-09-08 SCRAPE PASSES.
--
-- Retires only derived legacy Market Explorer storage after proving that a real
-- fresh scrape advanced the complete Price Storage V2 path.
--
-- Intentionally preserved by this proposal:
--   * public.card_variant_price_observations           (raw source history)
--   * public.card_variant_price_monthly_rollups        (still-current published destination)
--   * public.pokemon_market_explorer_card_daily_coverage (small compatibility routing metadata)
--   * all Price Storage V2 event/current/range/interval/daily/history tables
--
-- Targeted for retirement:
--   * public.pokemon_market_explorer_card_daily_states (~1.45 GB at 2026-09-08 audit)
--   * public.pokemon_card_variant_market_price_intervals (~2.09 GB after index reclaim)
--
-- Existing backend RPC signatures that may still be called are rebound to V2
-- before the physical tables are dropped. DROP TABLE deliberately omits CASCADE.

BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='120s';

-- -------------------------------------------------------------------------
-- A. Hard fresh-cycle gate. The latest raw scrape must be AFTER the frozen
--    Sep 8 transition date and must reconcile exactly into V2 current state,
--    change events, open intervals, and all tracked-set daily coverage.
-- -------------------------------------------------------------------------
DO $gate$
DECLARE
  v_date date;
  v_raw bigint;
  v_current_exact bigint;
  v_current_diff bigint;
  v_events bigint;
  v_event_exact bigint;
  v_event_diff bigint;
  v_interval_expected bigint;
  v_interval_actual bigint;
  v_interval_diff bigint;
  v_tracked_sets integer;
  v_coverage_rows integer;
  v_coverage_through integer;
BEGIN
  SELECT max(o.captured_at)::date
    INTO v_date
  FROM public.card_variant_price_observations o
  WHERE o.captured_at > DATE '2026-09-08';

  IF v_date IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE='Price Storage V2 derived retirement blocked: no fresh scrape exists after 2026-09-08';
  END IF;

  WITH raw_latest AS (
    SELECT *
    FROM (
      SELECT
        o.id,o.card_variant_id,o.condition_id,
        coalesce(o.source,'') AS source,
        trim(both '"' from upper(coalesce(o.currency,''))) AS currency,
        o.market_price,o.high_price,o.low_price,o.captured_at,o.created_at,
        row_number() OVER (
          PARTITION BY o.card_variant_id,o.condition_id,coalesce(o.source,''),
                       trim(both '"' from upper(coalesce(o.currency,'')))
          ORDER BY o.created_at DESC,o.id DESC
        ) AS rn
      FROM public.card_variant_price_observations o
      WHERE o.captured_at=v_date
    ) ranked
    WHERE rn=1
  ), current_cmp AS (
    SELECT (
      c.last_observation_id=r.id
      AND c.last_observed_date=r.captured_at
      AND c.market_price IS NOT DISTINCT FROM r.market_price
      AND c.high_price IS NOT DISTINCT FROM r.high_price
      AND c.low_price IS NOT DISTINCT FROM r.low_price
    ) AS exact
    FROM raw_latest r
    LEFT JOIN public.card_variant_price_current_v2 c
      ON c.card_variant_id=r.card_variant_id
     AND c.condition_id=r.condition_id
     AND c.source=r.source
     AND c.currency=r.currency
  )
  SELECT count(*),
         count(*) FILTER (WHERE exact),
         count(*) FILTER (WHERE NOT coalesce(exact,false))
    INTO v_raw,v_current_exact,v_current_diff
  FROM current_cmp;

  IF v_raw=0 OR v_current_exact<>v_raw OR v_current_diff<>0 THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE=format('Price Storage V2 current provenance failed for %s: raw=%s exact=%s diff=%s',
                     v_date,v_raw,v_current_exact,v_current_diff);
  END IF;

  WITH event_cmp AS (
    SELECT (
      o.id IS NOT NULL
      AND o.captured_at=e.effective_date
      AND o.market_price IS NOT DISTINCT FROM e.market_price
      AND o.high_price IS NOT DISTINCT FROM e.high_price
      AND o.low_price IS NOT DISTINCT FROM e.low_price
    ) AS exact
    FROM public.card_variant_price_events_v2 e
    LEFT JOIN public.card_variant_price_observations o
      ON o.id=e.source_observation_id
    WHERE e.effective_date=v_date
  )
  SELECT count(*),
         count(*) FILTER (WHERE exact),
         count(*) FILTER (WHERE NOT coalesce(exact,false))
    INTO v_events,v_event_exact,v_event_diff
  FROM event_cmp;

  IF v_event_exact<>v_events OR v_event_diff<>0 THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE=format('Price Storage V2 event provenance failed for %s: events=%s exact=%s diff=%s',
                     v_date,v_events,v_event_exact,v_event_diff);
  END IF;

  WITH near_mint AS (
    SELECT id FROM public.conditions WHERE lower(name)='near mint' ORDER BY id LIMIT 1
  ), expected AS (
    SELECT m.card_variant_id,m.set_id,c.market_price
    FROM public.pokemon_market_explorer_card_current_metadata m
    CROSS JOIN near_mint nm
    JOIN public.card_variant_price_current_v2 c
      ON c.card_variant_id=m.card_variant_id
     AND c.condition_id=nm.id
     AND c.source='TCGPlayer'
     AND c.currency='USD'
     AND c.market_price>0
  ), actual AS (
    SELECT card_variant_id,set_id,market_price
    FROM public.pokemon_market_price_intervals_v2_shadow
    WHERE valid_to IS NULL
  ), diff AS (
    SELECT coalesce(e.card_variant_id,a.card_variant_id) AS id
    FROM expected e
    FULL JOIN actual a USING(card_variant_id,set_id)
    WHERE e.card_variant_id IS NULL
       OR a.card_variant_id IS NULL
       OR e.market_price IS DISTINCT FROM a.market_price
  )
  SELECT (SELECT count(*) FROM expected),
         (SELECT count(*) FROM actual),
         (SELECT count(*) FROM diff)
    INTO v_interval_expected,v_interval_actual,v_interval_diff;

  IF v_interval_expected<>v_interval_actual OR v_interval_diff<>0 THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE=format('Price Storage V2 open-interval parity failed for %s: expected=%s actual=%s diff=%s',
                     v_date,v_interval_expected,v_interval_actual,v_interval_diff);
  END IF;

  SELECT count(DISTINCT set_id)::integer
    INTO v_tracked_sets
  FROM public.pokemon_market_explorer_card_current_metadata;

  SELECT count(*)::integer,
         count(*) FILTER (WHERE computed_through>=v_date)::integer
    INTO v_coverage_rows,v_coverage_through
  FROM public.pokemon_market_explorer_card_daily_coverage_v2_shadow;

  IF v_tracked_sets=0
     OR v_coverage_rows<>v_tracked_sets
     OR v_coverage_through<>v_tracked_sets THEN
    RAISE EXCEPTION USING ERRCODE='55000',
      MESSAGE=format('Price Storage V2 daily coverage failed for %s: tracked=%s coverage=%s through=%s',
                     v_date,v_tracked_sets,v_coverage_rows,v_coverage_through);
  END IF;
END
$gate$;

-- -------------------------------------------------------------------------
-- B. Preserve legacy RPC signatures, but remove their physical V1 dependency.
--    Existing callers continue to work; old-window queries now use the V2
--    compact-interval fallback instead of the legacy daily state table.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[],
  p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[],
  p_top_n integer DEFAULT NULL::integer,
  p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
) RETURNS TABLE(
  market_date date,
  constituent_count bigint,
  eligible_universe_count bigint,
  basket_value numeric,
  common_count bigint,
  common_current_value numeric,
  common_previous_value numeric,
  current_constituents jsonb
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET statement_timeout TO '300s'
AS $function$
  SELECT *
  FROM public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n,p_card_variant_ids
  );
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_use_v2 boolean,
  p_card_ids uuid[] DEFAULT NULL::uuid[],
  p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[],
  p_top_n integer DEFAULT NULL::integer,
  p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
) RETURNS TABLE(
  market_date date,
  constituent_count bigint,
  eligible_universe_count bigint,
  basket_value numeric,
  common_count bigint,
  common_current_value numeric,
  common_previous_value numeric
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET work_mem TO '64MB'
SET statement_timeout TO '300s'
AS $function$
  SELECT q.market_date,q.constituent_count,q.eligible_universe_count,q.basket_value,
         q.common_count,q.common_current_value,q.common_previous_value
  FROM public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n,p_card_variant_ids
  ) q;
$function$;

CREATE OR REPLACE FUNCTION public.accept_pokemon_market_explorer_filtered_cohort_two_date(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[],
  p_segment_ids text[] DEFAULT NULL::text[],
  p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
  p_price_segment_ids text[] DEFAULT NULL::text[],
  p_release_age_cohort_ids text[] DEFAULT NULL::text[],
  p_top_n integer DEFAULT NULL::integer
) RETURNS TABLE(
  market_date date,
  constituent_count bigint,
  eligible_universe_count bigint,
  basket_value numeric,
  common_count bigint,
  common_current_value numeric,
  common_previous_value numeric,
  current_constituents jsonb
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET statement_timeout TO '60s'
AS $function$
  SELECT *
  FROM public.get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids,p_segment_ids,p_pokemon_ids,
    p_price_segment_ids,p_release_age_cohort_ids,p_top_n,NULL::uuid[]
  );
$function$;

-- The old manual interval refresh entry points keep their names/return types,
-- but now rebuild the V2 interval authority. Rebuilding full affected sets is
-- deliberate and safer than pretending a subset-only V2 interval refresh exists.
CREATE OR REPLACE FUNCTION public.refresh_pokemon_card_variant_market_price_intervals(
  p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
) RETURNS bigint
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
  v_set_ids uuid[];
  v_result jsonb;
BEGIN
  IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids)=0 THEN
    RETURN 0;
  END IF;

  SELECT array_agg(DISTINCT c.set_id ORDER BY c.set_id)
    INTO v_set_ids
  FROM public.card_variants cv
  JOIN public.cards c ON c.id=cv.card_id
  WHERE cv.id=ANY(p_card_variant_ids);

  IF v_set_ids IS NULL OR cardinality(v_set_ids)=0 THEN
    RETURN 0;
  END IF;

  v_result:=public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(v_set_ids);
  RETURN coalesce((v_result->>'interval_rows')::bigint,0);
END
$function$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_card_variant_market_price_intervals_for_sets(
  p_set_ids uuid[]
) RETURNS bigint
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
  v_result jsonb;
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RETURN 0;
  END IF;
  v_result:=public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(p_set_ids);
  RETURN coalesce((v_result->>'interval_rows')::bigint,0);
END
$function$;

-- Keep the predecessor-retirement maintenance contract operational after the
-- V1 interval table disappears. Source observations remain the deletion guard;
-- V2 interval/monthly projections are the derived rows cleaned up here.
CREATE OR REPLACE FUNCTION public.retire_pokemon_card_variant_predecessor(
  p_predecessor_variant_id uuid,
  p_successor_variant_id uuid,
  p_merge_reason text DEFAULT 'vintage_edition_predecessor'::text
) RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
AS $function$
DECLARE
  v_pred_card uuid;
  v_succ_card uuid;
  v_existing_successor uuid;
  v_sensitive_refs bigint:=0;
  v_observations bigint:=0;
  v_rollups bigint:=0;
  v_v2_rollups bigint:=0;
  v_intervals bigint:=0;
  v_metrics bigint:=0;
  v_top_hits bigint:=0;
BEGIN
  SELECT card_id INTO v_pred_card FROM public.card_variants WHERE id=p_predecessor_variant_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'predecessor variant % not found',p_predecessor_variant_id; END IF;
  SELECT card_id INTO v_succ_card FROM public.card_variants WHERE id=p_successor_variant_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'successor variant % not found',p_successor_variant_id; END IF;
  IF v_pred_card<>v_succ_card THEN RAISE EXCEPTION 'predecessor/successor card_id mismatch'; END IF;

  SELECT successor_variant_id INTO v_existing_successor
  FROM public.pokemon_market_explorer_variant_merge_ledger
  WHERE predecessor_variant_id=p_predecessor_variant_id AND status='merged';
  IF FOUND THEN
    IF v_existing_successor<>p_successor_variant_id THEN
      RAISE EXCEPTION 'predecessor already retired to a different successor';
    END IF;
    RETURN jsonb_build_object('status','already_retired','predecessorVariantId',p_predecessor_variant_id,'successorVariantId',p_successor_variant_id);
  END IF;

  SELECT count(*) INTO v_observations
  FROM public.card_variant_price_observations
  WHERE card_variant_id=p_predecessor_variant_id;
  IF v_observations<>0 THEN
    RAISE EXCEPTION 'predecessor % still has % source observations; merge observations first',p_predecessor_variant_id,v_observations;
  END IF;

  SELECT
    (SELECT count(*) FROM public.user_card_holdings WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.simulation_input_cards WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.simulation_card_variant_pull_rates WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.simulation_card_variant_exclusions WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.graded_card_variants WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.sealed_product_composition_card_components WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.pokemon_card_chase_efficiency_rows WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.pokemon_canonical_card_market_prices_latest WHERE card_variant_id=p_predecessor_variant_id)+
    (SELECT count(*) FROM public.card_variant_external_identities WHERE card_variant_id=p_predecessor_variant_id)
    INTO v_sensitive_refs;
  IF v_sensitive_refs<>0 THEN
    RAISE EXCEPTION 'predecessor % has % non-derived references; refusing retirement',p_predecessor_variant_id,v_sensitive_refs;
  END IF;

  DELETE FROM public.card_variant_price_monthly_rollups WHERE card_variant_id=p_predecessor_variant_id;
  GET DIAGNOSTICS v_rollups=ROW_COUNT;
  DELETE FROM public.card_variant_price_monthly_rollups_v2_shadow WHERE card_variant_id=p_predecessor_variant_id;
  GET DIAGNOSTICS v_v2_rollups=ROW_COUNT;
  DELETE FROM public.pokemon_market_price_intervals_v2_shadow WHERE card_variant_id=p_predecessor_variant_id;
  GET DIAGNOSTICS v_intervals=ROW_COUNT;
  DELETE FROM public.card_variant_market_metrics_latest WHERE card_variant_id=p_predecessor_variant_id;
  GET DIAGNOSTICS v_metrics=ROW_COUNT;
  DELETE FROM public.card_market_top_hits_by_edition_latest WHERE card_variant_id=p_predecessor_variant_id;
  GET DIAGNOSTICS v_top_hits=ROW_COUNT;

  INSERT INTO public.pokemon_market_explorer_variant_merge_ledger(
    predecessor_variant_id,successor_variant_id,status,merge_reason,metadata,merged_at,updated_at
  ) VALUES(
    p_predecessor_variant_id,p_successor_variant_id,'merged',
    coalesce(nullif(p_merge_reason,''),'vintage_edition_predecessor'),
    jsonb_build_object('retirementMode','ledger','cardVariantRowPreserved',true),
    clock_timestamp(),clock_timestamp()
  )
  ON CONFLICT(predecessor_variant_id) DO UPDATE SET
    successor_variant_id=excluded.successor_variant_id,
    status='merged',merge_reason=excluded.merge_reason,
    metadata=excluded.metadata,updated_at=clock_timestamp();

  RETURN jsonb_build_object(
    'status','retired',
    'predecessorVariantId',p_predecessor_variant_id,
    'successorVariantId',p_successor_variant_id,
    'deletedRollups',v_rollups,
    'deletedV2Rollups',v_v2_rollups,
    'deletedIntervals',v_intervals,
    'deletedMetrics',v_metrics,
    'deletedTopHits',v_top_hits,
    'cardVariantRowPreserved',true
  );
END
$function$;

-- Explicitly remove legacy-only diagnostics/repair functions whose physical
-- source disappears. They are service-role-only and have no active callers
-- after the compatibility rebinds above.
DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_cohort_legacy_shadow(
  uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer
);
DROP FUNCTION IF EXISTS public.get_pokemon_market_root_set_value_daily_history_v1_legacy_shado(
  uuid,date,date
);
DROP FUNCTION IF EXISTS public.reproject_pokemon_market_explorer_card_daily_states(
  uuid[],date,date
);

-- -------------------------------------------------------------------------
-- C. Physical retirement. NO CASCADE: unexpected catalog dependencies block.
-- -------------------------------------------------------------------------
DROP TABLE public.pokemon_market_explorer_card_daily_states;
DROP TABLE public.pokemon_card_variant_market_price_intervals;

-- -------------------------------------------------------------------------
-- D. Postconditions: raw source history and the still-current monthly-rollup
--    destination must remain. Primary public readers must still be V2-routed.
-- -------------------------------------------------------------------------
DO $post$
BEGIN
  IF to_regclass('public.pokemon_market_explorer_card_daily_states') IS NOT NULL
     OR to_regclass('public.pokemon_card_variant_market_price_intervals') IS NOT NULL THEN
    RAISE EXCEPTION 'legacy derived relation retirement did not complete';
  END IF;
  IF to_regclass('public.card_variant_price_observations') IS NULL THEN
    RAISE EXCEPTION 'raw observation history was unexpectedly removed';
  END IF;
  IF to_regclass('public.card_variant_price_monthly_rollups') IS NULL THEN
    RAISE EXCEPTION 'current monthly-rollup destination was unexpectedly removed';
  END IF;
  IF strpos(pg_get_functiondef('public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[])'::regprocedure),
            'get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow')=0 THEN
    RAISE EXCEPTION 'Market Explorer primary reader is no longer V2-routed';
  END IF;
  IF strpos(pg_get_functiondef('public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[])'::regprocedure),
            'get_pokemon_cards_daily_constituents_v2_hybrid_shadow')=0 THEN
    RAISE EXCEPTION 'canonical constituent reader is no longer V2-routed';
  END IF;
  IF strpos(pg_get_functiondef('public.get_pokemon_market_root_set_value_daily_history_v1(uuid,date,date)'::regprocedure),
            'pokemon_market_root_set_value_daily_history_v2_shadow')=0 THEN
    RAISE EXCEPTION 'root Set Value history is no longer V2-routed';
  END IF;
END
$post$;

-- Preserve backend-only execution posture for compatibility helpers.
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]),
  public.get_pokemon_market_explorer_filtered_cohort_materialized_series(uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer,uuid[]),
  public.accept_pokemon_market_explorer_filtered_cohort_two_date(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer),
  public.refresh_pokemon_card_variant_market_price_intervals(uuid[]),
  public.refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[]),
  public.retire_pokemon_card_variant_predecessor(uuid,uuid,text)
FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer,uuid[]),
  public.get_pokemon_market_explorer_filtered_cohort_materialized_series(uuid[],date,date,boolean,uuid[],text[],bigint[],text[],text[],integer,uuid[]),
  public.accept_pokemon_market_explorer_filtered_cohort_two_date(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer),
  public.refresh_pokemon_card_variant_market_price_intervals(uuid[]),
  public.refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[]),
  public.retire_pokemon_card_variant_predecessor(uuid,uuid,text)
TO service_role;

COMMIT;