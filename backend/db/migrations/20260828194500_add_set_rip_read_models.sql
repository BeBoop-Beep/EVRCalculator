BEGIN;

ALTER TABLE public.pokemon_set_page_snapshot_latest
    ADD COLUMN IF NOT EXISTS rip_bootstrap_json JSONB,
    ADD COLUMN IF NOT EXISTS rip_simulation_evidence_json JSONB,
    ADD COLUMN IF NOT EXISTS rip_advanced_json JSONB;

CREATE OR REPLACE FUNCTION public.get_pokemon_set_rip_global_context(
    p_set_id UUID,
    p_expected_calculation_run_id UUID DEFAULT NULL
) RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
WITH publication AS (
    SELECT ranking_payload_json AS payload, updated_at
    FROM public.pokemon_explore_rankings_snapshot_latest
    WHERE tcg = 'pokemon' AND scope = 'rip-statistics'
    LIMIT 1
), selected_target AS (
    SELECT target
    FROM publication p
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(p.payload->'targets', '[]'::jsonb)) target
    WHERE COALESCE(target->>'target_id', target->>'set_id', target->>'id') = p_set_id::text
    LIMIT 1
), identity AS (
    SELECT COALESCE(target->>'calculation_run_id', target->>'calculationRunId') AS ranking_run_id
    FROM selected_target
), families AS (
    SELECT family.key, family.value
    FROM publication p
    CROSS JOIN LATERAL jsonb_each(COALESCE(p.payload#>'{productFamilyRankings,families}', '{}'::jsonb)) family
), selected_families AS (
    SELECT jsonb_object_agg(
        key,
        jsonb_build_object(
            'key', COALESCE(value->>'key', key),
            'label', value->'label',
            'count', value->'count',
            'currentlyRankableCount', value->'currentlyRankableCount',
            'products', COALESCE((
                SELECT jsonb_agg(product)
                FROM jsonb_array_elements(COALESCE(value->'products', '[]'::jsonb)) product
                WHERE COALESCE(product->>'setId', product->>'set_id', product->>'targetId') = p_set_id::text
                  AND (p_expected_calculation_run_id IS NULL OR
                       COALESCE(product->>'calculationRunId', product->>'calculation_run_id') = p_expected_calculation_run_id::text)
            ), '[]'::jsonb)
        )
    ) AS payload
    FROM families
), projection AS (
    SELECT
        st.target,
        i.ranking_run_id,
        sf.payload AS families,
        p.updated_at,
        p_expected_calculation_run_id IS NULL OR i.ranking_run_id = p_expected_calculation_run_id::text AS compatible
    FROM publication p
    LEFT JOIN selected_target st ON true
    LEFT JOIN identity i ON true
    LEFT JOIN selected_families sf ON true
)
SELECT jsonb_build_object(
    'contractVersion', 'pokemon-set-rip-global-context-v1',
    'setId', p_set_id,
    'expectedCalculationRunId', p_expected_calculation_run_id,
    'rankingCalculationRunId', ranking_run_id,
    'compatible', COALESCE(compatible, false),
    'status', CASE WHEN target IS NULL THEN 'unavailable'
                   WHEN compatible THEN 'ready' ELSE 'stale_ranking_generation' END,
    'target', CASE WHEN compatible THEN jsonb_strip_nulls(jsonb_build_object(
        'setRipV1', target->'setRipV1',
        'evRepresentativeness', target->'evRepresentativeness',
        'openingOutcomeProfile', target->'openingOutcomeProfile',
        'calculationRunId', COALESCE(target->'calculationRunId', target->'calculation_run_id')
    )) ELSE '{}'::jsonb END,
    'productFamilyRankings', jsonb_build_object('families', COALESCE(families, '{}'::jsonb)),
    'meta', jsonb_build_object('rankingUpdatedAt', updated_at)
) FROM projection;
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_set_rip_global_context(UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_pokemon_set_rip_global_context(UUID, UUID) FROM anon;
REVOKE ALL ON FUNCTION public.get_pokemon_set_rip_global_context(UUID, UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_rip_global_context(UUID, UUID) TO service_role;

COMMIT;
