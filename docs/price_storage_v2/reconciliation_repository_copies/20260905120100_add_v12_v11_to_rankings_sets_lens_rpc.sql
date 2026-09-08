BEGIN;

-- Forward-only follow-up to 20260830010000_tighten_compact_rankings_sets_lens_rpc.sql.
--
-- WHY A NEW MIGRATION, NOT AN EDIT IN PLACE
-- ------------------------------------------
-- 20260830010000 is already applied to the target production database
-- (verified read-only: `get_pokemon_rankings_sets_lens` returned HTTP 200 with
-- a populated payload). Per repo convention, an applied migration is never
-- edited after the fact - this is a forward-only `CREATE OR REPLACE` of the
-- same function, the same pattern every prior public RIP RPC cutover used.
--
-- WHAT THIS ADDS
-- --------------
-- `project_pokemon_rankings_set_target` carried `overallRipV10` /
-- `publicRipContractV10` (plus older V8/V9 lineage) but not the CURRENT
-- canonical `overallRipV12` / `publicRipContractV11` objects the Rankings page
-- and its client-side projection allowlist
-- (`frontend/lib/explore/rankingsClientProjection.mjs`) now need to reach.
-- V10 (and V8/V9) stay for historical availability - nothing is removed. No
-- score/rank recomputation happens here: every field is a straight
-- pass-through of an already-published value, using the same field allowlist
-- shape V10 already uses.

CREATE OR REPLACE FUNCTION public.project_pokemon_rankings_set_target(p_target JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT public.project_rankings_json_keys(p_target, ARRAY[
    'target_type','target_id','set_id','id','name','era','canonical_key',
    'logo_image_url','symbol_image_url','mean_value','median_value','medianValue',
    'modelBreakEvenPrice','model_break_even_price','pack_cost','prob_profit',
    'expected_loss_when_losing','expectedLossWhenLosing','top_chase_name',
    'top_chase_market_value','top_chase_one_in_packs','modeled_packs_to_50',
    'modeled_spend_to_50','previousOverallRipRank1d','previous_overall_rip_rank_1d',
    'overallRipRankComparisonStatus1d','overall_rip_rank_comparison_status_1d',
    'previousFinancialRipRank1d','previous_financial_rip_rank_1d',
    'financialRipRankComparisonStatus1d','financial_rip_rank_comparison_status_1d',
    'relative_experience_score','experience_rank','experience_tier',
    'relative_chase_potential_score','chase_potential_rank','chase_potential_tier',
    'mean_value_to_cost_ratio','mean_value_to_cost_rank','mean_value_to_cost_tier',
    'median_value_to_cost_ratio','relative_biggest_upside_score','biggest_upside_rank',
    'biggest_upside_tier','p99_value_to_cost_ratio','p99_value_to_cost_rank',
    'p99_value_to_cost_tier','checklist_set_value','checklist_set_value_as_of',
    'checklistSetValue','checklistSetValueAsOf','current_checklist_set_value',
    'current_checklist_set_value_date','currentChecklistSetValue','currentChecklistSetValueDate'
]) || jsonb_strip_nulls(jsonb_build_object(
    'setRipV1', public.project_rankings_json_keys(p_target->'setRipV1', ARRAY[
        'score','tier','rank','cohortSize','rankable','methodologyVersion',
        'participatingFamilyCount','participatingFamilies','skuEvidenceCount',
        'familyScores','displayFamilyScores'
    ]),
    'overallRipV8', public.project_rankings_json_keys(p_target->'overallRipV8', ARRAY['relativeScore','rank','cohortSize','tier']),
    'overallRipV9', public.project_rankings_json_keys(p_target->'overallRipV9', ARRAY['relativeScore','rank','cohortSize','tier']),
    'overallRipV10', public.project_rankings_json_keys(p_target->'overallRipV10', ARRAY['relativeScore','leaderNormalizedScore','rank','cohortSize','rankedSetCount','tier','status','statusReason']),
    -- CURRENT canonical Overall RIP model.
    'overallRipV12', public.project_rankings_json_keys(p_target->'overallRipV12', ARRAY['relativeScore','leaderNormalizedScore','rank','cohortSize','rankedSetCount','tier','status','statusReason']),
    'financialRipV3', public.project_rankings_json_keys(p_target->'financialRipV3', ARRAY['relativeScore','rank','cohortSize','tier']),
    'financialRipV4', public.project_rankings_json_keys(p_target->'financialRipV4', ARRAY['relativeScore','leaderNormalizedScore','rank','cohortSize','rankedSetCount','tier','status','statusReason']),
    'universalSetDesirability', public.project_rankings_json_keys(p_target->'universalSetDesirability', ARRAY['score','rank','rankedSetCount']),
    'rankingsChase', public.project_rankings_json_keys(p_target->'rankingsChase', ARRAY['cardName','currentMarketPrice','impliedOddsOneInN','packsFor50PercentChance']),
    'topChase', public.project_rankings_json_keys(p_target->'topChase', ARRAY['cardName','currentMarketPrice','impliedOddsOneInN','packsFor50PercentChance']),
    'top_chase', public.project_rankings_json_keys(p_target->'top_chase', ARRAY['card_name','current_market_price','implied_odds_one_in_n','packs_for_50_percent_chance']),
    'ripDecision', jsonb_build_object('topChase', p_target#>'{ripDecision,topChase}'),
    'rip_decision', jsonb_build_object('top_chase', p_target#>'{rip_decision,top_chase}'),
    'publicRipContractV8', public.project_public_rip_contract(p_target->'publicRipContractV8'),
    'publicRipContractV9', public.project_public_rip_contract(p_target->'publicRipContractV9'),
    'publicRipContractV10', public.project_public_rip_contract(p_target->'publicRipContractV10'),
    -- CURRENT canonical public RIP contract (carries V12 in its stable generic
    -- overallRip slot - see backend/desirability/public_rip_contract_v11.py).
    'publicRipContractV11', public.project_public_rip_contract(p_target->'publicRipContractV11')
));
$$;

REVOKE ALL ON FUNCTION public.project_pokemon_rankings_set_target(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_pokemon_rankings_set_target(JSONB) TO service_role;

COMMIT;
