-- Migration 20260822120000 — Repair the Base/Expedition source collision and
-- quarantine combined-product contamination for the four EX Trainer Kit sets.
--
-- BACKGROUND
-- ==========
-- Three of the 167 daily-cohort sets failed batch 26 (market_date 2026-08-20)
-- with `external_variant_identity_conflict`. Two distinct defects caused it.
--
-- Defect A — Expedition was configured with TCGplayer group 604, which is Base
-- Set (verified: group 604 -> "Base Set", xxx/102; group 1375 -> "Expedition",
-- EX, 2002-09-15, 165 cards). Expedition therefore ingested Base Set prices for
-- its entire history and claimed the 101 group-604 external identities that
-- belong to `base`, leaving `base` with zero identities and blocking its scrape
-- from 2026-08-18 onward.
--
-- Defect B — Both halves of each EX Trainer Kit resolved to the single combined
-- TCGplayer group (1542 "Plusle & Minun", 1543 "Latias & Latios"). The fuzzy
-- resolver's `is_trainer_kit_family` rule only LOOSENS the match threshold; it
-- never disambiguates, so both children matched the same group. The combined
-- rows cannot be deterministically partitioned: both decks share the 1/12-12/12
-- (resp. 1/10-10/10) numbering, and only 6 of 24 (resp. 4 of 20) rows carry a
-- "(Plusle)"/"(Minun)" marker, which TCGplayer adds solely to disambiguate
-- identical names rather than to label decks.
--
-- DESIGN
-- ======
-- Nothing is destroyed. Every row removed from a live table is first copied
-- verbatim (as jsonb) into a quarantine table together with its provenance, so
-- each operation is fully reversible and auditable.
--
-- Expedition's 63,393 observations are NOT re-homed into `base`. 62,776 of them
-- (99.0%) duplicate observations `base` already holds for the same
-- (variant, condition, source, captured_at); merging would be a no-op that trips
-- `unique_variant_price_day`. `base` keeps its own intact 62,888-row history and
-- reclaims its identities through a normal scrape. The 505-row gap
-- (2026-08-18..2026-08-22, 101/day) is preserved in quarantine and is optional
-- future backfill, explicitly NOT part of batch-26 recovery.
--
-- CONTAMINATION DISCRIMINATORS (different per defect, both evidence-backed)
-- ------------------------------------------------------------------------
-- Expedition: the printed denominator. All 101 rows are `%/102` (Base Set's
--   denominator) and the roster is Base Set's exactly — Alakazam 001, Blastoise
--   002, Chansey 003, Charizard 004 ... with Machamp 8/102 absent, which is why
--   the count is 101 and not 102. Their `ecard1-N` ids were synthesized by
--   position, not resolved from the Pokémon TCG API, so the api id is NOT
--   authoritative here. Expedition rebuilds its true 165-card roster from 1375.
--
-- Trainer Kits: the Pokémon TCG API id. Rows whose `pokemon_tcg_api_id` matches
--   the set's own `<pokemon_api_set_id>-N` are the authoritative child roster
--   (tk2a 9, tk2b 9, tk1a 8, tk1b 0). Every other row was generated from the
--   combined TCGplayer group and is not truthful child-set membership.
--
-- DELETION ORDER
-- --------------
-- `card_variant_price_observations.card_variant_id` is ON DELETE SET NULL, so
-- deleting variants first would silently ORPHAN observations rather than remove
-- them. Observations and identities are therefore deleted explicitly BEFORE
-- variants and cards. This keeps the "orphan rows: 0" invariant true.

BEGIN;

-- =============================================================================
-- 0. Quarantine storage
-- =============================================================================
-- One table, jsonb payloads. Schema-drift proof and trivially reversible: the
-- original row is recoverable with jsonb_populate_record.

