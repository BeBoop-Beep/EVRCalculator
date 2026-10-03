-- PROPOSED / NOT APPLIED / NOT IN ANY MIGRATION DIRECTORY.
--
-- Research-only, service-role, APPEND-ONLY ledger for the prospective inDex Fair Value shadow
-- (EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1). The `.proposed` extension and location are deliberate:
-- no migration runner globs this file. Applying it requires a separate reviewed change that
-- copies it into backend/db/migrations and supabase/migrations.
--
-- Structure (see FV_S3_PROSPECTIVE_SHADOW_FOUNDATION_20261001.md):
--   A  anchor publications + immutable membership   (written BEFORE any comparison price is read)
--   B  component observations                        (market / structural / scarcity / appeal kept separate)
--   C  evaluation outcomes                           (per publication x horizon; never edits A)
-- Nothing here is read by any public surface, Set Value, canonical price, Rankings or RIP.

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

CREATE OR REPLACE FUNCTION public.fv_shadow_forbid_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'fair_value_shadow ledger is append-only (% on %)', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

-- ---------------------------------------------------------------- A. anchor publications
CREATE TABLE public.fair_value_shadow_anchor_publications_v1 (
  publication_id uuid PRIMARY KEY,
  schema_version text NOT NULL CHECK (schema_version = 'fv_shadow_anchor_publication_v1'),
  rule_version text NOT NULL CHECK (btrim(rule_version) <> ''),
  canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE RESTRICT,
  card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE RESTRICT,
  evaluation_date date NOT NULL,
  information_cutoff timestamptz NOT NULL,
  evidence_cutoff timestamptz NOT NULL CHECK (evidence_cutoff = information_cutoff),
  status text NOT NULL CHECK (status IN ('ANCHORED','INSUFFICIENT_COMPS')),
  evidence_status text NOT NULL CHECK (evidence_status IN (
    'PROSPECTIVE_AS_KNOWN_AT_CUTOFF',
    'AS_KNOWN_AT_CUTOFF_REPLAY_NOT_PROSPECTIVE',
    'RETROSPECTIVE_BACKFILLED_EVIDENCE')),
  enrichment_policy text NOT NULL CHECK (enrichment_policy = 'FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY'),
  selected_window_days integer CHECK (selected_window_days IN (7,30,60,90,180)),
  eligible_comp_count integer NOT NULL CHECK (eligible_comp_count >= 0),
  eligible_counts_by_window jsonb NOT NULL CHECK (jsonb_typeof(eligible_counts_by_window) = 'object'),
  sold_at_min date,
  sold_at_max date,
  collected_at_max timestamptz,
  ingested_at_max timestamptz,
  median numeric(14,4),
  median_usd_2dp numeric(12,2),
  q1 numeric(14,4),
  q3 numeric(14,4),
  iqr numeric(14,4),
  mad numeric(14,4),
  distinct_transaction_days integer,
  membership_fingerprint text NOT NULL CHECK (membership_fingerprint ~ '^[0-9a-f]{64}$'),
  evidence_fingerprint text NOT NULL CHECK (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
  content_fingerprint text NOT NULL CHECK (content_fingerprint ~ '^[0-9a-f]{64}$'),
  exclusion_counts jsonb NOT NULL CHECK (jsonb_typeof(exclusion_counts) = 'object'),
  input_fingerprints jsonb NOT NULL CHECK (jsonb_typeof(input_fingerprints) = 'object'),
  rows_offered integer NOT NULL CHECK (rows_offered >= 0),
  generated_at timestamptz NOT NULL,
  source_commit text NOT NULL CHECK (source_commit ~ '^[0-9a-f]{7,40}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  -- Idempotent retry key: a second row for the same key is rejected, never overwritten.
  UNIQUE (rule_version, canonical_card_id, evaluation_date, information_cutoff),
  CHECK ((status = 'ANCHORED') = (median IS NOT NULL AND selected_window_days IS NOT NULL AND eligible_comp_count >= 10)),
  CHECK (status = 'ANCHORED' OR (median IS NULL AND eligible_comp_count = 0)),
  -- A genuinely prospective row must be generated at/after its information cutoff and may only
  -- reference evidence available by then.
  CHECK (evidence_status = 'RETROSPECTIVE_BACKFILLED_EVIDENCE' OR generated_at >= information_cutoff),
  CHECK (evidence_status = 'RETROSPECTIVE_BACKFILLED_EVIDENCE'
         OR (collected_at_max IS NULL OR collected_at_max <= information_cutoff)),
  CHECK (evidence_status = 'RETROSPECTIVE_BACKFILLED_EVIDENCE'
         OR (ingested_at_max IS NULL OR ingested_at_max <= information_cutoff)),
  CHECK (sold_at_max IS NULL OR sold_at_max <= evaluation_date)
);

CREATE INDEX fv_shadow_anchor_pub_eval_idx
  ON public.fair_value_shadow_anchor_publications_v1 (evaluation_date, canonical_card_id);

CREATE TABLE public.fair_value_shadow_anchor_members_v1 (
  publication_id uuid NOT NULL REFERENCES public.fair_value_shadow_anchor_publications_v1(publication_id) ON DELETE RESTRICT,
  provider_card_id bigint NOT NULL,
  provider_listing_id bigint NOT NULL,
  price numeric(12,2) NOT NULL CHECK (price > 0),
  sold_at date NOT NULL,
  collected_at timestamptz NOT NULL,
  ingested_at timestamptz,
  title_sha256 text NOT NULL CHECK (title_sha256 ~ '^[0-9a-f]{64}$'),
  grader_at_first_seen text,
  graded_at_first_seen boolean,
  PRIMARY KEY (publication_id, provider_card_id, provider_listing_id),
  -- Membership must point at real, append-only evidence rows.
  FOREIGN KEY (provider_listing_id, provider_card_id)
    REFERENCES public.pkmnprices_ebay_sold_evidence_v1 (provider_listing_id, provider_card_id) ON DELETE RESTRICT
);

-- Information-availability gate enforced at the database as well: no member may have been
-- collected (or provider-ingested) after the publication's cutoff unless it is a retrospective row.
CREATE FUNCTION public.fv_shadow_member_availability_gate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pub record;
BEGIN
  SELECT information_cutoff, evaluation_date, evidence_status INTO pub
    FROM public.fair_value_shadow_anchor_publications_v1 WHERE publication_id = NEW.publication_id;
  IF pub.evidence_status <> 'RETROSPECTIVE_BACKFILLED_EVIDENCE' THEN
    IF NEW.collected_at > pub.information_cutoff
       OR (NEW.ingested_at IS NOT NULL AND NEW.ingested_at > pub.information_cutoff)
       OR NEW.sold_at > pub.evaluation_date THEN
      RAISE EXCEPTION 'member evidence was not available at the publication information cutoff'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER fv_shadow_member_availability_gate BEFORE INSERT
  ON public.fair_value_shadow_anchor_members_v1 FOR EACH ROW EXECUTE FUNCTION public.fv_shadow_member_availability_gate();

-- ---------------------------------------------------------------- B. component observations
-- Deliberately NO foreign key from A to B and no price column in A.
CREATE TABLE public.fair_value_shadow_component_observations_v1 (
  publication_id uuid PRIMARY KEY REFERENCES public.fair_value_shadow_anchor_publications_v1(publication_id) ON DELETE RESTRICT,
  schema_version text NOT NULL,
  content_fingerprint text NOT NULL CHECK (content_fingerprint ~ '^[0-9a-f]{64}$'),
  canonical_card_id uuid NOT NULL,
  evaluation_date date NOT NULL,
  evidence_status text NOT NULL,
  enrichment_policy text NOT NULL CHECK (enrichment_policy = 'FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY'),
  shadow_status text NOT NULL CHECK (shadow_status IN ('COMPLETE','ANCHOR_INSUFFICIENT','MARKET_MISSING','STRUCTURAL_MISSING')),
  current_tcgplayer_market_price_usd numeric(12,2),
  market_price_date date,
  explicit_nm_sold_clearing_anchor_v1_usd numeric(14,4),
  structural_baseline_usd numeric(14,4),
  structural_baseline_source text,
  pull_probability numeric,
  negative_ln_pull_probability numeric,
  scarcity_source text,
  collector_appeal numeric,
  collector_appeal_source text,
  comp_count integer,
  selected_window_days integer,
  iqr numeric(14,4),
  mad numeric(14,4),
  evidence_age_days_since_newest_sale integer,
  divergence_sold_anchor_minus_current_market jsonb NOT NULL,
  divergence_structural_minus_current_market jsonb NOT NULL,
  divergence_sold_anchor_minus_structural jsonb NOT NULL,
  blended_value numeric CHECK (blended_value IS NULL),   -- no blending in this phase
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- ---------------------------------------------------------------- C. evaluation outcomes
CREATE TABLE public.fair_value_shadow_evaluation_outcomes_v1 (
  publication_id uuid NOT NULL REFERENCES public.fair_value_shadow_anchor_publications_v1(publication_id) ON DELETE RESTRICT,
  horizon_days integer NOT NULL CHECK (horizon_days IN (0,1,7,30)),
  schema_version text NOT NULL,
  content_fingerprint text NOT NULL CHECK (content_fingerprint ~ '^[0-9a-f]{64}$'),
  comparison_date date NOT NULL,
  comparison_market_price_usd numeric(12,2),
  comparison_price_source text,
  baseline_market_price_usd numeric(12,2),
  anchor_usd_at_publication numeric(14,4),
  abs_error_usd numeric(14,4),
  signed_pct_error numeric(14,4),
  abs_pct_error numeric(14,4),
  forward_market_change_pct numeric(14,4),
  divergence_at_publication numeric(14,6),
  outcome_status text NOT NULL CHECK (outcome_status IN ('COMPLETE','ANCHOR_INSUFFICIENT','MARKET_MISSING')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (publication_id, horizon_days)
);

-- An outcome must belong to its publication's date + horizon and carry the published anchor
-- unchanged; it can therefore never become a back door for editing the estimate.
CREATE FUNCTION public.fv_shadow_outcome_consistency_gate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pub record;
BEGIN
  SELECT evaluation_date, median INTO pub
    FROM public.fair_value_shadow_anchor_publications_v1 WHERE publication_id = NEW.publication_id;
  IF NEW.comparison_date <> pub.evaluation_date + NEW.horizon_days THEN
    RAISE EXCEPTION 'comparison_date must equal evaluation_date + horizon_days' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.comparison_date > current_date THEN
    RAISE EXCEPTION 'comparison_date is in the future' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.anchor_usd_at_publication IS DISTINCT FROM pub.median THEN
    RAISE EXCEPTION 'outcome anchor must equal the published anchor' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER fv_shadow_outcome_consistency_gate BEFORE INSERT
  ON public.fair_value_shadow_evaluation_outcomes_v1 FOR EACH ROW EXECUTE FUNCTION public.fv_shadow_outcome_consistency_gate();

-- ---------------------------------------------------------------- append-only enforcement + privileges
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'fair_value_shadow_anchor_publications_v1', 'fair_value_shadow_anchor_members_v1',
    'fair_value_shadow_component_observations_v1', 'fair_value_shadow_evaluation_outcomes_v1']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.fv_shadow_forbid_mutation()',
                   t || '_no_mutation', t);
    EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION public.fv_shadow_forbid_mutation()',
                   t || '_no_truncate', t);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, anon, authenticated, service_role', t);
    EXECUTE format('GRANT SELECT, INSERT ON public.%I TO service_role', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------- atomic publication RPC
-- Header + membership commit together; member failure rolls back the header.
CREATE OR REPLACE FUNCTION public.publish_fair_value_shadow_anchor_v1(
  p_publication jsonb,
  p_members jsonb
) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_existing record;
  v_publication_id uuid;
  v_payload jsonb;
BEGIN
  IF jsonb_typeof(p_publication) <> 'object' OR jsonb_typeof(p_members) <> 'array' THEN
    RAISE EXCEPTION 'invalid fair-value shadow publication payload' USING ERRCODE = '22023';
  END IF;
  IF p_publication ? 'members' THEN
    RAISE EXCEPTION 'members must be supplied separately' USING ERRCODE = '22023';
  END IF;

  v_publication_id := (p_publication->>'publication_id')::uuid;

  SELECT publication_id, content_fingerprint
    INTO v_existing
    FROM public.fair_value_shadow_anchor_publications_v1
   WHERE rule_version = p_publication->>'rule_version'
     AND canonical_card_id = (p_publication->>'canonical_card_id')::uuid
     AND evaluation_date = (p_publication->>'evaluation_date')::date
     AND information_cutoff = (p_publication->>'information_cutoff')::timestamptz
   FOR SHARE;

  IF FOUND THEN
    IF v_existing.content_fingerprint = p_publication->>'content_fingerprint'
       AND v_existing.publication_id = v_publication_id THEN
      RETURN 'IDEMPOTENT_NOOP';
    END IF;
    RAISE EXCEPTION 'SHADOW_PUBLICATION_CONFLICT'
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;

  v_payload := p_publication || jsonb_build_object('created_at', clock_timestamp());

  INSERT INTO public.fair_value_shadow_anchor_publications_v1
  SELECT (jsonb_populate_record(
    NULL::public.fair_value_shadow_anchor_publications_v1,
    v_payload
  )).*;

  INSERT INTO public.fair_value_shadow_anchor_members_v1
  SELECT (jsonb_populate_record(
    NULL::public.fair_value_shadow_anchor_members_v1,
    jsonb_build_object('publication_id', v_publication_id) || member
  )).*
  FROM jsonb_array_elements(p_members) AS member;

  RETURN 'INSERTED';
END;
$$;

REVOKE ALL ON FUNCTION public.fv_shadow_forbid_mutation() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.fv_shadow_member_availability_gate() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.fv_shadow_outcome_consistency_gate() FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.publish_fair_value_shadow_anchor_v1(jsonb, jsonb)
  FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.publish_fair_value_shadow_anchor_v1(jsonb, jsonb) TO service_role;

COMMENT ON TABLE public.fair_value_shadow_anchor_publications_v1 IS
  'Research-only append-only anchor publications for EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1. Not a price authority.';

COMMIT;
