BEGIN;

CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_sealed_instruments(
  p_query text,
  p_limit integer DEFAULT 20
)
RETURNS TABLE(
  sealed_product_id uuid,
  product_name text,
  set_id uuid,
  set_name text,
  image_url text,
  product_family text,
  variant_label text
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET statement_timeout TO '5s'
AS $function$
  SELECT
    nullif(product.item->>'sealedProductId','')::uuid,
    product.item->>'name',
    snapshot.set_id,
    snapshot.payload_json->'set'->>'name',
    product.item->>'imageUrl',
    product.item->>'productFamily',
    product.item->>'variantLabel'
  FROM public.pokemon_set_sealed_market_snapshot_latest snapshot
  CROSS JOIN LATERAL jsonb_array_elements(coalesce(snapshot.payload_json->'products','[]'::jsonb)) product(item)
  WHERE snapshot.tcg = 'pokemon'
    AND length(btrim(coalesce(p_query,''))) >= 2
    AND product.item->>'sealedProductId' IS NOT NULL
    AND product.item->>'name' ILIKE '%' || btrim(p_query) || '%'
  ORDER BY lower(product.item->>'name'), nullif(product.item->>'sealedProductId','')::uuid
  LIMIT least(greatest(coalesce(p_limit,20),1),50)
$function$;

REVOKE ALL ON FUNCTION public.search_pokemon_market_explorer_sealed_instruments(text,integer)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_pokemon_market_explorer_sealed_instruments(text,integer)
TO service_role;

COMMIT;
