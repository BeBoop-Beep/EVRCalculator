-- Canonical simulation business date.
--
-- New unattended runs carry the promoted market date explicitly. Existing rows
-- remain deterministic: when market_date IS NULL the canonical view retains its
-- original timestamp-derived snapshot_date. No historical row is rewritten.
--
-- WHY THE DATE MUST LIVE IN THE PARTITION KEY
-- ------------------------------------------
-- An earlier draft of this migration renamed the canonical views aside and
-- wrapped them with `COALESCE(r.market_date, l.snapshot_date) AS snapshot_date`.
-- That relabels the date only AFTER the legacy UTC-date partitioning has already
-- chosen one row per UTC day, which is wrong in both directions:
--
--   * Two runs straddling UTC midnight (23:59Z and 00:01Z) that both carry the
--     promoted market_date 2026-08-31 survive as TWO rows, then get relabelled
--     to the same date - two "daily latest" rows for one business day.
--   * Two runs sharing one UTC day but carrying DIFFERENT promoted dates are
--     collapsed to one row before the wrapper can distinguish them.
--
-- The effective business date must therefore participate in the daily identity
-- itself. This migration rebuilds the canonical view in place with
-- COALESCE(cr.market_date, cr.created_at::date) used in BOTH the projected
-- snapshot_date and the row_number() partition key. Everything else - column
-- names, order, types, joins, filters and calculations - is byte-for-byte the
-- production definition.
ALTER TABLE public.calculation_runs
    ADD COLUMN IF NOT EXISTS market_date date;

COMMENT ON COLUMN public.calculation_runs.market_date IS
    'Explicit promoted Pokemon market date for this simulation; NULL on legacy runs, whose historical date remains the pre-migration view result.';

CREATE INDEX IF NOT EXISTS idx_calculation_runs_market_date_target
    ON public.calculation_runs (market_date DESC, target_type, target_id)
    WHERE market_date IS NOT NULL;

-- CREATE OR REPLACE (never DROP) so that:
--   * the existing ACL is preserved verbatim - migration 075 revoked anon and
--     authenticated from this view and that revocation must survive;
--   * public.calculation_history_trend, which selects FROM this view, is not
--     dropped, recreated, or re-granted. Its P95 carry-forward definition is
--     correct as written and inherits the corrected day identity automatically.
-- The column list, order and types are unchanged, which is what OR REPLACE
-- requires; COALESCE(date, date) is still date.
CREATE OR REPLACE VIEW public.calculation_history_daily_latest
WITH (security_invoker = true) AS
 WITH ranked AS (
         SELECT cr_1.id AS calculation_run_id,
            cr_1.target_type,
            cr_1.target_id,
            cr_1.calculation_config_id,
            cr_1.valuation_method,
            cr_1.notes,
            cr_1.engine_version,
            cr_1.created_at,
            COALESCE(cr_1.market_date, (cr_1.created_at)::date) AS snapshot_date,
            row_number() OVER (
                PARTITION BY cr_1.target_type,
                             cr_1.target_id,
                             COALESCE(cr_1.market_date, (cr_1.created_at)::date)
                ORDER BY cr_1.created_at DESC) AS rn
           FROM calculation_runs cr_1
          WHERE (cr_1.valuation_method = ANY (ARRAY['expected_value'::text, 'combined'::text]))
        )
 SELECT r.calculation_run_id,
    r.target_type,
    r.target_id,
    r.calculation_config_id,
    r.valuation_method,
    r.notes,
    r.engine_version,
    r.created_at AS run_created_at,
    r.snapshot_date,
        CASE
            WHEN (srs.pack_cost > (0)::numeric) THEN (srs.mean_value / srs.pack_cost)
            ELSE NULL::numeric
        END AS simulated_mean_pack_value_vs_pack_cost,
        CASE
            WHEN (srs.pack_cost > (0)::numeric) THEN (srs.median_value / srs.pack_cost)
            ELSE NULL::numeric
        END AS simulated_median_pack_value_vs_pack_cost,
    cr.calculated_expected_pack_value_vs_pack_cost,
    cr.simulated_mean_etb_value_vs_etb_cost,
    cr.simulated_median_etb_value_vs_etb_cost,
    cr.calculated_expected_etb_value_vs_etb_cost,
    cr.simulated_mean_booster_box_value_vs_booster_box_cost,
    cr.simulated_median_booster_box_value_vs_booster_box_cost,
    cr.calculated_expected_booster_box_value_vs_booster_box_cost,
    sdm.p95_value_to_cost_ratio
   FROM (((ranked r
     JOIN calculation_runs cr ON ((cr.id = r.calculation_run_id)))
     LEFT JOIN simulation_run_summary srs ON ((srs.calculation_run_id = r.calculation_run_id)))
     LEFT JOIN simulation_derived_metrics sdm ON ((sdm.calculation_run_id = r.calculation_run_id)))
  WHERE (r.rn = 1);

-- No GRANT statements. The pre-existing ACL (postgres, service_role) is the
-- intended access model: these views are security_invoker and anon /
-- authenticated hold no SELECT on public.calculation_runs, so granting them the
-- view would produce a permission error at query time rather than access.
