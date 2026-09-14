BEGIN;

CREATE OR REPLACE FUNCTION public.project_pokemon_rip_statistics_target(p_target JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT public.project_rankings_json_keys(p_target, ARRAY[
    'id','set_id','target_id','target_type','name','slug','canonical_key',
    'pokemon_api_set_id','era','era_id','hero_image_url','logo_image_url',
    'symbol_image_url','checklist_set_value','checklist_set_value_as_of',
    'checklist_set_value_priced_card_count','checklist_set_value_total_card_count',
    'checklistSetValue','checklistSetValueAsOf','checklistSetValuePricedCardCount',
    'checklistSetValueTotalCardCount','current_checklist_set_value',
    'current_checklist_set_value_date','currentChecklistSetValue',
    'currentChecklistSetValueDate','publicAnalyticsStatus',
    'calculation_run_id','run_at','pack_cost','pack_score','relative_pack_score',
    'pack_rank','pack_tier','profit_score','relative_profit_score','profit_rank',
    'profit_tier','safety_score','relative_safety_score','safety_rank','safety_tier',
    'stability_score','relative_stability_score','stability_rank','stability_tier',
    'mean_value','median_value','prob_profit','prob_big_hit','roi_percent',
    'expected_loss_when_losing','mean_value_to_cost_ratio','mean_value_to_cost_rank',
    'mean_value_to_cost_tier','p95_value_to_cost_ratio','p95_value_to_cost_rank',
    'p95_value_to_cost_tier','p99_value_to_cost_ratio','p99_value_to_cost_rank',
    'p99_value_to_cost_tier','collector_appeal_score','collector_appeal_rank',
    'opening_desirability_score','opening_desirability_rank',
    'opening_desirability_summary','is_opening_set','isOpeningSet'
]) || jsonb_strip_nulls(jsonb_build_object(
    'rip', p_target->'rip',
    'ripCore', p_target->'ripCore',
    'financialRipV4', p_target->'financialRipV4',
    'overallRipV10', p_target->'overallRipV10',
    'publicRipContractV10', p_target->'publicRipContractV10',
    'overallRipV12', p_target->'overallRipV12',
    'publicRipContractV11', p_target->'publicRipContractV11',
    'chaseAccessibility', p_target->'chaseAccessibility',
    'setRipV1', p_target->'setRipV1',
    'openingExperience', p_target->'openingExperience',
    'rankingsChase', p_target->'rankingsChase'
));
$$;

REVOKE ALL ON FUNCTION public.project_pokemon_rip_statistics_target(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_pokemon_rip_statistics_target(JSONB) TO service_role;

COMMIT;