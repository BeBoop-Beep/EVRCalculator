-- Exact-only recovery strategies for legacy Raw Set Value leaf rosters.
-- Never changes Set Value economics and never accepts a residual mismatch.

begin;

create table if not exists public.pokemon_market_explorer_raw_roster_recovery_failures_v1 (
  market_date date not null,
  root_set_id uuid not null,
  methodology_version text not null,
  strategy_version text not null,
  error text not null,
  failed_at timestamptz not null default clock_timestamp(),
  primary key(market_date,root_set_id,methodology_version,strategy_version)
);

alter table public.pokemon_market_explorer_raw_roster_recovery_failures_v1 enable row level security;
revoke all on public.pokemon_market_explorer_raw_roster_recovery_failures_v1
from public,anon,authenticated;
grant select,insert,update,delete
on public.pokemon_market_explorer_raw_roster_recovery_failures_v1
to service_role;

create or replace function public.freeze_pokemon_market_legacy_set_value_roster_v2(
  p_root_set_id uuid,
  p_market_date date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '25s'
set lock_timeout = '2s'
set jit = 'off'
as $function$
declare
  v_methodology text;
  v_expected_value numeric;
  v_expected_count integer;
  v_history_value numeric;
  v_history_count integer;
  v_history_source text;
  v_count integer;
  v_unique_variants integer;
  v_unique_canonical integer;
  v_value numeric;
  v_items jsonb;
  v_lock_key bigint;
begin
  if p_root_set_id is null or p_market_date is null then
    raise exception 'LEGACY_SET_VALUE_ROSTER_V2_ARGUMENTS_REQUIRED';
  end if;

  select
    h.methodology_version,
    (x->>'setValue')::numeric,
    (x->>'includedCardCount')::integer
  into v_methodology,v_expected_value,v_expected_count
  from public.pokemon_market_index_daily_history h
  cross join lateral jsonb_array_elements(h.constituents_json) x
  where h.tcg='pokemon' and h.index_key='raw'
    and h.market_date=p_market_date
    and (x->>'setId')::uuid=p_root_set_id
  order by h.updated_at desc
  limit 1;

  if not found then
    raise exception 'LEGACY_SET_VALUE_ROSTER_V2_RAW_ROOT_NOT_FOUND';
  end if;

  select h.set_value,h.included_card_count,h.source
  into v_history_value,v_history_count,v_history_source
  from public.pokemon_set_value_daily_history h
  where h.set_id=p_root_set_id
    and h.snapshot_date=p_market_date
    and h.value_scope='standard'
  order by h.updated_at desc
  limit 1;

  if not found or v_history_source is distinct from
     'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
  then
    raise exception 'LEGACY_SET_VALUE_ROSTER_V2_SOURCE_NOT_ELIGIBLE';
  end if;

  if round(v_history_value,2)<>round(v_expected_value,2)
     or v_history_count<>v_expected_count then
    raise exception 'LEGACY_SET_VALUE_ROSTER_V2_RAW_HISTORY_MISMATCH';
  end if;

  if exists (
    select 1
    from public.pokemon_market_set_value_constituent_publications_v1 p
    where p.root_set_id=p_root_set_id
      and p.market_date=p_market_date
      and p.methodology_version=v_methodology
      and p.status='READY'
      and p.constituent_count=v_expected_count
      and round(p.constituent_value,2)=round(v_expected_value,2)
  ) then
    return jsonb_build_object(
      'status','already_frozen','setId',p_root_set_id,'marketDate',p_market_date
    );
  end if;

  v_lock_key:=pg_catalog.hashtextextended(
    'legacy-set-value-roster-v2:'||p_root_set_id::text||':'||p_market_date::text,0
  );
  if not pg_catalog.pg_try_advisory_xact_lock(v_lock_key) then
    raise exception 'LEGACY_SET_VALUE_ROSTER_V2_ALREADY_ACTIVE' using errcode='55P03';
  end if;

  -- Strategy 1: immutable published Set snapshot, restricted to the current
  -- Set Value eligibility checklist. Accept only exact economic parity.
  with items as materialized (
    select
      nullif(coalesce(c->>'id',c->>'canonicalCardId',c->>'canonical_card_id'),'')::uuid
        canonical_card_id,
      nullif(coalesce(c->>'cardVariantId',c->>'card_variant_id'),'')::uuid
        card_variant_id,
      coalesce(
        nullif(coalesce(c->>'setId',c->>'set_id'),'')::uuid,p_root_set_id
      ) set_id,
      nullif(coalesce(c->>'marketPrice',c->>'market_price'),'')::numeric market_price,
      nullif(coalesce(
        c->>'priceSourceDate',c->>'price_source_date',c->>'marketDate',c->>'market_date'
      ),'')::date captured_at,
      coalesce(nullif(coalesce(c->>'priceSource',c->>'price_source'),''),'TCGPlayer') source,
      nullif(coalesce(c->>'printingType',c->>'printing_type'),'') printing_type,
      coalesce(
        nullif(coalesce(c->>'priceSelectionReason',c->>'price_selection_reason'),''),
        'published_set_snapshot_set_value_eligible'
      ) price_selection_reason
    from public.pokemon_set_cards_snapshot_latest s
    cross join lateral jsonb_array_elements(s.cards_json) c
    where s.set_id=p_root_set_id
  ),
  eligible as materialized (
    select i.*
    from items i
    join public.pokemon_canonical_cards cc on cc.id=i.canonical_card_id
    where coalesce(cc.set_value_eligible,false)
      and i.card_variant_id is not null
      and i.market_price>0
      and i.captured_at is not null
      and i.captured_at<=p_market_date
  )
  select
    count(*)::integer,
    count(distinct card_variant_id)::integer,
    count(distinct canonical_card_id)::integer,
    round(sum(market_price),2),
    jsonb_agg(
      jsonb_build_object(
        'canonicalCardId',canonical_card_id,
        'cardVariantId',card_variant_id,
        'setId',set_id,
        'marketPrice',market_price,
        'capturedAt',captured_at,
        'source',source,
        'printingType',printing_type,
        'priceSelectionReason',price_selection_reason
      )
      order by canonical_card_id
    )
  into v_count,v_unique_variants,v_unique_canonical,v_value,v_items
  from eligible;

  if v_count=v_expected_count
     and v_unique_variants=v_expected_count
     and v_unique_canonical=v_expected_count
     and round(v_value,2)=round(v_expected_value,2)
  then
    perform public.replace_pokemon_market_set_value_constituents_v1(
      p_root_set_id,p_market_date,v_methodology,v_expected_value,v_expected_count,
      'legacy_set_snapshot_eligible_exact_frozen_v2',v_items
    );
    return jsonb_build_object(
      'status','frozen','strategy','snapshot_eligible_exact',
      'setId',p_root_set_id,'marketDate',p_market_date,
      'constituentCount',v_count,'constituentValue',v_value
    );
  end if;

  -- Strategy 2: current root resolver can contain multiple canonical aliases
  -- for one physical variant. Collapse aliases by physical card identity and
  -- accept only if the physical basket exactly matches persisted economics.
  with candidates as materialized (
    select
      p.canonical_card_id,p.card_variant_id,p.member_set_id set_id,
      p.market_price,p.captured_at,p.source,p.printing_type,p.price_selection_reason,
      row_number() over(
        partition by p.card_variant_id
        order by p.canonical_card_id::text
      ) physical_rank
    from public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) p
    where p.root_set_id=p_root_set_id
      and p.market_scope='standard'
      and p.card_variant_id is not null
      and p.market_price>0
      and p.captured_at is not null
      and p.captured_at<=p_market_date
  ),
  physical as materialized (
    select * from candidates where physical_rank=1
  )
  select
    count(*)::integer,
    count(distinct card_variant_id)::integer,
    count(distinct canonical_card_id)::integer,
    round(sum(market_price),2),
    jsonb_agg(
      jsonb_build_object(
        'canonicalCardId',canonical_card_id,
        'cardVariantId',card_variant_id,
        'setId',set_id,
        'marketPrice',market_price,
        'capturedAt',captured_at,
        'source',source,
        'printingType',printing_type,
        'priceSelectionReason',coalesce(price_selection_reason,'physical_variant_dedup_exact')
      )
      order by canonical_card_id
    )
  into v_count,v_unique_variants,v_unique_canonical,v_value,v_items
  from physical;

  if v_count=v_expected_count
     and v_unique_variants=v_expected_count
     and v_unique_canonical=v_expected_count
     and round(v_value,2)=round(v_expected_value,2)
  then
    perform public.replace_pokemon_market_set_value_constituents_v1(
      p_root_set_id,p_market_date,v_methodology,v_expected_value,v_expected_count,
      'legacy_physical_variant_dedup_exact_frozen_v2',v_items
    );
    return jsonb_build_object(
      'status','frozen','strategy','physical_variant_dedup_exact',
      'setId',p_root_set_id,'marketDate',p_market_date,
      'constituentCount',v_count,'constituentValue',v_value
    );
  end if;

  raise exception
    'LEGACY_SET_VALUE_ROSTER_V2_NO_EXACT_STRATEGY: last count %/% unique variants % unique canonical % value %/%',
    coalesce(v_count,0),v_expected_count,coalesce(v_unique_variants,0),
    coalesce(v_unique_canonical,0),coalesce(round(v_value,2),0),round(v_expected_value,2);