CREATE TABLE IF NOT EXISTS public.canonical_repair_quarantine (
    id             BIGSERIAL PRIMARY KEY,
    repair_tag     TEXT        NOT NULL,
    source_table   TEXT        NOT NULL,
    canonical_key  TEXT        NULL,
    reason         TEXT        NOT NULL,
    row_id         UUID        NULL,
    payload        JSONB       NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_canonical_repair_quarantine_tag
    ON public.canonical_repair_quarantine (repair_tag, source_table);
CREATE INDEX IF NOT EXISTS idx_canonical_repair_quarantine_key
    ON public.canonical_repair_quarantine (canonical_key);

COMMENT ON TABLE public.canonical_repair_quarantine IS
    'Non-destructive holding area for rows removed by canonical-set repairs. '
    'Every row is preserved verbatim as jsonb with its provenance so the repair '
    'is auditable and reversible. Never truncate without an explicit decision.';

-- =============================================================================
-- 1. Preconditions — fail loudly if production has drifted from the audit
-- =============================================================================
-- The repair is written against exact observed state. If any count differs, the
-- migration aborts rather than acting on stale assumptions.

DO $precheck$
DECLARE
    v_exp_contaminated INTEGER;
    v_exp_identities   INTEGER;
    v_base_identities  INTEGER;
    v_base_obs         INTEGER;
    v_kit_identities   INTEGER;
    v_cohort           INTEGER;
    v_expedition_roster INTEGER;
BEGIN
    SELECT count(*) INTO v_exp_contaminated
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key = 'expeditionBaseSet' AND c.card_number LIKE '%/102';

    SELECT count(*) INTO v_exp_identities
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_external_identities i ON i.card_variant_id = v.id
    WHERE s.canonical_key = 'expeditionBaseSet';

    SELECT count(*) INTO v_base_identities
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_external_identities i ON i.card_variant_id = v.id
    WHERE s.canonical_key = 'base';

    SELECT count(*) INTO v_base_obs
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_price_observations o ON o.card_variant_id = v.id
    WHERE s.canonical_key = 'base';

    SELECT count(*) INTO v_kit_identities
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_external_identities i ON i.card_variant_id = v.id
    WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                              'exTrainerKitLatias', 'exTrainerKitLatios');

    SELECT count(*) INTO v_cohort FROM public.pokemon_scrape_ready_cohort();

    SELECT count(*) INTO v_expedition_roster
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key = 'expedition';

    IF v_expedition_roster <> 165 THEN
        RAISE EXCEPTION 'Precondition failed: expected the authoritative 165-card expedition roster, found %', v_expedition_roster;
    END IF;
    IF v_exp_contaminated <> 101 THEN
        RAISE EXCEPTION 'Precondition failed: expected 101 contaminated /102 Expedition cards, found %', v_exp_contaminated;
    END IF;
    IF v_exp_identities <> 101 THEN
        RAISE EXCEPTION 'Precondition failed: expected 101 Expedition-held identities, found %', v_exp_identities;
    END IF;
    IF v_base_identities <> 0 THEN
        RAISE EXCEPTION 'Precondition failed: expected 0 base identities, found %', v_base_identities;
    END IF;
    IF v_base_obs <> 62888 THEN
        RAISE EXCEPTION 'Precondition failed: expected 62888 base observations to preserve, found %', v_base_obs;
    END IF;
    IF v_kit_identities <> 44 THEN
        RAISE EXCEPTION 'Precondition failed: expected 44 Trainer Kit identities, found %', v_kit_identities;
    END IF;
    IF v_cohort <> 167 THEN
        RAISE EXCEPTION 'Precondition failed: expected a 167-set daily cohort, found %', v_cohort;
    END IF;
END;
$precheck$;

-- =============================================================================
-- 2. Resolve the contaminated row sets once
-- =============================================================================

-- Authoritative Trainer Kit child rosters, taken from the Pokémon TCG API
-- (set.id tk1a/tk1b/tk2a/tk2b; 10/10/12/12 cards, confirmed against the live API
-- on 2026-08-22). This is the authority for child-set membership — NOT the
-- combined TCGplayer group, which cannot be partitioned.
--
-- Every one of these 44 cards ALREADY EXISTS as a row in its own canonical set:
-- the combined scrape wrote the full union (24, resp. 20) into BOTH children. So
-- restoring truthful membership is a SELECTION, not an insertion — no row is
-- fabricated and no set is left empty.
CREATE TEMP TABLE _kit_roster (api_set TEXT, num TEXT, nm TEXT) ON COMMIT DROP;
INSERT INTO _kit_roster VALUES
 ('tk1a','1','Bagon'),('tk1a','2','Combusken'),('tk1a','3','Delcatty'),('tk1a','4','Latias'),('tk1a','5','Numel'),
 ('tk1a','6','Skitty'),('tk1a','7','Torchic'),('tk1a','8','Potion'),('tk1a','9','Energy Search'),('tk1a','10','Fire Energy'),
 ('tk1b','1','Electrike'),('tk1b','2','Latios'),('tk1b','3','Linoone'),('tk1b','4','Magnemite'),('tk1b','5','Magneton'),
 ('tk1b','6','Pikachu'),('tk1b','7','Zigzagoon'),('tk1b','8','Potion'),('tk1b','9','Energy Search'),('tk1b','10','Lightning Energy'),
 ('tk2a','1','Beldum'),('tk2a','2','Electrike'),('tk2a','3','Grumpig'),('tk2a','4','Meowth'),('tk2a','5','Metang'),('tk2a','6','Plusle'),
 ('tk2a','7','Spoink'),('tk2a','8','Energy Search'),('tk2a','9','Potion'),('tk2a','10','Professor Cozmo''s Discovery'),
 ('tk2a','11','Lightning Energy'),('tk2a','12','Psychic Energy'),
 ('tk2b','1','Arcanine'),('tk2b','2','Charmander'),('tk2b','3','Charmeleon'),('tk2b','4','Growlithe'),('tk2b','5','Mareep'),('tk2b','6','Minun'),
 ('tk2b','7','Vulpix'),('tk2b','8','Celio''s Network'),('tk2b','9','Energy Search'),('tk2b','10','Potion'),
 ('tk2b','11','Fire Energy'),('tk2b','12','Lightning Energy');

