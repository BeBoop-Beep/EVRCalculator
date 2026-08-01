BEGIN;

CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard(
    p_snapshot JSONB, p_rows JSONB, p_latest JSONB
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_snapshot_id UUID;
    v_requested_id UUID := (p_snapshot->>'id')::UUID;
    v_expected INTEGER := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    v_rows INTEGER;
    v_total_targets INTEGER;
    v_ranked_targets INTEGER;
    v_ranked_target_ids INTEGER;
    v_distinct_ranked_target_ids INTEGER;
    v_history_ids INTEGER;
    v_distinct_history_ids INTEGER;
    v_payload JSONB := p_latest->'ranking_payload_json';
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'RIP history rows must be an array';
    END IF;
    IF jsonb_typeof(v_payload->'targets') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'latest RIP targets must be an array';
    END IF;

    v_rows := jsonb_array_length(p_rows);
    v_total_targets := jsonb_array_length(v_payload->'targets');
    SELECT count(*),
           count(CASE WHEN COALESCE(target->>'set_id', target->>'target_id') IS NOT NULL THEN 1 END),
           count(DISTINCT COALESCE(target->>'set_id', target->>'target_id'))
      INTO v_ranked_targets, v_ranked_target_ids, v_distinct_ranked_target_ids
      FROM jsonb_array_elements(v_payload->'targets') AS target
     WHERE target #> '{rip,rank}' IS NOT NULL
       AND target #> '{rip,rank}' <> 'null'::JSONB;
    SELECT count(CASE WHEN history->>'set_id' IS NOT NULL THEN 1 END),
           count(DISTINCT history->>'set_id')
      INTO v_history_ids, v_distinct_history_ids
      FROM jsonb_array_elements(p_rows) AS history;

    IF v_expected <= 0 THEN
        RAISE EXCEPTION 'invalid RIP cohort size: expected %', v_expected;
    END IF;
    IF v_rows <> v_expected THEN
        RAISE EXCEPTION 'incomplete RIP cohort: expected %, received %', v_expected, v_rows;
    END IF;
    IF v_ranked_targets <> v_expected THEN
        RAISE EXCEPTION
            'latest ranked RIP target count does not match cohort: expected %, received %',
            v_expected, v_ranked_targets;
    END IF;
    IF v_total_targets < v_expected THEN
        RAISE EXCEPTION 'latest RIP target array is smaller than ranked cohort';
    END IF;
    IF v_ranked_target_ids <> v_expected OR v_distinct_ranked_target_ids <> v_expected THEN
        RAISE EXCEPTION 'ranked RIP targets contain missing or duplicate stable set IDs';
    END IF;
    IF v_history_ids <> v_expected OR v_distinct_history_ids <> v_expected THEN
        RAISE EXCEPTION 'RIP history rows contain missing or duplicate set IDs';
    END IF;
    IF EXISTS (
        SELECT COALESCE(target->>'set_id', target->>'target_id')::UUID
          FROM jsonb_array_elements(v_payload->'targets') AS target
         WHERE target #> '{rip,rank}' IS NOT NULL
           AND target #> '{rip,rank}' <> 'null'::JSONB
        EXCEPT
        SELECT (history->>'set_id')::UUID FROM jsonb_array_elements(p_rows) AS history
    ) OR EXISTS (
        SELECT (history->>'set_id')::UUID FROM jsonb_array_elements(p_rows) AS history
        EXCEPT
        SELECT COALESCE(target->>'set_id', target->>'target_id')::UUID
          FROM jsonb_array_elements(v_payload->'targets') AS target
         WHERE target #> '{rip,rank}' IS NOT NULL
           AND target #> '{rip,rank}' <> 'null'::JSONB
    ) THEN
        RAISE EXCEPTION 'ranked RIP target IDs do not match history row set IDs';
    END IF;
    IF v_payload #>> '{meta,snapshot,publicationId}' IS NULL
       OR v_payload #>> '{meta,snapshot,publicationId}' IS DISTINCT FROM v_requested_id::TEXT
       OR v_payload #>> '{meta,snapshot,marketDate}' IS NULL
       OR v_payload #>> '{meta,snapshot,marketDate}' IS DISTINCT FROM p_snapshot->>'market_date'
       OR v_payload #>> '{meta,snapshot,builtAt}' IS NULL THEN
        RAISE EXCEPTION 'malformed canonical RIP latest publication metadata';
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
        v_payload, COALESCE(p_snapshot->'diagnostics', '{}'::JSONB)
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
