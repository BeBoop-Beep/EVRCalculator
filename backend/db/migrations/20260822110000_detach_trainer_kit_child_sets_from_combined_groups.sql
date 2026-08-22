-- Migration 20260822110000 — Forward lifecycle state for the four EX Trainer Kit
-- child sets: canonical/catalog, with no independently attributable TCGplayer
-- card-price source.
--
-- WHY A NEW MIGRATION RATHER THAN AN EDIT TO 058
-- ==============================================
-- Migration 058 established the lifecycle-flag model and backfilled it from the
-- SET_CONFIG_MAP as it existed then. It is applied history and must stay
-- byte-unchanged: rewriting an applied migration makes the schema history lie
-- about what production actually ran. Lifecycle state evolves forward, one
-- migration at a time. This is that step for the Trainer Kits.
--
-- WHY THESE FOUR SETS LOSE THEIR SOURCE
-- ------------------------------------
-- TCGplayer publishes ONE group per kit ("EX Trainer Kit 2: Plusle & Minun" =
-- 1542, "EX Trainer Kit 1: Latias & Latios" = 1543) covering both decks, and its
-- rows cannot be deterministically partitioned between the two canonical
-- children: both decks share the 1/12-12/12 (resp. 1/10-10/10) numbering, and
-- only 6 of 24 (resp. 4 of 20) rows carry a "(Plusle)"/"(Minun)" marker —
-- TCGplayer adds those solely to disambiguate identical card NAMES, not to label
-- decks. Attaching a combined group to either child would publish combined-market
-- data as though it were one canonical half.
--
-- The sets therefore stay canonical/catalog — they remain in the registry, remain
-- usable for manual, onboarding and historical catalog work, and keep their
-- existing UNSUPPORTED_TRAINER_KIT treatment in the RIP model — but they leave
-- the publication-critical daily cohort.
--
-- COHORT DERIVATION IS UNCHANGED
-- ------------------------------
-- No cohort size is hardcoded anywhere. `pokemon_scrape_ready_cohort()` remains
-- the sole authority and continues to derive membership from the predicate
-- established in 058 (ready_for_daily_scrape AND has_card_details_url AND
-- card_details_url IS NOT NULL AND NOT catalog_only). Clearing the source and
-- setting catalog_only is what removes these four; the cohort count follows on
-- its own, and `create_daily_scrape_batch` recomputes expected_set_count from
-- that function rather than from any literal.

BEGIN;

UPDATE public.sets
SET card_details_url       = NULL,
    sealed_details_url     = NULL,
    has_card_details_url   = FALSE,
    catalog_only           = TRUE,
    ready_for_daily_scrape = FALSE,
    updated_at             = timezone('utc', now())
WHERE canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                        'exTrainerKitLatias', 'exTrainerKitLatios');

DO $verify$
DECLARE
    v_rows      INTEGER;
    v_bad_flags INTEGER;
BEGIN
    SELECT count(*) INTO v_rows
    FROM public.sets
    WHERE canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                            'exTrainerKitLatias', 'exTrainerKitLatios');

    IF v_rows <> 4 THEN
        RAISE EXCEPTION 'Expected all four Trainer Kit canonical sets to remain, found %', v_rows;
    END IF;

    SELECT count(*) INTO v_bad_flags
    FROM public.sets
    WHERE canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                            'exTrainerKitLatias', 'exTrainerKitLatios')
      AND NOT (
            card_details_url IS NULL
        AND sealed_details_url IS NULL
        AND has_card_details_url = FALSE
        AND catalog_only = TRUE
        AND ready_for_daily_scrape = FALSE
      );

    IF v_bad_flags <> 0 THEN
        RAISE EXCEPTION '% Trainer Kit set(s) did not reach the detached catalog-only state', v_bad_flags;
    END IF;

    RAISE NOTICE 'Trainer Kit lifecycle: 4 sets detached from combined groups, retained as catalog-only';
END;
$verify$;

COMMIT;