-- The deck each child represents. Needed because a bare name+number is ambiguous
-- exactly where it matters: "Potion (Latias)" and "Potion (Latios)" are both
-- Potion at 8/10. TCGplayer's parenthetical — which it adds only to disambiguate
-- identical NAMES — resolves it, and it agrees with the API numbering on all 44
-- rows, so the two independent sources corroborate each other.
CREATE TEMP TABLE _kit_deck (api_set TEXT, deck_name TEXT) ON COMMIT DROP;
INSERT INTO _kit_deck VALUES
 ('tk1a','Latias'),('tk1b','Latios'),('tk2a','Plusle'),('tk2b','Minun');

CREATE TEMP TABLE _repair_variants ON COMMIT DROP AS
-- Expedition: every /102 row is Base Set data wearing an Expedition label.
SELECT s.canonical_key,
       c.id  AS card_id,
       v.id  AS variant_id,
       'expedition_base_set_contamination_group_604'::text AS reason
FROM public.sets s
JOIN public.cards c ON c.set_id = s.id
JOIN public.card_variants v ON v.card_id = c.id
WHERE s.canonical_key = 'expeditionBaseSet'
  AND c.card_number LIKE '%/102'
UNION ALL
-- Trainer Kits: a row is truthful child-set membership only if it appears in that
-- child's authoritative Pokémon TCG API roster, matched on printed number plus
-- name (parenthetical stripped) and, where the parenthetical exists, agreeing
-- with the child's deck. Everything else is the sibling deck's card, written in
-- by the combined-group scrape.
SELECT s.canonical_key,
       c.id  AS card_id,
       v.id  AS variant_id,
       'trainer_kit_combined_group_contamination'::text AS reason
FROM public.sets s
JOIN public.cards c ON c.set_id = s.id
JOIN public.card_variants v ON v.card_id = c.id
JOIN _kit_deck d ON d.api_set = s.pokemon_api_set_id
WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                          'exTrainerKitLatias', 'exTrainerKitLatios')
  AND NOT EXISTS (
      SELECT 1 FROM _kit_roster r
      WHERE r.api_set = s.pokemon_api_set_id
        AND r.num = split_part(c.card_number, '/', 1)::int::text
        AND r.nm = btrim(regexp_replace(c.name, '\s*\([^)]*\)\s*$', ''))
        AND (
              (regexp_match(c.name, '\(([^)]*)\)\s*$'))[1] IS NULL
           OR (regexp_match(c.name, '\(([^)]*)\)\s*$'))[1] = d.deck_name
        )
  );

-- Observations are quarantined on a WIDER set than cards/variants.
--
-- The 26 Trainer Kit rows that survive the roster repair are authoritative
-- MEMBERSHIP, but every price ever recorded against them came from the combined
-- TCGplayer group and is therefore combined-market data attributed to one
-- canonical half. The rows stay; their prices do not. Expedition contributes all
-- of its observations because every one of them is Base Set data.
CREATE TEMP TABLE _repair_observation_variants ON COMMIT DROP AS
SELECT v.id AS variant_id, s.canonical_key,
       CASE WHEN s.canonical_key = 'expeditionBaseSet'
            THEN 'expedition_base_set_contamination_group_604'
            ELSE 'trainer_kit_combined_group_prices' END AS reason
