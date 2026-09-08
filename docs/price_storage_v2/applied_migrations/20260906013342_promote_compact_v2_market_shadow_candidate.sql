BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_compact_state_v2_shadow(
    p_set_ids uuid[],
    p_market_date date
)
RETURNS TABLE (
    market_date date,
    card_variant_id uuid,
    canonical_card_id uuid,
    set_id uuid,
    market_price numeric,
    price_effective_date date,
    card_name text,
    card_number text,
    rarity text,
    edition text,
    printing_type text,
    special_type text,
    image_url text,
    identity_basis text
)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $$
    SELECT
        p_market_date AS market_date,
        interval_row.card_variant_id,
        metadata.canonical_card_id,
        interval_row.set_id,
        interval_row.market_price,
        interval_row.valid_from AS price_effective_date,
        metadata.card_name,
        metadata.card_number,
        metadata.rarity,
        metadata.edition,
        metadata.printing_type,
        metadata.special_type,
        metadata.image_url,
        metadata.identity_basis
    FROM public.pokemon_market_price_intervals_v2_shadow interval_row
    JOIN public.pokemon_market_explorer_card_current_metadata metadata
      ON metadata.card_variant_id = interval_row.card_variant_id
    WHERE p_set_ids IS NOT NULL
      AND cardinality(p_set_ids) > 0
      AND interval_row.set_id = ANY(p_set_ids)
      AND interval_row.valid_from <= p_market_date
      AND (interval_row.valid_to IS NULL OR p_market_date < interval_row.valid_to);
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_compact_state_v2_shadow(uuid[],date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_compact_state_v2_shadow(uuid[],date)
    TO service_role;

DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_v2_state_shadow(uuid[],date);
DROP INDEX IF EXISTS public.card_variant_price_events_v2_market_explorer_nm_idx;
DROP TABLE IF EXISTS public.pokemon_market_price_intervals_v2_shadow_pilot;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_compact_state_v2_shadow(uuid[],date) IS
'Backend-only compact Price Storage V2 point-in-time Market Explorer candidate. Reads the 345MB compact interval shadow plus current metadata; not a production authority.';

COMMIT;