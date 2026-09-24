-- DATABASE-AUTHORITY REVIEWED REPLACEMENT FOR PR #357 PROTOTYPE.
-- This file is intentionally DB-only.  It preserves the existing edition taxonomy
-- from 20260904173530_canonical_market_root_set_universe_v1.sql and adds fail-closed
-- guards for scope identity, fixed-basket history, and date-pinned constituents.
--
-- Rollout compatibility: before the application begins emitting any non-standard
-- marketScope rows, the current generic snapshot remains readable.  As soon as a
-- scoped row appears, the complete explicit-scope contract is enforced for every
-- root in that snapshot; no edition-split generic market may coexist with it.

-- Snapshot count contract: set_count remains the number of distinct root Sets.
-- market_count is the number of published Set-market identities in payload_json.sets.
-- Before scoped activation they are equal; after activation market_count may be larger.
alter table public.pokemon_explore_set_value_snapshot_latest
  add column if not exists market_count integer;

update public.pokemon_explore_set_value_snapshot_latest
set market_count=jsonb_array_length(coalesce(payload_json->'sets','[]'::jsonb))
where market_count is null;

alter table public.pokemon_explore_set_value_snapshot_latest
  alter column market_count set not null;

do $market_count$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid='public.pokemon_explore_set_value_snapshot_latest'::regclass
      and conname='pokemon_explore_set_value_snapshot_market_count_check'
  ) then
    alter table public.pokemon_explore_set_value_snapshot_latest
      add constraint pokemon_explore_set_value_snapshot_market_count_check
      check (market_count>=0 and market_count>=set_count);
  end if;
end;
$market_count$;

comment on column public.pokemon_explore_set_value_snapshot_latest.set_count is
'Distinct root Set count represented by the Global Set Market snapshot.';
comment on column public.pokemon_explore_set_value_snapshot_latest.market_count is
'Published Set-market identity count; equals jsonb_array_length(payload_json->sets) and may exceed set_count when edition scopes are explicit.';

create or replace view public.pokemon_market_set_scope_contract_v1
with (security_invoker = true)
as
with root_universe as (
  select distinct v.set_id
  from public.pokemon_market_root_set_value_latest_v1 v
  union
  select r.set_id
  from public.pokemon_edition_split_root_sets_v2 r
), scope_universe as (
  select
    u.set_id,
    coalesce(r.profile,'standard')::text as profile,
    x.market_scope
  from root_universe u
  left join public.pokemon_edition_split_root_sets_v2 r on r.set_id=u.set_id
  cross join lateral (
    select unnest(
      case
        when r.profile='base_three_printings'
          then array['first_edition','shadowless','unlimited']::text[]
        when r.profile='edition_split'
          then array['first_edition','unlimited']::text[]
        else array['standard']::text[]
      end
    ) as market_scope
  ) x
)
select
  u.set_id,
  s.name as base_set_name,
  u.profile,
  u.market_scope,
  case when u.market_scope='standard'
    then 'set:' || u.set_id::text
    else 'set:' || u.set_id::text || ':' || u.market_scope
  end as market_key,
  case u.market_scope
    when 'standard' then s.name
    when 'first_edition' then s.name || ' - 1st Edition'
    when 'unlimited' then s.name || ' - Unlimited'
    when 'shadowless' then s.name || ' - Shadowless'
    else s.name || ' - ' || u.market_scope
  end as display_label,
  v.set_value as authority_set_value,
  case when coalesce(v.publishable_100pct,false) then v.set_value else null end as public_current_value,
  v.expected_card_count,
  v.resolved_variant_count,
  v.priced_card_count,
  v.coverage_pct,
  v.oldest_component_price_date,
  v.newest_component_price_date,
  coalesce(v.quality_status,
    case when u.profile='standard' then 'unavailable' else 'scope_authority_missing' end
  )::text as quality_status,
  coalesce(v.publishable_100pct,false) as publishable_100pct
from scope_universe u
join public.sets s on s.id=u.set_id
left join public.pokemon_market_root_set_value_latest_v1 v
  on v.set_id=u.set_id and v.market_scope=u.market_scope;
revoke all on public.pokemon_market_set_scope_contract_v1 from public,anon,authenticated;
grant select on public.pokemon_market_set_scope_contract_v1 to service_role;

