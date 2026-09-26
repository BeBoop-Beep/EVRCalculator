create or replace function public.get_pokemon_cards_daily_constituents_v4_shadow(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] default null::uuid[]
)
returns table(
  canonical_card_id uuid,
  set_id uuid,
  market_date date,
  market_price numeric,
  card_variant_id uuid,
  source text,
  captured_at date
)
language sql
stable
security invoker
set search_path=''
set "TimeZone"='America/Phoenix'
set work_mem='64MB'
as $function$
with requested_roots as materialized (
  select distinct x.set_id
  from unnest(coalesce(p_set_ids,array[]::uuid[])) as x(set_id)
  where x.set_id is not null
), dates as materialized (
  select gs::date as market_date
  from generate_series(p_start_date,p_end_date,interval '1 day') gs
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
), member_map as materialized (
  select r.set_id as root_set_id,r.set_id as member_set_id
  from requested_roots r
  union
  select r.set_id,child.id
  from requested_roots r
  join public.sets child
    on child.parent_opening_set_id=r.set_id
   and child.counts_toward_parent_set_value=true
), expanded_set_ids as materialized (
  select coalesce(array_agg(distinct m.member_set_id order by m.member_set_id),array[]::uuid[]) as ids
  from member_map m
), canonical_root_days as materialized (
  select r.set_id as root_set_id,d.market_date
  from requested_roots r
  cross join dates d
  join public.pokemon_set_value_daily_history h
    on h.set_id=r.set_id
   and h.snapshot_date=d.market_date
   and h.value_scope='standard'
  where h.source in (
    'canonical_root_set_public_rollout_v1',
    'canonical_root_set_public_rollout_candidate_v1',
    'canonical_root_standard_backfill_v1',
    'canonical_root_set_rollout_v1',
    'price_storage_v2_transition_anchor_v1',
    'price_storage_v2_serving_compatibility_v1'
  )
), canonical_member_days as materialized (
  select c.root_set_id,m.member_set_id,c.market_date
  from canonical_root_days c
  join member_map m on m.root_set_id=c.root_set_id
), legacy_chunks as materialized (
  select r.set_id as root_set_id,
         (p_start_date + (g.n*3))::date as from_date,
         least(p_end_date,(p_start_date + (g.n*3) + 2))::date as through_date
  from requested_roots r
  cross join lateral generate_series(
    0,
    greatest(0,((p_end_date-p_start_date)/3))
  ) as g(n)
  where p_start_date is not null
    and p_end_date is not null
    and p_end_date>=p_start_date
    and exists (
      select 1
      from dates d
      where d.market_date between (p_start_date + (g.n*3))::date
                              and least(p_end_date,(p_start_date + (g.n*3) + 2))::date
        and not exists (
          select 1
          from canonical_root_days c
          where c.root_set_id=r.set_id
            and c.market_date=d.market_date
        )
    )
), legacy_member_chunks as materialized (
  select lc.root_set_id,lc.from_date,lc.through_date,
         array_agg(m.member_set_id order by m.member_set_id) as member_ids
  from legacy_chunks lc
  join member_map m on m.root_set_id=lc.root_set_id
  group by lc.root_set_id,lc.from_date,lc.through_date
), legacy_base as materialized (
  select b.*
  from legacy_member_chunks lc
  cross join lateral public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    lc.member_ids,lc.from_date,lc.through_date,p_card_ids
  ) b
), near_mint as materialized (
  select c.id
  from public.conditions c
  where c.name='Near Mint'
  order by c.id
  limit 1
), exception_variants as materialized (
  select e.canonical_card_id,e.set_id,e.card_variant_id
  from public.pokemon_cards_daily_constituent_variant_exceptions_v1 e
  cross join expanded_set_ids a
  where e.enabled
    and e.set_id=any(a.ids)
    and (p_card_ids is null or e.canonical_card_id=any(p_card_ids))
), exception_intervals as materialized (
  select ev.canonical_card_id,ev.set_id,price.card_variant_id,
         price.condition_id,price.source,price.currency,price.market_price,
         price.effective_date as valid_from,
         lead(price.effective_date) over(
           partition by price.card_variant_id,price.condition_id,price.source,price.currency
           order by price.effective_date,price.id
         ) as valid_to
  from exception_variants ev
  join public.card_variant_price_events_v2 price
    on price.card_variant_id=ev.card_variant_id
  cross join near_mint nm
  where price.condition_id=nm.id
    and price.currency='USD'
), exception_source_daily as materialized (
  select d.market_date,ei.canonical_card_id,ei.set_id,ei.card_variant_id,
         ei.source,ei.market_price,observed.latest_observed_date,
         row_number() over(
           partition by d.market_date,ei.canonical_card_id
           order by observed.latest_observed_date desc nulls last,
                    ei.source desc,ei.card_variant_id
         ) as source_rank
  from dates d
  join exception_intervals ei
    on ei.valid_from<=d.market_date
   and (ei.valid_to is null or d.market_date<ei.valid_to)
   and ei.market_price>0
  cross join near_mint nm
  join lateral (
    select max(least(r.observed_through,d.market_date)) as latest_observed_date
    from public.card_variant_price_observation_ranges_v2 r
    where r.card_variant_id=ei.card_variant_id
      and r.condition_id=nm.id
      and r.source=ei.source
      and r.currency='USD'
      and r.observed_from<=d.market_date
  ) observed on observed.latest_observed_date is not null
), exception_overlay as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.latest_observed_date as captured_at
  from exception_source_daily x
  where x.source_rank=1
), legacy_compatible as materialized (
  select b.canonical_card_id,b.set_id,b.market_date,b.market_price,
         b.card_variant_id,b.source,b.captured_at
  from legacy_base b
  union all
  select o.canonical_card_id,o.set_id,o.market_date,o.market_price,
         o.card_variant_id,o.source,o.captured_at
  from exception_overlay o
  where not exists (
    select 1
    from legacy_base b
    where b.canonical_card_id=o.canonical_card_id
      and b.market_date=o.market_date
  )
), canonical_raw as materialized (
  select cmd.root_set_id,
         p.canonical_card_id,p.set_id,cmd.market_date,
         p.market_price,p.card_variant_id,p.source,p.captured_at
  from canonical_member_days cmd
  cross join lateral public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(
    cmd.member_set_id,cmd.market_date
  ) p
  where p_card_ids is null or p.canonical_card_id=any(p_card_ids)
), canonical_rows as materialized (
  select x.canonical_card_id,x.set_id,x.market_date,x.market_price,
         x.card_variant_id,x.source,x.captured_at
  from (
    select c.*,
           row_number() over(
             partition by c.canonical_card_id,c.market_date
             order by c.root_set_id,c.set_id,c.card_variant_id
           ) as rn
    from canonical_raw c
  ) x
  where x.rn=1
)
select l.canonical_card_id,l.set_id,l.market_date,l.market_price,
       l.card_variant_id,l.source,l.captured_at
from legacy_compatible l
where not exists (
  select 1
  from canonical_member_days c
  where c.member_set_id=l.set_id
    and c.market_date=l.market_date
)
union all
select c.canonical_card_id,c.set_id,c.market_date,c.market_price,
       c.card_variant_id,c.source,c.captured_at
from canonical_rows c
order by market_date,canonical_card_id,set_id;
$function$;

revoke all on function public.get_pokemon_cards_daily_constituents_v4_shadow(uuid[],date,date,uuid[]) from public,anon,authenticated;
grant execute on function public.get_pokemon_cards_daily_constituents_v4_shadow(uuid[],date,date,uuid[]) to postgres,service_role;
comment on function public.get_pokemon_cards_daily_constituents_v4_shadow(uuid[],date,date,uuid[]) is
'Candidate authority-routed Cards constituent reader equivalent to V3, but legacy-compatible work is internally split into at most three-day per-root ranges to avoid statement-timeout pathologies. Canonical provenance routing and pricing semantics are unchanged. Non-serving shadow.';
