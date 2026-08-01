BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_public_rip_leaderboard_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_date DATE NOT NULL,
    built_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('complete', 'failed')),
    eligible_cohort_count INTEGER NOT NULL CHECK (eligible_cohort_count > 0),
    cohort_version TEXT NOT NULL,
    cohort_fingerprint TEXT NOT NULL,
    overall_rip_version TEXT NOT NULL,
    financial_rip_version TEXT NOT NULL,
    ca7_version TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version)
);

CREATE TABLE IF NOT EXISTS public.pokemon_public_rip_leaderboard_rows (
    snapshot_id UUID NOT NULL REFERENCES public.pokemon_public_rip_leaderboard_snapshots(id) ON DELETE CASCADE,
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE RESTRICT,
    set_canonical_key TEXT,
    overall_rip_score NUMERIC NOT NULL,
    overall_rip_rank INTEGER NOT NULL CHECK (overall_rip_rank > 0),
    financial_rip_score NUMERIC NOT NULL,
    financial_rip_rank INTEGER NOT NULL CHECK (financial_rip_rank > 0),
    overall_ranked_cohort_count INTEGER NOT NULL CHECK (overall_ranked_cohort_count > 0),
    financial_ranked_cohort_count INTEGER NOT NULL CHECK (financial_ranked_cohort_count > 0),
    simulation_calculation_run_id UUID,
    source_market_date DATE,
    pack_price NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (snapshot_id, set_id),
    UNIQUE (snapshot_id, overall_rip_rank),
    UNIQUE (snapshot_id, financial_rip_rank)
);

CREATE INDEX IF NOT EXISTS idx_public_rip_snapshots_market_date
    ON public.pokemon_public_rip_leaderboard_snapshots (market_date DESC, publication_status);
CREATE INDEX IF NOT EXISTS idx_public_rip_rows_set_snapshot
    ON public.pokemon_public_rip_leaderboard_rows (set_id, snapshot_id);

ALTER TABLE public.pokemon_public_rip_leaderboard_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_public_rip_leaderboard_rows ENABLE ROW LEVEL SECURITY;
CREATE POLICY pokemon_public_rip_leaderboard_snapshots_read_policy
    ON public.pokemon_public_rip_leaderboard_snapshots FOR SELECT USING (true);
CREATE POLICY pokemon_public_rip_leaderboard_rows_read_policy
    ON public.pokemon_public_rip_leaderboard_rows FOR SELECT USING (true);
GRANT SELECT ON public.pokemon_public_rip_leaderboard_snapshots, public.pokemon_public_rip_leaderboard_rows
    TO anon, authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON public.pokemon_public_rip_leaderboard_snapshots, public.pokemon_public_rip_leaderboard_rows
    TO service_role;

CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard(
    p_snapshot JSONB,
    p_rows JSONB,
    p_latest JSONB
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_snapshot_id UUID;
    v_expected INTEGER := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    v_rows INTEGER := jsonb_array_length(p_rows);
BEGIN
    IF v_rows <> v_expected OR v_rows <= 0 THEN
        RAISE EXCEPTION 'incomplete RIP cohort: expected %, received %', v_expected, v_rows;
    END IF;

    INSERT INTO pokemon_public_rip_leaderboard_snapshots (
        id, market_date, built_at, published_at, publication_status, eligible_cohort_count,
        cohort_version, cohort_fingerprint, overall_rip_version, financial_rip_version,
        ca7_version, payload_json, diagnostics_json
    ) VALUES (
        (p_snapshot->>'id')::UUID, (p_snapshot->>'market_date')::DATE, (p_snapshot->>'built_at')::TIMESTAMPTZ,
        timezone('utc', now()), 'complete', v_expected, p_snapshot->>'cohort_version',
        p_snapshot->>'cohort_fingerprint', p_snapshot->>'overall_rip_version',
        p_snapshot->>'financial_rip_version', p_snapshot->>'ca7_version',
        p_latest->'ranking_payload_json', COALESCE(p_snapshot->'diagnostics', '{}'::jsonb)
    )
    ON CONFLICT (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version)
    DO UPDATE SET payload_json = EXCLUDED.payload_json, built_at = EXCLUDED.built_at,
                  published_at = EXCLUDED.published_at, diagnostics_json = EXCLUDED.diagnostics_json
    RETURNING id INTO v_snapshot_id;

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
    VALUES ('pokemon', 'rip-statistics', p_latest->'ranking_payload_json',
            COALESCE(p_latest->'default_target_json', '{}'::jsonb))
    ON CONFLICT (tcg, scope) DO UPDATE SET
        ranking_payload_json = EXCLUDED.ranking_payload_json,
        default_target_json = EXCLUDED.default_target_json;
    RETURN v_snapshot_id;
END;
$$;
REVOKE ALL ON FUNCTION public.publish_pokemon_public_rip_leaderboard(JSONB, JSONB, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_public_rip_leaderboard(JSONB, JSONB, JSONB) TO service_role;

COMMIT;
