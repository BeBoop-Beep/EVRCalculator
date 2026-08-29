BEGIN;

CREATE OR REPLACE FUNCTION public.project_public_rank_block(p_block JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT jsonb_strip_nulls(jsonb_build_object(
    'relativeScore', p_block->'relativeScore',
    'leaderNormalizedScore', p_block->'leaderNormalizedScore',
    'absoluteScore', p_block->'absoluteScore',
    'score', p_block->'score',
    'rank', p_block->'rank',
    'tier', p_block->'tier',
    'publicTier', p_block->'publicTier',
    'rankedSetCount', p_block->'rankedSetCount',
    'cohortSize', p_block->'cohortSize',
    'status', p_block->'status',
    'statusReason', p_block->'statusReason'
));
$$;

CREATE OR REPLACE FUNCTION public.project_public_rip_contract(p_contract JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT jsonb_strip_nulls(jsonb_build_object(
    'overallRip', CASE WHEN jsonb_typeof(p_contract->'overallRip') = 'object'
        THEN public.project_public_rank_block(p_contract->'overallRip') END,
    'financialRip', CASE WHEN jsonb_typeof(p_contract->'financialRip') = 'object'
        THEN public.project_public_rank_block(p_contract->'financialRip') END,
    'collectorAppeal', CASE WHEN jsonb_typeof(p_contract->'collectorAppeal') = 'object'
        THEN public.project_public_rank_block(p_contract->'collectorAppeal') END
));
$$;

CREATE OR REPLACE FUNCTION public.get_pokemon_rankings_sets_lens(p_limit INTEGER DEFAULT 60)
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
    SELECT ordinality, jsonb_strip_nulls(
        target
        - ARRAY[
            'publicRipContractV7', 'publicRipContractV8', 'publicRipContractV9', 'publicRipContractV10',
            'openingExperience', 'financialRipV3', 'financialRipV4'
          ]
        || jsonb_build_object(
            'publicRipContractV8', public.project_public_rip_contract(target->'publicRipContractV8'),
            'publicRipContractV9', public.project_public_rip_contract(target->'publicRipContractV9'),
            'publicRipContractV10', public.project_public_rip_contract(target->'publicRipContractV10'),
            'financialRipV3', public.project_public_rank_block(target->'financialRipV3'),
            'financialRipV4', public.project_public_rank_block(target->'financialRipV4')
        )
    ) AS target
    FROM publication
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(payload->'targets', '[]'::jsonb))
        WITH ORDINALITY AS rows(target, ordinality)
    WHERE COALESCE((target->>'is_opening_set')::boolean, (target->>'isOpeningSet')::boolean, true)
    ORDER BY ordinality
    LIMIT LEAST(GREATEST(COALESCE(p_limit, 60), 1), 200)
)
SELECT jsonb_build_object(
    'targets', COALESCE((SELECT jsonb_agg(target ORDER BY ordinality) FROM projected), '[]'::jsonb),
    'default_target', default_target_json,
    'meta', COALESCE(payload->'meta', '{}'::jsonb) || jsonb_build_object(
        'snapshot', COALESCE(payload#>'{meta,snapshot}', '{}'::jsonb) || jsonb_build_object(
            'source', 'get_pokemon_rankings_sets_lens', 'updatedAt', updated_at
        )
    )
)
FROM publication;
$$;

REVOKE ALL ON FUNCTION public.project_public_rank_block(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.project_public_rip_contract(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_rankings_sets_lens(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_rankings_sets_lens(INTEGER) TO service_role;

COMMIT;