end;
$function$;

revoke all on function public.freeze_pokemon_market_legacy_set_value_roster_v2(uuid,date)
from public,anon,authenticated;
grant execute on function public.freeze_pokemon_market_legacy_set_value_roster_v2(uuid,date)
to service_role;

create or replace function public.freeze_pokemon_market_legacy_set_value_rosters_batch_v2(
  p_market_date date,
  p_limit integer default 10
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '90s'
set lock_timeout = '2s'
set jit = 'off'
as $function$
declare
  v_root record;
  v_receipt jsonb;
  v_processed integer:=0;
  v_failed integer:=0;
  v_failures jsonb:='[]'::jsonb;
  v_remaining integer;
  v_methodology text;
  v_strategy constant text:='legacy-exact-v2';
begin
  if p_market_date is null or p_limit is null or p_limit<1 or p_limit>10 then
    raise exception 'LEGACY_SET_VALUE_ROSTER_BATCH_V2_ARGUMENTS_INVALID';
  end if;

  select h.methodology_version into v_methodology
  from public.pokemon_market_index_daily_history h
  where h.tcg='pokemon' and h.index_key='raw' and h.market_date=p_market_date
  order by h.updated_at desc limit 1;

  if v_methodology is null then
    raise exception 'LEGACY_SET_VALUE_ROSTER_BATCH_V2_RAW_NOT_FOUND';
  end if;

  for v_root in
    with raw as materialized (
      select h.constituents_json
      from public.pokemon_market_index_daily_history h
      where h.tcg='pokemon' and h.index_key='raw'
        and h.market_date=p_market_date
        and h.methodology_version=v_methodology
      order by h.updated_at desc limit 1
    ),
    roots as materialized (
      select (x->>'setId')::uuid set_id
      from raw cross join lateral jsonb_array_elements(raw.constituents_json) x
    )
    select r.set_id
    from roots r
    join public.pokemon_set_value_daily_history h
      on h.set_id=r.set_id and h.snapshot_date=p_market_date
     and h.value_scope='standard'
     and h.source=
       'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
    where not exists (
      select 1
      from public.pokemon_market_set_value_constituent_publications_v1 p
      where p.root_set_id=r.set_id and p.market_date=p_market_date
        and p.methodology_version=v_methodology and p.status='READY'
    )
      and not exists (
        select 1
        from public.pokemon_market_explorer_raw_roster_recovery_failures_v1 f
        where f.market_date=p_market_date and f.root_set_id=r.set_id
          and f.methodology_version=v_methodology and f.strategy_version=v_strategy
      )
    order by r.set_id
    limit p_limit
  loop
    begin
      v_receipt:=public.freeze_pokemon_market_legacy_set_value_roster_v2(
        v_root.set_id,p_market_date
      );
      v_processed:=v_processed+1;
    exception when others then
      v_failed:=v_failed+1;
      v_failures:=v_failures||jsonb_build_array(jsonb_build_object(
        'setId',v_root.set_id,'sqlstate',sqlstate,'error',left(sqlerrm,1000)
      ));
      insert into public.pokemon_market_explorer_raw_roster_recovery_failures_v1(
        market_date,root_set_id,methodology_version,strategy_version,error,failed_at
      ) values (
        p_market_date,v_root.set_id,v_methodology,v_strategy,left(sqlerrm,1000),clock_timestamp()
      )
      on conflict(market_date,root_set_id,methodology_version,strategy_version)
      do update set error=excluded.error,failed_at=excluded.failed_at;
    end;
  end loop;

  with raw as materialized (
    select h.constituents_json
    from public.pokemon_market_index_daily_history h
    where h.tcg='pokemon' and h.index_key='raw'
      and h.market_date=p_market_date
      and h.methodology_version=v_methodology
    order by h.updated_at desc limit 1
  ),
  roots as materialized (
    select (x->>'setId')::uuid set_id
    from raw cross join lateral jsonb_array_elements(raw.constituents_json) x
  )
  select count(*)::integer into v_remaining
  from roots r
  where not exists (
    select 1
    from public.pokemon_market_set_value_constituent_publications_v1 p
    where p.root_set_id=r.set_id and p.market_date=p_market_date
      and p.methodology_version=v_methodology and p.status='READY'
  );

  return jsonb_build_object(
    'marketDate',p_market_date,
    'strategyVersion',v_strategy,
    'processed',v_processed,
    'failed',v_failed,
    'remaining',v_remaining,
    'failures',v_failures
  );
end;
$function$;

revoke all on function public.freeze_pokemon_market_legacy_set_value_rosters_batch_v2(date,integer)
from public,anon,authenticated;
grant execute on function public.freeze_pokemon_market_legacy_set_value_rosters_batch_v2(date,integer)
to service_role;

commit;
