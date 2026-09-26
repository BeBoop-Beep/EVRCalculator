-- The original compact tables remain an immutable first generation. New
-- generations are written alongside them and selected by one pointer row.
create table public.pokemon_market_explorer_prepared_generations_v1 (
  generation_id uuid primary key,
  status text not null check (status in ('candidate','complete','serving','retired','failed')),
  generated_at timestamptz not null,
  comparison_as_of date not null,
  source_as_of jsonb not null default '{}'::jsonb,
  directory_rows integer not null check (directory_rows >= 0),
  history_rows integer not null check (history_rows >= 0),
  history_markets integer not null check (history_markets >= 0),
  contract_version integer not null default 1 check (contract_version = 1),
  directory_fingerprint text not null,
  history_fingerprint text not null,
  completed_at timestamptz,
  promoted_at timestamptz,
  superseded_at timestamptz,
  failure_reason text
);

create table public.pokemon_market_explorer_prepared_serving_v1 (
  singleton boolean primary key default true check (singleton),
  generation_id uuid not null references public.pokemon_market_explorer_prepared_generations_v1(generation_id)
);

create table public.pokemon_market_explorer_prepared_directory_generations_v1
  (like public.pokemon_market_explorer_prepared_directory_v1 including defaults including constraints);
alter table public.pokemon_market_explorer_prepared_directory_generations_v1
  add primary key (generation_id, market_key);

create table public.pokemon_market_explorer_prepared_history_generations_v1
  (like public.pokemon_market_explorer_prepared_history_v1 including defaults including constraints);
alter table public.pokemon_market_explorer_prepared_history_generations_v1
  add primary key (generation_id, market_key, market_date);
alter table public.pokemon_market_explorer_prepared_history_generations_v1
  add constraint prepared_history_generation_directory_fk
  foreign key (generation_id, market_key)
  references public.pokemon_market_explorer_prepared_directory_generations_v1(generation_id, market_key)
  on delete cascade;

create index on public.pokemon_market_explorer_prepared_history_generations_v1 (generation_id, market_key, market_date);

create table public.pokemon_market_explorer_prepared_publication_audit_v1 (
  id bigint generated always as identity primary key,
  event_at timestamptz not null default clock_timestamp(),
  action text not null check (action in ('candidate','validated','promote','rollback','repromote')),
  from_generation_id uuid,
  to_generation_id uuid not null,
  operator_path text not null,
  result text not null,
  directory_rows integer,
  history_rows integer
);

-- Backfill only metadata. The existing 192 directory and 17,204 history rows
-- stay in place and continue to represent the current complete generation.
do $$
declare
  v_id uuid;
begin
  select generation_id into v_id from public.pokemon_market_explorer_prepared_directory_v1 limit 1;
  if v_id is null
     or exists(select 1 from public.pokemon_market_explorer_prepared_directory_v1 where generation_id <> v_id)
     or exists(select 1 from public.pokemon_market_explorer_prepared_history_v1 where generation_id <> v_id) then
    raise exception 'existing prepared generation is not internally consistent';
  end if;
  insert into public.pokemon_market_explorer_prepared_generations_v1
    (generation_id,status,generated_at,comparison_as_of,source_as_of,
     directory_rows,history_rows,history_markets,directory_fingerprint,history_fingerprint,
     completed_at,promoted_at)
  select v_id,'serving',min(d.generated_at),min(d.comparison_as_of),
    jsonb_build_object('sets',min(d.source_as_of) filter (where d.asset='cards'),
                       'sealed',min(d.source_as_of) filter (where d.asset='sealed')),
    count(*)::integer,
    (select count(*)::integer from public.pokemon_market_explorer_prepared_history_v1),
    (select count(distinct market_key)::integer from public.pokemon_market_explorer_prepared_history_v1),
    (select md5(coalesce(string_agg(md5(to_jsonb(x)::text),'' order by x.market_key),''))
       from public.pokemon_market_explorer_prepared_directory_v1 x),
    (select md5(coalesce(string_agg(md5(to_jsonb(x)::text),'' order by x.market_key,x.market_date),''))
       from public.pokemon_market_explorer_prepared_history_v1 x),
    clock_timestamp(),clock_timestamp()
  from public.pokemon_market_explorer_prepared_directory_v1 d;
  insert into public.pokemon_market_explorer_prepared_serving_v1(singleton,generation_id)
    values(true,v_id);
end;
$$;