create or replace function public.validate_pokemon_market_set_scope_payload_v1(
  p_payload jsonb,
  p_declared_market_count integer default null,
  p_declared_root_set_count integer default null
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
declare
  v_market_count integer;
  v_root_set_count integer;
  v_scoped_contract_active boolean;
begin
  if p_payload is null or jsonb_typeof(p_payload->'sets') is distinct from 'array' then
    raise exception 'Set Market payload must contain a sets array';
  end if;

  v_market_count := jsonb_array_length(p_payload->'sets');
  if p_declared_market_count is not null and v_market_count <> p_declared_market_count then
    raise exception 'Set Market payload count mismatch: payload=% declared=%',
      v_market_count,p_declared_market_count;
  end if;

  select count(distinct (e->>'setId')::uuid)::integer
    into v_root_set_count
  from jsonb_array_elements(p_payload->'sets') e;

  if p_declared_root_set_count is not null and v_root_set_count <> p_declared_root_set_count then
    raise exception 'Set Market root count mismatch: payload=% declared=%',
      v_root_set_count,p_declared_root_set_count;
  end if;

  select exists(
    select 1 from jsonb_array_elements(p_payload->'sets') e
    where coalesce(nullif(e->>'marketScope',''),'standard') <> 'standard'
  ) into v_scoped_contract_active;

  if exists (
    select 1
    from (
      select
        case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end as computed_key,
        count(*) as n
      from jsonb_array_elements(p_payload->'sets') e
      group by 1
      having count(*)>1
    ) d
  ) then
    raise exception 'Set Market payload contains duplicate market identity';
  end if;

  if v_scoped_contract_active then
    if exists (
      select 1
      from jsonb_array_elements(p_payload->'sets') e
      where nullif(e->>'marketScope','') is null
         or nullif(e->>'marketKey','') is null
         or nullif(e->>'baseSetName','') is null
    ) then
      raise exception 'Scoped Set Market payload requires marketScope, marketKey and baseSetName on every row';
    end if;

    if exists (
      select 1
      from jsonb_array_elements(p_payload->'sets') e
      where e->>'marketKey' is distinct from
        case when e->>'marketScope'='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end
    ) then
      raise exception 'Set Market payload marketKey disagrees with machine scope identity';
    end if;

    if exists (
      with actual as (
        select distinct (e->>'setId')::uuid as set_id,e->>'marketScope' as market_scope
        from jsonb_array_elements(p_payload->'sets') e
      ), roots as (
        select distinct set_id from actual
      ), expected as (
        select r.set_id,e.market_scope
        from roots r
        left join public.pokemon_edition_split_root_sets_v2 x on x.set_id=r.set_id
        cross join lateral (
          select unnest(
            case
              when x.profile='base_three_printings'
                then array['first_edition','shadowless','unlimited']::text[]
              when x.profile='edition_split'
                then array['first_edition','unlimited']::text[]
              else array['standard']::text[]
            end
          ) as market_scope
        ) e
      ), diff as (
        (select * from actual except select * from expected)
        union all
        (select * from expected except select * from actual)
      )
      select 1 from diff limit 1
    ) then
      raise exception 'Scoped Set Market payload does not exactly match authoritative root scope identities';
    end if;
  end if;

  return jsonb_build_object(
    'status','valid',
    'marketCount',v_market_count,
    'rootSetCount',v_root_set_count,
    'scopedContractActive',v_scoped_contract_active,
    'scopeContractVersion',case when v_scoped_contract_active then 'pokemon-set-market-scope-v1' else null end
  );
end;
$function$;

revoke all on function public.validate_pokemon_market_set_scope_payload_v1(jsonb,integer,integer)
  from public,anon,authenticated;
grant execute on function public.validate_pokemon_market_set_scope_payload_v1(jsonb,integer,integer)
  to service_role;

create or replace function public.validate_pokemon_market_scoped_history_baskets_v1(
  p_payload jsonb
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '60s'
as $function$
declare
  v_scoped_count integer;
begin
  with requested as (
    select distinct (e->>'setId')::uuid set_id,e->>'marketScope' market_scope
    from jsonb_array_elements(coalesce(p_payload->'sets','[]'::jsonb)) e
    where coalesce(nullif(e->>'marketScope',''),'standard')<>'standard'
  )
  select count(*)::integer into v_scoped_count from requested;

  if v_scoped_count=0 then
    return jsonb_build_object('status','legacy_compatible','scopedMarketCount',0);
  end if;

  if exists (
    with requested as (
      select distinct (e->>'setId')::uuid set_id,e->>'marketScope' market_scope
      from jsonb_array_elements(p_payload->'sets') e
      where e->>'marketScope'<>'standard'
    )
    select 1
    from public.pokemon_market_root_set_value_daily_history_v2_shadow h
    join requested r on r.set_id=h.set_id and r.market_scope=h.market_scope
    where h.certified_on_date
    group by h.set_id,h.market_scope
    having count(distinct h.expected_card_count)>1
    limit 1
  ) then
    raise exception 'Scoped Set Market history basket changed expected-card membership across certified dates';
  end if;

  if exists (
    with requested as (
      select distinct (e->>'setId')::uuid set_id,e->>'marketScope' market_scope
      from jsonb_array_elements(p_payload->'sets') e
      where e->>'marketScope'<>'standard'
    )
    select 1
    from public.pokemon_market_root_set_value_daily_history_v2_shadow h
    join requested r on r.set_id=h.set_id and r.market_scope=h.market_scope
    where h.certified_on_date and h.priced_card_count<>h.expected_card_count
    limit 1
  ) then
    raise exception 'Scoped Set Market history marks an incomplete basket certified';
  end if;

  if exists (
    with requested as (
      select distinct (e->>'setId')::uuid set_id,e->>'marketScope' market_scope
      from jsonb_array_elements(p_payload->'sets') e
      where e->>'marketScope'<>'standard'
    ), members as (
      select r.set_id root_set_id,r.set_id member_set_id from requested r
      union
      select r.set_id,s.id
      from requested r
      join public.sets s on s.parent_opening_set_id=r.set_id
        and s.counts_toward_parent_set_value=true
    ), cards as (
      select m.root_set_id,c.id canonical_card_id,c.set_id
      from members m
      join public.pokemon_canonical_cards c on c.set_id=m.member_set_id
      where c.set_value_eligible=true
    ), scoped_variants as (
      select c.root_set_id,c.canonical_card_id,
        case meta.edition
          when '1st-edition' then 'first_edition'
          when 'unlimited' then 'unlimited'
          when 'shadowless' then 'shadowless'
          else null
        end as market_scope,
        count(distinct meta.card_variant_id) as variant_count
      from cards c
      join public.pokemon_market_explorer_card_current_metadata meta
        on meta.canonical_card_id=c.canonical_card_id and meta.set_id=c.set_id
      where meta.edition in ('1st-edition','unlimited','shadowless')
      group by c.root_set_id,c.canonical_card_id,
        case meta.edition
          when '1st-edition' then 'first_edition'
          when 'unlimited' then 'unlimited'
          when 'shadowless' then 'shadowless'
          else null
        end
    )
    select 1
    from scoped_variants v
    join requested r on r.set_id=v.root_set_id and r.market_scope=v.market_scope
    where v.variant_count>1
    limit 1
  ) then
    raise exception 'Scoped Set Market fixed-basket invariant failed: multiple physical variants for canonical+scope';
  end if;

  return jsonb_build_object(
    'status','valid',
    'scopedMarketCount',v_scoped_count,
    'basketContract','fixed-physical-variant-per-canonical-scope-v1'
  );
end;
$function$;

revoke all on function public.validate_pokemon_market_scoped_history_baskets_v1(jsonb)
  from public,anon,authenticated;
grant execute on function public.validate_pokemon_market_scoped_history_baskets_v1(jsonb)
  to service_role;

create table if not exists public.pokemon_market_scoped_history_large_move_reviews_v1 (
  set_id uuid not null references public.sets(id) on delete cascade,
  market_scope text not null check (market_scope in ('first_edition','unlimited','shadowless')),
  market_date date not null,
  classification text not null check (classification in (
    'REAL_PRICE_MOVE','STALE_TO_FRESH_REPRICE','SOURCE_DEFECT','OBSERVATION_DEFECT','OTHER'
  )),
  history_action text not null check (history_action in ('accept','withhold')),
  explanation text not null,
  evidence jsonb not null default '{}'::jsonb,
  reviewed_at timestamptz not null default timezone('utc',now()),
  primary key (set_id,market_scope,market_date)
);

alter table public.pokemon_market_scoped_history_large_move_reviews_v1 enable row level security;
revoke all on public.pokemon_market_scoped_history_large_move_reviews_v1
  from public,anon,authenticated;
grant select,insert,update,delete on public.pokemon_market_scoped_history_large_move_reviews_v1
  to service_role;

insert into public.pokemon_market_scoped_history_large_move_reviews_v1
  (set_id,market_scope,market_date,classification,history_action,explanation,evidence)
select s.id,x.market_scope,x.market_date,x.classification,x.history_action,x.explanation,x.evidence
from (
  values
    ('Neo Discovery','first_edition',date '2026-05-10','SOURCE_DEFECT','withhold',
      'Umbreon 1st Edition Near Mint fell from 1799.99 to 974.47 while LP remained 1500.00.',
      jsonb_build_object('dominantCard','Umbreon','previousNm',1799.99,'newNm',974.47,'lp',1500.00)),
    ('Neo Discovery','first_edition',date '2026-05-14','SOURCE_DEFECT','withhold',
      'Umbreon 1st Edition Near Mint snapped back from 974.47 to 1799.99 with LP unchanged at 1500.00.',
      jsonb_build_object('dominantCard','Umbreon','previousNm',974.47,'newNm',1799.99,'lp',1500.00)),
    ('Neo Discovery','first_edition',date '2026-05-18','SOURCE_DEFECT','withhold',
      'Umbreon 1st Edition Near Mint again fell below unchanged LP: 1799.99 to 982.97 versus LP 1500.00.',
      jsonb_build_object('dominantCard','Umbreon','previousNm',1799.99,'newNm',982.97,'lp',1500.00)),
    ('Neo Discovery','first_edition',date '2026-05-21','SOURCE_DEFECT','withhold',
      'Umbreon 1st Edition Near Mint collapsed to 165.95 while LP remained 1500.00.',
      jsonb_build_object('dominantCard','Umbreon','previousNm',982.97,'newNm',165.95,'lp',1500.00)),
    ('Neo Genesis','first_edition',date '2026-05-12','SOURCE_DEFECT','withhold',
      'Lugia 1st Edition Near Mint appeared at 165.50 below LP 1299.96, MP 1034.34, HP 751.00 and DMG 600.00.',
      jsonb_build_object('dominantCard','Lugia','newNm',165.50,'lp',1299.96,'mp',1034.34,'hp',751.00,'dmg',600.00)),
    ('Team Rocket','first_edition',date '2026-05-23','SOURCE_DEFECT','withhold',
      'Dark Charizard 1st Edition Near Mint fell from 707.16 to 247.15 below LP 493.06, MP 390.80 and HP 303.20.',
      jsonb_build_object('dominantCard','Dark Charizard','previousNm',707.16,'newNm',247.15,'lp',493.06,'mp',390.80,'hp',303.20)),
    ('Neo Discovery','first_edition',date '2026-08-19','STALE_TO_FRESH_REPRICE','accept',
      'Fresh Near Mint coverage resumed for high-value Umbreon and Ursaring variants after NM gaps; new levels persisted.',
      jsonb_build_object('dominantCards',jsonb_build_array('Umbreon','Ursaring'),'umbreonNewNm',300.00,'ursaringNewNm',154.99)),
    ('Neo Discovery','unlimited',date '2026-08-31','REAL_PRICE_MOVE','accept',
      'Umbreon Unlimited Near Mint repriced from 500.00 to 752.74 and the new TCGPlayer level persisted across subsequent observations.',
      jsonb_build_object('dominantCard','Umbreon','previousNm',500.00,'newNm',752.74)),
    ('Neo Genesis','first_edition',date '2026-08-02','STALE_TO_FRESH_REPRICE','accept',
      'Typhlosion 1st Edition Near Mint coverage resumed at 699.99 after an NM gap while worse-condition observations remained fresh; the NM level persisted.',
      jsonb_build_object('dominantCard','Typhlosion','previousCarriedNm',86.00,'newNm',699.99,'lp',435.00)),
    ('Fossil','first_edition',date '2026-07-29','REAL_PRICE_MOVE','accept',
      'Gengar 1st Edition Near Mint repriced from 315.25 to 601.49 and the new TCGPlayer level persisted for multiple days.',
      jsonb_build_object('dominantCard','Gengar','previousNm',315.25,'newNm',601.49))
) as x(set_name,market_scope,market_date,classification,history_action,explanation,evidence)
join public.sets s on s.name=x.set_name and s.parent_opening_set_id is null
on conflict (set_id,market_scope,market_date) do update
set classification=excluded.classification,
    history_action=excluded.history_action,
    explanation=excluded.explanation,
    evidence=excluded.evidence,
    reviewed_at=timezone('utc',now());

create or replace view public.pokemon_market_scoped_history_market_certification_v1
with (security_invoker = true)
as
with scoped as (
  select distinct h.set_id,h.market_scope
  from public.pokemon_market_root_set_value_daily_history_v2_shadow h
  join public.pokemon_edition_split_root_sets_v2 r on r.set_id=h.set_id
  where h.market_scope<>'standard'
), ordered as (
  select h.set_id,h.market_scope,h.market_date,h.set_value,
         lag(h.set_value) over(
           partition by h.set_id,h.market_scope order by h.market_date
         ) as previous_value
  from public.pokemon_market_root_set_value_daily_history_v2_shadow h
  join scoped s on s.set_id=h.set_id and s.market_scope=h.market_scope
  where h.certified_on_date=true
), large_moves as (
  select o.set_id,o.market_scope,o.market_date,
         (o.set_value/nullif(o.previous_value,0)-1.0) as return_fraction
  from ordered o
  where o.previous_value>0
    and abs(o.set_value/nullif(o.previous_value,0)-1.0)>=0.10
), reviewed as (
  select m.set_id,m.market_scope,m.market_date,m.return_fraction,
         r.classification,r.history_action,r.explanation
  from large_moves m
  left join public.pokemon_market_scoped_history_large_move_reviews_v1 r
    on r.set_id=m.set_id
   and r.market_scope=m.market_scope
   and r.market_date=m.market_date
), summary as (
  select s.set_id,s.market_scope,
         count(r.market_date)::integer as large_move_count,
         count(*) filter(where r.market_date is not null and r.history_action='accept')::integer as accepted_large_move_count,
         count(*) filter(where r.market_date is not null and coalesce(r.history_action,'withhold')<>'accept')::integer as blocking_large_move_count
  from scoped s
  left join reviewed r on r.set_id=s.set_id and r.market_scope=s.market_scope
  group by s.set_id,s.market_scope
)
select
  s.set_id,s.market_scope,s.large_move_count,s.accepted_large_move_count,s.blocking_large_move_count,
  (s.blocking_large_move_count=0) as history_publishable,
  case
    when s.blocking_large_move_count>0 then 'withheld_source_review'
    when s.large_move_count>0 then 'reviewed'
    else 'no_large_move_exception'
  end::text as certification_status,
  case
    when s.blocking_large_move_count>0 then 'One or more >=10% certified scoped moves are rejected or unreviewed.'
    when s.large_move_count>0 then 'All >=10% certified scoped moves have explicit accepted reviews.'
    else null
  end::text as certification_reason
from summary s;

revoke all on public.pokemon_market_scoped_history_market_certification_v1
  from public,anon,authenticated;
grant select on public.pokemon_market_scoped_history_market_certification_v1
  to service_role;

comment on table public.pokemon_market_scoped_history_large_move_reviews_v1 is
'Explicit review ledger for large scoped vintage history moves.  Source defects are withheld rather than silently published; accepted real/stale-to-fresh repricings remain auditable.';

comment on view public.pokemon_market_scoped_history_market_certification_v1 is
'Fail-closed scoped-history certification.  Any >=10% certified move without an explicit accept review withholds that market history from new prepared generations.';

create or replace function public.get_pokemon_market_root_set_card_prices_as_of_v1(
  p_root_set_id uuid,
  p_market_scope text,
  p_market_date date
)
returns table(
  root_set_id uuid,
  root_set_name text,
  member_set_id uuid,
  member_set_name text,
  member_type text,
  market_scope text,
  canonical_card_id uuid,
  card_name text,
  card_number text,
  rarity text,
  canonical_review_status text,
  card_variant_id uuid,
  edition text,
  printing_type text,
  special_type text,
  identity_basis text,
  market_price numeric,
  captured_at date,
  source text,
  price_selection_reason text
)
language sql
stable
security invoker
set search_path = ''
set "TimeZone" = 'America/Phoenix'
set statement_timeout = '60s'
as $function$
with near_mint as (
  select c.id
  from public.conditions c
  where lower(c.name)='near mint'
  order by c.id
  limit 1
), fixed_identity as materialized (
  select q.*
  from public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) q
  where q.market_scope=p_market_scope
    and p_market_scope in ('first_edition','unlimited','shadowless')
), repriced as (
  select
    q.root_set_id,q.root_set_name,q.member_set_id,q.member_set_name,q.member_type,
    q.market_scope,q.canonical_card_id,q.card_name,q.card_number,q.rarity,
    q.canonical_review_status,q.card_variant_id,q.edition,q.printing_type,
    q.special_type,q.identity_basis,
    i.market_price,
    obs.latest_observed_date as captured_at,
    case when i.market_price is not null then 'TCGPlayer'::text else null::text end as source,
    case
      when q.card_variant_id is null then 'missing_required_edition_variant'
      when i.market_price is null then 'required_edition_variant_missing_nm_price_as_of'
      else 'edition_exact_fixed_variant_as_of'
    end::text as price_selection_reason
  from fixed_identity q
  left join public.pokemon_market_price_intervals_v2_shadow i
    on i.card_variant_id=q.card_variant_id
   and i.valid_from<=p_market_date
   and (i.valid_to is null or p_market_date<i.valid_to)
   and i.market_price>0
  cross join near_mint nm
  left join lateral (
    select max(least(r.observed_through,p_market_date)) as latest_observed_date
    from public.card_variant_price_observation_ranges_v2 r
    where r.card_variant_id=q.card_variant_id
      and r.condition_id=nm.id
      and r.source='TCGPlayer'
      and r.currency='USD'
      and r.observed_from<=p_market_date
  ) obs on true
)
select * from repriced;
$function$;

revoke all on function public.get_pokemon_market_root_set_card_prices_as_of_v1(uuid,text,date)
  from public,anon,authenticated;
grant execute on function public.get_pokemon_market_root_set_card_prices_as_of_v1(uuid,text,date)
  to service_role;

comment on view public.pokemon_market_set_scope_contract_v1 is
'Internal machine-identity authority for Set markets.  Standard roots expose one set:<id> market; edition-split roots expose only explicit scope identities.';

comment on function public.get_pokemon_market_root_set_card_prices_as_of_v1(uuid,text,date) is
'Internal date-pinned constituent reader for explicit vintage edition scopes.  Physical identity comes from canonical root-scope authority; only the price is resolved as-of the requested date.';

-- Publish edition-split vintage Sets as explicit market identities.
--
-- Contract:
--   standard roots -> set:<set_id>
--   edition roots  -> set:<set_id>:first_edition / unlimited / shadowless
-- No generic blended Set market is published for an edition-split root.
--
-- This migration rewrites only the currently deployed prepared Set-directory,
-- Set-history, lightweight sync, and prepared constituent-staging sections.
-- Every rewrite is guarded by stable comment markers / function identity and
-- fails closed if the deployed function shape has drifted.

-- 1. Prepared generation builder: scoped Set directory + scoped history.
do $$
declare
  v_sql text;
  v_start integer;
  v_end integer;
  v_old text;
  v_new text;
begin
  select pg_get_functiondef('public.refresh_pokemon_market_explorer_prepared_directory_v1()'::regprocedure)
    into v_sql;

  if ((length(v_sql)-length(replace(v_sql,'v_snapshot_set_count','')))/length('v_snapshot_set_count')) <> 6
     or position('select market_date, set_count' in v_sql)=0 then
    raise exception 'prepared refresh snapshot-count contract changed; refusing unsafe rewrite';
  end if;
  v_sql := replace(v_sql,'v_snapshot_set_count','v_snapshot_market_count');
  v_sql := replace(v_sql,'select market_date, set_count','select market_date, market_count');

  v_start := position('  -- Sets: the public prepared Set snapshot owns directory membership.' in v_sql);
  v_end := position('  -- Eras, curated Quick Markets and prepared rarity markets all come from the' in v_sql);
  if v_start = 0 or v_end = 0 or v_end <= v_start then
    raise exception 'prepared refresh Set-directory section changed; refusing unsafe rewrite';
  end if;
  v_old := substring(v_sql from v_start for v_end - v_start);
  v_new := $section$
  perform public.validate_pokemon_market_set_scope_payload_v1(
    (select snap.payload_json from public.pokemon_explore_set_value_snapshot_latest snap
      where snap.tcg='pokemon' and snap.scope='market' limit 1),
    (select snap.market_count from public.pokemon_explore_set_value_snapshot_latest snap
      where snap.tcg='pokemon' and snap.scope='market' limit 1),
    (select snap.set_count from public.pokemon_explore_set_value_snapshot_latest snap
      where snap.tcg='pokemon' and snap.scope='market' limit 1)
  );
  perform public.validate_pokemon_market_scoped_history_baskets_v1(
    (select snap.payload_json from public.pokemon_explore_set_value_snapshot_latest snap
      where snap.tcg='pokemon' and snap.scope='market' limit 1)
  );

  -- Sets: the public Set Market snapshot already publishes one explicit market
  -- identity per economically distinct scope. Standard roots keep set:<id>;
  -- edition-split roots publish only scoped keys and never a blended generic Set.
  insert into _phase5_dir_stage (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select
    coalesce(
      nullif(e->>'marketKey',''),
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then 'set:' || (e->>'setId')
        else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
      end
    ),
    'set', e->>'name', 'cards',
    (e->>'setId')::uuid, null::uuid, s.era_id,
    'set-cards-market-index:' || (e->>'setId') ||
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then '' else ':' || (e->>'marketScope') end,
    v_comparison_asof, nullif(e->>'setValueAsOf','')::date,
    nullif(e->>'currentSetValue','')::numeric,
    null, false, 'public_set_snapshot', e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey', e->>'canonicalKey',
      'eraName', er.name,
      'logoUrl', e->>'logoUrl',
      'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus',
      'marketScope', coalesce(nullif(e->>'marketScope',''),'standard'),
      'baseSetName', coalesce(nullif(e->>'baseSetName',''),e->>'name'),
      'scopeContractVersion', 'pokemon-set-market-scope-v1',
      'historyCertificationStatus', hc.certification_status,
      'historyCertificationReason', hc.certification_reason
    )),
    v_generation_id, v_generated_at
  from public.pokemon_explore_set_value_snapshot_latest snap
  cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
  join public.sets s on s.id=(e->>'setId')::uuid
  left join public.eras er on er.id=s.era_id
  left join public.pokemon_market_scoped_history_market_certification_v1 hc
    on hc.set_id=(e->>'setId')::uuid
   and hc.market_scope=coalesce(nullif(e->>'marketScope',''),'standard')
  where snap.tcg='pokemon' and snap.scope='market';

