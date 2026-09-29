BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Additive evidence enrichment only. Existing rows remain null and retain their
-- original provider_payload, so old normalization is reproducible.
ALTER TABLE public.pkmnprices_ebay_sold_evidence_v1
  ADD COLUMN grade_qualifier text;

COMMENT ON COLUMN public.pkmnprices_ebay_sold_evidence_v1.grade_qualifier IS
  'Opaque provider qualifier (for example CGC Pristine or BGS Black Label); never folded into numeric grade.';

-- Provider-agnostic fixed-panel offered-supply contract. Bucket A defines the
-- empty storage authority only; Bucket C owns population and continuity rules.
CREATE TABLE public.market_active_supply_snapshot_runs_v1 (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  panel_version text NOT NULL CHECK (btrim(panel_version) <> ''),
  panel_fingerprint text NOT NULL CHECK (panel_fingerprint ~ '^[0-9a-f]{64}$'),
  source_provider text NOT NULL CHECK (btrim(source_provider) <> ''),
  expected_observation_date date NOT NULL,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('RUNNING','COMPLETE','PARTIAL','FAILED','MISSING')),
  target_count integer NOT NULL CHECK (target_count >= 0),
  observed_target_count integer NOT NULL DEFAULT 0 CHECK (observed_target_count >= 0 AND observed_target_count <= target_count),
  provider_request_count integer NOT NULL DEFAULT 0 CHECK (provider_request_count >= 0),
  provider_credits_used integer NOT NULL DEFAULT 0 CHECK (provider_credits_used >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (panel_fingerprint, source_provider, expected_observation_date),
  CHECK ((status = 'RUNNING' AND finished_at IS NULL) OR (status <> 'RUNNING' AND finished_at IS NOT NULL))
);

CREATE TABLE public.market_active_supply_snapshots_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES public.market_active_supply_snapshot_runs_v1(run_id) ON DELETE RESTRICT,
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE RESTRICT,
  source_provider text NOT NULL CHECK (btrim(source_provider) <> ''),
  source_card_id text NOT NULL CHECK (btrim(source_card_id) <> ''),
  observed_at timestamptz,
  observation_state text NOT NULL CHECK (observation_state IN ('OBSERVED','TARGET_FAILED','RUN_MISSING')),
  language text NOT NULL CHECK (btrim(language) <> ''),
  condition_label text,
  printing_label text,
  requested_depth integer NOT NULL CHECK (requested_depth >= 0),
  captured_listing_count integer NOT NULL DEFAULT 0 CHECK (captured_listing_count >= 0 AND captured_listing_count <= requested_depth),
  captured_quantity integer NOT NULL DEFAULT 0 CHECK (captured_quantity >= 0),
  distinct_seller_count integer NOT NULL DEFAULT 0 CHECK (distinct_seller_count >= 0),
  has_more boolean,
  next_cursor_present boolean,
  continuity_eligible boolean NOT NULL DEFAULT false,
  error_code text,
  source_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (run_id, card_variant_id),
  CHECK ((observation_state = 'OBSERVED' AND observed_at IS NOT NULL) OR (observation_state <> 'OBSERVED' AND observed_at IS NULL)),
  CHECK (NOT continuity_eligible OR observation_state = 'OBSERVED')
);

CREATE TABLE public.market_active_supply_listing_observations_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_id uuid NOT NULL REFERENCES public.market_active_supply_snapshots_v1(id) ON DELETE RESTRICT,
  source_listing_id text NOT NULL CHECK (btrim(source_listing_id) <> ''),
  source_seller_id text,
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  item_price numeric(12,2) NOT NULL CHECK (item_price >= 0),
  shipping_price numeric(12,2) CHECK (shipping_price >= 0),
  currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  source_rank integer NOT NULL CHECK (source_rank > 0),
  source_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (snapshot_id, source_listing_id)
);

-- Provider/card mapping is exact physical variant identity. Edition scopes may
-- never share one mapping, including First Edition, Unlimited and Shadowless.
CREATE TABLE public.grading_population_provider_identities_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_provider text NOT NULL CHECK (btrim(source_provider) <> ''),
  source_card_id text NOT NULL CHECK (btrim(source_card_id) <> ''),
  card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE RESTRICT,
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  edition_scope text NOT NULL CHECK (edition_scope IN ('FIRST_EDITION','UNLIMITED','SHADOWLESS','OTHER','NOT_APPLICABLE')),
  source_card_name text,
  source_set_name text,
  match_state text NOT NULL CHECK (match_state IN ('EXACT','REVIEW','REJECTED')),
  match_basis text NOT NULL CHECK (btrim(match_basis) <> ''),
  verified_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (source_provider, source_card_id),
  UNIQUE (source_provider, card_variant_id)
);

CREATE TABLE public.grading_population_snapshots_v1 (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_identity_id uuid NOT NULL REFERENCES public.grading_population_provider_identities_v1(id) ON DELETE RESTRICT,
  source_provider text NOT NULL CHECK (btrim(source_provider) <> ''),
  grading_company text NOT NULL CHECK (btrim(grading_company) <> ''),
  grade text NOT NULL CHECK (btrim(grade) <> ''),
  grade_qualifier text NOT NULL DEFAULT '',
  population_count bigint NOT NULL CHECK (population_count >= 0),
  observed_date date NOT NULL,
  source_observed_at timestamptz,
  collected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  source_payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(source_payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (provider_identity_id, grading_company, grade, grade_qualifier, observed_date)
);

CREATE INDEX market_active_supply_snapshots_variant_idx ON public.market_active_supply_snapshots_v1 (card_variant_id, observed_at);
CREATE INDEX grading_population_snapshots_observed_idx ON public.grading_population_snapshots_v1 (provider_identity_id, observed_date);

COMMENT ON TABLE public.market_active_supply_snapshots_v1 IS 'Research-only fixed-panel active offered-supply evidence; not a pricing authority.';
COMMENT ON TABLE public.grading_population_snapshots_v1 IS 'Research-only grading-population evidence; population is submission-selected and not copies in existence.';

ALTER TABLE public.market_active_supply_snapshot_runs_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_active_supply_snapshots_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_active_supply_listing_observations_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grading_population_provider_identities_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grading_population_snapshots_v1 ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.market_active_supply_snapshot_runs_v1, public.market_active_supply_snapshots_v1,
  public.market_active_supply_listing_observations_v1, public.grading_population_provider_identities_v1,
  public.grading_population_snapshots_v1 FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.market_active_supply_snapshot_runs_v1 TO service_role;
GRANT SELECT, INSERT ON public.market_active_supply_snapshots_v1, public.market_active_supply_listing_observations_v1,
  public.grading_population_snapshots_v1 TO service_role;
GRANT SELECT, INSERT, UPDATE ON public.grading_population_provider_identities_v1 TO service_role;

COMMIT;
