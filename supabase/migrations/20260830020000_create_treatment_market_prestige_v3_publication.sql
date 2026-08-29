-- Treatment Market Prestige V3 candidate/publication infrastructure.
-- Additive and dark by default: no run is approved by this migration.
BEGIN;

CREATE TABLE public.treatment_market_prestige_publication_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version text NOT NULL,
    methodology_version text NOT NULL,
    score_transform_version text NOT NULL,
    baseline_version text NOT NULL,
    market_reference_date date NOT NULL,
    built_at timestamptz NOT NULL,
    approval_status text NOT NULL DEFAULT 'candidate'
        CHECK (approval_status IN ('candidate','approved','rejected','revoked','failed')),
    approved_at timestamptz,
    approval_actor text,
    approval_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    cohort_source_hash text NOT NULL CHECK (cohort_source_hash ~ '^[0-9a-f]{64}$'),
    taxonomy_hash text NOT NULL CHECK (taxonomy_hash ~ '^[0-9a-f]{64}$'),
    comparison_universe_hash text NOT NULL CHECK (comparison_universe_hash ~ '^[0-9a-f]{64}$'),
    production_contract_hash text NOT NULL CHECK (production_contract_hash ~ '^[0-9a-f]{64}$'),
    canonical_mapping_hash text NOT NULL CHECK (canonical_mapping_hash ~ '^[0-9a-f]{64}$'),
    candidate_validation_status text NOT NULL
        CHECK (candidate_validation_status IN ('pending','passed','failed')),
    expected_treatment_count integer NOT NULL CHECK (expected_treatment_count >= 0),
    expected_universe_count integer NOT NULL CHECK (expected_universe_count >= 0),
    expected_available_treatment_count integer NOT NULL CHECK (expected_available_treatment_count >= 0),
    expected_available_universe_count integer NOT NULL CHECK (expected_available_universe_count >= 0),
    temporal_validation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    failure_reason text,
    source_study_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CHECK (approval_status <> 'approved' OR approved_at IS NOT NULL),
    CHECK (approved_at IS NULL OR approval_status IN ('approved','revoked')),
    UNIQUE (source_study_id, production_contract_hash)
);

CREATE TABLE public.treatment_market_prestige_publication_universes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_run_id uuid NOT NULL REFERENCES public.treatment_market_prestige_publication_runs(id) ON DELETE RESTRICT,
    universe_key text NOT NULL,
    era_id uuid NOT NULL REFERENCES public.eras(id) ON DELETE RESTRICT,
    era_name text NOT NULL,
    comparison_universe_type text NOT NULL CHECK (comparison_universe_type IN ('ERA_RELATIVE','TREATMENT_REGIME_RELATIVE')),
    treatment_regime_id text,
    treatment_count integer NOT NULL CHECK (treatment_count >= 0),
    eligible_treatment_count integer NOT NULL CHECK (eligible_treatment_count >= 0),
    final_availability_status text NOT NULL,
    failure_reason text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CHECK ((comparison_universe_type = 'ERA_RELATIVE' AND treatment_regime_id IS NULL)
        OR (comparison_universe_type = 'TREATMENT_REGIME_RELATIVE' AND treatment_regime_id IS NOT NULL)),
    CHECK (eligible_treatment_count <= treatment_count),
    UNIQUE (publication_run_id, universe_key)
);

