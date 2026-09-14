CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(target_set_id uuid)
RETURNS TABLE(canonical_card_id uuid, set_id uuid, pokemon_tcg_api_card_id text, legacy_card_id uuid, card_variant_id uuid, condition_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
WITH near_mint_condition AS (
    SELECT id
    FROM public.conditions
    WHERE name = 'Near Mint'
      AND abbreviation = 'NM'
    ORDER BY id
    LIMIT 1
), manual_identity AS (
    SELECT pcc.*, link.legacy_card_id, -1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = pcc.id
    WHERE pcc.set_id = target_set_id
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
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
), name_number_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 2 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND lower(regexp_replace(trim(c.name), '\s+', ' ', 'g')) = lower(regexp_replace(trim(pcc.name), '\s+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', '')
     )
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
      AND NOT EXISTS (SELECT 1 FROM variant_api_identity variant_match WHERE variant_match.id = pcc.id)
), resolved_cards AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), identity_candidates AS (
    SELECT resolved.id AS canonical_card_id, resolved.set_id, resolved.pokemon_tcg_api_card_id,
           resolved.rarity, resolved.legacy_card_id, cv.id AS card_variant_id,
           cv.printing_type, cv.special_type, resolved.identity_rank
    FROM resolved_cards resolved
    JOIN public.card_variants cv ON cv.card_id = resolved.legacy_card_id
), candidates AS (
    SELECT ic.canonical_card_id, ic.set_id, ic.pokemon_tcg_api_card_id, ic.legacy_card_id,
           ic.card_variant_id, latest.condition_id, ic.printing_type, latest.market_price,
           latest.captured_at, latest.source,
           CASE
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_non_holo_base_print'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_holo_fallback'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
             WHEN ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_holo_base_print'
             WHEN ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_non_holo_fallback'
             WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
             ELSE 'latest_nm_special_or_other_fallback'
           END AS price_selection_reason,
           row_number() OVER (
             PARTITION BY ic.canonical_card_id
             ORDER BY ic.identity_rank,
                      latest.captured_at DESC NULLS LAST,
                      CASE WHEN ic.special_type IS NULL THEN 0 ELSE 1 END,
                      CASE
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' THEN 0
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' THEN 1
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        WHEN ic.printing_type='holo' THEN 0
                        WHEN ic.printing_type='non-holo' THEN 1
                        WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        ELSE 9
                      END,
                      latest.created_at DESC NULLS LAST,
                      ic.card_variant_id
           ) AS selection_rank
    FROM identity_candidates ic
    CROSS JOIN near_mint_condition nmc
    JOIN LATERAL (
      SELECT current_row.condition_id,
             current_row.market_price,
             current_row.last_observed_date AS captured_at,
             current_row.source,
             current_row.last_observation_created_at AS created_at,
             current_row.last_observation_id AS id
      FROM public.card_variant_price_current_v2 current_row
      WHERE current_row.card_variant_id = ic.card_variant_id
        AND current_row.condition_id = nmc.id
        AND current_row.market_price > 0
        AND current_row.currency = 'USD'
      ORDER BY current_row.last_observed_date DESC NULLS LAST,
               current_row.last_observation_created_at DESC NULLS LAST,
               current_row.last_observation_id DESC NULLS LAST
      LIMIT 1
    ) latest ON true
)
SELECT candidates.canonical_card_id, candidates.set_id, candidates.pokemon_tcg_api_card_id,
       candidates.legacy_card_id, candidates.card_variant_id, candidates.condition_id,
       candidates.printing_type, candidates.market_price, candidates.captured_at,
       candidates.source, candidates.price_selection_reason
FROM candidates
WHERE candidates.selection_rank = 1;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid) TO service_role;