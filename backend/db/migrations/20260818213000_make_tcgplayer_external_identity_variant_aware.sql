-- A TCGplayer commercial product may expose multiple canonical print variants.
BEGIN;

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

DO $$
DECLARE
    matching_constraints text[];
BEGIN
    SELECT array_agg(constraint_row.conname ORDER BY constraint_row.conname)
    INTO matching_constraints
    FROM (
        SELECT constraint_def.conname
        FROM pg_constraint AS constraint_def
        WHERE constraint_def.conrelid = 'public.card_variant_external_identities'::regclass
          AND constraint_def.contype = 'u'
          AND constraint_def.conkey = ARRAY[
              (SELECT attnum FROM pg_attribute
               WHERE attrelid = constraint_def.conrelid AND attname = 'provider'),
              (SELECT attnum FROM pg_attribute
               WHERE attrelid = constraint_def.conrelid AND attname = 'external_product_id')
          ]::smallint[]
    ) AS constraint_row;

    IF coalesce(array_length(matching_constraints, 1), 0) <> 1 THEN
        RAISE EXCEPTION
            'expected exactly one UNIQUE(provider, external_product_id) constraint, found %: %',
            coalesce(array_length(matching_constraints, 1), 0), matching_constraints;
    END IF;

    EXECUTE format(
        'ALTER TABLE public.card_variant_external_identities DROP CONSTRAINT %I',
        matching_constraints[1]
    );
END $$;

ALTER TABLE public.card_variant_external_identities
ADD CONSTRAINT card_variant_external_identities_provider_product_variant_key
UNIQUE (provider, external_product_id, external_variant_key);

COMMIT;
