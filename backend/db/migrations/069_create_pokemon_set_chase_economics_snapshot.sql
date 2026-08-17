-- Migration 069: target-card chase economics snapshot.
--
-- WHAT THIS ADDS
-- --------------
-- One row per set holding the published chase-economics contract: for the top
-- N highest-priced pullable cards, what chasing each one costs through each
-- modeled sealed product. Built by the snapshot builder, read by a dedicated
-- service function.
--
-- WHY A SEPARATE TABLE RATHER THAN A KEY IN THE SET PAGE PAYLOAD
-- --------------------------------------------------------------
-- The contract is roughly 60-90 KB per set: 25 cards x up to 6 products x ~22
-- numeric fields. `pokemon_set_page_snapshot_latest` is on the critical set
-- page path and is fetched on every set view; adding a block that nothing on
-- that path reads would make every set page slower to serve a payload no
-- current consumer wants.
--
-- It is also NOT appended to `pokemon_set_cards_snapshot_latest`, even though
-- that table is the established home for heavy per-card data. That row is
-- already multi-MB and IS read by the live cards page, so appending an
-- unrelated block there would grow a request users actually make. A separate
-- row is delivered only when something asks for it.
--
-- WHY STORED AT ALL RATHER THAN COMPUTED ON READ
-- ----------------------------------------------
-- A future frontend must be able to retrieve the canonical contract without
-- recomputing it. Computing on demand would require two whole-run population
-- reads (`simulation_input_cards` and the Near Mint price view) per request,
-- and would let two readers disagree about the same set.
--
-- RUN IDENTITY
-- ------------
-- `calculation_run_id` is stored because the payload's probabilities and EV
-- basis belong to exactly one run. A reader comparing this against the set
-- page's `ripDecision` must be able to see whether they describe the same run.
--
-- PRIVACY POSTURE
-- ---------------
-- Backend-only, matching migration 065's posture: RLS enabled, no read policy,
-- no grants to `anon` or `authenticated`, full DML to `service_role`. Nothing
-- consumes this publicly yet, and publishing an internal shape before deciding
-- it is the shape to publish makes every future column public by default.
-- When a frontend needs it, that is a deliberate grant or a projected view,
-- and it is not made here.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process.

BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_set_chase_economics_snapshot_latest (
    set_id UUID PRIMARY KEY
        REFERENCES public.sets(id) ON DELETE CASCADE,

    -- The run the payload's pull probabilities and EV price basis belong to.
    -- Nullable: a set with no scored run publishes an explicitly empty payload
    -- rather than no row, so a reader can tell "built and empty" from "never
    -- built".
    calculation_run_id UUID
        REFERENCES public.calculation_runs(id) ON DELETE SET NULL,

    payload_json JSONB NOT NULL,

    -- Projection of the payload for cheap diagnostics. Never a second source
    -- of truth: the payload is authoritative.
    card_count INTEGER NOT NULL DEFAULT 0 CHECK (card_count >= 0),

    as_of TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Freshness sweeps read by recency across all sets; the primary key does not
-- serve that access path.
CREATE INDEX IF NOT EXISTS pokemon_set_chase_economics_snapshot_latest_updated_at_idx
    ON public.pokemon_set_chase_economics_snapshot_latest (updated_at DESC);

ALTER TABLE public.pokemon_set_chase_economics_snapshot_latest
    ENABLE ROW LEVEL SECURITY;

-- Stated explicitly so re-running leaves the intended state even if something
-- created a policy out of band.
DROP POLICY IF EXISTS pokemon_set_chase_economics_snapshot_latest_read_policy
    ON public.pokemon_set_chase_economics_snapshot_latest;

REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM anon;
REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM authenticated;
REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.pokemon_set_chase_economics_snapshot_latest TO service_role;

COMMIT;