create view public.pokemon_market_explorer_prepared_serving_directory_v1 as
  select d.* from public.pokemon_market_explorer_prepared_directory_v1 d
  join public.pokemon_market_explorer_prepared_serving_v1 p on p.generation_id=d.generation_id
  union all
  select d.* from public.pokemon_market_explorer_prepared_directory_generations_v1 d
  join public.pokemon_market_explorer_prepared_serving_v1 p on p.generation_id=d.generation_id;

create view public.pokemon_market_explorer_prepared_serving_history_v1 as
  select h.* from public.pokemon_market_explorer_prepared_history_v1 h
  join public.pokemon_market_explorer_prepared_serving_v1 p on p.generation_id=h.generation_id
  union all
  select h.* from public.pokemon_market_explorer_prepared_history_generations_v1 h
  join public.pokemon_market_explorer_prepared_serving_v1 p on p.generation_id=h.generation_id;

revoke all on public.pokemon_market_explorer_prepared_generations_v1,
  public.pokemon_market_explorer_prepared_serving_v1,
  public.pokemon_market_explorer_prepared_directory_generations_v1,
  public.pokemon_market_explorer_prepared_history_generations_v1,
  public.pokemon_market_explorer_prepared_publication_audit_v1,
  public.pokemon_market_explorer_prepared_serving_directory_v1,
  public.pokemon_market_explorer_prepared_serving_history_v1 from public, anon, authenticated;
grant select on public.pokemon_market_explorer_prepared_serving_directory_v1,
  public.pokemon_market_explorer_prepared_serving_history_v1 to service_role;
grant select,insert,update,delete on public.pokemon_market_explorer_prepared_generations_v1,
  public.pokemon_market_explorer_prepared_serving_v1,
  public.pokemon_market_explorer_prepared_directory_generations_v1,
  public.pokemon_market_explorer_prepared_history_generations_v1,
  public.pokemon_market_explorer_prepared_publication_audit_v1 to service_role;
grant usage,select on sequence public.pokemon_market_explorer_prepared_publication_audit_v1_id_seq to service_role;

create function public.switch_pokemon_market_explorer_prepared_generation_v1(
  p_target uuid, p_action text, p_operator_path text
) returns jsonb language plpgsql volatile security invoker set search_path = '' as $$
declare
  v_current uuid;
  v_target public.pokemon_market_explorer_prepared_generations_v1%rowtype;
  v_directory_rows integer;
  v_history_rows integer;
  v_history_markets integer;
  v_directory_fingerprint text;
  v_history_fingerprint text;
begin
  if p_action not in ('promote','rollback','repromote') or nullif(p_operator_path,'') is null then
    raise exception 'INVALID_SWITCH_REQUEST' using errcode='P0001';
  end if;
  select generation_id into strict v_current
    from public.pokemon_market_explorer_prepared_serving_v1 where singleton for update;
  select * into v_target from public.pokemon_market_explorer_prepared_generations_v1
    where generation_id=p_target for update;
  if not found then raise exception 'UNKNOWN_GENERATION' using errcode='P0001'; end if;
  if v_target.status not in ('complete','retired','serving')
     or v_target.completed_at is null or v_target.contract_version <> 1 then
    raise exception 'INCOMPLETE_OR_INCOMPATIBLE_GENERATION' using errcode='P0001';
  end if;
  if p_target = v_current then
    return jsonb_build_object('generationId',v_current,'unchanged',true);
  end if;
  if exists(select 1 from public.pokemon_market_explorer_prepared_directory_v1 where generation_id=p_target) then
    select count(*)::integer,md5(coalesce(string_agg(md5(to_jsonb(d)::text),'' order by market_key),''))
      into v_directory_rows,v_directory_fingerprint
      from public.pokemon_market_explorer_prepared_directory_v1 d where generation_id=p_target;
    select count(*)::integer,count(distinct market_key)::integer,
      md5(coalesce(string_agg(md5(to_jsonb(h)::text),'' order by market_key,market_date),''))
      into v_history_rows,v_history_markets,v_history_fingerprint
      from public.pokemon_market_explorer_prepared_history_v1 h where generation_id=p_target;
  else
    select count(*)::integer,md5(coalesce(string_agg(md5(to_jsonb(d)::text),'' order by market_key),''))
      into v_directory_rows,v_directory_fingerprint
      from public.pokemon_market_explorer_prepared_directory_generations_v1 d where generation_id=p_target;
    select count(*)::integer,count(distinct market_key)::integer,
      md5(coalesce(string_agg(md5(to_jsonb(h)::text),'' order by market_key,market_date),''))
      into v_history_rows,v_history_markets,v_history_fingerprint
      from public.pokemon_market_explorer_prepared_history_generations_v1 h where generation_id=p_target;
  end if;
  if v_directory_rows <> v_target.directory_rows or v_history_rows <> v_target.history_rows
     or v_history_markets <> v_target.history_markets
     or v_directory_fingerprint <> v_target.directory_fingerprint
     or v_history_fingerprint <> v_target.history_fingerprint then
    raise exception 'GENERATION_INTEGRITY_MISMATCH' using errcode='P0001';
  end if;
  update public.pokemon_market_explorer_prepared_generations_v1
    set status='retired',superseded_at=clock_timestamp() where generation_id=v_current;
  update public.pokemon_market_explorer_prepared_generations_v1
    set status='serving',promoted_at=clock_timestamp(),superseded_at=null where generation_id=p_target;
  update public.pokemon_market_explorer_prepared_serving_v1
    set generation_id=p_target where singleton;
  insert into public.pokemon_market_explorer_prepared_publication_audit_v1
    (action,from_generation_id,to_generation_id,operator_path,result,directory_rows,history_rows)
    values(p_action,v_current,p_target,p_operator_path,'success',v_directory_rows,v_history_rows);
  return jsonb_build_object('fromGenerationId',v_current,'generationId',p_target,
    'directoryRows',v_directory_rows,'historyRows',v_history_rows);
