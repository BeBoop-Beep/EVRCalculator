create table public.pokemon_market_explorer_options_snapshots (
  id bigint generated always as identity primary key,
  tcg text not null,
  contract_key text not null,
  schema_version text not null,
  generated_at timestamptz not null,
  source_as_of date not null,
  source_metadata jsonb not null default '{}'::jsonb,
  source_fingerprint text null,
  payload_json jsonb not null,
  payload_bytes integer not null,
  is_current boolean not null default false,
  published_at timestamptz not null default now(),
  constraint pokemon_market_explorer_options_snapshots_tcg_check
    check (length(btrim(tcg)) between 1 and 64),
  constraint pokemon_market_explorer_options_snapshots_contract_key_check
    check (length(btrim(contract_key)) between 1 and 128),
  constraint pokemon_market_explorer_options_snapshots_schema_version_check
    check (length(btrim(schema_version)) between 1 and 128),
  constraint pokemon_market_explorer_options_snapshots_payload_object_check
    check (jsonb_typeof(payload_json) = 'object'),
  constraint pokemon_market_explorer_options_snapshots_source_metadata_object_check
    check (jsonb_typeof(source_metadata) = 'object'),
  constraint pokemon_market_explorer_options_snapshots_payload_bytes_check
    check (payload_bytes between 2 and 4194304)
);

create unique index pokemon_market_explorer_options_snapshots_one_current_idx
  on public.pokemon_market_explorer_options_snapshots(tcg, contract_key)
  where is_current;

alter table public.pokemon_market_explorer_options_snapshots enable row level security;

create policy pokemon_market_explorer_options_snapshots_service_role_all
  on public.pokemon_market_explorer_options_snapshots
  for all
  to service_role
  using (true)
  with check (true);

revoke all on table public.pokemon_market_explorer_options_snapshots from public, anon, authenticated;
grant select, insert, update on table public.pokemon_market_explorer_options_snapshots to service_role;
grant usage, select on sequence public.pokemon_market_explorer_options_snapshots_id_seq to service_role;

create or replace function public.publish_pokemon_market_explorer_options_snapshot_v1(
  p_tcg text,
  p_contract_key text,
  p_schema_version text,
  p_generated_at timestamptz,
  p_source_as_of date,
  p_payload_json jsonb,
  p_source_metadata jsonb default '{}'::jsonb,
  p_source_fingerprint text default null
)
returns table(snapshot_id bigint, payload_bytes integer, published_at timestamptz)
language plpgsql
volatile
security invoker
set search_path to ''
set statement_timeout to '5s'
as $function$
declare
  v_tcg text := pg_catalog.lower(pg_catalog.btrim(coalesce(p_tcg,'')));
  v_contract_key text := pg_catalog.btrim(coalesce(p_contract_key,''));
  v_schema_version text := pg_catalog.btrim(coalesce(p_schema_version,''));
  v_payload_bytes integer;
  v_snapshot_id bigint;
  v_published_at timestamptz;
begin
  if v_tcg = '' or pg_catalog.length(v_tcg) > 64 then
    raise exception 'p_tcg must be non-empty and at most 64 characters' using errcode='22023';
  end if;
  if v_contract_key = '' or pg_catalog.length(v_contract_key) > 128 then
    raise exception 'p_contract_key must be non-empty and at most 128 characters' using errcode='22023';
  end if;
  if v_schema_version = '' or pg_catalog.length(v_schema_version) > 128 then
    raise exception 'p_schema_version must be non-empty and at most 128 characters' using errcode='22023';
  end if;
  if p_generated_at is null then
    raise exception 'p_generated_at is required' using errcode='22023';
  end if;
  if p_source_as_of is null then
    raise exception 'p_source_as_of is required' using errcode='22023';
  end if;
  if p_payload_json is null or pg_catalog.jsonb_typeof(p_payload_json) <> 'object' then
    raise exception 'p_payload_json must be a JSON object' using errcode='22023';
  end if;
  if p_source_metadata is null or pg_catalog.jsonb_typeof(p_source_metadata) <> 'object' then
    raise exception 'p_source_metadata must be a JSON object' using errcode='22023';
  end if;

  v_payload_bytes := pg_catalog.octet_length(pg_catalog.convert_to(p_payload_json::text,'UTF8'));
  if v_payload_bytes < 2 or v_payload_bytes > 4194304 then
    raise exception 'options payload is % bytes; allowed range is 2..4194304', v_payload_bytes using errcode='22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('market-explorer-options:' || v_tcg || ':' || v_contract_key, 0)
  );

  update public.pokemon_market_explorer_options_snapshots
  set is_current=false
  where tcg=v_tcg
    and contract_key=v_contract_key
    and is_current;

  insert into public.pokemon_market_explorer_options_snapshots(
    tcg,contract_key,schema_version,generated_at,source_as_of,source_metadata,
    source_fingerprint,payload_json,payload_bytes,is_current
  ) values (
    v_tcg,v_contract_key,v_schema_version,p_generated_at,p_source_as_of,p_source_metadata,
    nullif(pg_catalog.btrim(coalesce(p_source_fingerprint,'')),''),
    p_payload_json,v_payload_bytes,true
  )
  returning id, pokemon_market_explorer_options_snapshots.published_at
  into v_snapshot_id, v_published_at;

  return query select v_snapshot_id, v_payload_bytes, v_published_at;
end;
$function$;

create or replace function public.get_pokemon_market_explorer_options_snapshot_v1(
  p_tcg text default 'pokemon',
  p_contract_key text default 'marketExplorerFilterOptions'
)
returns table(
  snapshot_id bigint,
  tcg text,
  contract_key text,
  schema_version text,
  generated_at timestamptz,
  source_as_of date,
  source_metadata jsonb,
  source_fingerprint text,
  payload_json jsonb,
  payload_bytes integer,
  published_at timestamptz
)
language sql
stable
security invoker
set search_path to ''
set statement_timeout to '1s'
as $function$
select
  s.id,
  s.tcg,
  s.contract_key,
  s.schema_version,
  s.generated_at,
  s.source_as_of,
  s.source_metadata,
  s.source_fingerprint,
  s.payload_json,
  s.payload_bytes,
  s.published_at
from public.pokemon_market_explorer_options_snapshots s
where s.tcg=pg_catalog.lower(pg_catalog.btrim(coalesce(p_tcg,'')))
  and s.contract_key=pg_catalog.btrim(coalesce(p_contract_key,''))
  and s.is_current
limit 1;
$function$;

comment on table public.pokemon_market_explorer_options_snapshots is
'Phase-3 persistent Market Explorer options snapshots. Payload construction occurs offline; request-time reads return only the already-published current row.';
comment on function public.publish_pokemon_market_explorer_options_snapshot_v1(text,text,text,timestamptz,date,jsonb,jsonb,text) is
'Atomically validates and publishes one bounded Market Explorer options JSON snapshot while retaining prior snapshots as history.';
comment on function public.get_pokemon_market_explorer_options_snapshot_v1(text,text) is
'Returns the single current prepublished Market Explorer options snapshot. Performs no catalog joins or refresh work.';

revoke all on function public.publish_pokemon_market_explorer_options_snapshot_v1(text,text,text,timestamptz,date,jsonb,jsonb,text) from public, anon, authenticated;
grant execute on function public.publish_pokemon_market_explorer_options_snapshot_v1(text,text,text,timestamptz,date,jsonb,jsonb,text) to service_role;
revoke all on function public.get_pokemon_market_explorer_options_snapshot_v1(text,text) from public, anon, authenticated;
grant execute on function public.get_pokemon_market_explorer_options_snapshot_v1(text,text) to service_role;