FROM public.sets s
JOIN public.cards c ON c.set_id = s.id
JOIN public.card_variants v ON v.card_id = c.id
WHERE s.canonical_key IN ('expeditionBaseSet', 'exTrainerKit2Minun',
                          'exTrainerKit2Plusle', 'exTrainerKitLatias',
                          'exTrainerKitLatios');

-- Trainer Kit identities attached to rows that survive the roster repair must
-- ALSO be released: no child may keep a combined-group provider identity.
CREATE TEMP TABLE _repair_identities ON COMMIT DROP AS
SELECT i.id AS identity_id, s.canonical_key
FROM public.sets s
JOIN public.cards c ON c.set_id = s.id
JOIN public.card_variants v ON v.card_id = c.id
JOIN public.card_variant_external_identities i ON i.card_variant_id = v.id
WHERE s.canonical_key IN ('expeditionBaseSet', 'exTrainerKit2Minun',
                          'exTrainerKit2Plusle', 'exTrainerKitLatias',
                          'exTrainerKitLatios');

-- =============================================================================
-- 3. Snapshot everything into quarantine BEFORE any delete
-- =============================================================================

INSERT INTO public.canonical_repair_quarantine
    (repair_tag, source_table, canonical_key, reason, row_id, payload)
SELECT 'repair_20260822', 'card_variant_price_observations', ov.canonical_key,
       ov.reason, NULL, to_jsonb(o)
FROM public.card_variant_price_observations o
JOIN _repair_observation_variants ov ON ov.variant_id = o.card_variant_id;

INSERT INTO public.canonical_repair_quarantine
    (repair_tag, source_table, canonical_key, reason, row_id, payload)
SELECT 'repair_20260822', 'card_variant_external_identities', ri.canonical_key,
       'released_so_the_correct_canonical_set_can_reclaim_it', i.id, to_jsonb(i)
FROM public.card_variant_external_identities i
JOIN _repair_identities ri ON ri.identity_id = i.id;

INSERT INTO public.canonical_repair_quarantine
    (repair_tag, source_table, canonical_key, reason, row_id, payload)
SELECT 'repair_20260822', 'card_variants', rv.canonical_key, rv.reason, v.id, to_jsonb(v)
FROM public.card_variants v
JOIN _repair_variants rv ON rv.variant_id = v.id;

INSERT INTO public.canonical_repair_quarantine
    (repair_tag, source_table, canonical_key, reason, row_id, payload)
SELECT DISTINCT 'repair_20260822', 'cards', rv.canonical_key, rv.reason, c.id, to_jsonb(c)
FROM public.cards c
JOIN _repair_variants rv ON rv.card_id = c.id;

-- =============================================================================
-- 4. Remove the contamination — observations and identities FIRST
-- =============================================================================
-- Order matters: observations FK is ON DELETE SET NULL, so removing variants
-- ahead of observations would orphan them instead of deleting them.

DELETE FROM public.card_variant_price_observations o
USING _repair_observation_variants ov
WHERE o.card_variant_id = ov.variant_id;

DELETE FROM public.card_variant_external_identities i
USING _repair_identities ri
WHERE i.id = ri.identity_id;

DELETE FROM public.card_variants v
USING _repair_variants rv
WHERE v.id = rv.variant_id;

DELETE FROM public.cards c
USING (SELECT DISTINCT card_id FROM _repair_variants) d
WHERE c.id = d.card_id;

-- =============================================================================
-- 5. Correct the source mappings
-- =============================================================================

-- Expedition -> its verified own group 1375. `base` is left on 604, untouched.
UPDATE public.sets
SET card_details_url   = 'https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=1',
    sealed_details_url = 'https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=25',
    has_card_details_url = TRUE,
    updated_at = timezone('utc', now())
WHERE canonical_key = 'expeditionBaseSet';

