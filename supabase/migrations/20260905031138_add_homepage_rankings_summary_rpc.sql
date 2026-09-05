BEGIN;

-- Narrow public Homepage Rankings projection (Prompt 2 / A2 fast-follow).
--
-- The Homepage previously sourced its landing Rankings module from the
-- general-purpose compact `/explore/rip-statistics/targets` payload
-- (~3.25MB live-measured for the full cohort), even though the Homepage's
-- public landing surface (frontend/lib/landing/landingHeroServer.js ->
-- landingHeroSpotlight.mjs / landingPreviews.mjs / landingDistribution.mjs)
-- only ever reads: set identity (target_type/target_id/canonical_key/name/
-- era), hero/logo/symbol imagery, the published Set RIP V1 score/rank/tier/
-- cohortSize, checklist Set Value (+ 7-day comparison), opening pack
-- economics (pack_cost/mean_value/median_value/prob_profit/expected loss),
-- and the public Set Desirability/Collector Appeal figures. It never reads
-- product rankings, openingExperience, Financial RIP internals, or
-- simulation distributions -- those stay Plus-only and are correctly absent
-- from this projection.
--
-- Mirrors the existing get_pokemon_rankings_sets_lens pattern
-- (20260830010000_tighten_compact_rankings_sets_lens_rpc.sql): a pure
-- projection over the already-published Rankings publication row. It never
-- recomputes scores, ranks, tiers, or cohort membership -- every value here
-- is read straight off the already-published target, exactly like the Sets
-- lens. Rows are limited only AFTER the publication's own rank ordering is
-- attached (the CROSS JOIN LATERAL below preserves the publication's own
-- `targets` array order, which is already rank-ordered).
--
-- Deliberately narrower than get_pokemon_rankings_sets_lens's field list:
-- no overallRipV8/V9/V10, financialRipV3/V4, rankingsChase/topChase, or
-- publicRipContract blocks -- the Homepage does not render any of those, so
-- they are not projected here. Reusing project_rankings_json_keys (defined
-- in 20260830010000) rather than redefining it.

CREATE OR REPLACE FUNCTION public.project_pokemon_homepage_rankings_target(p_target JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT public.project_rankings_json_keys(p_target, ARRAY[
    'target_type','target_id','name','era','canonical_key','canonicalKey','slug',
    'hero_image_url','heroImageUrl','logo_image_url','symbol_image_url',
    'checklist_set_value','checklist_set_value_as_of','checklistSetValue','checklistSetValueAsOf',
    'current_checklist_set_value','current_checklist_set_value_date',
    'currentChecklistSetValue','currentChecklistSetValueDate',
    'previousChecklistSetValue7d','previous_checklist_set_value_7d',
    'setValueComparisonStatus7d','set_value_comparison_status_7d',
    'pack_cost','packCost','mean_value','meanValue','median_value','medianValue',
    'prob_profit','probProfit','expected_loss_per_pack','expectedLossPerPack',
    'collector_appeal_score','collectorAppealScore',
    'desirability_is_fallback','desirabilityIsFallback',
    'is_opening_set','isOpeningSet'
]) || jsonb_strip_nulls(jsonb_build_object(
    'setRipV1', public.project_rankings_json_keys(p_target->'setRipV1', ARRAY[
        'score','tier','rank','cohortSize','rankable'
    ]),
    'universalSetDesirability', public.project_rankings_json_keys(p_target->'universalSetDesirability', ARRAY[
        'score','rank'
    ])
));
$$;

CREATE OR REPLACE FUNCTION public.get_pokemon_rankings_homepage_lens(p_limit INTEGER DEFAULT 60)
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
    SELECT ordinality, public.project_pokemon_homepage_rankings_target(target) AS target
    FROM publication
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(payload->'targets', '[]'::jsonb))
        WITH ORDINALITY AS rows(target, ordinality)
    WHERE COALESCE((target->>'is_opening_set')::boolean, (target->>'isOpeningSet')::boolean, true)
    ORDER BY ordinality
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 60), 1), 60)
)
SELECT jsonb_build_object(
    'targets', COALESCE((SELECT jsonb_agg(target ORDER BY ordinality) FROM projected), '[]'::jsonb),
    'default_target', default_target_json,
    'meta', COALESCE(payload->'meta', '{}'::jsonb) || jsonb_build_object(
        'snapshot', COALESCE(payload#>'{meta,snapshot}', '{}'::jsonb) || jsonb_build_object(
            'source', 'get_pokemon_rankings_homepage_lens', 'updatedAt', updated_at
        )
    )
)
FROM publication;
$$;

REVOKE ALL ON FUNCTION public.project_pokemon_homepage_rankings_target(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_rankings_homepage_lens(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_pokemon_homepage_rankings_target(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_rankings_homepage_lens(INTEGER) TO service_role;

COMMIT;
