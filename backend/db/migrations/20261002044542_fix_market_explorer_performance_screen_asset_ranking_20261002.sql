begin;

-- Production parity for the 2026-10-02 screen-ranking correction.
-- Asset qualification belongs inside the ranked universe; applying it after
-- p_limit can return fewer than p_limit rows even when the asset has enough.
create or replace function public.get_pokemon_market_explorer_performance_screen_v1(
  p_screen_key text,
  p_asset text,
  p_generation_id uuid,
  p_limit integer default 25
)
returns table(
  rank integer,screen_key text,market_key text,label text,asset text,
  market_type text,metric_7d_pct numeric,comparison_as_of date,
  relative_7d_vs_era_pct numeric,current_drawdown_pct numeric,
  constituent_count integer
)
language plpgsql stable security invoker
set search_path=''
set statement_timeout='1s'
as $function$
declare
  v_serving uuid;
  v_asset text:=pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset,'all')));
begin
  if p_screen_key not in ('top-performers','worst-performers') then
    raise exception 'PERFORMANCE_SCREEN_KEY_INVALID';
  end if;
  if v_asset not in ('cards','sealed','graded','all') then
    raise exception 'PERFORMANCE_SCREEN_ASSET_INVALID';
  end if;
  if p_limit is null or p_limit<1 or p_limit>25 then
    raise exception 'PERFORMANCE_SCREEN_LIMIT_INVALID';
  end if;

  select s.generation_id into v_serving
  from public.pokemon_market_explorer_surface_serving_v2 s where s.singleton=1;
  if p_generation_id is distinct from v_serving and not exists (
    select 1 from public.pokemon_market_explorer_surface_generations_v2 g
    where g.generation_id=p_generation_id and g.state='VALIDATED'
  ) then raise exception 'PERFORMANCE_SCREEN_GENERATION_MISMATCH'; end if;

  return query
  with asset_ranked as (
    select row_number() over(order by
      case when p_screen_key='top-performers' then d.return_7d_pct end desc nulls last,
      case when p_screen_key='worst-performers' then d.return_7d_pct end asc nulls last,
      d.market_key)::integer asset_rank,d.*
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id and d.screen_eligible
      and d.availability='available' and d.history_available
      and d.return_7d_pct is not null
      and (v_asset='all' or d.asset=v_asset)
  )
  select r.asset_rank,p_screen_key,r.market_key,r.label,r.asset,r.scope_kind,
    r.return_7d_pct,r.comparison_as_of,null::numeric,r.current_drawdown_pct,
    r.constituent_count
  from asset_ranked r
  where r.asset_rank<=p_limit
  order by r.asset_rank;
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
to service_role;

commit;