-- -----------------------------------------------------------------------------
-- 5b. Consolidate the two duplicate Expedition canonical sets
-- -----------------------------------------------------------------------------
-- Production carries TWO canonical sets for one real-world set:
--
--   expeditionBaseSet — holds the cohort slot, the `ecard1` identity and 393
--     public daily-history rows, but its roster was Base Set contamination
--     (removed in step 4 above).
--   expedition — a cold-start catalog artifact, out of the cohort with no public
--     history, but already holding the AUTHORITATIVE 165-card roster on group
--     1375 (Alakazam 001/165 ... Charizard 006/165, matching TCGplayer exactly).
--
-- Consolidating onto `expeditionBaseSet` keeps the key downstream already uses
-- and its history continuity, while adopting the correct roster that already
-- exists rather than re-deriving it. Cards are REPARENTED, not recreated, so
-- their variants, identities and observations follow by foreign key and no
-- history is lost. `unique_set_card_number_name` cannot collide: the /102
-- contamination was deleted in step 4 and the incoming roster is /165.
UPDATE public.cards
SET set_id = (SELECT id FROM public.sets WHERE canonical_key = 'expeditionBaseSet')
WHERE set_id = (SELECT id FROM public.sets WHERE canonical_key = 'expedition');

-- `expedition` stays a canonical/catalog row but must no longer claim group
-- 1375: one provider group, one canonical owner.
UPDATE public.sets
SET card_details_url     = NULL,
    sealed_details_url   = NULL,
    has_card_details_url = FALSE,
    catalog_only         = TRUE,
    ready_for_daily_scrape = FALSE,
    updated_at = timezone('utc', now())
WHERE canonical_key = 'expedition';

-- The four Trainer Kit sets are detached from their combined groups by the
-- preceding forward lifecycle migration
-- (20260822110000_detach_trainer_kit_child_sets_from_combined_groups.sql), which
-- owns that state transition. This migration only removes the contamination they
-- accumulated while attached, and asserts the detached state below.

-- =============================================================================
-- 6. Postconditions — the invariants this repair promises
-- =============================================================================

DO $postcheck$
DECLARE
    v_exp_102        INTEGER;
    v_exp_variants   INTEGER;
    v_kit_urls       INTEGER;
    v_kit_identities INTEGER;
    v_cohort         INTEGER;
    v_total_sets     INTEGER;
    v_orphan_obs     INTEGER;
    v_orphan_ident   INTEGER;
    v_base_obs       INTEGER;
    v_quarantined    INTEGER;
    v_exp_roster     INTEGER;
    v_expedition_leftover INTEGER;
    v_dupe_groups    INTEGER;
    v_kit_roster     INTEGER;
    v_kit_obs        INTEGER;
    v_kit_empty      INTEGER;
