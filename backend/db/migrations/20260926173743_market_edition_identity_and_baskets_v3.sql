BEGIN;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '12s';

-- Additive, candidate-only foundation. No legacy writer or serving pointer changes.
CREATE TABLE public.pokemon_market_registry_v3 (
  root_set_id uuid NOT NULL REFERENCES public.sets(id),
  market_scope text NOT NULL CHECK (market_scope IN ('standard','first_edition','unlimited','shadowless')),
  profile text NOT NULL CHECK (profile IN ('standard','edition_split','base_three_printings')),
  market_key text GENERATED ALWAYS AS ('set:' || root_set_id::text || CASE WHEN market_scope='standard' THEN '' ELSE ':' || market_scope END) STORED,
  condition_id uuid NOT NULL REFERENCES public.conditions(id),
  price_source text NOT NULL DEFAULT 'TCGPlayer' CHECK (price_source='TCGPlayer'),
  currency text NOT NULL DEFAULT 'USD' CHECK (currency='USD'),
  registered_authority_date date NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  contract_version text NOT NULL DEFAULT 'edition_exact_basket_v3' CHECK (contract_version='edition_exact_basket_v3'),
  PRIMARY KEY(root_set_id,market_scope),
  UNIQUE(market_key),
  CHECK ((profile='standard' AND market_scope='standard') OR (profile='edition_split' AND market_scope IN ('first_edition','unlimited')) OR (profile='base_three_printings' AND market_scope IN ('first_edition','unlimited','shadowless')))
);

CREATE TABLE public.pokemon_market_basket_versions_v3 (
  root_set_id uuid NOT NULL,
  market_scope text NOT NULL,
  basket_version integer NOT NULL CHECK (basket_version>0),
  effective_from date NOT NULL,
  definition_basis text NOT NULL CHECK (definition_basis='current_catalog_staged_v1'),
  selection_policy text NOT NULL DEFAULT 'catalog_identity_then_printing_no_price_v1' CHECK (selection_policy='catalog_identity_then_printing_no_price_v1'),
  state text NOT NULL DEFAULT 'DRAFT' CHECK (state IN ('DRAFT','APPROVED')),
  expected_member_count integer NOT NULL CHECK (expected_member_count>0),
  expected_card_count integer NOT NULL CHECK (expected_card_count>0),
  catalog_fingerprint text NOT NULL CHECK (catalog_fingerprint ~ '^[0-9a-f]{64}$'),
  binding_fingerprint text CHECK (binding_fingerprint ~ '^[0-9a-f]{64}$'),
  request_key text NOT NULL UNIQUE CHECK(length(request_key) BETWEEN 8 AND 180),
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  evidence text NOT NULL CHECK(length(evidence) BETWEEN 12 AND 4000),
  PRIMARY KEY(root_set_id,market_scope,basket_version),
  FOREIGN KEY(root_set_id,market_scope) REFERENCES public.pokemon_market_registry_v3(root_set_id,market_scope),
  CHECK ((state='DRAFT' AND approved_at IS NULL AND binding_fingerprint IS NULL) OR (state='APPROVED' AND approved_at IS NOT NULL AND binding_fingerprint IS NOT NULL))
);
CREATE UNIQUE INDEX pokemon_market_basket_effective_v3 ON public.pokemon_market_basket_versions_v3(root_set_id,market_scope,effective_from) WHERE state='APPROVED';

CREATE TABLE public.pokemon_market_basket_members_v3 (
  root_set_id uuid NOT NULL,
  market_scope text NOT NULL,
  basket_version integer NOT NULL,
  member_set_id uuid NOT NULL REFERENCES public.sets(id),
  member_type text NOT NULL CHECK (member_type IN ('root','counted_subset')),
  expected_card_count integer NOT NULL CHECK (expected_card_count>=0),
  PRIMARY KEY(root_set_id,market_scope,basket_version,member_set_id),
  FOREIGN KEY(root_set_id,market_scope,basket_version) REFERENCES public.pokemon_market_basket_versions_v3(root_set_id,market_scope,basket_version),
  CHECK ((member_type='root' AND member_set_id=root_set_id) OR (member_type='counted_subset' AND member_set_id<>root_set_id))
);

CREATE TABLE public.pokemon_market_basket_bindings_v3 (
  root_set_id uuid NOT NULL,
  market_scope text NOT NULL,
  basket_version integer NOT NULL,
  member_set_id uuid NOT NULL,
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id),
  card_variant_id uuid REFERENCES public.card_variants(id),
  edition text,
  printing_type text,
  special_type text,
  identity_basis text,
  resolution text NOT NULL CHECK (resolution IN ('BOUND','MISSING','AMBIGUOUS','REVIEW_REQUIRED')),
  candidate_count integer NOT NULL CHECK (candidate_count>=0),
  PRIMARY KEY(root_set_id,market_scope,basket_version,canonical_card_id),
  UNIQUE(root_set_id,market_scope,basket_version,card_variant_id),
  UNIQUE(root_set_id,market_scope,basket_version,canonical_card_id,card_variant_id),
  FOREIGN KEY(root_set_id,market_scope,basket_version,member_set_id) REFERENCES public.pokemon_market_basket_members_v3(root_set_id,market_scope,basket_version,member_set_id),
  CHECK ((resolution='BOUND' AND card_variant_id IS NOT NULL AND candidate_count=1 AND identity_basis IS NOT NULL) OR (resolution<>'BOUND' AND card_variant_id IS NULL AND edition IS NULL AND printing_type IS NULL AND special_type IS NULL AND identity_basis IS NULL)),
  CHECK (resolution<>'BOUND' OR (market_scope='first_edition' AND edition IS NOT DISTINCT FROM '1st-edition') OR (market_scope='unlimited' AND edition IS NOT DISTINCT FROM 'unlimited') OR (market_scope='shadowless' AND edition IS NOT DISTINCT FROM 'shadowless') OR (market_scope='standard' AND coalesce(edition,'') IN ('','unlimited')))
);

ALTER TABLE public.pokemon_market_registry_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_basket_versions_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_basket_members_v3 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_basket_bindings_v3 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_registry_v3,public.pokemon_market_basket_versions_v3,public.pokemon_market_basket_members_v3,public.pokemon_market_basket_bindings_v3 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.pokemon_market_registry_v3,public.pokemon_market_basket_versions_v3,public.pokemon_market_basket_members_v3,public.pokemon_market_basket_bindings_v3 TO service_role;
COMMENT ON TABLE public.pokemon_market_registry_v3 IS 'Permanent candidate market identities. Edition scopes are separate assets; this table does not alter legacy serving.';
COMMENT ON TABLE public.pokemon_market_basket_bindings_v3 IS 'Versioned exact variant bindings, including unresolved expected cards. Approved baskets must be complete and immutable.';
COMMIT;
