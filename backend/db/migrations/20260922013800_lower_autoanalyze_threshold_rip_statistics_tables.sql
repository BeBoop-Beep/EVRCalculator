-- Lower the autoanalyze threshold on the small, frequently-queried tables that back the
-- deeply-nested RIP-statistics/Rankings view chain (explore_rip_statistics_latest,
-- calculation_history_trend, set_pack_score_rankings_latest, ...).
--
-- ROOT CAUSE (Prompt 5E-B): these tables have 2,000-3,500 rows and grow by small daily
-- appends, well under Postgres's default autovacuum_analyze threshold
-- (10% of rows + 50). pg_stat_user_tables showed last_autoanalyze = NULL for all of them:
-- autoanalyze had NEVER fired since table creation. With no planner statistics, the
-- planner's cardinality estimates for the window-function ranks and multi-way joins in
-- this view chain were unreliable, and PostgREST/API-role requests through these views
-- intermittently exceeded the 8s statement timeout (57014), most recently blocking the
-- 2026-09-21 scheduled daily-opening-publication run at its `calculation_history_trend`
-- read, before Chase Accessibility or Rankings publication were even attempted.
--
-- FIX: pure storage-parameter tuning (ALTER TABLE ... SET). No data, grant, RLS, function
-- or view change. Additive and reversible (RESET restores the default). Chosen over
-- rewriting the view chain, which would be a much larger, riskier change out of scope for
-- this bucket.
ALTER TABLE public.calculation_runs
  SET (autovacuum_analyze_scale_factor = 0.02, autovacuum_analyze_threshold = 50);

ALTER TABLE public.simulation_run_summary
  SET (autovacuum_analyze_scale_factor = 0.02, autovacuum_analyze_threshold = 50);

ALTER TABLE public.simulation_derived_metrics
  SET (autovacuum_analyze_scale_factor = 0.02, autovacuum_analyze_threshold = 50);

ALTER TABLE public.simulation_sealed_product_results
  SET (autovacuum_analyze_scale_factor = 0.02, autovacuum_analyze_threshold = 50);

ALTER TABLE public.pokemon_set_chase_accessibility_snapshot_latest
  SET (autovacuum_analyze_scale_factor = 0.02, autovacuum_analyze_threshold = 20);

-- Analyze once immediately so the new thresholds don't wait for the next autovacuum cycle
-- (autovacuum itself was already re-run manually as part of this bucket's diagnosis; this
-- statement makes the migration self-contained and idempotent on replay).
ANALYZE public.calculation_runs;
ANALYZE public.simulation_run_summary;
ANALYZE public.simulation_derived_metrics;
ANALYZE public.simulation_sealed_product_results;
ANALYZE public.pokemon_set_chase_accessibility_snapshot_latest;