$section$;
  v_sql := overlay(v_sql placing v_new from v_start for v_end - v_start);

  v_start := position('  -- Prepared Set market-index histories, clipped to the continuous chain segment' in v_sql);
  v_end := position('  -- Maintained prepared series are already current-chain normalized histories.' in v_sql);
  if v_start = 0 or v_end = 0 or v_end <= v_start then
    raise exception 'prepared refresh Set-history section changed; refusing unsafe rewrite';
  end if;
  v_old := substring(v_sql from v_start for v_end - v_start);
  v_new := $section$
  -- Prepared Set histories. Standard Sets retain the already-prepared dashboard
  -- Market Index. Edition-scoped markets use the certified canonical root-scope
  -- Set Value history.  validate_pokemon_market_scoped_history_baskets_v1()
  -- proves one physical variant per canonical+scope and constant certified
  -- expected-card membership before this section runs.  Under those invariants,
  -- SetValue(t)/SetValue(base) is exactly the fixed-basket common-cohort index.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with public_markets as (
    select
      coalesce(
        nullif(e->>'marketKey',''),
        case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end
      ) as market_key,
      (e->>'setId')::uuid as set_id,
      coalesce(nullif(e->>'marketScope',''),'standard') as market_scope
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
  ), standard_dashboards as (
    select p.market_key,d.set_id,d.payload_json->'cardsMarket'->'marketIndex' as mi
    from public.pokemon_set_market_dashboard_snapshot_latest d
    join public_markets p on p.set_id=d.set_id and p.market_scope='standard'
    where d.window_key='365d'
  ), standard_selected as (
    select d.market_key,d.set_id,d.mi,
           (select (x->>'chainSegmentId')::integer
            from jsonb_array_elements(coalesce(d.mi->'history','[]'::jsonb)) x
            where (x->>'date')::date=v_comparison_asof
            limit 1) as segment_id
    from standard_dashboards d
    where jsonb_typeof(d.mi)='object'
  ), standard_history as (
    select s.market_key,(h->>'date')::date as market_date,
           (h->>'indexValue')::numeric as index_value,
           rv.set_value as tracked_value,
           coalesce((h->>'chainSegmentId')::integer,0) as chain_segment_id
    from standard_selected s
    cross join lateral jsonb_array_elements(coalesce(s.mi->'history','[]'::jsonb)) h
    left join public.pokemon_market_root_set_value_daily_history_v2_shadow rv
      on rv.set_id=s.set_id and rv.market_scope='standard' and rv.market_date=(h->>'date')::date
    where s.segment_id is not null
      and (h->>'date')::date <= v_comparison_asof
      and coalesce((h->>'chainSegmentId')::integer,0)=s.segment_id
  ), scoped_values as (
    select p.market_key,rv.market_date,rv.set_value,
           first_value(rv.set_value) over(
             partition by p.market_key order by rv.market_date
             rows between unbounded preceding and unbounded following
           ) as base_value
    from public_markets p
    join public.pokemon_market_root_set_value_daily_history_v2_shadow rv
      on rv.set_id=p.set_id and rv.market_scope=p.market_scope
    join public.pokemon_market_scoped_history_market_certification_v1 hc
      on hc.set_id=p.set_id and hc.market_scope=p.market_scope
    where p.market_scope<>'standard'
      and hc.history_publishable=true
      and rv.certified_on_date=true
      and rv.set_value>0
      and rv.market_date<=v_comparison_asof
  ), scoped_history as (
    select market_key,market_date,
           100.0 * set_value / nullif(base_value,0) as index_value,
           set_value as tracked_value,
           0::integer as chain_segment_id
    from scoped_values
  )
  select market_key,market_date,index_value,tracked_value,chain_segment_id,v_generation_id
  from standard_history
  union all
  select market_key,market_date,index_value,tracked_value,chain_segment_id,v_generation_id
  from scoped_history;

