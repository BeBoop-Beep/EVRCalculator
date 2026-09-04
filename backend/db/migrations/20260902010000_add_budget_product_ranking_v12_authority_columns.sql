-- Gate F (budget ranking V12 authority wiring): additive, nullable V12
-- authority columns on the existing budget-ranking snapshot/row tables.
--
-- CODE-ONLY / EXPLICIT-OPT-IN. This migration does NOT change canonical
-- authority: `budget_product_ranking_rows.overall_rip_v10_score` and every
-- existing V10 column, constraint and default remain exactly as they were.
-- No row is backfilled, no column is reinterpreted, no existing NOT NULL /
-- CHECK constraint is touched. A pre-existing snapshot/row with every new
-- column NULL reads back unchanged.
--
-- See docs/research/OVERALL_RIP_V12_CANONICAL_PROMOTION_IMPLEMENTATION.md,
-- "Gate F completion" section, for the authority rule and orchestration this
-- schema supports.
--
-- STATUS: this migration file is CREATED ONLY and has NOT been applied to
-- any environment (including production). It must not be applied as part of
-- this task.

BEGIN;

ALTER TABLE public.budget_product_ranking_snapshots
    ADD COLUMN IF NOT EXISTS overall_rip_v12_version TEXT,
    ADD COLUMN IF NOT EXISTS chase_accessibility_version TEXT,
    ADD COLUMN IF NOT EXISTS chase_accessibility_transform_version TEXT,
    -- Whether this snapshot's rows were ranked under V12 sort authority
    -- (TRUE) or the default/canonical V10 authority (FALSE/NULL). NEVER
    -- defaults to TRUE - a snapshot with this column NULL or FALSE is a V10
    -- snapshot exactly as before this migration.
    ADD COLUMN IF NOT EXISTS ranked_under_v12_authority BOOLEAN;

COMMENT ON COLUMN public.budget_product_ranking_snapshots.ranked_under_v12_authority IS
    'Explicit opt-in flag only. NULL/FALSE = ranked under the default/canonical V10 authority (unchanged historical meaning). TRUE = this snapshot was published under the explicit, non-default V12 budget-ranking authority (Gate F). Never implicitly TRUE.';

ALTER TABLE public.budget_product_ranking_rows
    -- Overall RIP V12 for this row's strategy, additive/shadow only - never
    -- consumed by budget_rank/budget_tier/financial_only_rank above, which
    -- remain exactly the V10-authority values they always were.
    ADD COLUMN IF NOT EXISTS overall_rip_v12_score NUMERIC,
    ADD COLUMN IF NOT EXISTS overall_rip_v12_rankable BOOLEAN,
    ADD COLUMN IF NOT EXISTS overall_rip_v12_status TEXT,
    -- Set-level raw Chase Accessibility (A_raw) used for this row's strategy.
    -- Identity/audit reference only - the authoritative published value is
    -- `pokemon_set_chase_accessibility_snapshot_latest`; this is NOT a second
    -- copy of record, only the exact value consumed by this specific row's
    -- V12 computation, for reproducibility of a historical publication.
    ADD COLUMN IF NOT EXISTS chase_accessibility_raw NUMERIC,
    -- Under EXPLICIT V12 sort authority only: this strategy's rank/cohort
    -- size by Overall RIP V12. NULL under the default V10 authority.
    ADD COLUMN IF NOT EXISTS budget_rank_v12 INTEGER CHECK (budget_rank_v12 IS NULL OR budget_rank_v12 >= 1),
    ADD COLUMN IF NOT EXISTS budget_cohort_size_v12 INTEGER CHECK (budget_cohort_size_v12 IS NULL OR budget_cohort_size_v12 >= 1);

COMMENT ON COLUMN public.budget_product_ranking_rows.overall_rip_v12_score IS
    'Additive/shadow Overall RIP V12 score for this budget strategy. Never read by the V10 budget_rank/budget_tier/financial_only_rank columns. NULL when V12 was not computed or was unavailable for this row (never a 0/fallback).';
COMMENT ON COLUMN public.budget_product_ranking_rows.chase_accessibility_raw IS
    'The set-level raw Chase Accessibility (A_raw) value actually used for this row''s Overall RIP V12 computation, resolved via a single cohort-wide batch read at build time - never recomputed per row.';

COMMIT;
