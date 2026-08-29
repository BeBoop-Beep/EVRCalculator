BEGIN;

CREATE OR REPLACE FUNCTION public.project_rankings_json_keys(p_value JSONB, p_keys TEXT[])
RETURNS JSONB
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = public, pg_temp
AS $$
SELECT COALESCE(jsonb_object_agg(entry.key, entry.value), '{}'::jsonb)
FROM jsonb_each(
    CASE WHEN jsonb_typeof(p_value) = 'object' THEN p_value ELSE '{}'::jsonb END
) AS entry
WHERE entry.key = ANY(p_keys);
$$;

REVOKE ALL ON FUNCTION public.project_rankings_json_keys(JSONB, TEXT[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.project_rankings_json_keys(JSONB, TEXT[]) TO service_role;

COMMIT;
