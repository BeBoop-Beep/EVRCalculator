-- Harden public.publish_pokemon_rip_stats_snapshot with the scrape-batch
-- publication authority.
--
-- Incident: on 2026-08-18 a direct service-level call published RIP Stats for
-- an UNPROMOTED market date (batch 24, status=incomplete, promoted_at NULL)
-- while the promoted public cohort was still 2026-08-17. The CLI gate was
-- correct but was never on that code path, and the RPC trusted its caller.
--
-- This makes the invariant unbypassable from any client, including a raw
-- PostgREST POST: the snapshot's own market_date must own a scrape batch that
-- is complete, promoted, and whole BEFORE any row is written.
--
-- Replaces the function body only. No table, grant, policy, or RLS change.
-- The function remains SECURITY INVOKER with search_path pinned to public, and
-- EXECUTE remains restricted to service_role (re-asserted below, idempotently).

BEGIN;

CREATE OR REPLACE FUNCTION public.publish_pokemon_rip_stats_snapshot(p_snapshot JSONB, p_constituents JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE
    v_id UUID;
    v_expected INTEGER;
    v_now TIMESTAMPTZ := timezone('utc', now());
    v_market_date DATE;
    v_batch RECORD;
BEGIN
    -- ---- Publication authority. Evaluated FIRST, before any mutation. ------
    v_market_date := (p_snapshot->>'market_date')::DATE;
    IF v_market_date IS NULL THEN
        RAISE EXCEPTION 'RIP Stats publication denied: snapshot has no market_date';
    END IF;

    SELECT b.id, b.status, b.promoted_at, b.missing_set_count, b.expected_set_count
      INTO v_batch
      FROM public.pokemon_scrape_batches b
     WHERE b.market_date = v_market_date
     ORDER BY b.id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'RIP Stats publication denied for %: no scrape batch cohort exists', v_market_date;
    END IF;
    IF v_batch.status IS DISTINCT FROM 'complete' THEN
        RAISE EXCEPTION 'RIP Stats publication denied for %: batch % status=% is not complete',
            v_market_date, v_batch.id, COALESCE(v_batch.status, 'unknown');
    END IF;
    IF v_batch.promoted_at IS NULL THEN
        RAISE EXCEPTION 'RIP Stats publication denied for %: batch % is not promoted (promoted_at is null)',
            v_market_date, v_batch.id;
    END IF;
    IF v_batch.missing_set_count IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'RIP Stats publication denied for %: batch % missing_set_count=% (expected 0)',
            v_market_date, v_batch.id, COALESCE(v_batch.missing_set_count, -1);
    END IF;
    IF v_batch.expected_set_count IS NULL OR v_batch.expected_set_count <= 0 THEN
        RAISE EXCEPTION 'RIP Stats publication denied for %: batch % expected_set_count=% (expected > 0)',
            v_market_date, v_batch.id, COALESCE(v_batch.expected_set_count, -1);
    END IF;

    -- ---- Existing cohort integrity contract, unchanged. -------------------
    IF jsonb_typeof(p_constituents) <> 'array' THEN RAISE EXCEPTION 'constituents must be an array'; END IF;
    v_expected := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    IF jsonb_array_length(p_constituents) <> v_expected OR
       (p_snapshot->>'exact_outcome_set_count')::INTEGER <> v_expected OR
       (SELECT count(DISTINCT item->>'set_id') FROM jsonb_array_elements(p_constituents) item) <> v_expected
    THEN RAISE EXCEPTION 'incomplete or duplicate RIP Stats cohort'; END IF;
    INSERT INTO public.pokemon_rip_stats_snapshots
      (market_date,built_at,published_at,publication_status,contract_version,methodology_version,weighting_version,
       eligible_cohort_count,exact_outcome_set_count,total_source_outcome_count,cohort_fingerprint,source_run_fingerprint,payload_json,diagnostics_json)
    VALUES (v_market_date,(p_snapshot->>'built_at')::TIMESTAMPTZ,v_now,'published',
       p_snapshot->>'contract_version',p_snapshot->>'methodology_version',p_snapshot->>'weighting_version',v_expected,v_expected,
       (p_snapshot->>'total_source_outcome_count')::BIGINT,p_snapshot->>'cohort_fingerprint',p_snapshot->>'source_run_fingerprint',
       p_snapshot->'payload_json',COALESCE(p_snapshot->'diagnostics_json','{}'::jsonb))
    ON CONFLICT (market_date,contract_version,methodology_version,weighting_version) DO UPDATE SET
       built_at=EXCLUDED.built_at,published_at=v_now,publication_status='published',eligible_cohort_count=EXCLUDED.eligible_cohort_count,
       exact_outcome_set_count=EXCLUDED.exact_outcome_set_count,total_source_outcome_count=EXCLUDED.total_source_outcome_count,
       cohort_fingerprint=EXCLUDED.cohort_fingerprint,source_run_fingerprint=EXCLUDED.source_run_fingerprint,
       payload_json=EXCLUDED.payload_json,diagnostics_json=EXCLUDED.diagnostics_json RETURNING id INTO v_id;
    DELETE FROM public.pokemon_rip_stats_snapshot_sets WHERE snapshot_id=v_id;
    INSERT INTO public.pokemon_rip_stats_snapshot_sets
      (snapshot_id,set_id,calculation_run_id,set_canonical_key,pack_cost,set_weight,artifact_outcome_count,artifact_sha256,source_market_date)
    SELECT v_id,(item->>'set_id')::UUID,(item->>'calculation_run_id')::UUID,item->>'set_canonical_key',
      (item->>'pack_cost')::NUMERIC,(item->>'set_weight')::NUMERIC,(item->>'artifact_outcome_count')::INTEGER,
      item->>'artifact_sha256',(item->>'source_market_date')::DATE FROM jsonb_array_elements(p_constituents) item;
    IF (SELECT count(*) FROM public.pokemon_rip_stats_snapshot_sets WHERE snapshot_id=v_id) <> v_expected
      THEN RAISE EXCEPTION 'persisted RIP Stats cohort did not reconcile'; END IF;
    INSERT INTO public.pokemon_rip_stats_snapshot_latest
      (tcg,scope,market_date,payload_json,source_run_fingerprint,payload_size_bytes,created_at,updated_at)
    VALUES ('pokemon','rip-stats',v_market_date,p_snapshot->'payload_json',p_snapshot->>'source_run_fingerprint',
      octet_length(convert_to((p_snapshot->'payload_json')::TEXT,'UTF8')),v_now,v_now)
    ON CONFLICT (tcg,scope) DO UPDATE SET market_date=EXCLUDED.market_date,payload_json=EXCLUDED.payload_json,
      source_run_fingerprint=EXCLUDED.source_run_fingerprint,payload_size_bytes=EXCLUDED.payload_size_bytes,updated_at=v_now
      WHERE public.pokemon_rip_stats_snapshot_latest.market_date <= EXCLUDED.market_date;
    RETURN v_id;
END $$;

REVOKE ALL ON FUNCTION public.publish_pokemon_rip_stats_snapshot(JSONB,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_rip_stats_snapshot(JSONB,JSONB) TO service_role;

COMMIT;
