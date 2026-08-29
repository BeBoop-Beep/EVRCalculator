BEGIN;

CREATE OR REPLACE FUNCTION public.project_pokemon_rankings_era_input(p_target JSONB)
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT public.project_rankings_json_keys(p_target, ARRAY[
    'target_id','set_id','id','name','era','era_id','logo_image_url',
    'symbol_image_url','publicAnalyticsStatus','is_opening_set','isOpeningSet'
]) || jsonb_build_object(
    'setRipV1', public.project_rankings_json_keys(p_target->'setRipV1', ARRAY[
        'score','rank','tier','rankable','methodologyVersion'
    ])
);
$$;

CREATE OR REPLACE FUNCTION public.get_pokemon_rankings_eras_lens()
RETURNS JSONB
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
), compact_inputs AS (
    SELECT ordinality, public.project_pokemon_rankings_era_input(target) AS target
    FROM publication
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(payload->'targets', '[]'::jsonb))
        WITH ORDINALITY AS rows(target, ordinality)
    WHERE COALESCE((target->>'is_opening_set')::boolean, (target->>'isOpeningSet')::boolean, true)
)
SELECT jsonb_build_object(
    'eraSetStrengthV1', payload->'eraSetStrengthV1',
    'targets', CASE WHEN payload->'eraSetStrengthV1' IS NULL
        THEN COALESCE((SELECT jsonb_agg(target ORDER BY ordinality) FROM compact_inputs), '[]'::jsonb)
        ELSE '[]'::jsonb END,
    'meta', COALESCE(payload->'meta', '{}'::jsonb),
    'updated_at', updated_at
)
FROM publication;
$$;

REVOKE ALL ON FUNCTION public.project_pokemon_rankings_era_input(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_rankings_eras_lens() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_pokemon_rankings_era_input(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_rankings_eras_lens() TO service_role;

COMMIT;