$section$;
  v_sql := overlay(v_sql placing v_new from v_start for v_end - v_start);

  execute v_sql;
end;
$$;

-- 2. Lightweight Set-directory sync must preserve the same scoped identities
-- between full prepared-generation publications.
create or replace function public.sync_pokemon_market_explorer_set_directory_v1()
returns jsonb
language plpgsql
security definer
set search_path = ''
set statement_timeout = '60s'
as $function$
declare
  v_payload jsonb;
  v_market_date date;
  v_snapshot_set_count integer;
  v_snapshot_market_count integer;
  v_payload_set_count integer;
  v_existing_min_comparison date;
  v_existing_max_comparison date;
  v_generation_id uuid;
  v_generated_at timestamptz;
  v_upserted integer := 0;
  v_directory_set_count integer := 0;
begin
  select s.payload_json,s.market_date,s.set_count,s.market_count
    into v_payload,v_market_date,v_snapshot_set_count,v_snapshot_market_count
  from public.pokemon_explore_set_value_snapshot_latest s
  where s.tcg='pokemon' and s.scope='market'
  limit 1;

  if v_payload is null or v_market_date is null
     or coalesce(v_snapshot_set_count,0)<1 or coalesce(v_snapshot_market_count,0)<1 then
    raise exception 'Global Set Market snapshot unavailable for Explorer Set-directory sync';
  end if;

  v_payload_set_count := jsonb_array_length(coalesce(v_payload->'sets','[]'::jsonb));
  if v_payload_set_count <> v_snapshot_market_count then
    raise exception 'Global Set Market snapshot market_count mismatch: payload=% row=%',
      v_payload_set_count,v_snapshot_market_count;
  end if;

  perform public.validate_pokemon_market_set_scope_payload_v1(
    v_payload,v_snapshot_market_count,v_snapshot_set_count
  );
  perform public.validate_pokemon_market_scoped_history_baskets_v1(v_payload);

  select min(d.comparison_as_of),max(d.comparison_as_of)
    into v_existing_min_comparison,v_existing_max_comparison
  from public.pokemon_market_explorer_prepared_directory_v1 d;

  if v_existing_min_comparison is null or v_existing_max_comparison is null
     or v_existing_min_comparison is distinct from v_existing_max_comparison then
    raise exception 'Prepared Explorer directory has no single comparison watermark';
  end if;

  select d.generation_id,d.generated_at
    into v_generation_id,v_generated_at
  from public.pokemon_market_explorer_prepared_directory_v1 d
  order by d.generated_at desc,d.market_key
  limit 1;

  v_generation_id := coalesce(v_generation_id,extensions.gen_random_uuid());
  v_generated_at := coalesce(v_generated_at,clock_timestamp());

  -- Remove superseded generic or retired scoped Set identities before upsert.
  delete from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.market_type='set'
    and not exists (
      select 1
      from jsonb_array_elements(v_payload->'sets') e
      where coalesce(
        nullif(e->>'marketKey',''),
        case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end
      )=d.market_key
    );

  insert into public.pokemon_market_explorer_prepared_directory_v1 (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select
    coalesce(
      nullif(e->>'marketKey',''),
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then 'set:' || (e->>'setId')
        else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
      end
    ),
    'set',e->>'name','cards',(e->>'setId')::uuid,null::uuid,s.era_id,
    'set-cards-market-index:' || (e->>'setId') ||
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then '' else ':' || (e->>'marketScope') end,
    v_existing_min_comparison,nullif(e->>'setValueAsOf','')::date,
    nullif(e->>'currentSetValue','')::numeric,null,false,
    'public_set_snapshot',e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey',e->>'canonicalKey','eraName',er.name,
      'logoUrl',e->>'logoUrl','symbolUrl',e->>'symbolUrl',
      'certificationStatus',e->>'certificationStatus',
      'marketScope',coalesce(nullif(e->>'marketScope',''),'standard'),
      'baseSetName',coalesce(nullif(e->>'baseSetName',''),e->>'name'),
      'scopeContractVersion','pokemon-set-market-scope-v1',
      'historyCertificationStatus',hc.certification_status,
      'historyCertificationReason',hc.certification_reason
    )),
    v_generation_id,v_generated_at
  from jsonb_array_elements(v_payload->'sets') e
  join public.sets s on s.id=(e->>'setId')::uuid
  left join public.eras er on er.id=s.era_id
  left join public.pokemon_market_scoped_history_market_certification_v1 hc
    on hc.set_id=(e->>'setId')::uuid
   and hc.market_scope=coalesce(nullif(e->>'marketScope',''),'standard')
  on conflict (market_key) do update
  set label=excluded.label,asset=excluded.asset,set_id=excluded.set_id,
      era_id=excluded.era_id,parent_era_id=excluded.parent_era_id,
      prepared_series_key=excluded.prepared_series_key,
      source_as_of=excluded.source_as_of,current_value=excluded.current_value,
      source_kind=excluded.source_kind,source_status=excluded.source_status,
      metadata=excluded.metadata;
  get diagnostics v_upserted = row_count;

  select count(*)::integer into v_directory_set_count
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.market_type='set';

  if v_directory_set_count <> v_snapshot_market_count then
    raise exception 'Prepared Explorer Set-directory market_count mismatch after sync: directory=% snapshot=%',
      v_directory_set_count,v_snapshot_market_count;
  end if;

  if exists (
    select 1 from public.pokemon_market_explorer_prepared_directory_v1 s
    where s.market_type='set'
      and (s.parent_era_id is null or not exists (
        select 1 from public.pokemon_market_explorer_prepared_directory_v1 e
        where e.market_type='era' and e.era_id=s.parent_era_id
      ))
  ) then
    raise exception 'Prepared Explorer Set directory contains a Set without its parent Era';
  end if;

  return jsonb_build_object(
    'status','complete','marketDate',v_market_date,
    'snapshotSetCount',v_snapshot_set_count,'snapshotMarketCount',v_snapshot_market_count,
    'directorySetCount',v_directory_set_count,
    'rowsUpserted',v_upserted,'comparisonAsOf',v_existing_min_comparison
  );
