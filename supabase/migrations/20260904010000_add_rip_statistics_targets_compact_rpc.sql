BEGIN;

-- Compact reader for GET /explore/rip-statistics/targets (Phase B of the
-- 2026-09-04 memory P0 fast-follow). Mirrors the existing
-- get_pokemon_rankings_sets_lens pattern (20260830010000) but projects the
-- FULL Base+Plus target field contract that `/targets` serves (not the
-- narrower Sets lens contract used by the Rankings page), so the endpoint
-- never has to materialize the mega-contract's productFamilyRankings/
-- setRip/eraSetStrengthV1 blocks in Python on the healthy path.
--
-- Unlike get_pokemon_rankings_sets_lens, this RPC passes several already-
-- published nested objects (setRipV1, financialRipV4, overallRipV10,
-- publicRipContractV10, openingExperience, rankingsChase) through WHOLE,
-- not re-picked field-by-field: the Base/Plus entitlement split for those
-- objects happens in Python (backend/domain/access/index_plan_access.py
-- project_rankings_response / _project_public_set_leaderboard_target), and
-- that code expects the full published shape when the caller is Plus. No
-- score/rank recomputation happens here - this only selects already-
-- published fields.
--
-- `meta` is passed through unfiltered from the publication: it already
-- excludes productFamilyRankings/setRip/eraSetStrengthV1 (those are
-- sibling top-level keys on the publication, not nested under meta), is
-- small relative to the mega-contract, and already carries the persisted
-- `openingSetAudit`/`opening_set_audit` this endpoint must serve unchanged
-- rather than rebuild from a filtered target array.

CREATE OR REPLACE FUNCTION public.project_pokemon_rip_statistics_target(p_target JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT public.project_rankings_json_keys(p_target, ARRAY[
    -- _BASE_TARGET_FIELDS (backend/domain/access/index_plan_access.py)
    'id','set_id','target_id','target_type','name','slug','canonical_key',
    'pokemon_api_set_id','era','era_id','hero_image_url','logo_image_url',
    'symbol_image_url','checklist_set_value','checklist_set_value_as_of',
    'checklist_set_value_priced_card_count','checklist_set_value_total_card_count',
    'checklistSetValue','checklistSetValueAsOf','checklistSetValuePricedCardCount',
    'checklistSetValueTotalCardCount','current_checklist_set_value',
    'current_checklist_set_value_date','currentChecklistSetValue',
    'currentChecklistSetValueDate','publicAnalyticsStatus',
    -- _PLUS_TARGET_FIELDS additions (scalars only; nested objects below)
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
    -- Nested objects passed through WHOLE, not re-picked -- Plus/Base
    -- entitlement filtering of these happens in Python.
    'rip', p_target->'rip',
    'ripCore', p_target->'ripCore',
    'financialRipV4', p_target->'financialRipV4',
    'overallRipV10', p_target->'overallRipV10',
    'publicRipContractV10', p_target->'publicRipContractV10',
    'setRipV1', p_target->'setRipV1',
    'openingExperience', p_target->'openingExperience',
    'rankingsChase', p_target->'rankingsChase'
));
$$;

CREATE OR REPLACE FUNCTION public.get_pokemon_rip_statistics_targets_compact(p_limit INTEGER DEFAULT 200)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
WITH publication AS (
    SELECT ranking_payload_json AS payload, default_target_json, updated_at
    FROM public.pokemon_explore_rankings_snapshot_latest
    WHERE tcg = 'pokemon' AND scope = 'rip-statistics'
    LIMIT 1
), projected AS (
    SELECT ordinality, public.project_pokemon_rip_statistics_target(target) AS target
    FROM publication
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(payload->'targets', '[]'::jsonb))
        WITH ORDINALITY AS rows(target, ordinality)
    WHERE COALESCE((target->>'is_opening_set')::boolean, (target->>'isOpeningSet')::boolean, true)
    ORDER BY ordinality
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 200), 1), 200)
)
SELECT jsonb_build_object(
    'targets', COALESCE((SELECT jsonb_agg(target ORDER BY ordinality) FROM projected), '[]'::jsonb),
    'default_target', default_target_json,
    'meta', COALESCE(payload->'meta', '{}'::jsonb),
    'updated_at', updated_at
)
FROM publication;
$$;

REVOKE ALL ON FUNCTION public.project_pokemon_rip_statistics_target(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_rip_statistics_targets_compact(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_pokemon_rip_statistics_target(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_rip_statistics_targets_compact(INTEGER) TO service_role;

COMMIT;