end;
$$;
revoke all on function public.switch_pokemon_market_explorer_prepared_generation_v1(uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.switch_pokemon_market_explorer_prepared_generation_v1(uuid,text,text)
  to service_role;

create function public.rollback_pokemon_market_explorer_prepared_generation_v1(
  p_target uuid, p_operator_path text
) returns jsonb language plpgsql volatile security invoker set search_path = '' as $$
begin
  return public.switch_pokemon_market_explorer_prepared_generation_v1(
    p_target,'rollback',p_operator_path);
end;
$$;
revoke all on function public.rollback_pokemon_market_explorer_prepared_generation_v1(uuid,text)
  from public, anon, authenticated;
grant execute on function public.rollback_pokemon_market_explorer_prepared_generation_v1(uuid,text)
  to service_role;

-- Cleanup is deliberately separate from promotion and requires an explicit
-- post-publication verification flag. Keep the serving generation and the
-- two most recently superseded complete generations regardless of age.
create function public.cleanup_pokemon_market_explorer_prepared_generations_v1(
  p_post_publication_verified boolean, p_min_retention interval default interval '7 days'
) returns integer language plpgsql volatile security invoker set search_path = '' as $$
declare
  v_id uuid;
  v_deleted integer := 0;
begin
  if p_post_publication_verified is distinct from true
     or p_min_retention < interval '7 days' then
    raise exception 'RETENTION_VERIFICATION_REQUIRED' using errcode='P0001';
  end if;
  perform generation_id from public.pokemon_market_explorer_prepared_serving_v1
    where singleton for update;
  for v_id in
    select g.generation_id
    from public.pokemon_market_explorer_prepared_generations_v1 g
    where g.status='retired'
      and g.superseded_at < clock_timestamp()-p_min_retention
      and g.generation_id not in (
        select generation_id from public.pokemon_market_explorer_prepared_generations_v1
        where status in ('serving','retired')
        order by coalesce(promoted_at,generated_at) desc limit 3
      )
  loop
    delete from public.pokemon_market_explorer_prepared_history_generations_v1
      where generation_id=v_id;
    delete from public.pokemon_market_explorer_prepared_directory_generations_v1
      where generation_id=v_id;
    -- The migration's first generation remains in the original tables.
    if exists(select 1 from public.pokemon_market_explorer_prepared_directory_v1
              where generation_id=v_id) then
      continue;
    end if;
    delete from public.pokemon_market_explorer_prepared_generations_v1
      where generation_id=v_id;
    v_deleted := v_deleted+1;
  end loop;
  return v_deleted;
end;
$$;
revoke all on function public.cleanup_pokemon_market_explorer_prepared_generations_v1(boolean,interval)
  from public, anon, authenticated;
grant execute on function public.cleanup_pokemon_market_explorer_prepared_generations_v1(boolean,interval)
  to service_role;

-- The current refresh's build and validation stages remain intact. Replace
-- only its final destructive swap with additive storage and pointer promotion.
do $$
declare
  v_sql text;
  v_old text := '  -- Transactional replacement: on any error, the previous generation remains.' || chr(10) ||
    '  delete from public.pokemon_market_explorer_prepared_directory_v1' || chr(10) ||
    '  where market_key is not null;' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_directory_v1' || chr(10) ||
    '  select * from _phase5_dir_stage;' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_history_v1' || chr(10) ||
    '  select * from _phase5_history_stage;';
  v_new text := '  -- Candidate data is immutable after this transaction commits.' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_directory_generations_v1 select * from _phase5_dir_stage;' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_history_generations_v1 select * from _phase5_history_stage;' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_generations_v1' || chr(10) ||
    '    (generation_id,status,generated_at,comparison_as_of,source_as_of,directory_rows,history_rows,history_markets,directory_fingerprint,history_fingerprint,completed_at)' || chr(10) ||
    '  select v_generation_id,''complete'',v_generated_at,v_comparison_asof,' || chr(10) ||
    '    jsonb_build_object(''sets'',v_set_source_asof,''sealed'',v_sealed_source_asof),' || chr(10) ||
    '    (select count(*) from _phase5_dir_stage),(select count(*) from _phase5_history_stage),' || chr(10) ||
    '    (select count(distinct market_key) from _phase5_history_stage),' || chr(10) ||
    '    (select md5(coalesce(string_agg(md5(to_jsonb(d)::text),'''' order by market_key),'''')) from _phase5_dir_stage d),' || chr(10) ||
    '    (select md5(coalesce(string_agg(md5(to_jsonb(h)::text),'''' order by market_key,market_date),'''')) from _phase5_history_stage h),' || chr(10) ||
    '    clock_timestamp();' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_publication_audit_v1(action,to_generation_id,operator_path,result,directory_rows,history_rows)' || chr(10) ||
    '    values(''candidate'',v_generation_id,''guarded_refresh'',''created'',(select count(*) from _phase5_dir_stage),(select count(*) from _phase5_history_stage));' || chr(10) ||
    '  insert into public.pokemon_market_explorer_prepared_publication_audit_v1(action,to_generation_id,operator_path,result,directory_rows,history_rows)' || chr(10) ||
    '    values(''validated'',v_generation_id,''guarded_refresh'',''complete'',(select count(*) from _phase5_dir_stage),(select count(*) from _phase5_history_stage));' || chr(10) ||
    '  perform public.switch_pokemon_market_explorer_prepared_generation_v1(v_generation_id,''promote'',''guarded_refresh'');';
begin
  select pg_get_functiondef(p.oid) into v_sql from pg_proc p
    where p.oid='public.refresh_pokemon_market_explorer_prepared_directory_v1()'::regprocedure;
  if position(v_old in v_sql)=0 then
    raise exception 'prepared refresh definition changed; refusing unsafe rewrite';
  end if;
  execute replace(v_sql,v_old,v_new);
end;
$$;

comment on function public.refresh_pokemon_market_explorer_prepared_directory_v1() is
'Builds a validated compact prepared generation, retains previous complete data, and atomically promotes the serving pointer. Guarded wrapper remains the scheduled publication entry point.';

-- Preserve RPC signatures and row types. Only their serving source changes.
do $$
declare
  v_name text;
  v_sql text;
  v_old text;
  v_new text;
  v_oid oid;
begin
  foreach v_name in array array[
    'get_pokemon_market_explorer_prepared_directory_v1',
    'get_pokemon_market_explorer_prepared_comparison_v1',
    'get_pokemon_market_explorer_prepared_history_v1',
    'get_pokemon_market_explorer_prepared_screen_v1',
    'get_pokemon_market_explorer_prepared_constituents_v2'] loop
    select p.oid,pg_get_functiondef(p.oid) into strict v_oid,v_sql
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
      where n.nspname='public' and p.proname=v_name;
    if v_name='get_pokemon_market_explorer_prepared_history_v1' then
      v_old := 'from public.pokemon_market_explorer_prepared_history_v1';
      v_new := 'from public.pokemon_market_explorer_prepared_serving_history_v1';
    else
      v_old := 'from public.pokemon_market_explorer_prepared_directory_v1';
      v_new := 'from public.pokemon_market_explorer_prepared_serving_directory_v1';
    end if;
    if position(v_old in v_sql)=0 then
      raise exception 'prepared reader % changed; refusing unsafe rewrite',v_name;
    end if;
    execute replace(v_sql,v_old,v_new);
  end loop;
end;
$$;
