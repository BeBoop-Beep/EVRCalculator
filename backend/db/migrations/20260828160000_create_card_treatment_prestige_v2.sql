BEGIN;

CREATE TABLE public.pokemon_card_treatment_study_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_version text NOT NULL,
    methodology_version text NOT NULL,
    taxonomy_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('research','passed','approved','rejected')),
    study_as_of_date date NOT NULL,
    price_window_start date NOT NULL,
    price_window_end date NOT NULL,
    source_git_sha text NOT NULL,
    worktree_dirty boolean NOT NULL,
    cohort_fingerprint text NOT NULL CHECK (cohort_fingerprint ~ '^[0-9a-f]{64}$'),
    primary_model_spec jsonb NOT NULL DEFAULT '{}'::jsonb,
    sensitivity_specs jsonb NOT NULL DEFAULT '{}'::jsonb,
    acceptance_gates jsonb NOT NULL DEFAULT '{}'::jsonb,
    bootstrap_seed bigint NOT NULL,
    bootstrap_draws integer NOT NULL CHECK (bootstrap_draws > 0),
    input_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    diagnostics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    approved_at timestamptz,
    CHECK ((status = 'approved') = (approved_at IS NOT NULL))
);

CREATE TABLE public.pokemon_card_treatment_scores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_run_id uuid NOT NULL REFERENCES public.pokemon_card_treatment_study_runs(id) ON DELETE RESTRICT,
    treatment_key text NOT NULL,
    rarity_key text,
    printing_type text,
    special_type text,
    edition text,
    scope_type text NOT NULL CHECK (scope_type IN ('global','era','supertype','era_supertype')),
    era_id uuid REFERENCES public.eras(id) ON DELETE RESTRICT,
    supertype text,
    coefficient_log_price double precision,
    adjusted_premium_pct double precision,
    adjusted_premium_ci_low double precision,
    adjusted_premium_ci_high double precision,
    treatment_score_100 double precision CHECK (treatment_score_100 BETWEEN 0 AND 100),
    treatment_score_10 double precision CHECK (treatment_score_10 BETWEEN 0 AND 10),
    score_ci_low double precision CHECK (score_ci_low BETWEEN 0 AND 10),
    score_ci_high double precision CHECK (score_ci_high BETWEEN 0 AND 10),
    card_count integer NOT NULL DEFAULT 0 CHECK (card_count >= 0),
    variant_count integer NOT NULL DEFAULT 0 CHECK (variant_count >= 0),
    matched_pair_count integer NOT NULL DEFAULT 0 CHECK (matched_pair_count >= 0),
    set_count integer NOT NULL DEFAULT 0 CHECK (set_count >= 0),
    species_count integer NOT NULL DEFAULT 0 CHECK (species_count >= 0),
    pull_probability_coverage double precision CHECK (pull_probability_coverage BETWEEN 0 AND 1),
    common_support_coverage double precision CHECK (common_support_coverage BETWEEN 0 AND 1),
    status text NOT NULL CHECK (status IN ('approved','insufficient_evidence','unstable','scarcity_separation_weak','unmapped')),
    model_source text NOT NULL,
    methodology_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE NULLS NOT DISTINCT (study_run_id,treatment_key,scope_type,era_id,supertype)
);

CREATE INDEX pokemon_card_treatment_scores_lookup_idx ON public.pokemon_card_treatment_scores
    (treatment_key,scope_type,era_id,supertype,status,study_run_id);
CREATE INDEX pokemon_card_treatment_study_runs_approved_idx ON public.pokemon_card_treatment_study_runs
    (approved_at DESC) WHERE status = 'approved';

ALTER TABLE public.pokemon_card_treatment_study_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_card_treatment_scores ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_card_treatment_study_runs, public.pokemon_card_treatment_scores FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.pokemon_card_treatment_study_runs, public.pokemon_card_treatment_scores TO service_role;

CREATE VIEW public.pokemon_card_treatment_scores_latest WITH (security_invoker = true) AS
SELECT s.*, r.study_as_of_date, r.approved_at, r.taxonomy_version
FROM public.pokemon_card_treatment_scores s
JOIN public.pokemon_card_treatment_study_runs r ON r.id = s.study_run_id
WHERE r.status = 'approved' AND s.status = 'approved'
  AND r.id = (SELECT r2.id FROM public.pokemon_card_treatment_study_runs r2
              WHERE r2.status = 'approved' ORDER BY r2.approved_at DESC, r2.id DESC LIMIT 1);
REVOKE ALL ON public.pokemon_card_treatment_scores_latest FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.pokemon_card_treatment_scores_latest TO service_role;

COMMIT;
