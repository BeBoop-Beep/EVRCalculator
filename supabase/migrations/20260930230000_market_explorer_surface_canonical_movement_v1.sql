begin;

-- Resolve surface movement from observed market dates. Fixed windows use true
-- elapsed-calendar targets and the newest observation on or before each target;
-- no row is synthesized for a missing date.
create or replace function public.get_pokemon_market_explorer_surface_movement_v1(
  p_generation_id uuid,
  p_as_of date
)
returns table(
  market_key text,
  endpoint_date date,
  endpoint_index numeric,
  baseline_7d_date date,
  return_7d_pct numeric,
  baseline_30d_date date,
  return_30d_pct numeric,
  baseline_90d_date date,
  return_90d_pct numeric,
  baseline_1y_date date,
  return_1y_pct numeric
)
language sql stable security invoker
set search_path=''
set statement_timeout='5s'
as $function$
  with markets as (
    select d.market_key
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id
  )
  select m.market_key,
    e.market_date,e.index_value,
    b7.market_date,
    case when e.index_value>0 and b7.index_value>0 then (e.index_value/b7.index_value-1.0)*100.0 end,
    b30.market_date,
    case when e.index_value>0 and b30.index_value>0 then (e.index_value/b30.index_value-1.0)*100.0 end,
    b90.market_date,
    case when e.index_value>0 and b90.index_value>0 then (e.index_value/b90.index_value-1.0)*100.0 end,
    b365.market_date,
    case when e.index_value>0 and b365.index_value>0 then (e.index_value/b365.index_value-1.0)*100.0 end
  from markets m
  left join lateral (
    select h.market_date,h.index_value
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id and h.market_key=m.market_key
      and h.market_date=p_as_of
    limit 1
  ) e on true
  left join lateral (
    select h.market_date,h.index_value
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id and h.market_key=m.market_key
      and h.market_date<=p_as_of-7
    order by h.market_date desc limit 1
  ) b7 on true
  left join lateral (
    select h.market_date,h.index_value
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id and h.market_key=m.market_key
      and h.market_date<=p_as_of-30
    order by h.market_date desc limit 1
  ) b30 on true
  left join lateral (
    select h.market_date,h.index_value
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id and h.market_key=m.market_key
      and h.market_date<=p_as_of-90
    order by h.market_date desc limit 1
  ) b90 on true
  left join lateral (
    select h.market_date,h.index_value
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id and h.market_key=m.market_key
      and h.market_date<=p_as_of-365
    order by h.market_date desc limit 1
  ) b365 on true;
$function$;

revoke all on function public.get_pokemon_market_explorer_surface_movement_v1(uuid,date)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_surface_movement_v1(uuid,date)
to service_role;

-- Replace only the metric finalizer. History construction, identities, values,
-- eligibility, and publication remain unchanged.
create or replace function public.finalize_pokemon_market_explorer_surface_metrics_v2(
  p_generation_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql volatile security invoker
set search_path=''
set statement_timeout='60s'
as $function$
declare v_rows integer;
begin
  with running as (
    select h.*,
      max(h.index_value) over(partition by h.generation_id,h.market_key
        order by h.market_date rows unbounded preceding) running_high
    from public.pokemon_market_explorer_surface_history_v2 h
    where h.generation_id=p_generation_id
  ), stats as (
    select market_key,min(market_date) history_start,max(market_date) history_end,
      count(*)::integer point_count,
      max(tracked_value) filter(where market_date=p_market_date) end_tracked,
      max(constituent_count) filter(where market_date=p_market_date) end_count,
      max(index_value) since_high,
      min((index_value/nullif(running_high,0)-1.0)*100.0) max_drawdown
    from running group by market_key
  ), movement as materialized (
    select * from public.get_pokemon_market_explorer_surface_movement_v1(p_generation_id,p_market_date)
  )
  update public.pokemon_market_explorer_surface_directory_v2 d
  set current_tracked_value=s.end_tracked,current_index_value=m.endpoint_index,
      history_available=(m.endpoint_index is not null),
      history_start_date=s.history_start,history_end_date=s.history_end,
      history_point_count=s.point_count,
      constituent_count=coalesce(s.end_count,d.constituent_count),
      return_7d_pct=m.return_7d_pct,return_30d_pct=m.return_30d_pct,
      return_90d_pct=m.return_90d_pct,return_1y_pct=m.return_1y_pct,
      current_drawdown_pct=case when m.endpoint_index is not null and s.since_high>0
        then (m.endpoint_index/s.since_high-1.0)*100.0 end,
      max_drawdown_pct=s.max_drawdown
  from stats s join movement m using(market_key)
  where d.generation_id=p_generation_id and d.market_key=s.market_key;
  get diagnostics v_rows=row_count;
  return jsonb_build_object('updatedMarkets',v_rows);
end;
$function$;

revoke all on function public.finalize_pokemon_market_explorer_surface_metrics_v2(uuid,date)
from public,anon,authenticated;
grant execute on function public.finalize_pokemon_market_explorer_surface_metrics_v2(uuid,date)
to service_role;

-- Rank once across the eligible global universe, then apply an asset filter.
-- This preserves the rank's meaning and returns no fabricated graded rows.
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
  with globally_ranked as (
    select row_number() over(order by
      case when p_screen_key='top-performers' then d.return_7d_pct end desc nulls last,
      case when p_screen_key='worst-performers' then d.return_7d_pct end asc nulls last,
      d.market_key)::integer global_rank,d.*
    from public.pokemon_market_explorer_surface_directory_v2 d
    where d.generation_id=p_generation_id and d.screen_eligible
      and d.availability='available' and d.history_available
      and d.return_7d_pct is not null
  )
  select r.global_rank,p_screen_key,r.market_key,r.label,r.asset,r.scope_kind,
    r.return_7d_pct,r.comparison_as_of,null::numeric,r.current_drawdown_pct,
    r.constituent_count
  from globally_ranked r
  where r.global_rank<=p_limit and (v_asset='all' or r.asset=v_asset)
  order by r.global_rank;
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer)
to service_role;

commit;
