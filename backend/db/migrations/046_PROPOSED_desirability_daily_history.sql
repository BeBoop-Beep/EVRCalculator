-- PROPOSED (NOT APPLIED). Point-in-time history for collector-appeal inputs.
--
-- WHY THIS EXISTS
-- ---------------
-- The collector-appeal / market-prediction study (docs/research/
-- collector_appeal_market_prediction_results.md) found that every longitudinal
-- research question is hard-blocked, not by method, but by the absence of any
-- appeal history:
--
--   * pokemon_desirability_composite_scores holds ONE row per subject and is
--     UPSERTED in place. At audit: 1,025 rows, all updated_at = 2026-06-11.
--   * pokemon_trend_scores likewise: 1,048 rows, all created_at = 2026-06-11.
--   * Google Trends was captured once, over a "today 1-m" window, and one of
--     the three snapshots recorded status = 'rate_limited_gracefully'.
--
-- With one observation per subject, Appeal Momentum and Appeal Persistence are
-- undefined, the appeal-vs-price lead-lag test has nothing to lag, and the
-- stable-appeal recovery hypothesis cannot be evaluated at all. No modelling
-- choice recovers this; only elapsed time with retained snapshots does.
--
-- These tables are APPEND-ONLY by design. The existing scores tables stay
-- exactly as they are and keep serving "current"; these accumulate the history
-- beside them. Nothing here changes any production read path.
--
-- POINT-IN-TIME SAFETY
-- --------------------
-- observed_on is the date the underlying SOURCE describes, and captured_at is
-- when we recorded it. They are kept separate so a backfill can never be
-- mistaken for a contemporaneous observation: any walk-forward model must
-- filter on captured_at <= t, never observed_on <= t. is_backfilled makes that
-- explicit rather than implied.

BEGIN;

-- ---------------------------------------------------------------------------
-- Subject-level desirability history
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.pokemon_desirability_score_daily_history (
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE CASCADE,
    observed_on DATE NOT NULL,
    scoring_version TEXT NOT NULL,
    desirability_score NUMERIC,
    desirability_rank INTEGER,
    desirability_tier TEXT,
    fan_popularity_score NUMERIC,
    current_trend_score NUMERIC,
    score_components_json JSONB,
    -- Provenance: never infer these from row order.
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_backfilled BOOLEAN NOT NULL DEFAULT FALSE,
    source_snapshot_id BIGINT,
    PRIMARY KEY (pokemon_reference_id, observed_on, scoring_version)
);

COMMENT ON TABLE public.pokemon_desirability_score_daily_history IS
'Append-only point-in-time history of subject desirability. observed_on = the date the source describes; captured_at = when inDex recorded it. Walk-forward models must filter on captured_at, not observed_on.';

COMMENT ON COLUMN public.pokemon_desirability_score_daily_history.is_backfilled IS
'TRUE when the row was reconstructed after the fact. Backfilled rows are NOT point-in-time safe for forecasting: they encode information that was not available on observed_on.';

CREATE INDEX IF NOT EXISTS idx_desirability_history_observed_on
    ON public.pokemon_desirability_score_daily_history(observed_on);
CREATE INDEX IF NOT EXISTS idx_desirability_history_subject_observed
    ON public.pokemon_desirability_score_daily_history(pokemon_reference_id, observed_on DESC);

-- ---------------------------------------------------------------------------
-- Google Trends search-interest history
-- ---------------------------------------------------------------------------
--
-- Google Trends returns a RELATIVE index that is renormalized per request, so
-- two captures are not comparable unless they share an anchor term. anchor_term
-- and timeframe are part of the key for exactly that reason: silently mixing
-- differently-anchored series would manufacture spurious momentum.

CREATE TABLE IF NOT EXISTS public.pokemon_trend_score_weekly_history (
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE CASCADE,
    observed_week DATE NOT NULL,
    source_name TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    geo TEXT NOT NULL DEFAULT '',
    anchor_term TEXT NOT NULL DEFAULT '',
    relative_search_interest_score NUMERIC,
    normalized_rank INTEGER,
    confidence TEXT,
    scoring_version TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_backfilled BOOLEAN NOT NULL DEFAULT FALSE,
    source_snapshot_id BIGINT,
    PRIMARY KEY (pokemon_reference_id, observed_week, source_name, timeframe, geo, anchor_term)
);

COMMENT ON TABLE public.pokemon_trend_score_weekly_history IS
'Append-only weekly Google Trends history. anchor_term and timeframe are part of the key because Trends renormalizes per request: series with different anchors are NOT comparable and must never be blended.';

CREATE INDEX IF NOT EXISTS idx_trend_history_observed_week
    ON public.pokemon_trend_score_weekly_history(observed_week);
CREATE INDEX IF NOT EXISTS idx_trend_history_subject_week
    ON public.pokemon_trend_score_weekly_history(pokemon_reference_id, observed_week DESC);

-- ---------------------------------------------------------------------------
-- Set-level appeal history
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.pokemon_set_appeal_daily_history (
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    observed_on DATE NOT NULL,
    scoring_version TEXT NOT NULL,
    universal_roster_appeal NUMERIC,
    accessible_appeal NUMERIC,
    elite_chase_magnetism NUMERIC,
    -- Research constructs, nullable until/unless they ship.
    chase_appeal NUMERIC,
    dual_path_depth NUMERIC,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_backfilled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (set_id, observed_on, scoring_version)
);

COMMENT ON TABLE public.pokemon_set_appeal_daily_history IS
'Append-only point-in-time history of set-level appeal constructs, so appeal momentum can eventually be measured at the set level as well as the subject level.';

CREATE INDEX IF NOT EXISTS idx_set_appeal_history_observed_on
    ON public.pokemon_set_appeal_daily_history(observed_on);

-- ---------------------------------------------------------------------------
-- RLS: match the read-only public posture of the existing snapshot tables.
-- ---------------------------------------------------------------------------

ALTER TABLE public.pokemon_desirability_score_daily_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_trend_score_weekly_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_set_appeal_daily_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_desirability_score_daily_history'
          AND policyname = 'public_read_desirability_history'
    ) THEN
        CREATE POLICY public_read_desirability_history
            ON public.pokemon_desirability_score_daily_history FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_trend_score_weekly_history'
          AND policyname = 'public_read_trend_history'
    ) THEN
        CREATE POLICY public_read_trend_history
            ON public.pokemon_trend_score_weekly_history FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_set_appeal_daily_history'
          AND policyname = 'public_read_set_appeal_history'
    ) THEN
        CREATE POLICY public_read_set_appeal_history
            ON public.pokemon_set_appeal_daily_history FOR SELECT USING (true);
    END IF;
END
$$;

COMMIT;
