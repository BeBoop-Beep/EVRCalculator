-- Avoid the set-wide canonical-card x legacy-card expansion caused by the
-- fallback OR predicates in migration 040. Resolve identity in ordered,
-- indexable branches before considering price observations.

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id UUID)
RETURNS TABLE (
    canonical_card_id UUID,
    set_id UUID,
    pokemon_tcg_api_card_id TEXT,
    legacy_card_id UUID,
    card_variant_id UUID,
    condition_id UUID,
    printing_type TEXT,
    market_price NUMERIC,
    captured_at DATE,
    source TEXT,
    price_selection_reason TEXT
)
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
WITH near_mint_condition AS (
    SELECT id
    FROM public.conditions
    WHERE name = 'Near Mint'
      AND abbreviation = 'NM'
    ORDER BY id
    LIMIT 1
), parent_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 0 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    WHERE pcc.set_id = target_set_id
), variant_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.card_variants matched_variant
      ON matched_variant.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    JOIN public.cards c
      ON c.id = matched_variant.card_id
     AND c.set_id = pcc.set_id
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (
          SELECT 1
          FROM parent_api_identity parent_match
          WHERE parent_match.id = pcc.id
      )
), name_number_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 2 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND lower(regexp_replace(trim(c.name), '\s+', ' ', 'g')) =
         lower(regexp_replace(trim(pcc.name), '\s+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', '')
     )
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (
          SELECT 1
          FROM parent_api_identity parent_match
          WHERE parent_match.id = pcc.id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM variant_api_identity variant_match
          WHERE variant_match.id = pcc.id
      )
), resolved_cards AS (
    SELECT * FROM parent_api_identity
    UNION ALL
    SELECT * FROM variant_api_identity
    UNION ALL
    SELECT * FROM name_number_identity
), identity_candidates AS (
    SELECT
        resolved.id AS canonical_card_id,
        resolved.set_id,
        resolved.pokemon_tcg_api_card_id,
        resolved.rarity,
        resolved.legacy_card_id,
        cv.id AS card_variant_id,
        cv.printing_type,
        cv.special_type,
        resolved.identity_rank
    FROM resolved_cards resolved
    JOIN public.card_variants cv
      ON cv.card_id = resolved.legacy_card_id
), candidates AS (
    SELECT
        ic.canonical_card_id,
        ic.set_id,
        ic.pokemon_tcg_api_card_id,
        ic.legacy_card_id,
        ic.card_variant_id,
        latest.condition_id,
        ic.printing_type,
        latest.market_price,
        latest.captured_at,
        latest.source,
        CASE
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'non-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_non_holo_base_print'
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_holo_fallback'
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
            WHEN ic.printing_type = 'holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_holo_base_print'
            WHEN ic.printing_type = 'non-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_non_holo_fallback'
            WHEN ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
            ELSE 'latest_nm_special_or_other_fallback'
        END AS price_selection_reason,
        row_number() OVER (
            PARTITION BY ic.canonical_card_id
            ORDER BY
                ic.identity_rank,
                latest.captured_at DESC NULLS LAST,
                CASE WHEN ic.special_type IS NULL THEN 0 ELSE 1 END,
                CASE
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'non-holo' THEN 0
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'holo' THEN 1
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL THEN 2
                    WHEN ic.printing_type = 'holo' THEN 0
                    WHEN ic.printing_type = 'non-holo' THEN 1
                    WHEN ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL THEN 2
                    ELSE 9
                END,
                latest.created_at DESC NULLS LAST,
                ic.card_variant_id
        ) AS selection_rank
    FROM identity_candidates ic
    CROSS JOIN near_mint_condition nmc
    JOIN LATERAL (
        SELECT
            po.condition_id,
            po.market_price,
            po.captured_at,
            po.source,
            po.created_at,
            po.id
        FROM public.card_variant_price_observations po
        WHERE po.card_variant_id = ic.card_variant_id
          AND po.condition_id = nmc.id
          AND po.market_price > 0
          AND trim(both '"' from upper(coalesce(po.currency, ''))) = 'USD'
        ORDER BY po.captured_at DESC NULLS LAST, po.created_at DESC NULLS LAST, po.id DESC
        LIMIT 1
    ) latest ON true
)
SELECT
    candidates.canonical_card_id,
    candidates.set_id,
    candidates.pokemon_tcg_api_card_id,
    candidates.legacy_card_id,
    candidates.card_variant_id,
    candidates.condition_id,
    candidates.printing_type,
    candidates.market_price,
    candidates.captured_at,
    candidates.source,
    candidates.price_selection_reason
FROM candidates
WHERE candidates.selection_rank = 1;
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(UUID)
    TO service_role;
