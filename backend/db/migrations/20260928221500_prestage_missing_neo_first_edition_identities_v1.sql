BEGIN;

-- Pre-stage two missing vintage 1st Edition physical identities without
-- fabricating a market price. Both products are public TCGplayer product
-- identities whose Unlimited sibling is already present in the local catalog.
-- Set Value remains fail-closed until a real qualifying Near Mint USD
-- observation is ingested for these exact variant identities.
SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended('prestage-missing-neo-first-edition-identities-v1', 0)
);

DO $$
DECLARE
  v_sources integer;
BEGIN
  WITH seed(set_key, api_id) AS (
    VALUES
      ('neoDestiny','neo4-110'),
      ('neoRevelation','neo3-65')
  )
  SELECT count(*)::integer INTO v_sources
  FROM seed
  JOIN public.sets s ON s.canonical_key=seed.set_key
  JOIN public.cards c
    ON c.set_id=s.id
   AND c.pokemon_tcg_api_id=seed.api_id;

  IF v_sources<>2 THEN
    RAISE EXCEPTION 'NEO_FIRST_EDITION_PRESTAGE_SOURCE_MISMATCH: expected 2 found %',v_sources;
  END IF;
END;
$$;

WITH seed(set_key, api_id) AS (
  VALUES
    ('neoDestiny','neo4-110'),
    ('neoRevelation','neo3-65')
), source AS (
  SELECT c.id AS card_id,
         c.pokemon_tcg_api_id,
         c.image_small_url,
         c.image_large_url
  FROM seed
  JOIN public.sets s ON s.canonical_key=seed.set_key
  JOIN public.cards c
    ON c.set_id=s.id
   AND c.pokemon_tcg_api_id=seed.api_id
)
INSERT INTO public.card_variants(
  card_id,printing_type,special_type,edition,
  pokemon_tcg_api_id,image_small_url,image_large_url
)
SELECT source.card_id,'holo',NULL,'1st-edition',
       NULL,source.image_small_url,source.image_large_url
FROM source
WHERE NOT EXISTS (
  SELECT 1
  FROM public.card_variants v
  WHERE v.card_id=source.card_id
    AND v.printing_type='holo'
    AND v.special_type IS NULL
    AND v.edition='1st-edition'
);

WITH identities(
  set_key,api_id,product_id,product_name,card_number,source_reference
) AS (
  VALUES
    (
      'neoDestiny',
      'neo4-110',
      '89168',
      'Shining Noctowl',
      '110/105',
      'https://www.tcgplayer.com/product/89168/pokemon-neo-destiny-shining-noctowl'
    ),
    (
      'neoRevelation',
      'neo3-65',
      '89164',
      'Shining Gyarados',
      '65/64',
      'https://www.tcgplayer.com/product/89164/pokemon-neo-revelation-shining-gyarados'
    )
), resolved AS (
  SELECT i.*,v.id AS card_variant_id
  FROM identities i
  JOIN public.sets s ON s.canonical_key=i.set_key
  JOIN public.cards c
    ON c.set_id=s.id
   AND c.pokemon_tcg_api_id=i.api_id
  JOIN public.card_variants v
    ON v.card_id=c.id
   AND v.printing_type='holo'
   AND v.special_type IS NULL
   AND v.edition='1st-edition'
)
INSERT INTO public.card_variant_external_identities(
  card_variant_id,provider,external_product_id,external_variant_key,
  source_reference,source_payload,created_at,updated_at
)
SELECT r.card_variant_id,
       'tcgplayer',
       r.product_id,
       'edition=1st-edition|printing_type=holo|special_type=',
       r.source_reference,
       jsonb_build_object(
         'productName',r.product_name,
         'number',r.card_number,
         'printing','1st Edition Holofoil',
         'provenance','public_tcgplayer_product_identity_verified_2026-09-28',
         'identityOnly',true,
         'pricePrestaged',false
       ),
       now(),now()
FROM resolved r
ON CONFLICT(provider,external_product_id,external_variant_key) DO UPDATE
SET card_variant_id=excluded.card_variant_id,
    source_reference=excluded.source_reference,
    source_payload=excluded.source_payload,
    updated_at=now();

DO $$
DECLARE
  v_variants integer;
  v_identities integer;
BEGIN
  WITH seed(set_key,api_id) AS (
    VALUES
      ('neoDestiny','neo4-110'),
      ('neoRevelation','neo3-65')
  )
  SELECT count(*)::integer INTO v_variants
  FROM seed
  JOIN public.sets s ON s.canonical_key=seed.set_key
  JOIN public.cards c ON c.set_id=s.id AND c.pokemon_tcg_api_id=seed.api_id
  JOIN public.card_variants v
    ON v.card_id=c.id
   AND v.printing_type='holo'
   AND v.special_type IS NULL
   AND v.edition='1st-edition';

  SELECT count(*)::integer INTO v_identities
  FROM public.card_variant_external_identities x
  WHERE x.provider='tcgplayer'
    AND (
      (x.external_product_id='89168'
       AND x.external_variant_key='edition=1st-edition|printing_type=holo|special_type=')
      OR
      (x.external_product_id='89164'
       AND x.external_variant_key='edition=1st-edition|printing_type=holo|special_type=')
    );

  IF v_variants<>2 OR v_identities<>2 THEN
    RAISE EXCEPTION
      'NEO_FIRST_EDITION_PRESTAGE_POSTCONDITION_FAILED: variants % identities %',
      v_variants,v_identities;
  END IF;
END;
$$;

COMMIT;
