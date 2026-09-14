-- Migration 20260906120000 — Remove the two orphan "Boss's Orders" display-name
-- alias base cards created by the external-identity base-card resolution bug.
--
-- BACKGROUND
-- ==========
-- Brilliant Stars and Shining Fates failed every daily scrape since
-- 2026-09-02 with `external_variant_identity_conflict`. Root cause: TCGPlayer
-- changed the display title of an already-ingested card while keeping the
-- same underlying TCGPlayer product/variant IDs ("Boss's Orders" ->
-- "Boss's Orders [Cyrus]" in Brilliant Stars, "Boss's Orders [Lysandre]" in
-- Shining Fates). The pre-fix ingestion code grouped incoming rows into base
-- cards by (display name, card_number) BEFORE consulting the provider
-- identity, so it inserted a brand-new base card for the new display name.
-- Variant persistence then discovered the TCGPlayer product already belonged
-- to the original canonical card and raised a deterministic identity
-- conflict, failing the whole batch for both sets from 2026-09-02 onward.
--
-- The ingestion-side fix (CardsService.resolve_external_identity_card_owners_
-- before_insert) now consults the provider identity BEFORE any base-card
-- insertion decision, so a display-name change alone can never create a
-- duplicate base card again. This migration only cleans up the two orphan
-- alias rows that the bug already created on 2026-09-02, so a normal re-scrape
-- can proceed against the real canonical cards.
--
-- SAFETY
-- ======
-- Each alias is targeted with semantic predicates (set canonical_key + card
-- name + card_number), never a hardcoded UUID, so the migration is portable
-- across environments. It fails closed (RAISE EXCEPTION, whole transaction
-- rolled back) if:
--   * the expected canonical survivor card is not present, or
--   * the alias has acquired ANY dependent state (card_variants, external
--     identities, price observations, legacy identity links, canonical
--     market-price rows, market-price interval rows, simulation_input_cards,
--     simulation_card_variant_pull_rates, or card-market-top-hit references)
--     that would make deleting it unsafe.
-- If an alias row is already absent, that alias is treated as already
-- resolved (no-op), so the migration is idempotent and safe to re-run.
--
-- This migration does not fabricate any historical price data. The 2026-09-02
-- through 2026-09-05 gap for these two sets is a genuine absence and stays
-- absent; it is expected to backfill naturally once a normal re-scrape lands.

BEGIN;

DO $cleanup$
DECLARE
    v_target RECORD;
    v_alias_card_id UUID;
    v_survivor_card_id UUID;
    v_variant_count INTEGER;
    v_identity_count INTEGER;
    v_observation_count INTEGER;
    v_legacy_link_count INTEGER;
    v_canonical_price_count INTEGER;
    v_price_interval_count INTEGER;
    v_simulation_input_count INTEGER;
    v_pull_rate_count INTEGER;
    v_top_hit_count INTEGER;
    v_deleted INTEGER := 0;