CREATE TABLE public.treatment_market_prestige_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_run_id uuid NOT NULL REFERENCES public.treatment_market_prestige_publication_runs(id) ON DELETE RESTRICT,
    universe_key text NOT NULL,
    era_id uuid NOT NULL REFERENCES public.eras(id) ON DELETE RESTRICT,
    era_name text NOT NULL,
    comparison_universe_type text NOT NULL CHECK (comparison_universe_type IN ('ERA_RELATIVE','TREATMENT_REGIME_RELATIVE')),
    treatment_regime_id text,
    treatment_key text NOT NULL,
    treatment_label text NOT NULL,
    treatment_effect numeric(10,6) NOT NULL,
    magnitude_score numeric(6,4),
    score_interval_low numeric(6,4),
    score_interval_high numeric(6,4),
    confidence_status text NOT NULL,
    evidence_status text NOT NULL,
    ordering_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    card_count integer NOT NULL CHECK (card_count >= 0),
    species_count integer NOT NULL CHECK (species_count >= 0),
    set_count integer NOT NULL CHECK (set_count >= 0),
    temporal_checkpoint_count integer NOT NULL CHECK (temporal_checkpoint_count >= 0),
    temporal_span_days integer NOT NULL CHECK (temporal_span_days >= 0),
    between_set_variance numeric(14,8),
    heterogeneity_status text NOT NULL,
    temporal_status text NOT NULL,
    final_availability_status text NOT NULL,
    market_reference_date date NOT NULL,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CHECK ((comparison_universe_type = 'ERA_RELATIVE' AND treatment_regime_id IS NULL)
        OR (comparison_universe_type = 'TREATMENT_REGIME_RELATIVE' AND treatment_regime_id IS NOT NULL)),
    CHECK ((final_availability_status = 'AVAILABLE'
            AND magnitude_score IS NOT NULL AND score_interval_low IS NOT NULL AND score_interval_high IS NOT NULL)
        OR (final_availability_status <> 'AVAILABLE'
            AND magnitude_score IS NULL AND score_interval_low IS NULL AND score_interval_high IS NULL)),
    CHECK (magnitude_score IS NULL OR magnitude_score BETWEEN 1 AND 9),
    CHECK (score_interval_low IS NULL OR score_interval_low BETWEEN 1 AND 9),
    CHECK (score_interval_high IS NULL OR score_interval_high BETWEEN 1 AND 9),
    CHECK (score_interval_low IS NULL OR score_interval_low <= score_interval_high),
    UNIQUE (publication_run_id, universe_key, treatment_key),
    FOREIGN KEY (publication_run_id, universe_key)
        REFERENCES public.treatment_market_prestige_publication_universes(publication_run_id, universe_key)
        ON DELETE RESTRICT
);

CREATE TABLE public.treatment_market_prestige_regime_sets (
    publication_run_id uuid NOT NULL REFERENCES public.treatment_market_prestige_publication_runs(id) ON DELETE RESTRICT,
    universe_key text NOT NULL,
    treatment_regime_id text NOT NULL,
    set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (publication_run_id, universe_key, set_id),
    FOREIGN KEY (publication_run_id, universe_key)
        REFERENCES public.treatment_market_prestige_publication_universes(publication_run_id, universe_key)
        ON DELETE RESTRICT
);

CREATE INDEX treatment_market_prestige_universes_run_idx
    ON public.treatment_market_prestige_publication_universes (publication_run_id);
CREATE INDEX treatment_market_prestige_results_run_idx
    ON public.treatment_market_prestige_results (publication_run_id);
CREATE INDEX treatment_market_prestige_results_resolver_idx
    ON public.treatment_market_prestige_results (era_id, treatment_key, universe_key, final_availability_status, publication_run_id);
CREATE INDEX treatment_market_prestige_regime_sets_set_idx
    ON public.treatment_market_prestige_regime_sets (set_id, publication_run_id, universe_key);
CREATE INDEX treatment_market_prestige_runs_approved_latest_idx
    ON public.treatment_market_prestige_publication_runs
    (market_reference_date DESC, approved_at DESC, id DESC)
    WHERE approval_status = 'approved';

ALTER TABLE public.treatment_market_prestige_publication_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.treatment_market_prestige_publication_universes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.treatment_market_prestige_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.treatment_market_prestige_regime_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.treatment_market_prestige_publication_runs,
    public.treatment_market_prestige_publication_universes,
    public.treatment_market_prestige_results,
    public.treatment_market_prestige_regime_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.treatment_market_prestige_publication_runs,
    public.treatment_market_prestige_publication_universes,
    public.treatment_market_prestige_results,
    public.treatment_market_prestige_regime_sets TO service_role;

