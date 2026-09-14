BEGIN;

CREATE INDEX IF NOT EXISTS card_variant_price_events_v2_market_explorer_nm_idx
    ON public.card_variant_price_events_v2 (card_variant_id, effective_date DESC, id DESC)
    INCLUDE (market_price)
    WHERE condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
      AND source = 'TCGPlayer'
      AND currency = 'USD'
      AND market_price > 0;

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
    WITH scoped_metadata AS MATERIALIZED (
        SELECT metadata.*
        FROM public.pokemon_market_explorer_card_current_metadata metadata
        WHERE p_set_ids IS NOT NULL
          AND cardinality(p_set_ids) > 0
          AND metadata.set_id = ANY(p_set_ids)
    ), latest_event AS MATERIALIZED (
        SELECT DISTINCT ON (event_row.card_variant_id)
            event_row.card_variant_id,
            event_row.market_price,
            event_row.effective_date,
            event_row.source
        FROM public.card_variant_price_events_v2 event_row
        JOIN scoped_metadata metadata
          ON metadata.card_variant_id = event_row.card_variant_id
        WHERE event_row.condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
          AND event_row.source = 'TCGPlayer'
          AND event_row.currency = 'USD'
          AND event_row.market_price > 0
          AND event_row.effective_date <= p_market_date
        ORDER BY event_row.card_variant_id, event_row.effective_date DESC, event_row.id DESC
    )
    SELECT
        p_market_date AS market_date,
        metadata.card_variant_id,
        metadata.canonical_card_id,
        metadata.set_id,
        latest_event.market_price,
        latest_event.effective_date AS price_effective_date,
        latest_event.source,
        metadata.card_name,
        metadata.card_number,
        metadata.rarity,
        metadata.edition,
        metadata.printing_type,
        metadata.special_type,
        metadata.image_url,
        metadata.identity_basis
    FROM scoped_metadata metadata
    JOIN latest_event
      ON latest_event.card_variant_id = metadata.card_variant_id;
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(uuid[], date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_v2_state_shadow(uuid[], date)
    TO service_role;

COMMIT;