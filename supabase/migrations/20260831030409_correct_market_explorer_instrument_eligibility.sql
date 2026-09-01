-- Market Explorer instruments are distinct physical traded card identities.
-- Identity-only aliases and abstract shells must be rejected before variant
-- expansion, independently of Set Value and booster-opening eligibility.
BEGIN;

CREATE OR REPLACE FUNCTION public.is_pokemon_market_instrument_catalog_role(
    p_catalog_role text
)
RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE SECURITY INVOKER SET search_path = ''
AS $function$
SELECT coalesce(p_catalog_role = ANY(ARRAY[
    'main', 'subset', 'pack_variant', 'pack_energy', 'promo',
    'promo_variant', 'product_exclusive', 'product_insert'
]::text[]), false);
$function$;

COMMENT ON FUNCTION public.is_pokemon_market_instrument_catalog_role(text) IS
'Fail-safe Market Explorer physical-instrument role allowlist. Future physical catalog roles must be explicitly reviewed and added; Set Value and opening eligibility are separate contracts.';

REVOKE ALL ON FUNCTION public.is_pokemon_market_instrument_catalog_role(text)
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.is_pokemon_market_instrument_catalog_role(text)
 TO service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_variant_authority(
    p_set_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
    canonical_card_id uuid, legacy_card_id uuid, card_variant_id uuid,
    set_id uuid, card_name text, card_number text, rarity text,
    edition text, printing_type text, special_type text, image_url text,
    identity_basis text
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
WITH canonical_scope AS (
    SELECT canonical.*
    FROM public.pokemon_canonical_cards canonical
    WHERE public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)
      AND (p_set_ids IS NULL OR cardinality(p_set_ids) = 0
           OR canonical.set_id = ANY(p_set_ids))
), candidates AS (
    SELECT canonical.id canonical_card_id, link.legacy_card_id,
           canonical.set_id,
           'explicit_legacy_identity_link'::text identity_basis,
           0 identity_rank
    FROM canonical_scope canonical
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = canonical.id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'parent_pokemon_tcg_api_id', 1
    FROM canonical_scope canonical
    JOIN public.cards card
      ON card.set_id = canonical.set_id
     AND card.pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'variant_pokemon_tcg_api_id', 2
    FROM canonical_scope canonical
    JOIN public.card_variants matched
      ON matched.pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id
    JOIN public.cards card
      ON card.id = matched.card_id AND card.set_id = canonical.set_id
    UNION ALL
    SELECT canonical.id, card.id, canonical.set_id,
           'normalized_name_number_fallback', 3
    FROM canonical_scope canonical
    JOIN public.cards card
      ON card.set_id = canonical.set_id
     AND lower(regexp_replace(trim(card.name), '[[:space:]]+', ' ', 'g')) =
         lower(regexp_replace(trim(canonical.name), '[[:space:]]+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(card.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(canonical.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(canonical.printed_number, '')), '/', 1), '^0+', ''))
), resolved AS (
    SELECT DISTINCT ON (canonical_card_id)
           canonical_card_id, legacy_card_id, set_id, identity_basis
    FROM candidates
    ORDER BY canonical_card_id, identity_rank, legacy_card_id
)
SELECT resolved.canonical_card_id, resolved.legacy_card_id, variant.id,
       resolved.set_id, canonical.name,
       coalesce(canonical.number, canonical.printed_number, legacy.card_number),
       canonical.rarity, variant.edition, variant.printing_type,
       variant.special_type,
       coalesce(variant.image_small_url, canonical.image_small_url,
                legacy.image_small_url),
       resolved.identity_basis
FROM resolved
JOIN public.pokemon_canonical_cards canonical
  ON canonical.id = resolved.canonical_card_id
JOIN public.cards legacy ON legacy.id = resolved.legacy_card_id
JOIN public.card_variants variant ON variant.card_id = resolved.legacy_card_id;
$function$;

COMMENT ON FUNCTION public.get_pokemon_canonical_card_variant_authority(uuid[]) IS
'Market Explorer canonical-to-variant authority. Only reviewed physical catalog roles may produce traded card_variant_id instruments.';

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_variant_authority(uuid[])
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_variant_authority(uuid[])
 TO service_role;

-- Fail closed if production has drifted beyond the explicitly authorized
-- two-alias Celebrations cleanup.
DO $cleanup_guard$
DECLARE
    invalid_rows bigint;
    invalid_variants bigint;
    invalid_canonical bigint;
    invalid_sets bigint;
    canonical_ids uuid[];
    variant_ids uuid[];
BEGIN
    SELECT count(*), count(DISTINCT interval_row.card_variant_id),
           count(DISTINCT interval_row.canonical_card_id),
           count(DISTINCT interval_row.set_id),
           array_agg(DISTINCT interval_row.canonical_card_id
                     ORDER BY interval_row.canonical_card_id),
           array_agg(DISTINCT interval_row.card_variant_id
                     ORDER BY interval_row.card_variant_id)
      INTO invalid_rows, invalid_variants, invalid_canonical, invalid_sets,
           canonical_ids, variant_ids
    FROM public.pokemon_card_variant_market_price_intervals interval_row
    JOIN public.pokemon_canonical_cards canonical
      ON canonical.id = interval_row.canonical_card_id
    WHERE NOT public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role);

    IF invalid_rows <> 116 OR invalid_variants <> 2
       OR invalid_canonical <> 2 OR invalid_sets <> 1
       OR canonical_ids <> ARRAY[
          '81d1a23e-84b2-478f-a53a-195b80ee48f0'::uuid,
          '974af7c8-adda-4a24-a56b-65f1a6e4bf22'::uuid]
       OR variant_ids <> ARRAY[
          '310b3b23-d736-46a2-bb70-0a3a7f461450'::uuid,
          'aa8ab25a-5f50-4621-949f-6cfac3140da8'::uuid] THEN
        RAISE EXCEPTION
          'Market Explorer invalid-instrument cleanup scope changed: rows %, variants %, canonical %, sets %',
          invalid_rows, invalid_variants, invalid_canonical, invalid_sets;
    END IF;

    DELETE FROM public.pokemon_card_variant_market_price_intervals interval_row
    USING public.pokemon_canonical_cards canonical
    WHERE canonical.id = interval_row.canonical_card_id
      AND NOT public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)
      AND interval_row.canonical_card_id = ANY(canonical_ids)
      AND interval_row.card_variant_id = ANY(variant_ids);
END;
$cleanup_guard$;

COMMIT;