CREATE OR REPLACE FUNCTION public.stage_treatment_market_prestige_v3_candidate(
    p_run jsonb, p_universes jsonb, p_results jsonb, p_regime_sets jsonb DEFAULT '[]'::jsonb
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_run_id uuid; v_universe_count integer; v_result_count integer; v_available_results integer;
BEGIN
    IF jsonb_typeof(p_universes) <> 'array' OR jsonb_typeof(p_results) <> 'array'
       OR jsonb_typeof(p_regime_sets) <> 'array' THEN RAISE EXCEPTION 'candidate collections must be arrays'; END IF;
    IF p_run->>'approval_status' IS DISTINCT FROM 'candidate' THEN RAISE EXCEPTION 'staging only accepts candidate status'; END IF;
    IF COALESCE((p_run->>'approved')::boolean, false) THEN RAISE EXCEPTION 'staging cannot approve a run'; END IF;
    v_universe_count := jsonb_array_length(p_universes); v_result_count := jsonb_array_length(p_results);
    SELECT count(*) INTO v_available_results FROM jsonb_array_elements(p_results) x WHERE x->>'final_availability_status' = 'AVAILABLE';
    IF v_universe_count <> (p_run->>'expected_universe_count')::integer
       OR v_result_count <> (p_run->>'expected_treatment_count')::integer
       OR v_available_results <> (p_run->>'expected_available_treatment_count')::integer THEN
        RAISE EXCEPTION 'candidate payload counts do not reconcile';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_results) x
               WHERE (x->>'final_availability_status' = 'AVAILABLE') IS DISTINCT FROM ((x->>'magnitude_score') IS NOT NULL)) THEN
        RAISE EXCEPTION 'available/null-score contract violated';
    END IF;
    INSERT INTO public.treatment_market_prestige_publication_runs (
        model_version, methodology_version, score_transform_version, baseline_version,
        market_reference_date, built_at, approval_status, cohort_source_hash, taxonomy_hash,
        comparison_universe_hash, production_contract_hash, canonical_mapping_hash,
        candidate_validation_status, expected_treatment_count, expected_universe_count,
        expected_available_treatment_count, expected_available_universe_count,
        temporal_validation_metadata, validation_metadata, failure_reason, source_study_id
    ) VALUES (
        p_run->>'model_version', p_run->>'methodology_version', p_run->>'score_transform_version', p_run->>'baseline_version',
        (p_run->>'market_reference_date')::date, (p_run->>'built_at')::timestamptz, 'candidate',
        p_run->>'cohort_source_hash', p_run->>'taxonomy_hash', p_run->>'comparison_universe_hash',
        p_run->>'production_contract_hash', p_run->>'canonical_mapping_hash', p_run->>'candidate_validation_status',
        (p_run->>'expected_treatment_count')::integer, (p_run->>'expected_universe_count')::integer,
        (p_run->>'expected_available_treatment_count')::integer, (p_run->>'expected_available_universe_count')::integer,
        COALESCE(p_run->'temporal_validation_metadata','{}'::jsonb), COALESCE(p_run->'validation_metadata','{}'::jsonb),
        NULLIF(p_run->>'failure_reason',''), p_run->>'source_study_id'
    ) RETURNING id INTO v_run_id;
    INSERT INTO public.treatment_market_prestige_publication_universes (
        publication_run_id, universe_key, era_id, era_name, comparison_universe_type,
        treatment_regime_id, treatment_count, eligible_treatment_count, final_availability_status, failure_reason)
    SELECT v_run_id, x->>'universe_key', (x->>'era_id')::uuid, x->>'era_name', x->>'comparison_universe_type',
        NULLIF(x->>'treatment_regime_id',''), (x->>'treatment_count')::integer,
        (x->>'eligible_treatment_count')::integer, x->>'final_availability_status', NULLIF(x->>'failure_reason','')
    FROM jsonb_array_elements(p_universes) x;
    INSERT INTO public.treatment_market_prestige_results (
        publication_run_id, universe_key, era_id, era_name, comparison_universe_type, treatment_regime_id,
        treatment_key, treatment_label, treatment_effect, magnitude_score, score_interval_low, score_interval_high,
        confidence_status, evidence_status, ordering_metadata, card_count, species_count, set_count,
        temporal_checkpoint_count, temporal_span_days, between_set_variance, heterogeneity_status, temporal_status,
        final_availability_status, market_reference_date, provenance)
    SELECT v_run_id, x->>'universe_key', (x->>'era_id')::uuid, x->>'era_name', x->>'comparison_universe_type', NULLIF(x->>'treatment_regime_id',''),
        x->>'treatment_key', x->>'treatment_label', (x->>'treatment_effect')::numeric, NULLIF(x->>'magnitude_score','')::numeric,
        NULLIF(x->>'score_interval_low','')::numeric, NULLIF(x->>'score_interval_high','')::numeric,
        x->>'confidence_status', x->>'evidence_status', COALESCE(x->'ordering_metadata','{}'::jsonb),
        (x->>'card_count')::integer, (x->>'species_count')::integer, (x->>'set_count')::integer,
        (x->>'temporal_checkpoint_count')::integer, (x->>'temporal_span_days')::integer,
        NULLIF(x->>'between_set_variance','')::numeric, x->>'heterogeneity_status', x->>'temporal_status',
        x->>'final_availability_status', (x->>'market_reference_date')::date, COALESCE(x->'provenance','{}'::jsonb)
    FROM jsonb_array_elements(p_results) x;
    INSERT INTO public.treatment_market_prestige_regime_sets (publication_run_id, universe_key, treatment_regime_id, set_id)
    SELECT v_run_id, x->>'universe_key', x->>'treatment_regime_id', (x->>'set_id')::uuid FROM jsonb_array_elements(p_regime_sets) x;
    IF (SELECT count(*) FROM public.treatment_market_prestige_publication_universes WHERE publication_run_id=v_run_id) <> v_universe_count
       OR (SELECT count(*) FROM public.treatment_market_prestige_results WHERE publication_run_id=v_run_id) <> v_result_count THEN
        RAISE EXCEPTION 'persisted candidate is incomplete';
    END IF;
    RETURN v_run_id;
