BEGIN;

-- Two canonical Gold Stars were absent from the legacy cards/card_variants layer.
-- Their official Pokemon TCG API identities and TCGPlayer commercial product
-- identities are known, but TCGPlayer currently publishes no qualifying market
-- price. Pre-stage identity only; Set Value remains fail-closed until an actual
-- Near Mint USD observation is ingested.
WITH seed(set_name, api_id, legacy_name, card_number, rarity, tcgplayer_product_id) AS (
  VALUES
    ('Holon Phantoms', 'ex13-103', 'Mewtwo Star', '103/110', 'Ultra Rare', '87427'),
    ('Team Rocket Returns', 'ex7-107', 'Mudkip Star', '107/109', 'Ultra Rare', '87616')
), source AS (
  SELECT s.id AS set_id,
         seed.*,
         pcc.image_small_url,
         pcc.image_large_url
  FROM seed
  JOIN public.sets s
    ON s.name = seed.set_name
  JOIN public.pokemon_canonical_cards pcc
    ON pcc.set_id = s.id
   AND pcc.pokemon_tcg_api_card_id = seed.api_id
)
INSERT INTO public.cards(
  set_id, name, rarity, card_number, pokemon_tcg_api_id,
  image_small_url, image_large_url
)
SELECT set_id, legacy_name, rarity, card_number, api_id,
       image_small_url, image_large_url
FROM source
ON CONFLICT (set_id, card_number, name) DO UPDATE
SET pokemon_tcg_api_id = coalesce(public.cards.pokemon_tcg_api_id, excluded.pokemon_tcg_api_id),
    image_small_url = coalesce(public.cards.image_small_url, excluded.image_small_url),
    image_large_url = coalesce(public.cards.image_large_url, excluded.image_large_url);

WITH seed(api_id) AS (
  VALUES ('ex13-103'), ('ex7-107')
)
INSERT INTO public.card_variants(
  card_id, printing_type, special_type, edition,
  pokemon_tcg_api_id, image_small_url, image_large_url
)
SELECT c.id, 'holo', NULL, NULL,
       c.pokemon_tcg_api_id, c.image_small_url, c.image_large_url
FROM public.cards c
JOIN seed ON seed.api_id = c.pokemon_tcg_api_id
WHERE NOT EXISTS (
  SELECT 1
  FROM public.card_variants v
  WHERE v.card_id = c.id
    AND v.printing_type = 'holo'
    AND v.special_type IS NULL
    AND v.edition IS NULL
);

INSERT INTO public.pokemon_canonical_card_legacy_identity_links(
  canonical_card_id, legacy_card_id, match_basis, confidence, notes,
  created_at, updated_at
)
SELECT pcc.id,
       c.id,
       'official_pokemon_tcg_api_identity_prestage_20260904',
       'verified',
       'Pre-staged from the shared official Pokemon TCG API identity before the next TCGPlayer scrape; current Set Value remains blocked until a qualifying Near Mint USD observation exists.',
       now(), now()
FROM public.pokemon_canonical_cards pcc
JOIN public.cards c
  ON c.set_id = pcc.set_id
 AND c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
WHERE pcc.pokemon_tcg_api_card_id IN ('ex13-103','ex7-107')
ON CONFLICT (canonical_card_id) DO NOTHING;

WITH identities(api_id, product_id, source_reference, source_payload) AS (
  VALUES
    (
      'ex13-103',
      '87427',
      'https://www.tcgplayer.com/product/87427/pokemon-holon-phantoms-mewtwo-star',
      jsonb_build_object(
        'productName','Mewtwo Star',
        'number','103/110',
        'printing','Holofoil',
        'set','EX Holon Phantoms',
        'provenance','public_tcgplayer_product_page_2026-09-04'
      )
    ),
    (
      'ex7-107',
      '87616',
      'https://www.tcgplayer.com/product/87616/pokemon-ex-team-rocket-returns-mudkip-star',
      jsonb_build_object(
        'productName','Mudkip Star',
        'number','107/109',
        'printing','Holofoil',
        'set','EX Team Rocket Returns',
        'provenance','public_tcgplayer_product_page_2026-09-04'
      )
    )
)
INSERT INTO public.card_variant_external_identities(
  card_variant_id, provider, external_product_id, external_variant_key,
  source_reference, source_payload, created_at, updated_at
)
SELECT v.id,
       'tcgplayer',
       i.product_id,
       'edition=|printing_type=holo|special_type=',
       i.source_reference,
       i.source_payload,
       now(), now()
FROM identities i
JOIN public.card_variants v
  ON v.pokemon_tcg_api_id = i.api_id
ON CONFLICT (provider, external_product_id, external_variant_key) DO UPDATE
SET source_reference = excluded.source_reference,
    source_payload = excluded.source_payload,
    updated_at = now();

COMMIT;
