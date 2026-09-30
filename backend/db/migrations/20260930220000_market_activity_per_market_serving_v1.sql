-- FMA-2/FMA-1 reconciliation: market-scoped Activity publication authority.
-- Additive serving replacement; canonical pricing and Explorer authority are unchanged.

begin;
set local lock_timeout = '2s';
set local statement_timeout = '30s';

create table public.market_activity_market_serving_v1 (
  market_key text primary key,
  activity_generation_id uuid references public.market_activity_generations_v1(activity_generation_id) on delete restrict,
  previous_activity_generation_id uuid references public.market_activity_generations_v1(activity_generation_id) on delete restrict,
  promoted_at timestamptz
);

-- Preserve a legacy singleton publication only when its generation has exactly
-- one roster. Production has not applied FMA yet, but this keeps the ordered
-- migration chain safe for any isolated/staging application of FMA-1.
insert into public.market_activity_market_serving_v1(
  market_key, activity_generation_id, previous_activity_generation_id, promoted_at)
select roster.market_key, serving.activity_generation_id,
       serving.previous_activity_generation_id, serving.promoted_at
from public.market_activity_serving_v1 serving
join lateral (
  select min(market_key) as market_key
  from public.market_activity_rosters_v1
  where activity_generation_id = serving.activity_generation_id
  having count(*) = 1
) roster on true
where serving.singleton = 1 and serving.activity_generation_id is not null
on conflict (market_key) do nothing;

create or replace function public.promote_market_activity_generation_v1(p_activity_generation_id uuid)
returns boolean language plpgsql security definer set search_path = public, pg_temp as $$
declare
  old_id uuid;
  pinned_surface uuid;
  served_surface uuid;
  target_market text;
  market_count integer;
begin
  select g.surface_generation_id, count(r.market_key), min(r.market_key)
    into pinned_surface, market_count, target_market
  from public.market_activity_generations_v1 g
  left join public.market_activity_rosters_v1 r
    on r.activity_generation_id = g.activity_generation_id
  where g.activity_generation_id = p_activity_generation_id
    and g.state = 'VALIDATED'
  group by g.surface_generation_id;

  if not found or market_count <> 1 or target_market is null then
    return false;
  end if;

  if pinned_surface is not null then
    select generation_id into served_surface
    from public.pokemon_market_explorer_surface_serving_v2
    where singleton = 1;
    if served_surface is distinct from pinned_surface then
      return false;
    end if;
  end if;

  insert into public.market_activity_market_serving_v1(market_key)
  values(target_market)
  on conflict (market_key) do nothing;

  select activity_generation_id into old_id
  from public.market_activity_market_serving_v1
  where market_key = target_market
  for update;

  update public.market_activity_generations_v1
  set serving_state = 'RETAINED'
  where activity_generation_id = old_id
    and activity_generation_id <> p_activity_generation_id;

  update public.market_activity_generations_v1
  set serving_state = 'SERVING'
  where activity_generation_id = p_activity_generation_id;

  update public.market_activity_market_serving_v1
  set activity_generation_id = p_activity_generation_id,
      previous_activity_generation_id =
        case when old_id is distinct from p_activity_generation_id
             then old_id else previous_activity_generation_id end,
      promoted_at = clock_timestamp()
  where market_key = target_market;

  return true;
end $$;

-- The global singleton is fully replaced; retaining it would leave a second,
-- ambiguous publication authority.
drop table public.market_activity_serving_v1;

alter table public.market_activity_market_serving_v1 enable row level security;
revoke all on table public.market_activity_market_serving_v1 from public,anon,authenticated,service_role;
grant select,insert on table public.market_activity_market_serving_v1 to service_role;
grant update(activity_generation_id,previous_activity_generation_id,promoted_at)
  on public.market_activity_market_serving_v1 to service_role;

revoke all on function public.promote_market_activity_generation_v1(uuid) from public,anon,authenticated;
grant execute on function public.promote_market_activity_generation_v1(uuid) to service_role;

commit;

