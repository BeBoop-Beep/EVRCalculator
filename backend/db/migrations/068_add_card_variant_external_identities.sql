CREATE UNIQUE INDEX IF NOT EXISTS uq_card_variants_local_identity
ON public.card_variants (card_id, printing_type, special_type, edition) NULLS NOT DISTINCT;

CREATE TABLE IF NOT EXISTS public.card_variant_external_identities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE CASCADE,
 provider text NOT NULL CHECK (provider = lower(btrim(provider)) AND provider <> ''),
 external_product_id text NOT NULL CHECK (btrim(external_product_id) <> ''),
 external_catalog_key text,
 source_reference text NOT NULL CHECK (btrim(source_reference) <> ''),
 source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (provider, external_product_id)
);
CREATE INDEX IF NOT EXISTS idx_card_variant_external_identities_variant ON public.card_variant_external_identities(card_variant_id);
CREATE INDEX IF NOT EXISTS idx_card_variant_external_identities_catalog ON public.card_variant_external_identities(provider, external_catalog_key);
ALTER TABLE public.card_variant_external_identities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.card_variant_external_identities FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.card_variant_external_identities TO service_role;
