BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Shadow-only transaction evidence for inDex Fair Value research.
--
-- V1 deliberately cannot become a public Set Value / Near Mint price authority:
-- PkmnPrices eBay sold rows distinguish printing attribution and grading but do
-- not expose raw-card condition.  Every persisted sold row therefore carries
-- set_value_nm_eligible=false and condition_state='UNKNOWN'.  Any future NM
-- bridge requires a separately reviewed migration/policy rather than a code-only
-- reinterpretation of these rows.

CREATE TABLE public.pkmnprices_sold_runs_v1 (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('RUNNING','COMPLETE','PARTIAL','FAILED')),
  selector_version text NOT NULL CHECK (btrim(selector_version) <> ''),
  collector_version text NOT NULL CHECK (btrim(collector_version) <> ''),
  target_count integer NOT NULL DEFAULT 0 CHECK (target_count >= 0),
  item_credit_cap integer NOT NULL CHECK (item_credit_cap >= 0),
  api_request_count integer NOT NULL DEFAULT 0 CHECK (api_request_count >= 0),
  credits_used integer NOT NULL DEFAULT 0 CHECK (credits_used >= 0 AND credits_used <= item_credit_cap),
  provider_card_lookup_count integer NOT NULL DEFAULT 0 CHECK (provider_card_lookup_count >= 0),
  sold_item_count integer NOT NULL DEFAULT 0 CHECK (sold_item_count >= 0),
  exact_attribution_count integer NOT NULL DEFAULT 0 CHECK (exact_attribution_count >= 0),
  fair_value_eligible_count integer NOT NULL DEFAULT 0 CHECK (fair_value_eligible_count >= 0),
  set_value_nm_eligible_count integer NOT NULL DEFAULT 0 CHECK (set_value_nm_eligible_count = 0),
  manifest_fingerprint text NOT NULL CHECK (manifest_fingerprint ~ '^[0-9a-f]{64}$'),
  error_code text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (
    (status = 'RUNNING' AND finished_at IS NULL)
    OR
    (status IN ('COMPLETE','PARTIAL','FAILED') AND finished_at IS NOT NULL)
  )
);

CREATE INDEX pkmnprices_sold_runs_v1_started_idx
  ON public.pkmnprices_sold_runs_v1 (started_at DESC);

CREATE TABLE public.pkmnprices_card_identity_v1 (
  provider_card_id bigint PRIMARY KEY CHECK (provider_card_id > 0),
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  tcgplayer_product_id text NOT NULL CHECK (tcgplayer_product_id ~ '^[0-9]+$'),
  language text NOT NULL DEFAULT 'English' CHECK (btrim(language) <> ''),
  match_basis text NOT NULL CHECK (btrim(match_basis) <> ''),
  provider_name text,
  provider_set_id text,
  verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tcgplayer_product_id, language),
  UNIQUE (canonical_card_id, language)
);

CREATE INDEX pkmnprices_card_identity_v1_canonical_idx
  ON public.pkmnprices_card_identity_v1 (canonical_card_id);

CREATE TABLE public.pkmnprices_ebay_sold_evidence_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES public.pkmnprices_sold_runs_v1(run_id) ON DELETE RESTRICT,
  provider_listing_id bigint NOT NULL CHECK (provider_listing_id > 0),
  provider_card_id bigint NOT NULL REFERENCES public.pkmnprices_card_identity_v1(provider_card_id) ON DELETE RESTRICT,
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  card_variant_id uuid REFERENCES public.card_variants(id) ON DELETE RESTRICT,
  title text NOT NULL DEFAULT '',
  price numeric(12,2) NOT NULL CHECK (price > 0),
  currency text NOT NULL CHECK (currency IN ('USD','EUR')),
  grader text,
  grade text,
  graded boolean NOT NULL,
  provider_variant text,
  attribution text NOT NULL CHECK (attribution IN ('exact','shared','unknown')),
  sold_at date NOT NULL,
  ingested_at timestamptz,
  listing_url text,
  identity_state text NOT NULL CHECK (identity_state IN ('EXACT','AMBIGUOUS','NO_MATCH')),
  fair_value_eligible boolean NOT NULL DEFAULT false,
  set_value_nm_eligible boolean NOT NULL DEFAULT false CHECK (NOT set_value_nm_eligible),
  condition_state text NOT NULL DEFAULT 'UNKNOWN' CHECK (condition_state = 'UNKNOWN'),
  exclusion_reason text,
  collected_at timestamptz NOT NULL,
  provider_payload jsonb NOT NULL CHECK (jsonb_typeof(provider_payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (provider_listing_id, provider_card_id),
  CHECK (
    NOT fair_value_eligible
    OR (
      attribution = 'exact'
      AND NOT graded
      AND currency = 'USD'
      AND card_variant_id IS NOT NULL
      AND identity_state = 'EXACT'
    )
  )
);

CREATE INDEX pkmnprices_ebay_sold_evidence_v1_canonical_sold_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (canonical_card_id, sold_at DESC, provider_listing_id DESC);

CREATE INDEX pkmnprices_ebay_sold_evidence_v1_variant_sold_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (card_variant_id, sold_at DESC, provider_listing_id DESC)
  WHERE card_variant_id IS NOT NULL;

CREATE INDEX pkmnprices_ebay_sold_evidence_v1_ingested_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (ingested_at DESC, provider_listing_id DESC)
  WHERE ingested_at IS NOT NULL;

CREATE INDEX pkmnprices_ebay_sold_evidence_v1_fair_value_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (canonical_card_id, sold_at DESC)
  WHERE fair_value_eligible;

CREATE TABLE public.pkmnprices_sold_sync_state_v1 (
  provider_card_id bigint PRIMARY KEY REFERENCES public.pkmnprices_card_identity_v1(provider_card_id) ON DELETE RESTRICT,
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  last_ingested_at timestamptz,
  last_sold_at date,
  last_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_success_at timestamptz,
  status text NOT NULL CHECK (status IN ('NEVER','CURRENT','PARTIAL','FAILED')),
  consecutive_failures integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
  rows_seen bigint NOT NULL DEFAULT 0 CHECK (rows_seen >= 0),
  rows_inserted bigint NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0 AND rows_inserted <= rows_seen),
  last_error_code text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (canonical_card_id)
);

COMMENT ON TABLE public.pkmnprices_ebay_sold_evidence_v1 IS
  'Shadow-only PkmnPrices eBay completed-sale evidence. V1 is NOT a Near Mint Set Value price source.';
COMMENT ON COLUMN public.pkmnprices_ebay_sold_evidence_v1.set_value_nm_eligible IS
  'Hard-false in V1 because PkmnPrices sold rows do not expose raw-card condition.';
COMMENT ON COLUMN public.pkmnprices_ebay_sold_evidence_v1.fair_value_eligible IS
  'Exact-attribution, exact-internal-variant, ungraded USD transaction evidence; condition remains unknown.';

ALTER TABLE public.pkmnprices_sold_runs_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pkmnprices_card_identity_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pkmnprices_ebay_sold_evidence_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pkmnprices_sold_sync_state_v1 ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.pkmnprices_sold_runs_v1 FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.pkmnprices_card_identity_v1 FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.pkmnprices_ebay_sold_evidence_v1 FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON public.pkmnprices_sold_sync_state_v1 FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE ON public.pkmnprices_sold_runs_v1 TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.pkmnprices_card_identity_v1 TO service_role;
GRANT SELECT, INSERT ON public.pkmnprices_ebay_sold_evidence_v1 TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.pkmnprices_sold_sync_state_v1 TO service_role;

COMMIT;
