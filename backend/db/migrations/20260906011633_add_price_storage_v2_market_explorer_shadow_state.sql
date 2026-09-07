BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(
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
    source text,
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
        metadata.card_variant_id,
        metadata.canonical_card_id,
        metadata.set_id,
        event_row.market_price,
        event_row.effective_date AS price_effective_date,
        event_row.source,
        metadata.card_name,
        metadata.card_number,
        metadata.rarity,
        metadata.edition,
        metadata.printing_type,
        metadata.special_type,
        metadata.image_url,
        metadata.identity_basis
    FROM public.pokemon_market_explorer_card_current_metadata metadata
    JOIN LATERAL (
        SELECT
            event_row.market_price,
            event_row.effective_date,
            event_row.source,
            event_row.id
        FROM public.card_variant_price_events_v2 event_row
        WHERE event_row.card_variant_id = metadata.card_variant_id
          AND event_row.condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
          AND event_row.source = 'TCGPlayer'
          AND event_row.currency = 'USD'
          AND event_row.market_price > 0
          AND event_row.effective_date <= p_market_date
        ORDER BY event_row.effective_date DESC, event_row.id DESC
        LIMIT 1
    ) event_row ON true
    WHERE p_set_ids IS NOT NULL
      AND cardinality(p_set_ids) > 0
      AND metadata.set_id = ANY(p_set_ids);
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(uuid[], date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(uuid[], date)
    TO service_role;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(uuid[], date) IS
'Backend-only Price Storage V2 point-in-time Market Explorer candidate. Reads compact price events plus current metadata; does not modify production interval or daily-state authorities.';

COMMIT;