end;
$function$;

revoke all on function public.sync_pokemon_market_explorer_set_directory_v1()
  from public,anon,authenticated;
grant execute on function public.sync_pokemon_market_explorer_set_directory_v1()
  to service_role;

-- Keep the lightweight sync trigger count-aware. market_count changes are first-class
-- publication changes even when the distinct root cohort is unchanged.
create or replace function public.refresh_market_explorer_directory_after_set_market_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if TG_OP = 'UPDATE'
     and OLD.market_date is not distinct from NEW.market_date
     and OLD.set_count is not distinct from NEW.set_count
     and OLD.market_count is not distinct from NEW.market_count
     and OLD.source_generation_fingerprint is not distinct from NEW.source_generation_fingerprint
     and OLD.payload_json is not distinct from NEW.payload_json then
    return NEW;
  end if;

  perform public.sync_pokemon_market_explorer_set_directory_v1();
  return NEW;
end;
$function$;

revoke all on function public.refresh_market_explorer_directory_after_set_market_v1()
  from public,anon,authenticated,service_role;

drop trigger if exists pokemon_global_set_market_refresh_explorer_directory
  on public.pokemon_explore_set_value_snapshot_latest;
create trigger pokemon_global_set_market_refresh_explorer_directory
after insert or update of market_date,set_count,market_count,source_generation_fingerprint,payload_json
on public.pokemon_explore_set_value_snapshot_latest
for each row
when (new.tcg='pokemon' and new.scope='market')
execute function public.refresh_market_explorer_directory_after_set_market_v1();

