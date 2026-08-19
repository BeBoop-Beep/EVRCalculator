-- A TCGplayer commercial product may expose multiple canonical print variants.
ALTER TABLE public.card_variant_external_identities
ADD COLUMN external_variant_key text;

UPDATE public.card_variant_external_identities AS identity
SET external_variant_key =
    'edition=' || lower(btrim(coalesce(variant.edition, ''))) ||
    '|printing_type=' || lower(btrim(coalesce(variant.printing_type, ''))) ||
    '|special_type=' || lower(btrim(coalesce(variant.special_type, '')))
FROM public.card_variants AS variant
WHERE variant.id = identity.card_variant_id
  AND identity.external_variant_key IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.card_variant_external_identities
        WHERE external_variant_key IS NULL
    ) THEN
        RAISE EXCEPTION 'external identity variant-key backfill was incomplete';
    END IF;
END $$;

ALTER TABLE public.card_variant_external_identities
ALTER COLUMN external_variant_key SET NOT NULL;

ALTER TABLE public.card_variant_external_identities
ADD CONSTRAINT card_variant_external_identities_external_variant_key_check
CHECK (btrim(external_variant_key) <> '');

ALTER TABLE public.card_variant_external_identities
DROP CONSTRAINT card_variant_external_identities_provider_external_product_id_key;

ALTER TABLE public.card_variant_external_identities
ADD CONSTRAINT card_variant_external_identities_provider_product_variant_key
UNIQUE (provider, external_product_id, external_variant_key);
