-- Compact, order-preserving routing projection of the canonical Rankings publication.
create or replace function public.get_pokemon_set_route_directory(p_limit integer default 150)
returns table (
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
language sql
stable
security invoker
set search_path = public
as $$
  with authority as (
    select ranking_payload_json
    from public.pokemon_explore_rankings_snapshot_latest
    where tcg = 'pokemon' and scope = 'rip-statistics'
    limit 1
  ), published as (
    select value as target, ordinality::integer as ordinal
    from authority,
      jsonb_array_elements(ranking_payload_json -> 'targets') with ordinality
    where ordinality <= greatest(1, least(coalesce(p_limit, 150), 200))
  )
  select
    p.ordinal,
    p.target ->> 'target_id',
    p.target ->> 'name',
    p.target ->> 'canonical_key',
    p.target -> 'era',
    s.release_date,
    s.pokemon_api_set_id,
    s.logo_image_url,
    s.symbol_image_url,
    s.hero_image_url,
    nullif(p.target ->> 'pack_score', '')::numeric,
    nullif(p.target ->> 'relative_pack_score', '')::numeric,
    nullif(p.target ->> 'pack_rank', '')::integer,
    p.target ->> 'pack_tier',
    coalesce(
      nullif(p.target #>> '{overallRipV10,cohortSize}', '')::integer,
      nullif(p.target ->> 'ranked_set_count', '')::integer
    )
  from published p
  left join public.sets s on s.id::text = p.target ->> 'target_id'
  order by p.ordinal;
$$;

revoke all on function public.get_pokemon_set_route_directory(integer) from public;
grant execute on function public.get_pokemon_set_route_directory(integer) to service_role;
