-- Migration 017: switch chase/experience tiers to rank-bucket tiering in
-- public.set_pack_score_rankings_latest.
--
-- Scope: SQL-only change to tier assignment logic for:
--   - chase_potential_tier
--   - experience_tier
--
-- Non-goals:
--   - No backend Python changes
--   - No simulation logic changes
--   - No table schema changes
--   - No changes to pack/profit/safety/stability or other existing tiers

DO $$
BEGIN
  IF to_regclass('public.set_pack_score_rankings_latest') IS NULL THEN
    RAISE EXCEPTION 'View public.set_pack_score_rankings_latest does not exist';
  END IF;

  IF to_regclass('public.set_pack_score_rankings_latest__tier_base') IS NULL THEN
    EXECUTE 'ALTER VIEW public.set_pack_score_rankings_latest RENAME TO set_pack_score_rankings_latest__tier_base';
  END IF;
END $$;

CREATE OR REPLACE VIEW public.set_pack_score_rankings_latest AS
SELECT
  b.set_name,
  b.canonical_key,
  b.calculation_run_id,
  b.target_id,
  b.run_at,
  b.ranked_set_count,
  b.pack_score,
  b.relative_pack_score,
  b.pack_rank,
  b.profit_score,
  b.relative_profit_score,
  b.profit_rank,
  b.prob_profit,
  b.prob_profit_rank,
  b.mean_value,
  b.mean_value_to_cost_ratio,
  b.mean_value_to_cost_rank,
  b.median_value,
  b.median_value_to_cost_ratio,
  b.median_value_to_cost_rank,
  b.p95_value,
  b.p95_value_to_cost_ratio,
  b.p95_value_to_cost_rank,
  b.safety_score,
  b.relative_safety_score,
  b.safety_rank,
  b.expected_loss_when_losing,
  b.expected_loss_when_losing_fraction,
  b.expected_loss_when_losing_rank,
  b.median_loss_when_losing,
  b.median_loss_when_losing_fraction,
  b.median_loss_when_losing_rank,
  b.expected_loss_per_pack,
  b.tail_value_p05,
  b.p05_shortfall_to_cost,
  b.p05_shortfall_to_cost_rank,
  b.stability_score,
  b.relative_stability_score,
  b.stability_rank,
  b.coefficient_of_variation,
  b.coefficient_of_variation_rank,
  b.effective_chase_count,
  b.effective_chase_count_rank,
  b.hhi_ev_concentration,
  b.hhi_ev_concentration_rank,
  b.top1_ev_share,
  b.top1_ev_share_rank,
  b.top3_ev_share,
  b.top3_ev_share_rank,
  b.top5_ev_share,
  b.top5_ev_share_rank,
  b.current_market_pack_cost,
  b.score_version,
  b.normalization_mode,
  b.pack_score_is_placeholder,
  b.pack_tier,
  b.profit_tier,
  b.safety_tier,
  b.stability_tier,
  b.prob_profit_tier,
  b.mean_value_to_cost_tier,
  b.median_value_to_cost_tier,
  b.p95_value_to_cost_tier,
  b.expected_loss_when_losing_tier,
  b.median_loss_when_losing_tier,
  b.p05_shortfall_to_cost_tier,
  b.coefficient_of_variation_tier,
  b.effective_chase_count_tier,
  b.hhi_ev_concentration_tier,
  b.top1_ev_share_tier,
  b.top3_ev_share_tier,
  b.top5_ev_share_tier,
  b.chase_potential_score,
  b.relative_chase_potential_score,
  b.chase_potential_rank,
  case
    when b.chase_potential_rank is null then null::text
    when b.chase_potential_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.05)) then 'S'::text
    when b.chase_potential_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.15)) then 'A'::text
    when b.chase_potential_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.30)) then 'B'::text
    when b.chase_potential_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.50)) then 'C'::text
    when b.chase_potential_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.75)) then 'D'::text
    else 'F'::text
  end as chase_potential_tier,
  b.experience_score,
  b.relative_experience_score,
  b.experience_rank,
  case
    when b.experience_rank is null then null::text
    when b.experience_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.05)) then 'S'::text
    when b.experience_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.15)) then 'A'::text
    when b.experience_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.30)) then 'B'::text
    when b.experience_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.50)) then 'C'::text
    when b.experience_rank::numeric <= greatest(1::numeric, ceil(b.ranked_set_count::numeric * 0.75)) then 'D'::text
    else 'F'::text
  end as experience_tier,
  b.derived_metric_version
FROM public.set_pack_score_rankings_latest__tier_base AS b;
