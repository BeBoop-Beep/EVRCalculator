BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_set_route_directory(p_limit integer DEFAULT 500)
RETURNS TABLE(
  ordinal integer,
  target_id text,
  name text,
  canonical_key text,
  era jsonb,
  release_date date,
  pokemon_api_set_id text,
  logo_image_url text,
  symbol_image_url text,
  hero_image_url text,
  pack_score numeric,
  relative_pack_score numeric,
  pack_rank integer,
  pack_tier text,
  ranked_set_count integer
)
LANGUAGE sql
STABLE
SET search_path TO 'public'
AS $function$
  WITH pokemon_tcg AS (
    SELECT t.id
    FROM public.tcgs t
    WHERE lower(t.name) IN ('pokemon', 'pokémon')
    ORDER BY CASE WHEN lower(t.name) = 'pokemon' THEN 0 ELSE 1 END, t.id
    LIMIT 1
  ), ranking_authority AS (
    SELECT r.ranking_payload_json
    FROM public.pokemon_explore_rankings_snapshot_latest r
    WHERE r.tcg = 'pokemon' AND r.scope = 'rip-statistics'
    LIMIT 1
  ), ranking_targets AS (
    SELECT value AS target
    FROM ranking_authority
    CROSS JOIN LATERAL jsonb_array_elements(
      COALESCE(ranking_payload_json -> 'targets', '[]'::jsonb)
    )
  ), catalog AS (
    SELECT
      row_number() OVER (
        ORDER BY s.release_date DESC NULLS LAST, s.name ASC, s.id ASC
      )::integer AS ordinal,
      s.id,
      s.name,
      s.canonical_key,
      s.era_id,
      s.release_date,
      s.pokemon_api_set_id,
      s.logo_image_url,
      s.symbol_image_url,
      s.hero_image_url
    FROM public.sets s
    JOIN pokemon_tcg p ON p.id = s.tcg_id
    WHERE COALESCE(s.is_subset, false) = false
  )
  SELECT
    c.ordinal,
    c.id::text AS target_id,
    c.name,
    c.canonical_key,
    CASE
      WHEN e.id IS NULL THEN NULL
      ELSE jsonb_build_object('id', e.id::text, 'name', e.name)
    END AS era,
    c.release_date,
    c.pokemon_api_set_id,
    c.logo_image_url,
    c.symbol_image_url,
    c.hero_image_url,
    NULLIF(rt.target ->> 'pack_score', '')::numeric AS pack_score,
    NULLIF(rt.target ->> 'relative_pack_score', '')::numeric AS relative_pack_score,
    NULLIF(rt.target ->> 'pack_rank', '')::integer AS pack_rank,
    rt.target ->> 'pack_tier' AS pack_tier,
    COALESCE(
      NULLIF(rt.target #>> '{overallRipV12,cohortSize}', '')::integer,
      NULLIF(rt.target #>> '{overallRipV10,cohortSize}', '')::integer,
      NULLIF(rt.target ->> 'ranked_set_count', '')::integer
    ) AS ranked_set_count
  FROM catalog c
  LEFT JOIN public.eras e ON e.id = c.era_id
  LEFT JOIN ranking_targets rt
    ON COALESCE(rt.target ->> 'target_id', rt.target ->> 'set_id') = c.id::text
  WHERE c.ordinal <= greatest(1, least(coalesce(p_limit, 500), 500))
  ORDER BY c.ordinal;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM public;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) TO service_role;

COMMIT;
