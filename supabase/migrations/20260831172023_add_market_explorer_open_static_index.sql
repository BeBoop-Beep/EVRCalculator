-- One entry per published physical variant for static Market Explorer filters.
BEGIN;

CREATE INDEX IF NOT EXISTS idx_pokemon_variant_market_intervals_open_static
 ON public.pokemon_card_variant_market_price_intervals(set_id, card_variant_id)
 INCLUDE (canonical_card_id, rarity)
 WHERE valid_to IS NULL;

COMMIT;
