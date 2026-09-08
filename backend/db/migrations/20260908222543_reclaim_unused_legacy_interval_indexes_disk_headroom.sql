-- Emergency disk-headroom reclaim on the frozen legacy Market Explorer interval table.
-- Current production Market Explorer and canonical Set Value readers are V2-promoted;
-- guarded fallback uses raw card_variant_price_observations, not this table.
-- Preserve all legacy interval rows, the PK, the recently-used variant-validity index,
-- and the tiny open-static index. Drop only non-constraint performance indexes with
-- no recorded scans in current production statistics.
--
-- Recreate if legacy rollback performance is ever needed:
-- CREATE INDEX idx_pokemon_variant_market_intervals_validity_gist
--   ON public.pokemon_card_variant_market_price_intervals
--   USING gist (daterange(valid_from, valid_to, '[)'))
--   INCLUDE (observation_id, card_variant_id, canonical_card_id, set_id, market_price, rarity);
-- CREATE INDEX idx_pokemon_variant_market_intervals_canonical_validity
--   ON public.pokemon_card_variant_market_price_intervals(canonical_card_id, valid_from, valid_to)
--   INCLUDE(card_variant_id, market_price, set_id);
-- CREATE INDEX idx_pokemon_variant_market_intervals_set_validity
--   ON public.pokemon_card_variant_market_price_intervals(set_id, valid_from, valid_to)
--   INCLUDE(card_variant_id, canonical_card_id, market_price, rarity);

SET LOCAL lock_timeout='2s';
DROP INDEX IF EXISTS public.idx_pokemon_variant_market_intervals_validity_gist;
DROP INDEX IF EXISTS public.idx_pokemon_variant_market_intervals_canonical_validity;
DROP INDEX IF EXISTS public.idx_pokemon_variant_market_intervals_set_validity;