-- 20260909030411: source-repo mirror of a live production repair applied
-- directly, out-of-band, by a party with DB access (NOT executed by this
-- migration -- see the "DO NOT RUN" note below).
--
-- WHY THIS EXISTS
-- ----------------
-- CATALOG/ROUTE MEMBERSHIP != RIP ELIGIBILITY != MARKET ELIGIBILITY. Before
-- this repair, public.get_pokemon_set_route_directory(integer) (added by
-- 20260828014500_create_pokemon_set_route_directory_rpc.sql) derived its
-- entire target list from `pokemon_explore_rankings_snapshot_latest`'s
-- `targets` array -- i.e. from RIP Rankings PUBLICATION membership. A
-- canonical root Pokemon set with cards and market data but no supported
-- RIP simulation (or one simply not yet re-published under the current
-- Rankings identity, as happened after the V10->V12 cutover) could not
-- resolve a canonical set-detail route at all: it was invisible to this RPC
-- even though it belongs in the catalog. That is the exact architectural
-- violation this effort was told never to reintroduce.
--
-- Also: this coupling was hazardous even when Rankings publication was
-- fresh. A stale, unpublished, or narrowed Rankings cohort could silently
-- shrink the route directory -- meaning a page-level 404 for a real set
-- would have been a side effect of a Rankings problem, not a routing
-- problem.
--
-- WHAT LIVE CHANGED
-- ------------------
-- The live repair repoints this RPC's driving table at canonical
-- `public.sets` ROOT-set membership -- COALESCE(is_subset, false) = false
-- -- instead of Rankings publication membership. Verified live: directory
-- count at limit 150 = 150; Evolving Skies, Cosmic Eclipse, and Team Up are
-- all present (none of the three needs a supported RIP simulation, or
-- Rankings cohort membership, to appear here). Optional pack-score/rank/tier
-- fields are still LEFT JOINed from the current Rankings publication when
-- available, purely as supplemental display data for sets that DO have a
-- published ranking -- their absence never removes a set from the
-- directory, and no set is ever added or excluded on their account.
--
-- SECURITY INVOKER is preserved (this RPC touches only public, non-RLS-
-- sensitive relational columns -- it never needs to read the multi-megabyte
-- Rankings payload's sensitive internals), as is service_role-only EXECUTE.
--
-- PROVENANCE / HONESTY ABOUT WHAT THIS FILE IS
-- ---------------------------------------------
-- Unlike 20260908224500_mirror_set_page_generation_lifecycle_rpcs.sql, no
-- verbatim `pg_get_functiondef` transcription of the live function body was
-- supplied out-of-band for this repair. This file is a RECONSTRUCTION of the
-- live semantics described above (root-set membership via is_subset,
-- SECURITY INVOKER, service_role-only, verified-live row count and named-set
-- presence), written against the canonical `public.sets` / `public.eras`
-- columns actually used elsewhere in this repo (see
-- backend/db/services/pokemon_market_rollout_cohort.py's
-- `_CORE_SET_COLUMNS` and backend/db/services/pokemon_sets_catalog_service.py
-- for the verified column list) -- it is NOT a byte-for-byte transcription
-- of the running function. Treat it as a best-effort, reviewable starting
-- point: a maintainer with live DB access should diff
-- `pg_get_functiondef('public.get_pokemon_set_route_directory(integer)')`
-- against this file before relying on it as the canonical historical record,
-- and correct this file (in a follow-up migration, never by editing this
-- one) if the live body differs in any material way.
--
-- DO NOT RUN THIS AGAINST ANY DATABASE FROM THIS BRANCH. This effort has no
-- production or dev DB credentials in this sandbox.
--
-- 20260828014500 IS NOT EDITED. This is a forward-only CREATE OR REPLACE,
-- so the historical (Rankings-membership) definition stays in the record.
--
-- The default/ceiling limit is raised from 150 to 200 to match the current
-- canonical root Pokemon set count (~200), consistent with the frontend and
-- backend service ceiling raised alongside this migration (see
-- frontend/lib/pokemon/pokemonSetRouteDirectoryServer.js,
-- frontend/app/TCGs/Pokemon/Sets/[setSlug]/page.js, frontend/app/Explore/
-- page.js, and backend/db/services/pokemon_set_route_directory_service.py).

BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_set_route_directory(p_limit integer default 200)
RETURNS TABLE (
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
SECURITY INVOKER
SET search_path = public
AS $$
  WITH root_sets AS (
    -- Canonical route/catalog membership: every root (non-subset) Pokemon
    -- set, independent of RIP simulation support and independent of
    -- Rankings publication membership. This is deliberately the SAME root
    -- membership predicate as the Pokemon Sets catalog
    -- (COALESCE(is_subset, false) = false).
    SELECT
      s.id,
      s.name,
      s.canonical_key,
      s.era_id,
      s.release_date,
      s.pokemon_api_set_id,
      s.logo_image_url,
      s.symbol_image_url,
      s.hero_image_url,
      row_number() OVER (
        ORDER BY s.release_date DESC NULLS LAST, s.name
      ) AS ordinal
    FROM public.sets s
    JOIN public.tcgs t ON t.id = s.tcg_id AND t.name IN ('Pokemon', 'Pokémon')
    WHERE COALESCE(s.is_subset, false) = false
  ), authority AS (
    SELECT ranking_payload_json
    FROM public.pokemon_explore_rankings_snapshot_latest
    WHERE tcg = 'pokemon' AND scope = 'rip-statistics'
    LIMIT 1
  ), published AS (
    -- Supplemental-only: pack score/rank/tier for whichever root sets
    -- currently have a published ranking. A set missing from this CTE
    -- (unpublished, unsupported simulation, or stale Rankings cohort)
    -- still resolves a route -- it simply carries null pack fields, which
    -- callers must already treat as "RIP module unavailable", not as
    -- "page not found".
    SELECT
      value ->> 'target_id' AS target_id,
      nullif(value ->> 'pack_score', '')::numeric AS pack_score,
      nullif(value ->> 'relative_pack_score', '')::numeric AS relative_pack_score,
      nullif(value ->> 'pack_rank', '')::integer AS pack_rank,
      value ->> 'pack_tier' AS pack_tier,
      COALESCE(
        nullif(value #>> '{overallRipV10,cohortSize}', '')::integer,
        nullif(value ->> 'ranked_set_count', '')::integer
      ) AS ranked_set_count
    FROM authority, jsonb_array_elements(authority.ranking_payload_json -> 'targets') AS value
  )
  SELECT
    r.ordinal::integer,
    r.id::text,
    r.name,
    r.canonical_key,
    CASE WHEN e.id IS NULL THEN NULL ELSE jsonb_build_object('id', e.id, 'name', e.name) END,
    r.release_date,
    r.pokemon_api_set_id,
    r.logo_image_url,
    r.symbol_image_url,
    r.hero_image_url,
    p.pack_score,
    p.relative_pack_score,
    p.pack_rank,
    p.pack_tier,
    p.ranked_set_count
  FROM root_sets r
  LEFT JOIN public.eras e ON e.id = r.era_id
  LEFT JOIN published p ON p.target_id = r.id::text
  WHERE r.ordinal <= greatest(1, least(coalesce(p_limit, 200), 200))
  ORDER BY r.ordinal;
$$;

REVOKE ALL ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM public;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) TO service_role;

COMMIT;
