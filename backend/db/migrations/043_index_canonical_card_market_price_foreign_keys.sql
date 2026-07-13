-- Cover selected-price foreign keys used by refresh cleanup and identity joins.

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_card_market_prices_latest_variant_id
    ON public.pokemon_canonical_card_market_prices_latest(card_variant_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_card_market_prices_latest_condition_id
    ON public.pokemon_canonical_card_market_prices_latest(condition_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_card_market_prices_latest_legacy_card_id
    ON public.pokemon_canonical_card_market_prices_latest(legacy_card_id);