END; $$;

CREATE OR REPLACE FUNCTION public.approve_treatment_market_prestige_v3_candidate(
    p_run_id uuid, p_production_contract_hash text, p_approval_actor text, p_approval_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE r public.treatment_market_prestige_publication_runs%ROWTYPE; v_available_universes integer; v_available_results integer;
BEGIN
    SELECT * INTO r FROM public.treatment_market_prestige_publication_runs WHERE id=p_run_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'candidate run not found'; END IF;
    IF r.approval_status <> 'candidate' OR r.candidate_validation_status <> 'passed' THEN RAISE EXCEPTION 'candidate is not approvable'; END IF;
    IF r.production_contract_hash IS DISTINCT FROM p_production_contract_hash THEN RAISE EXCEPTION 'production contract mismatch'; END IF;
    IF (SELECT count(*) FROM public.treatment_market_prestige_results WHERE publication_run_id=p_run_id) <> r.expected_treatment_count
       OR (SELECT count(*) FROM public.treatment_market_prestige_publication_universes WHERE publication_run_id=p_run_id) <> r.expected_universe_count THEN
        RAISE EXCEPTION 'candidate row counts are incomplete';
    END IF;
    SELECT count(*) INTO v_available_universes FROM public.treatment_market_prestige_publication_universes WHERE publication_run_id=p_run_id AND final_availability_status='AVAILABLE';
    SELECT count(*) INTO v_available_results FROM public.treatment_market_prestige_results WHERE publication_run_id=p_run_id AND final_availability_status='AVAILABLE';
    IF v_available_universes <> r.expected_available_universe_count OR v_available_results <> r.expected_available_treatment_count THEN RAISE EXCEPTION 'candidate availability counts changed'; END IF;
    IF EXISTS (SELECT 1 FROM public.treatment_market_prestige_results x JOIN public.treatment_market_prestige_publication_universes u ON u.publication_run_id=x.publication_run_id AND u.universe_key=x.universe_key
               WHERE x.publication_run_id=p_run_id AND x.final_availability_status='AVAILABLE' AND u.final_availability_status<>'AVAILABLE') THEN RAISE EXCEPTION 'treatment bypasses failed universe'; END IF;
    UPDATE public.treatment_market_prestige_publication_runs SET approval_status='approved',approved_at=timezone('utc',now()),approval_actor=p_approval_actor,approval_metadata=COALESCE(p_approval_metadata,'{}'::jsonb) WHERE id=p_run_id;
    RETURN p_run_id;
END; $$;

REVOKE ALL ON FUNCTION public.stage_treatment_market_prestige_v3_candidate(jsonb,jsonb,jsonb,jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.approve_treatment_market_prestige_v3_candidate(uuid,text,text,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.stage_treatment_market_prestige_v3_candidate(jsonb,jsonb,jsonb,jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.approve_treatment_market_prestige_v3_candidate(uuid,text,text,jsonb) TO service_role;

CREATE VIEW public.latest_approved_treatment_market_prestige WITH (security_invoker=true) AS
WITH latest_run AS (
    SELECT r.* FROM public.treatment_market_prestige_publication_runs r
    WHERE r.approval_status='approved'
      AND r.production_contract_hash='fd7cdfb3e8dcba9d18e18390e482542be6d68cd11927ec3998e2412e4e2b0862'
      AND r.baseline_version='6c1ae19217ee8758057bf251aa60d26a397f66319729f1abbff51e21424cdbf4'
      AND current_date-r.market_reference_date <= 45
      AND current_date-r.approved_at::date <= 62
    ORDER BY r.market_reference_date DESC,r.approved_at DESC,r.id DESC LIMIT 1
)
SELECT x.*,u.final_availability_status AS universe_availability_status,u.treatment_count AS comparison_universe_size,
       rs.set_id,r.model_version,r.methodology_version,r.score_transform_version,r.baseline_version,r.approved_at,r.source_study_id
FROM latest_run r
JOIN public.treatment_market_prestige_publication_universes u ON u.publication_run_id=r.id
JOIN public.treatment_market_prestige_results x ON x.publication_run_id=r.id AND x.universe_key=u.universe_key
LEFT JOIN public.treatment_market_prestige_regime_sets rs ON rs.publication_run_id=r.id AND rs.universe_key=u.universe_key;
REVOKE ALL ON public.latest_approved_treatment_market_prestige FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.latest_approved_treatment_market_prestige TO service_role;

COMMIT;
