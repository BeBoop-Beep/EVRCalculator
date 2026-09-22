-- 20260921183500: restore the Pokemon set-route directory to a truly slim
-- relational routing authority.
--
-- INCIDENT
-- --------
-- The 2026-09-20 limit expansion to 500 retained a LEFT JOIN against the
-- multi-megabyte Rankings publication JSON. In production that made the
-- routing RPC itself take ~15-28 seconds for 201 root sets and spill 3,316
-- temp blocks. Both /Explore and every Pokemon set-detail route await this
-- directory during server rendering, so Next flushed loading.js and then
-- appeared stuck indefinitely. The TCG catalog page remained healthy because
-- it uses a separate catalog read path.
--
-- MEASURED BEFORE THIS REPAIR
--   get_pokemon_set_route_directory(200): ~5.1s
--   get_pokemon_set_route_directory(201): ~15.2s
--   get_pokemon_set_route_directory(500): ~27.6s
--
-- The pack score/rank/tier columns are supplemental display metadata only.
-- Routing/catalog membership must not depend on RIP publication or on an
-- expensive simulation/rank view. Those analytics are loaded by their own
-- dedicated contracts after route resolution.
--
-- MEASURED AFTER THE LIVE REPAIR
--   get_pokemon_set_route_directory(500): ~41ms for all 201 root sets
--
-- Preserve the existing return shape and service_role-only EXECUTE so callers
-- need no compatibility change; unavailable ranking enrichment is represented
-- as NULL rather than blocking route resolution.

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
  ),
  catalog AS (
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
    NULL::numeric AS pack_score,
    NULL::numeric AS relative_pack_score,
    NULL::integer AS pack_rank,
    NULL::text AS pack_tier,
    NULL::integer AS ranked_set_count
  FROM catalog c
  LEFT JOIN public.eras e ON e.id = c.era_id
  WHERE c.ordinal <= greatest(1, least(coalesce(p_limit, 500), 500))
  ORDER BY c.ordinal;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM public;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) TO service_role;

COMMIT;
