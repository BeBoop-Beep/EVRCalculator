-- 067: repoint the authoritative publish RPC at the canonical V9 contract.
--
-- WHY THIS EXISTS
-- ---------------
-- Migration 062 pinned the RPC to the V7 identity: it counted ranked targets by
-- `overallRipV7.rank`, required `publicRipContractV7.contractVersion`, and
-- asserted the snapshot's version columns against the V7-era strings. The
-- Collector Appeal V5 cutover changes three of those four strings:
--
--     collector appeal : collector_appeal_v3_balanced_d40_h35_p25
--                     -> collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2
--     overall rip      : overall_rip_v7_90_financial_v3_10_collector_appeal_v3
--                     -> overall_rip_v9_90_financial_v3_10_collector_appeal_v5
--     public contract  : public_rip_contract_v7 -> public_rip_contract_v9
--
-- Financial RIP V3 is UNCHANGED, and so is the 90/10 split. Only the appeal
-- input moved - but the identity strings name the inputs, so they all move with
-- it, and this function fails closed against the old ones.
--
-- WITHOUT THIS MIGRATION THE CUTOVER CANNOT PUBLISH AT ALL, which is the
-- correct failure mode: the application would build a V9 payload and the
-- database would refuse it as "overall RIP version ... is not the canonical
-- ...". That is a loud, immediate, transactional rejection rather than a
-- half-published leaderboard, and it is why the version assertions live in the
-- RPC in the first place.
--
-- 054 AND 061 ARE NOT EDITED. This is a forward-only CREATE OR REPLACE, so the
-- historical record of what the RPC used to be stays intact and reversible: the
-- rollback is to re-apply 062.
--
-- WHAT IS PRESERVED VERBATIM FROM 062
-- -----------------------------------
-- Everything except the four identity strings and the two payload key paths:
--   * one atomic transaction, history rows inserted BEFORE `latest` is promoted;
--   * idempotent snapshot conflict behaviour on
--     (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version);
--   * the single materialised `v_canonical` definition of a ranked target, so
--     no second copy of the predicate can drift from the first;
--   * ranked targets must carry a ready, rankable Financial RIP V3;
--   * ranks must be CONTIGUOUS 1..expected with no duplicates;
--   * set parity checked in BOTH directions;
--   * SECURITY DEFINER with a pinned search_path, REVOKE FROM PUBLIC, and the
--     service_role EXECUTE grant.
--
-- A NOTE ON `ca7_version`
-- -----------------------
-- The column is still called `ca7_version`. It has been the canonical Collector
-- Appeal version column since long before CA7 stopped being canonical, and
-- renaming it here would rewrite the meaning of every historical row for a
-- cosmetic gain. It carries the V4 string now, exactly as it carried the V3
-- string before. The publication contract already documents this.

BEGIN;

CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard(
    p_snapshot JSONB, p_rows JSONB, p_latest JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    -- The canonical identity this RPC will publish under. Restated here because
    -- a SQL function cannot import Python config; every one of these strings is
    -- asserted against backend.desirability.scoring_config /
    -- backend.desirability.collector_appeal by the migration contract test, so
    -- the two copies cannot drift silently.
    c_financial_rip_version CONSTANT TEXT := 'financial_rip_v3_outcome_profile_25_20_15_25_10_5';
    c_collector_appeal_version CONSTANT TEXT := 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2';
    c_overall_rip_version CONSTANT TEXT := 'overall_rip_v9_90_financial_v3_10_collector_appeal_v5';
    c_public_contract_version CONSTANT TEXT := 'public_rip_contract_v9';

    v_snapshot_id UUID;
    v_requested_id UUID := (p_snapshot->>'id')::UUID;
    v_expected INTEGER := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    v_rows INTEGER;
    v_total_targets INTEGER;
    v_ranked_targets INTEGER;
    v_ranked_target_ids INTEGER;
    v_distinct_ranked_target_ids INTEGER;
    v_distinct_ranks INTEGER;
    v_min_rank INTEGER;
    v_max_rank INTEGER;
    v_history_ids INTEGER;
    v_distinct_history_ids INTEGER;
    v_unsupported INTEGER;
    v_payload JSONB := p_latest->'ranking_payload_json';
    v_canonical JSONB;
    v_diag JSONB := COALESCE(p_snapshot->'diagnostics', '{}'::JSONB);
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'RIP history rows must be an array';
    END IF;
    IF jsonb_typeof(v_payload->'targets') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'latest RIP targets must be an array';
    END IF;

    v_rows := jsonb_array_length(p_rows);
    v_total_targets := jsonb_array_length(v_payload->'targets');

    -- The ONE definition of a canonical ranked target in this function. It is
    -- materialised into `v_canonical` exactly once; every count, every set
    -- comparison and every rank check below reads that variable, so there is no
    -- second copy of the predicate that can fall out of step with the first.
    -- (Deliberately a JSONB variable rather than a temp table: this function is
    -- SECURITY DEFINER with `search_path = public` pinned, and pg_temp is not on
    -- that path.)
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
               'set_id', COALESCE(target->>'set_id', target->>'target_id'),
               'v9_rank', target #> '{overallRipV9,rank}'
           )), '[]'::JSONB)
      INTO v_canonical
      FROM jsonb_array_elements(v_payload->'targets') AS target
     WHERE target #> '{overallRipV9,rank}' IS NOT NULL
       AND target #> '{overallRipV9,rank}' <> 'null'::JSONB
       AND target #> '{overallRipV9,score}' IS NOT NULL
       AND target #> '{overallRipV9,score}' <> 'null'::JSONB
       AND target #> '{financialRipV3,score}' IS NOT NULL
       AND target #> '{financialRipV3,score}' <> 'null'::JSONB
       AND target #> '{financialRipV3,rank}' IS NOT NULL
       AND target #> '{financialRipV3,rank}' <> 'null'::JSONB
       AND target #>> '{financialRipV3,status}' = 'ready'
       AND target #> '{financialRipV3,rankable}' = 'true'::JSONB
       AND target #>> '{publicRipContractV9,contractVersion}' = c_public_contract_version;

    SELECT count(*),
           count(NULLIF(entry->>'set_id', '')),
           count(DISTINCT NULLIF(entry->>'set_id', '')),
           count(DISTINCT (entry->>'v9_rank')::INTEGER),
           min((entry->>'v9_rank')::INTEGER),
           max((entry->>'v9_rank')::INTEGER)
      INTO v_ranked_targets, v_ranked_target_ids, v_distinct_ranked_target_ids,
           v_distinct_ranks, v_min_rank, v_max_rank
      FROM jsonb_array_elements(v_canonical) AS entry;

    SELECT count(CASE WHEN history->>'set_id' IS NOT NULL THEN 1 END),
           count(DISTINCT history->>'set_id')
      INTO v_history_ids, v_distinct_history_ids
      FROM jsonb_array_elements(p_rows) AS history;

    -- 1. The cohort must exist and must be complete on both sides.
    IF v_expected <= 0 THEN
        RAISE EXCEPTION 'invalid RIP cohort size: expected %', v_expected;
    END IF;
    IF v_rows <> v_expected THEN
        RAISE EXCEPTION 'incomplete RIP cohort: expected %, received %', v_expected, v_rows;
    END IF;
    IF v_ranked_targets <> v_expected THEN
        RAISE EXCEPTION
            'canonical Overall RIP V9 ranked target count does not match cohort: expected %, received %',
            v_expected, v_ranked_targets;
    END IF;
    IF v_total_targets < v_expected THEN
        RAISE EXCEPTION 'latest RIP target array is smaller than ranked cohort';
    END IF;

    -- 2. Stable IDs, present and unique on both sides.
    IF v_ranked_target_ids <> v_expected OR v_distinct_ranked_target_ids <> v_expected THEN
        RAISE EXCEPTION 'canonical V9 ranked targets contain missing or duplicate stable set IDs';
    END IF;
    IF v_history_ids <> v_expected OR v_distinct_history_ids <> v_expected THEN
        RAISE EXCEPTION 'RIP history rows contain missing or duplicate set IDs';
    END IF;

    -- 3. Contiguous 1..expected ranks, no duplicates. Cardinality alone does not
    --    make a ranking: {1,2,2,4} passes a count check and is still not one.
    IF v_distinct_ranks <> v_expected THEN
        RAISE EXCEPTION
            'canonical V9 ranks contain duplicates: % distinct ranks across % ranked targets',
            v_distinct_ranks, v_expected;
    END IF;
    IF v_min_rank IS DISTINCT FROM 1 OR v_max_rank IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'canonical V9 ranks are not contiguous 1..%: observed min=% max=%',
            v_expected, v_min_rank, v_max_rank;
    END IF;

    -- 4. Set parity, checked in BOTH directions. A one-directional EXCEPT would
    --    accept a history row set that is a strict superset of the ranked cohort.
    IF EXISTS (
        SELECT (entry->>'set_id')::UUID FROM jsonb_array_elements(v_canonical) AS entry
        EXCEPT
        SELECT (history->>'set_id')::UUID FROM jsonb_array_elements(p_rows) AS history
    ) THEN
        RAISE EXCEPTION 'canonical V9 ranked target IDs are missing from the history rows';
    END IF;
    SELECT count(*) INTO v_unsupported FROM (
        SELECT (history->>'set_id')::UUID AS set_id FROM jsonb_array_elements(p_rows) AS history
        EXCEPT
        SELECT (entry->>'set_id')::UUID FROM jsonb_array_elements(v_canonical) AS entry
    ) AS extra;
    IF v_unsupported > 0 THEN
        RAISE EXCEPTION
            'RIP history rows contain % set(s) that are not canonical V9 ranked targets',
            v_unsupported;
    END IF;

    -- 5. Publication metadata identifies THIS publication.
    IF v_payload #>> '{meta,snapshot,publicationId}' IS NULL
       OR v_payload #>> '{meta,snapshot,publicationId}' IS DISTINCT FROM v_requested_id::TEXT
       OR v_payload #>> '{meta,snapshot,marketDate}' IS NULL
       OR v_payload #>> '{meta,snapshot,marketDate}' IS DISTINCT FROM p_snapshot->>'market_date'
       OR v_payload #>> '{meta,snapshot,builtAt}' IS NULL THEN
        RAISE EXCEPTION 'malformed canonical RIP latest publication metadata';
    END IF;

    -- 6. The snapshot's own version fields must BE the canonical identity. The
    --    contract version has no column of its own and travels in diagnostics.
    IF p_snapshot->>'financial_rip_version' IS DISTINCT FROM c_financial_rip_version THEN
        RAISE EXCEPTION 'financial RIP version % is not the canonical %',
            p_snapshot->>'financial_rip_version', c_financial_rip_version;
    END IF;
    IF p_snapshot->>'overall_rip_version' IS DISTINCT FROM c_overall_rip_version THEN
        RAISE EXCEPTION 'overall RIP version % is not the canonical %',
            p_snapshot->>'overall_rip_version', c_overall_rip_version;
    END IF;
    IF p_snapshot->>'ca7_version' IS DISTINCT FROM c_collector_appeal_version THEN
        RAISE EXCEPTION 'collector appeal version % is not the canonical %',
            p_snapshot->>'ca7_version', c_collector_appeal_version;
    END IF;
    IF v_diag->>'public_rip_contract_version' IS DISTINCT FROM c_public_contract_version THEN
        RAISE EXCEPTION 'public RIP contract version % is not the canonical %',
            v_diag->>'public_rip_contract_version', c_public_contract_version;
    END IF;

    INSERT INTO pokemon_public_rip_leaderboard_snapshots (
        id, market_date, built_at, published_at, publication_status, eligible_cohort_count,
        cohort_version, cohort_fingerprint, overall_rip_version, financial_rip_version,
        ca7_version, payload_json, diagnostics_json
    ) VALUES (
        v_requested_id, (p_snapshot->>'market_date')::DATE, (p_snapshot->>'built_at')::TIMESTAMPTZ,
        timezone('utc', now()), 'complete', v_expected, p_snapshot->>'cohort_version',
        p_snapshot->>'cohort_fingerprint', p_snapshot->>'overall_rip_version',
        p_snapshot->>'financial_rip_version', p_snapshot->>'ca7_version',
        v_payload, v_diag
    )
    ON CONFLICT (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version)
    DO UPDATE SET payload_json = EXCLUDED.payload_json, built_at = EXCLUDED.built_at,
                  published_at = EXCLUDED.published_at, publication_status = 'complete',
                  diagnostics_json = EXCLUDED.diagnostics_json
    RETURNING id INTO v_snapshot_id;

    v_payload := jsonb_set(v_payload, '{meta,snapshot,publicationId}', to_jsonb(v_snapshot_id::TEXT));
    UPDATE pokemon_public_rip_leaderboard_snapshots SET payload_json = v_payload WHERE id = v_snapshot_id;
    DELETE FROM pokemon_public_rip_leaderboard_rows WHERE snapshot_id = v_snapshot_id;
    INSERT INTO pokemon_public_rip_leaderboard_rows (
        snapshot_id, set_id, set_canonical_key, overall_rip_score, overall_rip_rank,
        financial_rip_score, financial_rip_rank, overall_ranked_cohort_count,
        financial_ranked_cohort_count, simulation_calculation_run_id, source_market_date, pack_price
    )
    SELECT v_snapshot_id, x.set_id, x.set_canonical_key, x.overall_rip_score,
           x.overall_rip_rank, x.financial_rip_score, x.financial_rip_rank,
           x.overall_ranked_cohort_count, x.financial_ranked_cohort_count,
           x.simulation_calculation_run_id, x.source_market_date, x.pack_price
    FROM jsonb_to_recordset(p_rows) AS x(
        set_id UUID, set_canonical_key TEXT, overall_rip_score NUMERIC, overall_rip_rank INTEGER,
        financial_rip_score NUMERIC, financial_rip_rank INTEGER,
        overall_ranked_cohort_count INTEGER, financial_ranked_cohort_count INTEGER,
        simulation_calculation_run_id UUID, source_market_date DATE, pack_price NUMERIC
    );

    -- Promotion of `latest` happens LAST, and only because every statement above
    -- succeeded inside this transaction.
    INSERT INTO pokemon_explore_rankings_snapshot_latest(tcg, scope, ranking_payload_json, default_target_json)
    VALUES ('pokemon', 'rip-statistics', v_payload, COALESCE(p_latest->'default_target_json', '{}'::JSONB))
    ON CONFLICT (tcg, scope) DO UPDATE SET
        ranking_payload_json = EXCLUDED.ranking_payload_json,
        default_target_json = EXCLUDED.default_target_json;
    RETURN v_snapshot_id;
END;
$$;

REVOKE ALL ON FUNCTION public.publish_pokemon_public_rip_leaderboard(JSONB, JSONB, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_public_rip_leaderboard(JSONB, JSONB, JSONB) TO service_role;

COMMIT;