BEGIN
    FOR v_target IN
        SELECT * FROM (VALUES
            ('brilliantStars', 'Boss''s Orders [Cyrus]',    '132/172', 'Boss''s Orders', 'swsh9-132'),
            ('shiningFates',   'Boss''s Orders [Lysandre]', '058/072', 'Boss''s Orders', 'swsh45-58')
        ) AS t(set_canonical_key, alias_name, card_number, canonical_name, canonical_api_id)
    LOOP
        SELECT c.id INTO v_alias_card_id
        FROM public.sets s
        JOIN public.cards c ON c.set_id = s.id
        WHERE s.canonical_key = v_target.set_canonical_key
          AND c.name = v_target.alias_name
          AND c.card_number = v_target.card_number;

        IF v_alias_card_id IS NULL THEN
            RAISE NOTICE 'boss_orders_alias_cleanup: % / % already absent — no-op',
                v_target.set_canonical_key, v_target.alias_name;
            CONTINUE;
        END IF;

        SELECT c.id INTO v_survivor_card_id
        FROM public.sets s
        JOIN public.cards c ON c.set_id = s.id
        WHERE s.canonical_key = v_target.set_canonical_key
          AND c.name = v_target.canonical_name
          AND c.card_number = v_target.card_number
          AND c.pokemon_tcg_api_id = v_target.canonical_api_id;

        IF v_survivor_card_id IS NULL THEN
            RAISE EXCEPTION
                'boss_orders_alias_cleanup: expected canonical survivor % / % (api_id=%) not found; '
                'refusing to delete alias % (id=%) without a confirmed survivor',
                v_target.set_canonical_key, v_target.canonical_name, v_target.canonical_api_id,
                v_target.alias_name, v_alias_card_id;
        END IF;

        IF v_survivor_card_id = v_alias_card_id THEN
            RAISE EXCEPTION
                'boss_orders_alias_cleanup: alias and survivor resolved to the same card id (%) for % — '
                'refusing to act on unexpected state', v_alias_card_id, v_target.set_canonical_key;
        END IF;

        SELECT count(*) INTO v_variant_count
        FROM public.card_variants v WHERE v.card_id = v_alias_card_id;

        SELECT count(*) INTO v_identity_count
        FROM public.card_variant_external_identities i
        JOIN public.card_variants v ON v.id = i.card_variant_id
        WHERE v.card_id = v_alias_card_id;

        SELECT count(*) INTO v_observation_count
        FROM public.card_variant_price_observations o
        JOIN public.card_variants v ON v.id = o.card_variant_id
        WHERE v.card_id = v_alias_card_id;

        SELECT count(*) INTO v_legacy_link_count
        FROM public.pokemon_canonical_card_legacy_identity_links l
        WHERE l.legacy_card_id = v_alias_card_id;

        SELECT count(*) INTO v_canonical_price_count
        FROM public.pokemon_canonical_card_market_prices_latest p
        WHERE p.legacy_card_id = v_alias_card_id;

        SELECT count(*) INTO v_price_interval_count
        FROM public.pokemon_card_variant_market_price_intervals pi
        JOIN public.card_variants v ON v.id = pi.card_variant_id
        WHERE v.card_id = v_alias_card_id;

        SELECT count(*) INTO v_simulation_input_count
        FROM public.simulation_input_cards sic
        WHERE sic.card_id = v_alias_card_id;

        SELECT count(*) INTO v_pull_rate_count
        FROM public.simulation_card_variant_pull_rates spr
        WHERE spr.card_id = v_alias_card_id;

        SELECT count(*) INTO v_top_hit_count
        FROM public.card_market_top_hits_by_edition_latest t
        JOIN public.card_variants v ON v.id = t.card_variant_id
        WHERE v.card_id = v_alias_card_id;

        IF v_variant_count <> 0 OR v_identity_count <> 0 OR v_observation_count <> 0
           OR v_legacy_link_count <> 0 OR v_canonical_price_count <> 0
           OR v_price_interval_count <> 0 OR v_simulation_input_count <> 0
           OR v_pull_rate_count <> 0 OR v_top_hit_count <> 0 THEN
            RAISE EXCEPTION
                'boss_orders_alias_cleanup: alias % (id=%, set=%) has acquired dependent state — '
                'refusing to delete. variants=%, identities=%, observations=%, legacy_links=%, '
                'canonical_prices=%, price_intervals=%, simulation_input_cards=%, pull_rates=%, top_hits=%',
                v_target.alias_name, v_alias_card_id, v_target.set_canonical_key,
                v_variant_count, v_identity_count, v_observation_count, v_legacy_link_count,
                v_canonical_price_count, v_price_interval_count, v_simulation_input_count,
                v_pull_rate_count, v_top_hit_count;
        END IF;

        DELETE FROM public.cards WHERE id = v_alias_card_id;
        v_deleted := v_deleted + 1;

        RAISE NOTICE 'boss_orders_alias_cleanup: deleted alias % (id=%) for %, survivor % (id=%) untouched',
            v_target.alias_name, v_alias_card_id, v_target.set_canonical_key,
            v_target.canonical_name, v_survivor_card_id;
    END LOOP;

    RAISE NOTICE 'boss_orders_alias_cleanup: complete, % alias row(s) deleted this run', v_deleted;
END;
$cleanup$;

DO $postcheck$
DECLARE
    v_remaining_aliases INTEGER;
    v_survivors INTEGER;
BEGIN
    SELECT count(*) INTO v_remaining_aliases
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    WHERE (s.canonical_key = 'brilliantStars' AND c.name = 'Boss''s Orders [Cyrus]' AND c.card_number = '132/172')
       OR (s.canonical_key = 'shiningFates' AND c.name = 'Boss''s Orders [Lysandre]' AND c.card_number = '058/072');

    IF v_remaining_aliases <> 0 THEN
        RAISE EXCEPTION 'boss_orders_alias_cleanup postcheck failed: % alias row(s) still present', v_remaining_aliases;
    END IF;

    SELECT count(*) INTO v_survivors
    FROM public.sets s
    JOIN public.cards c ON c.set_id = s.id
    WHERE (s.canonical_key = 'brilliantStars' AND c.name = 'Boss''s Orders' AND c.card_number = '132/172'
           AND c.pokemon_tcg_api_id = 'swsh9-132')
       OR (s.canonical_key = 'shiningFates' AND c.name = 'Boss''s Orders' AND c.card_number = '058/072'
           AND c.pokemon_tcg_api_id = 'swsh45-58');

    IF v_survivors <> 2 THEN
        RAISE EXCEPTION 'boss_orders_alias_cleanup postcheck failed: expected 2 canonical survivors intact, found %', v_survivors;
    END IF;
END;
$postcheck$;

COMMIT;