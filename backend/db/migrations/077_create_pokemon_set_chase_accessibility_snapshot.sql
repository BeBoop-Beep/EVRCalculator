-- Migration 077: set-level Chase Accessibility snapshot.
--
-- WHAT THIS ADDS
-- --------------
-- One row per set holding the published Chase Accessibility contract:
--
--     HC_i   = V_i^2 / sum_j V_j^2        (Chase Significance)
--     O_pack = sum_i HC_i * p_i           (Chase Accessibility)
--     N_HC   = 1 / sum_i HC_i^2           (Chase Depth, an EFFECTIVE count)
--
-- V_i is `simulation_card_variant_pull_rates.price_used` and p_i is
-- `modeled_probability` from the SAME row of the SAME calculation run.
--
-- WHY A SEPARATE TABLE RATHER THAN A COLUMN ON THE CHASE ECONOMICS SNAPSHOT
-- -------------------------------------------------------------------------
-- `pokemon_set_chase_economics_snapshot_latest` (migration 069) is entirely
-- PRODUCT-COUPLED: its payload prices chasing each card through each modeled
-- sealed product. Chase Accessibility reads no product cost, no product identity
-- and no pack count at all. Storing it there would tie a set-level access metric
-- to a row that must be rebuilt whenever a sealed-product price moves, and would
-- imply a product dependency the metric does not have.
--
-- It is also not appended to `pokemon_set_page_snapshot_latest`: this is a small
-- scalar row, and it needs its own status, version and coverage columns so the
-- publication gate can reject it independently of the set page payload.
--
-- WHY NOT PER-CARD CHASE SIGNIFICANCE
-- -----------------------------------
-- HC_i is deterministically regenerable from `price_used` on the same run's
-- rows, which are already persisted. Storing ~7,000 additional rows per run to
-- hold a quantity that is one division away from data we already keep would be
-- duplicate state with no current consumer. If a card page later needs HC, that
-- is a deliberate versioned per-card read model, and it is not made here.
--
-- WHY STORED AT ALL RATHER THAN COMPUTED ON READ
-- ----------------------------------------------
-- Computing on demand would require a whole-run read of
-- `simulation_card_variant_pull_rates` (300-465 rows per set) per request, and
-- would let two readers disagree about the same set if a run changed between
-- them. `calculation_run_id` is stored for exactly that reason: a reader
-- comparing this against the set page must be able to see whether the two
-- describe the same run.
--
-- COVERAGE GATE
-- -------------
-- `mapped_hc_mass` is the share of Chase Significance carrying BOTH a finite
-- positive value and a valid modeled probability, measured against the FULL
-- drawable priced universe. It is never renormalised around missing rows: doing
-- so would make a set look MORE accessible precisely because an important card
-- went missing. Below 0.99 the row stores a NULL accessibility and an explicit
-- status, never a zero.
--
-- NULL VERSUS ZERO
-- ----------------
-- `accessibility` NULL means unavailable. Zero means a measured zero. The
-- CHECK constraint below enforces that a `ready` row has a value and a
-- non-`ready` row does not, so the two can never be confused by a reader.
--
-- PRIVACY POSTURE
-- ---------------
-- Backend-only, matching migrations 065 and 069: RLS enabled, no read policy, no
-- grants to `anon` or `authenticated`, full DML to `service_role`. When a
-- frontend needs it, that is a deliberate grant or a projected view, and it is
-- not made here.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process. Nothing in
-- this migration has been applied.

BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_set_chase_accessibility_snapshot_latest (
    set_id UUID PRIMARY KEY
        REFERENCES public.sets(id) ON DELETE CASCADE,

    -- The run whose price_used and modeled_probability the value belongs to.
    -- Nullable so a set with no scored run stores an explicit unavailable row
    -- rather than no row: a reader can then tell "built and unavailable" from
    -- "never built".
    calculation_run_id UUID
        REFERENCES public.calculation_runs(id) ON DELETE SET NULL,

    -- The market date of the authoritative run, carried so a reader can align
    -- this with the set page without a second lookup.
    market_date DATE,

    -- Canonical mathematical value: a DECIMAL FRACTION, not a percentage.
    -- Observed production range is roughly 0.00074 - 0.00562. Presentation
    -- multiplies by 100; storage never does.
    accessibility DOUBLE PRECISION,

    -- 1 / sum(HC^2): the EFFECTIVE number of cards carrying the set's value
    -- concentration. Continuous on purpose - it is never rounded into a card
    -- count and there is no Core/Extended tier behind it.
    chase_depth DOUBLE PRECISION,

    -- Share of Chase Significance carrying both a value and a probability,
    -- measured against the full drawable priced universe.
    mapped_hc_mass DOUBLE PRECISION,

    -- 'ready' | 'unavailable_pull_model'
    -- | 'chase_accessibility_insufficient_probability_coverage'
    -- | 'unavailable_no_drawable_universe' | 'unavailable_no_priced_universe'
    status TEXT NOT NULL,
    status_reason TEXT,

    -- Model lineage. Stored so a value can never be read without the model that
    -- produced it.
    version TEXT NOT NULL,
    significance_version TEXT,
    depth_version TEXT,

    -- Diagnostics, deliberately few: enough to explain a rejection without
    -- publishing the whole internal shape.
    eligible_variant_count INTEGER,
    priced_variant_count INTEGER,
    probability_mapped_variant_count INTEGER,
    parity_delta DOUBLE PRECISION,

    built_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- A ready row must carry a value; an unavailable row must not. This is the
    -- schema-level guarantee that NULL and 0.0 never get confused.
    CONSTRAINT pokemon_set_chase_accessibility_value_matches_status CHECK (
        (status = 'ready' AND accessibility IS NOT NULL AND chase_depth IS NOT NULL)
        OR (status <> 'ready' AND accessibility IS NULL AND chase_depth IS NULL)
    ),

    -- A probability-weighted mean of probabilities cannot leave [0, 1].
    CONSTRAINT pokemon_set_chase_accessibility_in_unit_interval CHECK (
        accessibility IS NULL OR (accessibility >= 0.0 AND accessibility <= 1.0)
    ),

    CONSTRAINT pokemon_set_chase_accessibility_mass_in_unit_interval CHECK (
        mapped_hc_mass IS NULL OR (mapped_hc_mass >= 0.0 AND mapped_hc_mass <= 1.0)
    ),

    -- The published coverage gate, enforced by the database and not only by the
    -- builder, so a row that failed coverage can never be written as ready.
    CONSTRAINT pokemon_set_chase_accessibility_coverage_gate CHECK (
        status <> 'ready' OR (mapped_hc_mass IS NOT NULL AND mapped_hc_mass >= 0.99)
    )
);

COMMENT ON TABLE public.pokemon_set_chase_accessibility_snapshot_latest IS
    'Set-level Chase Accessibility V1: the Chase-Significance-weighted mean of '
    'modeled per-pack card probabilities. NOT a probability of pulling a chase '
    'card - there is no discrete chase roster. Contains no sealed-product input.';

COMMENT ON COLUMN public.pokemon_set_chase_accessibility_snapshot_latest.accessibility IS
    'Decimal fraction, not a percentage. Multiply by 100 for display only.';

COMMENT ON COLUMN public.pokemon_set_chase_accessibility_snapshot_latest.chase_depth IS
    'N_HC = 1/sum(HC^2). An effective count, never a literal number of cards.';

COMMENT ON COLUMN public.pokemon_set_chase_accessibility_snapshot_latest.mapped_hc_mass IS
    'Share of Chase Significance with both a value and a modeled probability, '
    'measured over the full drawable priced universe. Never renormalised.';

CREATE INDEX IF NOT EXISTS pokemon_set_chase_accessibility_run_idx
    ON public.pokemon_set_chase_accessibility_snapshot_latest (calculation_run_id);

CREATE INDEX IF NOT EXISTS pokemon_set_chase_accessibility_status_idx
    ON public.pokemon_set_chase_accessibility_snapshot_latest (status);

ALTER TABLE public.pokemon_set_chase_accessibility_snapshot_latest
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.pokemon_set_chase_accessibility_snapshot_latest FROM PUBLIC;
REVOKE ALL ON public.pokemon_set_chase_accessibility_snapshot_latest FROM anon;
REVOKE ALL ON public.pokemon_set_chase_accessibility_snapshot_latest FROM authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.pokemon_set_chase_accessibility_snapshot_latest TO service_role;

COMMIT;
