-- Migration 059 — Correct `supports_opening_simulation` to mean what it says:
-- "the opening-simulation runner would actually execute this set".
--
-- Context
-- -------
-- Migration 058 introduced `supports_opening_simulation` with the default
-- `NOT catalog_only`. That is not a capability test — it is merely the absence
-- of a catalog flag, so every ordinary non-catalog HISTORICAL set (base set,
-- neo, e-card, ex, gym, ...) was marked simulation-supported even though
-- `run_all_v2_sets.py` would never execute it. Production reflects exactly that:
-- 172 rows true (= 209 configs - 37 catalog-only), against a real V2 set list of
-- 22.
--
-- Corrected resolution (see backend/db/services/pokemon_set_lifecycle_flags.py,
-- `supports_opening_simulation`):
--   1. an explicit SUPPORTS_OPENING_SIMULATION declaration wins;
--   2. otherwise derive from the SAME runtime criterion run_all_v2_sets.py uses
--      to build its batch (USE_MONTE_CARLO_V2);
--   3. otherwise false;
--   4. catalog_only always implies false.
--
-- The allow-list below is GENERATED — never hand-maintained — by
--   python backend/scripts/generate_set_lifecycle_flag_backfill.py \
--       --sql-simulation-capability
-- and backend/tests/unit/db/test_set_lifecycle_flag_backfill.py fails if the
-- committed list drifts from the configs. It was verified to match
-- `filter_v2_enabled_sets(discover_sets())` exactly (22 = 22, zero difference).
--
-- An ALLOW-list is used rather than a deny-list deliberately: it is 22 entries
-- instead of 187, and it fails CLOSED — a config added later resolves to false
-- until this list is regenerated, rather than silently defaulting to supported.
--
-- Scope guard: this migration touches ONLY `supports_opening_simulation`.
-- `catalog_only` and `ready_for_daily_scrape` semantics from migration 058 are
-- left exactly as they are — the corrected daily cohort (card URL AND NOT
-- catalog_only) is working and is not reopened here.
--
-- Idempotent: re-running recomputes the same values and re-asserts the same
-- invariants. It creates no functions, adds no grants, and adds no RLS policy,
-- so the migration-051 privilege rules remain in force untouched.
--
-- Apply manually in the Supabase SQL editor.

BEGIN;

COMMENT ON COLUMN public.sets.supports_opening_simulation IS
    'Set has a simulatable sealed product configuration AND the opening-simulation '
    'runner (run_all_v2_sets.py, criterion USE_MONTE_CARLO_V2) would actually '
    'execute it. Authoritative "unsupported" reason for opening-simulation '
    'eligibility and for Opening Profit vs Cost audit applicability.';

DO $simulation_capability$
DECLARE
    -- Generated from the real SET_CONFIG_MAP registry (22 keys).
    v_simulation_supported_keys TEXT[] := ARRAY[
        'ascendedHeroes',
        'blackBolt',
        'chaosRising',
        'destinedRivals',
        'journeyTogether',
        'megaEvolution',
        'obsidianFlames',
        'paldeaEvolved',
        'paldeanFates',
        'paradoxRift',
        'perfectOrder',
        'phantasmalFlames',
        'pitchBlack',
        'prismaticEvolutions',
        'scarletAndViolet151',
        'scarletAndVioletBase',
        'shroudedFable',
        'stellarCrown',
        'surgingSparks',
        'temporalForces',
        'twilightMasquerade',
        'whiteFlare'
    ]::text[];

    v_expected_supported INTEGER := 22;
    v_supported_rows INTEGER := 0;
    v_unsupported_rows INTEGER := 0;
    v_null_key_rows INTEGER := 0;
    v_leaked INTEGER := 0;
BEGIN
    -- Recompute for every set row. A row whose canonical_key is NULL cannot be
    -- matched to a config and therefore cannot be shown to be supported: it
    -- resolves to FALSE (fail-closed), never left at a stale TRUE.
    UPDATE public.sets
    SET supports_opening_simulation = (
            canonical_key IS NOT NULL
            AND canonical_key = ANY(v_simulation_supported_keys)
            AND NOT COALESCE(catalog_only, FALSE)
        );

    SELECT COUNT(*) INTO v_supported_rows
    FROM public.sets WHERE supports_opening_simulation;

    SELECT COUNT(*) INTO v_unsupported_rows
    FROM public.sets WHERE NOT supports_opening_simulation;

    SELECT COUNT(*) INTO v_null_key_rows
    FROM public.sets WHERE canonical_key IS NULL;

    -- Invariant: a catalog-only set can never be simulation-supported.
    SELECT COUNT(*) INTO v_leaked
    FROM public.sets
    WHERE COALESCE(catalog_only, FALSE) AND supports_opening_simulation;

    IF v_leaked > 0 THEN
        RAISE EXCEPTION
            'Migration 059 invariant violated: % catalog-only set(s) marked supports_opening_simulation',
            v_leaked;
    END IF;

    -- The allow-list has 22 keys, so at most 22 rows can be supported. More than
    -- that means the UPDATE did not apply as written.
    IF v_supported_rows > v_expected_supported THEN
        RAISE EXCEPTION
            'Migration 059 invariant violated: % supported row(s) exceeds the % generated keys',
            v_supported_rows, v_expected_supported;
    END IF;

    -- Fewer is legitimate (a config may have no row in this database yet), so it
    -- is reported rather than raised.
    RAISE NOTICE
        'Migration 059: supports_opening_simulation=% (allow-list keys=%, unsupported=%, null canonical_key=%)',
        v_supported_rows, v_expected_supported, v_unsupported_rows, v_null_key_rows;
END;
$simulation_capability$;

COMMIT;
