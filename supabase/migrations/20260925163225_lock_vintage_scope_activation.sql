
create table if not exists public.pokemon_market_set_scope_activation_v1 (
  singleton boolean primary key default true check (singleton),
  active boolean not null default true,
  contract_version text not null check (contract_version='pokemon-set-market-scope-v1'),
  activated_market_date date not null,
  activated_root_set_count integer not null check (activated_root_set_count > 0),
  activated_market_count integer not null check (activated_market_count >= activated_root_set_count),
  activated_at timestamptz not null default timezone('utc',now()),
  deactivated_at timestamptz,
  deactivation_reason text,
  check (
    (active and deactivated_at is null and deactivation_reason is null)
    or
    (not active and deactivated_at is not null and nullif(btrim(deactivation_reason),'') is not null)
  )
);

alter table public.pokemon_market_set_scope_activation_v1 enable row level security;
revoke all on public.pokemon_market_set_scope_activation_v1 from public,anon,authenticated;
grant select on public.pokemon_market_set_scope_activation_v1 to service_role;

create or replace function public.guard_pokemon_market_set_scope_snapshot_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
set statement_timeout = '60s'
as $function$
declare
  v_scoped boolean := false;
  v_active boolean := false;
begin
  if new.tcg is distinct from 'pokemon' or new.scope is distinct from 'market' then
    return new;
  end if;

  if new.payload_json is null or jsonb_typeof(new.payload_json->'sets') is distinct from 'array' then
    raise exception 'Global Set Market payload must contain a sets array';
  end if;

  select exists(
    select 1
    from jsonb_array_elements(new.payload_json->'sets') e
    where coalesce(nullif(e->>'marketScope',''),'standard') <> 'standard'
  ) into v_scoped;

  select coalesce(a.active,false)
    into v_active
  from public.pokemon_market_set_scope_activation_v1 a
  where a.singleton=true;

  v_active := coalesce(v_active,false);

  if v_active and not v_scoped then
    raise exception
      'LEGACY_VINTAGE_MARKET_SNAPSHOT_REJECTED: explicit vintage scope contract is active'
      using errcode='P0001';
  end if;

  if v_scoped then
    perform public.validate_pokemon_market_set_scope_payload_v1(
      new.payload_json,new.market_count,new.set_count
    );

    insert into public.pokemon_market_set_scope_activation_v1 (
      singleton,active,contract_version,activated_market_date,
      activated_root_set_count,activated_market_count,activated_at,
      deactivated_at,deactivation_reason
    )
    values (
      true,true,'pokemon-set-market-scope-v1',new.market_date,
      new.set_count,new.market_count,timezone('utc',now()),null,null
    )
    on conflict (singleton) do update
    set active=true,
        contract_version=excluded.contract_version,
        activated_market_date=excluded.activated_market_date,
        activated_root_set_count=excluded.activated_root_set_count,
        activated_market_count=excluded.activated_market_count,
        activated_at=excluded.activated_at,
        deactivated_at=null,
        deactivation_reason=null
    where not public.pokemon_market_set_scope_activation_v1.active;
  end if;

  return new;
end;
$function$;

revoke all on function public.guard_pokemon_market_set_scope_snapshot_v1()
  from public,anon,authenticated,service_role;

drop trigger if exists pokemon_explore_set_value_scope_contract_guard
  on public.pokemon_explore_set_value_snapshot_latest;
create trigger pokemon_explore_set_value_scope_contract_guard
before insert or update of payload_json,set_count,market_count,market_date
on public.pokemon_explore_set_value_snapshot_latest
for each row
execute function public.guard_pokemon_market_set_scope_snapshot_v1();

create or replace function public.rollback_pokemon_market_set_scope_activation_v1(
  p_expected_activated_at timestamptz,
  p_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
set statement_timeout = '10s'
as $function$
declare
  v_row public.pokemon_market_set_scope_activation_v1%rowtype;
begin
  if p_expected_activated_at is null or nullif(btrim(p_reason),'') is null then
    raise exception 'expected activation timestamp and non-empty rollback reason are required';
  end if;

  update public.pokemon_market_set_scope_activation_v1
  set active=false,
      deactivated_at=timezone('utc',now()),
      deactivation_reason=btrim(p_reason)
  where singleton=true
    and active=true
    and activated_at=p_expected_activated_at
  returning * into v_row;

  if not found then
    raise exception 'ACTIVATION_ROLLBACK_GUARD_MISMATCH'
      using errcode='P0001';
  end if;

  return jsonb_build_object(
    'status','deactivated',
    'contractVersion',v_row.contract_version,
    'activatedMarketDate',v_row.activated_market_date,
    'activatedAt',v_row.activated_at,
    'deactivatedAt',v_row.deactivated_at,
    'reason',v_row.deactivation_reason
  );
end;
$function$;

revoke all on function public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)
  from public,anon,authenticated;
grant execute on function public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)
  to service_role;

comment on table public.pokemon_market_set_scope_activation_v1 is
'Singleton activation latch for the explicit vintage Set market-scope contract. Once active, legacy generic vintage Global Set Market payloads fail closed until an explicitly guarded rollback deactivates the latch.';

comment on function public.guard_pokemon_market_set_scope_snapshot_v1() is
'Fail-closed snapshot trigger. The first valid scoped payload activates the vintage scope contract transactionally; after activation a legacy generic vintage payload cannot overwrite it.';

comment on function public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text) is
'Explicit service-role rollback gate for the vintage scope activation latch. Requires the exact activation timestamp and a non-empty reason so restoring the pre-cutover snapshot is deliberate and auditable.';

notify pgrst,'reload schema';
