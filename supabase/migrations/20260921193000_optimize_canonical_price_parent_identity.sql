BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(
    target_set_id uuid
)
RETURNS TABLE(
    canonical_card_id uuid,
    set_id uuid,
    pokemon_tcg_api_card_id text,
    legacy_card_id uuid,
    card_variant_id uuid,
    condition_id uuid,
    printing_type text,
    market_price numeric,
    captured_at date,
    source text,
    price_selection_reason text
)
LANGUAGE plpgsql
STABLE
SET search_path TO ''
AS $function$
DECLARE
    v_parent_identity_fast_path boolean := false;
BEGIN
    /*
     * The canonical Market metadata projection already resolves one reviewed
     * physical legacy identity per canonical card and expands its live variants.
     * For ordinary API-parent identities that is the same identity decision made
     * by the V2 price resolver, but without rebuilding the expensive identity
     * CTE/regex fallback graph on every set refresh.
     *
     * Keep the optimization deliberately narrow: a set qualifies only when it
     * has projected metadata and every row is parent_pokemon_tcg_api_id. Vintage
     * explicit links / variant-only identities / name-number fallbacks continue
     * through the established V2 resolver unchanged.
     */
    SELECT
        EXISTS (
            SELECT 1
            FROM public.pokemon_market_explorer_card_current_metadata metadata
            WHERE metadata.set_id = target_set_id
        )
        AND NOT EXISTS (
            SELECT 1
            FROM public.pokemon_market_explorer_card_current_metadata metadata
            WHERE metadata.set_id = target_set_id
              AND metadata.identity_basis IS DISTINCT FROM 'parent_pokemon_tcg_api_id'
        )
    INTO v_parent_identity_fast_path;

    IF v_parent_identity_fast_path THEN
        RETURN QUERY
        WITH near_mint_condition AS (
            SELECT condition_row.id
            FROM public.conditions condition_row
            WHERE condition_row.name = 'Near Mint'
              AND condition_row.abbreviation = 'NM'
            ORDER BY condition_row.id
            LIMIT 1
        ), candidates AS MATERIALIZED (
            SELECT
                metadata.canonical_card_id,
                metadata.set_id,
                canonical.pokemon_tcg_api_card_id,
                metadata.legacy_card_id,
                metadata.card_variant_id,
                latest.condition_id,
                metadata.printing_type,
                latest.market_price,
                latest.captured_at,
                latest.source,
                CASE
                  WHEN metadata.rarity IN ('Common','Uncommon')
                       AND metadata.printing_type='non-holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_common_uncommon_non_holo_base_print'
                  WHEN metadata.rarity IN ('Common','Uncommon')
                       AND metadata.printing_type='holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_common_uncommon_holo_fallback'
                  WHEN metadata.rarity IN ('Common','Uncommon')
                       AND metadata.printing_type='reverse-holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
                  WHEN metadata.printing_type='holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_rare_or_hit_holo_base_print'
                  WHEN metadata.printing_type='non-holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_rare_or_hit_non_holo_fallback'
                  WHEN metadata.printing_type='reverse-holo'
                       AND metadata.special_type IS NULL
                    THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
                  ELSE 'latest_nm_special_or_other_fallback'
                END::text AS price_selection_reason,
                row_number() OVER (
                    PARTITION BY metadata.canonical_card_id
                    ORDER BY
                        latest.captured_at DESC NULLS LAST,
                        CASE WHEN metadata.special_type IS NULL THEN 0 ELSE 1 END,
                        CASE
                          WHEN metadata.rarity IN ('Common','Uncommon')
                               AND metadata.printing_type='non-holo' THEN 0
                          WHEN metadata.rarity IN ('Common','Uncommon')
                               AND metadata.printing_type='holo' THEN 1
                          WHEN metadata.rarity IN ('Common','Uncommon')
                               AND metadata.printing_type='reverse-holo'
                               AND metadata.special_type IS NULL THEN 2
                          WHEN metadata.printing_type='holo' THEN 0
                          WHEN metadata.printing_type='non-holo' THEN 1
                          WHEN metadata.printing_type='reverse-holo'
                               AND metadata.special_type IS NULL THEN 2
                          ELSE 9
                        END,
                        CASE
                          WHEN preference.preferred_card_variant_id = metadata.card_variant_id
                          THEN 0 ELSE 1
                        END,
                        latest.created_at DESC NULLS LAST,
                        metadata.card_variant_id
                ) AS selection_rank
            FROM public.pokemon_market_explorer_card_current_metadata metadata
            JOIN public.pokemon_canonical_cards canonical
              ON canonical.id = metadata.canonical_card_id
             AND canonical.set_id = metadata.set_id
            LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 preference
              ON preference.canonical_card_id = metadata.canonical_card_id
            CROSS JOIN near_mint_condition near_mint
            JOIN LATERAL (
                SELECT
                    current_row.condition_id,
                    current_row.market_price,
                    current_row.last_observed_date AS captured_at,
                    current_row.source,
                    current_row.last_observation_created_at AS created_at,
                    current_row.last_observation_id AS id
                FROM public.card_variant_price_current_v2 current_row
                WHERE current_row.card_variant_id = metadata.card_variant_id
                  AND current_row.condition_id = near_mint.id
                  AND current_row.market_price > 0
                  AND current_row.currency = 'USD'
                ORDER BY
                    current_row.last_observed_date DESC NULLS LAST,
                    current_row.last_observation_created_at DESC NULLS LAST,
                    current_row.last_observation_id DESC NULLS LAST
                LIMIT 1
            ) latest ON true
            WHERE metadata.set_id = target_set_id
              AND metadata.identity_basis = 'parent_pokemon_tcg_api_id'
              AND public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)
        )
        SELECT
            candidate.canonical_card_id,
            candidate.set_id,
            candidate.pokemon_tcg_api_card_id,
            candidate.legacy_card_id,
            candidate.card_variant_id,
            candidate.condition_id,
            candidate.printing_type,
            candidate.market_price,
            candidate.captured_at,
            candidate.source,
            candidate.price_selection_reason
        FROM candidates candidate
        WHERE candidate.selection_rank = 1;

        RETURN;
    END IF;

    RETURN QUERY
    SELECT resolved.*
    FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(
        target_set_id
    ) AS resolved
    JOIN public.pokemon_canonical_cards canonical
      ON canonical.id = resolved.canonical_card_id
    WHERE public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role);
END;
$function$;

COMMENT ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid) IS
'Canonical latest card-market price resolver. Parent Pokemon-TCG identity sets use the pre-resolved Market metadata projection; vintage/exception identities retain the established V2 resolver fallback. Final output remains restricted to reviewed physical Market instrument roles.';

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid)
    TO service_role;

COMMIT;
