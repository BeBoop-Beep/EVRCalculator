BEGIN;

CREATE TABLE public.pokemon_rip_stats_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), market_date DATE NOT NULL,
    built_at TIMESTAMPTZ NOT NULL, published_at TIMESTAMPTZ,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('published')),
    contract_version TEXT NOT NULL, methodology_version TEXT NOT NULL, weighting_version TEXT NOT NULL,
    eligible_cohort_count INTEGER NOT NULL CHECK (eligible_cohort_count > 0),
    exact_outcome_set_count INTEGER NOT NULL CHECK (exact_outcome_set_count > 0),
    total_source_outcome_count BIGINT NOT NULL CHECK (total_source_outcome_count > 0),
    cohort_fingerprint TEXT NOT NULL, source_run_fingerprint TEXT NOT NULL,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(diagnostics_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (market_date, contract_version, methodology_version, weighting_version),
    CHECK (exact_outcome_set_count = eligible_cohort_count)
);
CREATE TABLE public.pokemon_rip_stats_snapshot_sets (
    snapshot_id UUID NOT NULL REFERENCES public.pokemon_rip_stats_snapshots(id) ON DELETE CASCADE,
    set_id UUID NOT NULL REFERENCES public.sets(id),
    calculation_run_id UUID NOT NULL REFERENCES public.calculation_runs(id),
    set_canonical_key TEXT, pack_cost NUMERIC NOT NULL CHECK (pack_cost > 0),
    set_weight NUMERIC NOT NULL CHECK (set_weight > 0),
    artifact_outcome_count INTEGER NOT NULL CHECK (artifact_outcome_count > 0),
    artifact_sha256 TEXT NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    source_market_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (snapshot_id, set_id), UNIQUE (snapshot_id, calculation_run_id)
);
CREATE TABLE public.pokemon_rip_stats_snapshot_latest (
    tcg TEXT NOT NULL DEFAULT 'pokemon', scope TEXT NOT NULL DEFAULT 'rip-stats',
    market_date DATE NOT NULL, payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    source_run_fingerprint TEXT NOT NULL, payload_size_bytes INTEGER NOT NULL CHECK (payload_size_bytes > 0),
    created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tcg, scope), CHECK (tcg = 'pokemon' AND scope = 'rip-stats')
);

ALTER TABLE public.pokemon_rip_stats_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_rip_stats_snapshot_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_rip_stats_snapshot_latest ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_rip_stats_snapshots, public.pokemon_rip_stats_snapshot_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_rip_stats_snapshots, public.pokemon_rip_stats_snapshot_sets TO service_role;
REVOKE ALL ON public.pokemon_rip_stats_snapshot_latest FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_rip_stats_snapshot_latest TO anon, authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_rip_stats_snapshot_latest TO service_role;
CREATE POLICY pokemon_rip_stats_snapshot_latest_read_policy ON public.pokemon_rip_stats_snapshot_latest FOR SELECT TO anon, authenticated USING (true);

CREATE FUNCTION public.publish_pokemon_rip_stats_snapshot(p_snapshot JSONB, p_constituents JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
DECLARE v_id UUID; v_expected INTEGER; v_now TIMESTAMPTZ := timezone('utc', now());
BEGIN
    IF jsonb_typeof(p_constituents) <> 'array' THEN RAISE EXCEPTION 'constituents must be an array'; END IF;
    v_expected := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    IF jsonb_array_length(p_constituents) <> v_expected OR
       (p_snapshot->>'exact_outcome_set_count')::INTEGER <> v_expected OR
       (SELECT count(DISTINCT item->>'set_id') FROM jsonb_array_elements(p_constituents) item) <> v_expected
    THEN RAISE EXCEPTION 'incomplete or duplicate RIP Stats cohort'; END IF;
    INSERT INTO public.pokemon_rip_stats_snapshots
      (market_date,built_at,published_at,publication_status,contract_version,methodology_version,weighting_version,
       eligible_cohort_count,exact_outcome_set_count,total_source_outcome_count,cohort_fingerprint,source_run_fingerprint,payload_json,diagnostics_json)
    VALUES ((p_snapshot->>'market_date')::DATE,(p_snapshot->>'built_at')::TIMESTAMPTZ,v_now,'published',
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
    VALUES ('pokemon','rip-stats',(p_snapshot->>'market_date')::DATE,p_snapshot->'payload_json',p_snapshot->>'source_run_fingerprint',
      octet_length(convert_to((p_snapshot->'payload_json')::TEXT,'UTF8')),v_now,v_now)
    ON CONFLICT (tcg,scope) DO UPDATE SET market_date=EXCLUDED.market_date,payload_json=EXCLUDED.payload_json,
      source_run_fingerprint=EXCLUDED.source_run_fingerprint,payload_size_bytes=EXCLUDED.payload_size_bytes,updated_at=v_now
      WHERE public.pokemon_rip_stats_snapshot_latest.market_date <= EXCLUDED.market_date;
    RETURN v_id;
END $$;
REVOKE ALL ON FUNCTION public.publish_pokemon_rip_stats_snapshot(JSONB,JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_rip_stats_snapshot(JSONB,JSONB) TO service_role;

COMMIT;