-- 3. Prepared constituent staging: standard Set markets keep the existing
-- date-pinned reader. Explicit edition markets stage only the matching root
-- scope and never allow another edition to substitute.
do $$
declare
  v_sql text;
  v_start integer;
  v_end integer;
  v_new text;
begin
  select pg_get_functiondef('public.stage_pokemon_market_explorer_prepared_constituents_v1(uuid)'::regprocedure)
    into v_sql;
  v_start := position('    if d.source_kind = ''public_set_snapshot'' and d.market_type = ''set'' and d.asset = ''cards'' and d.set_id is not null then' in v_sql);
  v_end := position('    elsif d.source_kind = ''prepared_sealed_snapshots'' and d.market_type = ''prepared_format'' and d.asset = ''sealed'' then' in v_sql);
  if v_start=0 or v_end=0 or v_end<=v_start then
    raise exception 'prepared constituent Set staging section changed; refusing unsafe rewrite';
  end if;

  v_new := $section$
    if d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' and d.set_id is not null then
      insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
        (generation_id,market_key,asset,source_kind,definition_version,source_as_of,total_count,availability)
      values (
        p_generation_id,d.market_key,'cards',d.source_kind,
        coalesce(d.metadata->>'scopeContractVersion',d.prepared_series_key),
        d.source_as_of,0,'empty'
      );

      if coalesce(d.metadata->>'marketScope','standard')='standard' then
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id,market_key,rank,instrument_id,asset,market_price,price_as_of,item)
        select p_generation_id,d.market_key,r.rank,r.card_variant_id::text,'cards',
          r.market_price,r.market_date,
          jsonb_build_object(
            'rank',r.rank,'instrumentId',r.card_variant_id,'cardVariantId',r.card_variant_id,
            'canonicalCardId',r.canonical_card_id,'cardName',cc.name,'setId',r.set_id,
            'setName',s.name,'cardNumber',cc.printed_number,'rarity',cc.rarity,
            'edition',cv.edition,'printingType',cv.printing_type,'specialType',cv.special_type,
            'marketPrice',r.market_price,'asOf',r.market_date
          )
        from (
          select q.*,row_number() over(order by q.market_price desc nulls last,q.card_variant_id)::integer as rank
          from public.get_pokemon_cards_daily_constituents(
            array[d.set_id],d.source_as_of,d.source_as_of,null::uuid[]
          ) q
        ) r
        left join public.pokemon_canonical_cards cc on cc.id=r.canonical_card_id
        left join public.card_variants cv on cv.id=r.card_variant_id
        left join public.sets s on s.id=r.set_id;
        get diagnostics v_total = row_count;
      elsif d.source_status='current' and d.source_as_of is not null then
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id,market_key,rank,instrument_id,asset,market_price,price_as_of,item)
        select p_generation_id,d.market_key,r.rank,r.card_variant_id::text,'cards',
          r.market_price,d.source_as_of,
          jsonb_build_object(
            'rank',r.rank,'instrumentId',r.card_variant_id,'cardVariantId',r.card_variant_id,
            'canonicalCardId',r.canonical_card_id,'cardName',r.card_name,
            'setId',r.member_set_id,'setName',r.member_set_name,'cardNumber',r.card_number,
            'rarity',r.rarity,'edition',r.edition,'printingType',r.printing_type,
            'specialType',r.special_type,'marketPrice',r.market_price,'asOf',d.source_as_of,
            'sourceDate',r.captured_at,'marketScope',r.market_scope
          )
        from (
          select q.*,row_number() over(order by q.market_price desc nulls last,q.card_variant_id)::integer as rank
          from public.get_pokemon_market_root_set_card_prices_as_of_v1(
            d.set_id,d.metadata->>'marketScope',d.source_as_of
          ) q
          where q.market_scope=d.metadata->>'marketScope'
            and q.market_price>0
        ) r;
        get diagnostics v_total = row_count;

        if not exists (
          select 1
          from public.pokemon_market_root_set_value_daily_history_v2_shadow h
          where h.set_id=d.set_id
            and h.market_scope=d.metadata->>'marketScope'
            and h.market_date=d.source_as_of
            and h.certified_on_date=true
            and h.expected_card_count=v_total
            and h.priced_card_count=v_total
        ) then
          raise exception 'Scoped prepared constituent roster is not an exact certified basket: market_key=% as_of=% count=%',
            d.market_key,d.source_as_of,v_total;
        end if;
      else
        v_total := 0;
      end if;

      update public.pokemon_market_explorer_prepared_constituent_totals_v1
      set total_count=v_total,
          availability=case
            when coalesce(d.metadata->>'marketScope','standard')<>'standard'
                 and d.source_status<>'current' then 'unavailable'
            when v_total=0 then 'empty'
            else 'available'
          end,
          availability_reason=case
            when coalesce(d.metadata->>'marketScope','standard')<>'standard'
                 and d.source_status<>'current'
              then 'Edition-scoped market is not current for this prepared generation'
            else null
          end
      where generation_id=p_generation_id and market_key=d.market_key;
$section$;

  v_sql := overlay(v_sql placing v_new from v_start for v_end-v_start);
  execute v_sql;
end;
$$;
