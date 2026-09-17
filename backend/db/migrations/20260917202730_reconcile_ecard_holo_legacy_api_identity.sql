-- Reconcile the legacy `cards` identity for Aquapolis / Skyridge H-series rows
-- that already have an approved explicit canonical legacy-identity link.
--
-- Why this is needed:
-- `pokemon_canonical_card_market_prices_latest` correctly excludes canonical
-- `duplicate_alias` rows.  The historical Top Chase fallback still resolves a
-- legacy card to a canonical card by `cards.pokemon_tcg_api_id` before falling
-- back to name/number matching.  These eighteen TCGplayer H-series legacy rows
-- have an approved explicit link to the native Pokemon TCG API canonical card,
-- but their legacy API id is NULL.  Name/number fallback can therefore select
-- the `duplicate_alias` shell instead of the linked physical `main` card.
--
-- This migration does NOT create new identity evidence.  It copies the native
-- Pokemon TCG API id only where an explicit reviewed legacy-identity link already
-- exists, the canonical card is an approved physical `main` card, the legacy id
-- is currently NULL, and no other legacy row already owns that API id.

BEGIN;

DO $reconcile$
DECLARE
    v_candidate_count integer;
    v_conflict_count integer;
    v_updated_count integer;
BEGIN
    WITH candidates AS (
        SELECT
            legacy.id AS legacy_card_id,
            canonical.id AS canonical_card_id,
            canonical.pokemon_tcg_api_card_id AS canonical_api_id
        FROM public.pokemon_canonical_card_legacy_identity_links link
        JOIN public.pokemon_canonical_cards canonical
          ON canonical.id = link.canonical_card_id
        JOIN public.cards legacy
          ON legacy.id = link.legacy_card_id
        JOIN public.sets set_row
          ON set_row.id = canonical.set_id
        WHERE set_row.canonical_key IN ('aquapolis', 'skyridge')
          AND canonical.catalog_role = 'main'
          AND canonical.canonical_review_status = 'approved'
          AND canonical.pokemon_tcg_api_card_id ~ '^ecard[23]-H[0-9]+$'
          AND legacy.pokemon_tcg_api_id IS NULL
    )
    SELECT
        count(*)::integer,
        count(*) FILTER (
            WHERE EXISTS (
                SELECT 1
                FROM public.cards other
                WHERE other.id <> candidates.legacy_card_id
                  AND other.pokemon_tcg_api_id = candidates.canonical_api_id
            )
        )::integer
    INTO v_candidate_count, v_conflict_count
    FROM candidates;

    IF v_candidate_count <> 18 THEN
        RAISE EXCEPTION
            'Refusing e-card legacy API identity reconciliation: expected 18 reviewed candidates, found %',
            v_candidate_count;
    END IF;

    IF v_conflict_count <> 0 THEN
        RAISE EXCEPTION
            'Refusing e-card legacy API identity reconciliation: % candidate API ids are already owned by another legacy card',
            v_conflict_count;
    END IF;

    UPDATE public.cards legacy
       SET pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id
      FROM public.pokemon_canonical_card_legacy_identity_links link
      JOIN public.pokemon_canonical_cards canonical
        ON canonical.id = link.canonical_card_id
      JOIN public.sets set_row
        ON set_row.id = canonical.set_id
     WHERE legacy.id = link.legacy_card_id
       AND set_row.canonical_key IN ('aquapolis', 'skyridge')
       AND canonical.catalog_role = 'main'
       AND canonical.canonical_review_status = 'approved'
       AND canonical.pokemon_tcg_api_card_id ~ '^ecard[23]-H[0-9]+$'
       AND legacy.pokemon_tcg_api_id IS NULL;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;

    IF v_updated_count <> 18 THEN
        RAISE EXCEPTION
            'Refusing partial e-card legacy API identity reconciliation: expected 18 updates, wrote %',
            v_updated_count;
    END IF;
END;
$reconcile$;

COMMIT;
