-- Canonical current-price rows are a market-instrument projection. Identity-only
-- aliases (duplicate_alias, abstract_identity, or any future unapproved role)
-- must not be materialized beside the physical canonical card they alias.
--
-- The V2 shadow resolver intentionally owns the price/variant-selection logic.
-- This wrapper adds only the already-established physical-instrument authority
-- used by Market Explorer so every current-price consumer sees one reviewed
-- canonical identity per physical market instrument.
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
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
    SELECT resolved.*
    FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(target_set_id) AS resolved
    JOIN public.pokemon_canonical_cards AS canonical
      ON canonical.id = resolved.canonical_card_id
    WHERE public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role);
$function$;

COMMENT ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid) IS
'Canonical latest card-market price resolver. Price selection remains owned by the V2 shadow resolver; final publication is restricted to reviewed physical Market instrument catalog roles so duplicate/abstract identities cannot materialize as parallel priced cards.';

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(uuid)
    TO service_role;

COMMIT;
