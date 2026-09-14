-- Align the public Cards constituent boundary with canonical root Set Value.
--
-- Two bounded gaps are repaired here without changing the accepted Price Storage V2
-- reader or its acceptance hash:
--   1) a root Set Value may explicitly include child subsets;
--   2) a reviewed canonical card may have a legitimate reverse-only physical variant
--      that the accepted V2 reader deliberately excludes.
--
-- The public wrapper remains service-role only and still delegates ordinary cards to
-- get_pokemon_cards_daily_constituents_v2_hybrid_shadow().

create table if not exists public.pokemon_cards_daily_constituent_variant_exceptions_v1 (
    canonical_card_id uuid primary key references public.pokemon_canonical_cards(id) on delete cascade,
    set_id uuid not null references public.sets(id) on delete cascade,
    card_variant_id uuid not null unique references public.card_variants(id) on delete cascade,
    reason text not null,
    enabled boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.pokemon_cards_daily_constituent_variant_exceptions_v1 enable row level security;
revoke all on public.pokemon_cards_daily_constituent_variant_exceptions_v1 from public, anon, authenticated;
grant select on public.pokemon_cards_daily_constituent_variant_exceptions_v1 to service_role;

-- Seed by durable business identity, never by generated UUID literal. These three
-- Pokémon GO Peelable Ditto canonical cards are distinct collectible identities whose
-- reviewed canonical market variant is reverse-holo only.
insert into public.pokemon_cards_daily_constituent_variant_exceptions_v1 (
    canonical_card_id, set_id, card_variant_id, reason, enabled
)
select
    pcc.id,
    pcc.set_id,
    prices.card_variant_id,
    'pokemon_go_peelable_ditto_reverse_only_v1',
    true
from public.pokemon_canonical_cards pcc
join public.sets s on s.id = pcc.set_id
join public.pokemon_canonical_card_market_prices_latest prices
  on prices.canonical_card_id = pcc.id
join public.card_variants cv on cv.id = prices.card_variant_id
where s.canonical_key = 'pokMonGO'
  and pcc.name in (
      'Bidoof (Peelable Ditto)',
      'Numel (Peelable Ditto)',
      'Spinarak (Peelable Ditto)'
  )
  and cv.printing_type = 'reverse-holo'
  and coalesce(cv.special_type, '') = ''
on conflict (canonical_card_id) do update
set set_id = excluded.set_id,
    card_variant_id = excluded.card_variant_id,
    reason = excluded.reason,
    enabled = true;

-- Fail closed if the reviewed identity query ever stops resolving exactly the three
-- intended cards.
do $$
declare
    v_count integer;
begin
    select count(*) into v_count
    from public.pokemon_cards_daily_constituent_variant_exceptions_v1
    where reason = 'pokemon_go_peelable_ditto_reverse_only_v1'
      and enabled;
    if v_count <> 3 then
        raise exception 'expected exactly 3 enabled Pokémon GO Peelable Ditto constituent exceptions, found %', v_count;
    end if;
end
$$;

create or replace function public.get_pokemon_cards_daily_constituents(
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
set "TimeZone" to 'America/Phoenix'
set search_path to ''
as $function$
with requested_sets as materialized (
    select distinct requested_id as set_id
    from unnest(coalesce(p_set_ids, array[]::uuid[])) requested_id
), expanded_sets as materialized (
    select r.set_id
    from requested_sets r
    union
    select child.id
    from public.sets child
    join requested_sets parent on parent.set_id = child.parent_opening_set_id
    where child.counts_toward_parent_set_value = true
), call_args as materialized (
    select case
        when p_set_ids is null then null::uuid[]
        else coalesce((select array_agg(e.set_id order by e.set_id) from expanded_sets e), array[]::uuid[])
    end as set_ids
), base as materialized (
    select b.*
    from call_args a
    cross join lateral public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
        a.set_ids, p_start_date, p_end_date, p_card_ids
    ) b
), near_mint as materialized (
    select c.id
    from public.conditions c
    where c.name = 'Near Mint'
    limit 1
), exception_variants as materialized (
    select e.canonical_card_id, e.set_id, e.card_variant_id
    from public.pokemon_cards_daily_constituent_variant_exceptions_v1 e
    cross join call_args a
    where e.enabled
      and (a.set_ids is null or e.set_id = any(a.set_ids))
      and (p_card_ids is null or e.canonical_card_id = any(p_card_ids))
), event_intervals as materialized (
    select
        ev.canonical_card_id,
        ev.set_id,
        price.card_variant_id,
        price.condition_id,
        price.source,
        price.currency,
        price.market_price,
        price.effective_date as valid_from,
        lead(price.effective_date) over (
            partition by price.card_variant_id, price.condition_id, price.source, price.currency
            order by price.effective_date, price.id
        ) as valid_to
    from exception_variants ev
    join public.card_variant_price_events_v2 price
      on price.card_variant_id = ev.card_variant_id
    cross join near_mint nm
    where price.condition_id = nm.id
      and price.currency = 'USD'
), dates as materialized (
    select gs::date as market_date
    from generate_series(p_start_date, p_end_date, interval '1 day') gs
    where p_start_date is not null
      and p_end_date is not null
      and p_end_date >= p_start_date
), exception_source_daily as materialized (
    select
        d.market_date,
        ei.canonical_card_id,
        ei.set_id,
        ei.card_variant_id,
        ei.source,
        ei.market_price,
        observed.latest_observed_date,
        row_number() over (
            partition by d.market_date, ei.canonical_card_id
            order by observed.latest_observed_date desc nulls last,
                     ei.source desc,
                     ei.card_variant_id
        ) as source_rank
    from dates d
    join event_intervals ei
      on ei.valid_from <= d.market_date
     and (ei.valid_to is null or d.market_date < ei.valid_to)
     and ei.market_price > 0
    cross join near_mint nm
    join lateral (
        select max(least(r.observed_through, d.market_date)) as latest_observed_date
        from public.card_variant_price_observation_ranges_v2 r
        where r.card_variant_id = ei.card_variant_id
          and r.condition_id = nm.id
          and r.source = ei.source
          and r.currency = 'USD'
          and r.observed_from <= d.market_date
    ) observed on observed.latest_observed_date is not null
), overlay as materialized (
    select
        x.canonical_card_id,
        x.set_id,
        x.market_date,
        x.market_price,
        x.card_variant_id,
        x.source,
        x.latest_observed_date as captured_at
    from exception_source_daily x
    where x.source_rank = 1
)
select
    b.canonical_card_id,
    b.set_id,
    b.market_date,
    b.market_price,
    b.card_variant_id,
    b.source,
    b.captured_at
from base b
union all
select
    o.canonical_card_id,
    o.set_id,
    o.market_date,
    o.market_price,
    o.card_variant_id,
    o.source,
    o.captured_at
from overlay o
where not exists (
    select 1
    from base b
    where b.canonical_card_id = o.canonical_card_id
      and b.market_date = o.market_date
)
order by market_date, canonical_card_id;
$function$;

-- Preserve the existing least-privilege RPC surface.
revoke all on function public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) from public, anon, authenticated;
grant execute on function public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) to service_role;
