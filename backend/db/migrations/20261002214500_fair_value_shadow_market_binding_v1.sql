-- Research-only append-only market binding for FV-S3 forward outcome evaluation.
-- Freezes the exact TCGplayer card-variant + condition lineage used at horizon 0 so
-- later +1/+7/+30 comparisons cannot silently switch condition scope.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE public.fair_value_shadow_market_bindings_v1 (
  publication_id uuid PRIMARY KEY
    REFERENCES public.fair_value_shadow_anchor_publications_v1(publication_id) ON DELETE RESTRICT,
  schema_version text NOT NULL CHECK (schema_version = 'fv_shadow_market_binding_v1'),
  content_fingerprint text NOT NULL CHECK (content_fingerprint ~ '^[0-9a-f]{64}$'),
  canonical_card_id uuid NOT NULL
    REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  card_variant_id uuid NOT NULL
    REFERENCES public.card_variants(id) ON DELETE RESTRICT,
  condition_id uuid NOT NULL
    REFERENCES public.conditions(id) ON DELETE RESTRICT,
  baseline_date date NOT NULL,
  baseline_market_price_usd numeric(12,2) NOT NULL CHECK (baseline_market_price_usd > 0),
  price_source text NOT NULL CHECK (btrim(price_source) <> ''),
  currency text NOT NULL CHECK (currency = 'USD'),
  binding_method text NOT NULL CHECK (binding_method = 'UNIQUE_H0_EXACT_PRICE_MATCH_V1'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TRIGGER fair_value_shadow_market_bindings_v1_no_mutation
  BEFORE UPDATE OR DELETE ON public.fair_value_shadow_market_bindings_v1
  FOR EACH ROW EXECUTE FUNCTION public.fv_shadow_forbid_mutation();
CREATE TRIGGER fair_value_shadow_market_bindings_v1_no_truncate
  BEFORE TRUNCATE ON public.fair_value_shadow_market_bindings_v1
  FOR EACH STATEMENT EXECUTE FUNCTION public.fv_shadow_forbid_mutation();

ALTER TABLE public.fair_value_shadow_market_bindings_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.fair_value_shadow_market_bindings_v1 FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.fair_value_shadow_market_bindings_v1 TO service_role;

COMMENT ON TABLE public.fair_value_shadow_market_bindings_v1 IS
  'Research-only immutable H0 TCGplayer condition binding for FV-S3 forward evaluation; not a price authority.';

COMMIT;