BEGIN
    -- Each child must end with exactly its authoritative roster size.
    SELECT count(*) INTO v_kit_empty FROM (
        SELECT s.canonical_key, count(c.id) AS n
        FROM public.sets s
        LEFT JOIN public.cards c ON c.set_id = s.id
        WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                                  'exTrainerKitLatias', 'exTrainerKitLatios')
        GROUP BY s.canonical_key, s.pokemon_api_set_id
        HAVING count(c.id) <> CASE
            WHEN s.pokemon_api_set_id IN ('tk2a', 'tk2b') THEN 12 ELSE 10 END
    ) bad;

    SELECT count(*) INTO v_kit_roster
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                              'exTrainerKitLatias', 'exTrainerKitLatios');

    SELECT count(*) INTO v_kit_obs
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_price_observations o ON o.card_variant_id = v.id
    WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                              'exTrainerKitLatias', 'exTrainerKitLatios');

    SELECT count(*) INTO v_exp_roster
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key = 'expeditionBaseSet';

    SELECT count(*) INTO v_expedition_leftover
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key = 'expedition';

    -- One provider group may have at most one canonical owner.
    SELECT count(*) INTO v_dupe_groups FROM (
        SELECT substring(card_details_url from '/priceguide/set/([0-9]+)/') AS grp
        FROM public.sets
        WHERE card_details_url IS NOT NULL
        GROUP BY 1 HAVING count(*) > 1
    ) d;

    SELECT count(*) INTO v_exp_102
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    WHERE s.canonical_key = 'expeditionBaseSet' AND c.card_number LIKE '%/102';

    SELECT count(*) INTO v_exp_variants
    FROM public.sets s JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    WHERE s.canonical_key = 'expeditionBaseSet';

    SELECT count(*) INTO v_kit_urls
    FROM public.sets
    WHERE canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                            'exTrainerKitLatias', 'exTrainerKitLatios')
      AND (card_details_url IS NOT NULL OR sealed_details_url IS NOT NULL);

    SELECT count(*) INTO v_kit_identities
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_external_identities i ON i.card_variant_id = v.id
    WHERE s.canonical_key IN ('exTrainerKit2Minun', 'exTrainerKit2Plusle',
                              'exTrainerKitLatias', 'exTrainerKitLatios');

    SELECT count(*) INTO v_cohort     FROM public.pokemon_scrape_ready_cohort();
    SELECT count(*) INTO v_total_sets FROM public.sets;

    SELECT count(*) INTO v_orphan_obs
    FROM public.card_variant_price_observations WHERE card_variant_id IS NULL;

    SELECT count(*) INTO v_orphan_ident
    FROM public.card_variant_external_identities i
    WHERE NOT EXISTS (SELECT 1 FROM public.card_variants v WHERE v.id = i.card_variant_id);

    SELECT count(*) INTO v_base_obs
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    JOIN public.card_variants v ON v.card_id = c.id
    JOIN public.card_variant_price_observations o ON o.card_variant_id = v.id
    WHERE s.canonical_key = 'base';

    SELECT count(*) INTO v_quarantined
    FROM public.canonical_repair_quarantine WHERE repair_tag = 'repair_20260822';

    IF v_exp_102 <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % contaminated /102 Expedition cards remain', v_exp_102;
    END IF;
    IF v_exp_variants <> 324 THEN
        RAISE EXCEPTION 'Postcondition failed: Expedition should carry the authoritative 324 variants, found %', v_exp_variants;
    END IF;
    IF v_exp_roster <> 165 THEN
        RAISE EXCEPTION 'Postcondition failed: Expedition roster is % (expected the legitimate 165)', v_exp_roster;
    END IF;
    IF v_expedition_leftover <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % cards still parented to the retired `expedition` set', v_expedition_leftover;
    END IF;
    IF v_dupe_groups <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % TCGplayer group(s) still claimed by more than one canonical set', v_dupe_groups;
    END IF;
    IF v_kit_roster <> 44 THEN
        RAISE EXCEPTION 'Postcondition failed: Trainer Kit roster totals % (expected 44 = 12+12+10+10)', v_kit_roster;
    END IF;
    IF v_kit_empty <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % Trainer Kit set(s) left with the wrong card count; none may be empty', v_kit_empty;
    END IF;
    IF v_kit_obs <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % combined-group Trainer Kit observations remain', v_kit_obs;
    END IF;
    IF v_kit_urls <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % Trainer Kit TCGplayer URLs still active', v_kit_urls;
    END IF;
    IF v_kit_identities <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % Trainer Kit external identities still attached', v_kit_identities;
    END IF;
    IF v_cohort <> 163 THEN
        RAISE EXCEPTION 'Postcondition failed: expected a 163-set daily cohort, found %', v_cohort;
    END IF;
    IF v_total_sets <> 210 THEN
        RAISE EXCEPTION 'Postcondition failed: canonical set count changed to % (expected 210)', v_total_sets;
    END IF;
    IF v_orphan_obs <> 0 OR v_orphan_ident <> 0 THEN
        RAISE EXCEPTION 'Postcondition failed: % orphan observations, % orphan identities', v_orphan_obs, v_orphan_ident;
    END IF;
    IF v_base_obs <> 62888 THEN
        RAISE EXCEPTION 'Postcondition failed: base observations changed to % (expected 62888 preserved)', v_base_obs;
    END IF;

    RAISE NOTICE 'repair_20260822 complete: % rows quarantined, cohort 167 -> %, canonical sets %, base observations preserved %',
        v_quarantined, v_cohort, v_total_sets, v_base_obs;
END;
$postcheck$;

COMMIT;

-- =============================================================================
-- FOLLOW-UP (deliberately NOT part of this migration)
-- =============================================================================
-- This migration removes contamination and corrects source mappings. It does not
-- fabricate replacement rows. Rosters are rebuilt through the normal catalog
-- path, from authoritative sources, after this lands:
--
--   * expeditionBaseSet -> 165 cards, consolidated in step 5b from the `expedition`
--     catalog row that already held the authoritative roster
--
-- The four Trainer Kit rosters need NO follow-up: all 44 authoritative cards
-- (tk2a 12, tk2b 12, tk1a 10, tk1b 10) already existed as rows in their own
-- canonical sets, because the combined scrape wrote the full union into both
-- children. Step 4 keeps those 44 and removes the 44 sibling-deck rows, so every
-- child ends with exactly its true roster and none is left empty.
--
-- The 505 quarantined Base observations for 2026-08-18..2026-08-22 remain
-- available for optional backfill. They are NOT required for batch-26 recovery:
-- `base` reclaims its identities and earns its own 2026-08-20 observation
-- through a normal scrape.
