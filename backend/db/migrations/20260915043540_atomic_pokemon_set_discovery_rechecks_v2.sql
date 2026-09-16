alter table public.pokemon_set_onboarding_jobs
  add column if not exists provider_discovery_json jsonb not null default '{}'::jsonb,
  add column if not exists provider_last_checked_at timestamptz,
  add column if not exists provider_next_check_at timestamptz,
  add column if not exists provider_card_listing_count integer,
  add column if not exists provider_sealed_listing_count integer;

alter table public.pokemon_set_onboarding_jobs
  drop constraint if exists pokemon_set_onboarding_provider_card_listing_count_check,
  add constraint pokemon_set_onboarding_provider_card_listing_count_check
    check (provider_card_listing_count is null or provider_card_listing_count >= 0),
  drop constraint if exists pokemon_set_onboarding_provider_sealed_listing_count_check,
  add constraint pokemon_set_onboarding_provider_sealed_listing_count_check
    check (provider_sealed_listing_count is null or provider_sealed_listing_count >= 0);

create index if not exists idx_pokemon_set_onboarding_provider_recheck_v2
  on public.pokemon_set_onboarding_jobs (provider_next_check_at, detected_at, id)
  where provider_next_check_at is not null and status <> 'running';

create or replace function public.reconcile_pokemon_set_onboarding_discovery_v2(
    p_source_system text,
    p_source_set_id text,
    p_source_set_name text,
    p_candidate_status text,
    p_discovery_json jsonb,
    p_observed_at timestamptz default now(),
    p_next_check_at timestamptz default null,
    p_card_listing_count integer default null,
    p_sealed_listing_count integer default null
) returns table(
    job_id uuid,
    disposition text,
    status text,
    current_step text,
    state_preserved boolean,
    provider_last_checked_at timestamptz,
    provider_next_check_at timestamptz,
    provider_card_listing_count integer,
    provider_sealed_listing_count integer
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_existing public.pokemon_set_onboarding_jobs;
    v_row public.pokemon_set_onboarding_jobs;
begin
    if nullif(btrim(p_source_system), '') is null then raise exception 'source_system is required'; end if;
    if nullif(btrim(p_source_set_id), '') is null then raise exception 'source_set_id is required'; end if;
    if nullif(btrim(p_source_set_name), '') is null then raise exception 'source_set_name is required'; end if;
    if p_candidate_status not in ('detected','manual_review') then raise exception 'candidate_status must be detected or manual_review'; end if;
    if p_discovery_json is null or jsonb_typeof(p_discovery_json) <> 'object' then raise exception 'discovery_json must be a JSON object'; end if;
    if p_observed_at is null then raise exception 'observed_at is required'; end if;
    if p_card_listing_count is not null and p_card_listing_count < 0 then raise exception 'card_listing_count must be nonnegative'; end if;
    if p_sealed_listing_count is not null and p_sealed_listing_count < 0 then raise exception 'sealed_listing_count must be nonnegative'; end if;

    select * into v_existing
      from public.pokemon_set_onboarding_jobs
     where source_system = p_source_system
       and source_set_id = p_source_set_id
     for update;

    if not found then
        insert into public.pokemon_set_onboarding_jobs(
            tcg, source_system, source_set_id, source_set_name,
            status, current_step, metadata_json,
            provider_discovery_json, provider_last_checked_at, provider_next_check_at,
            provider_card_listing_count, provider_sealed_listing_count,
            detected_at, next_attempt_at
        ) values (
            'pokemon', p_source_system, p_source_set_id, p_source_set_name,
            p_candidate_status, 'metadata_resolution', p_discovery_json,
            p_discovery_json, p_observed_at, p_next_check_at,
            p_card_listing_count, p_sealed_listing_count,
            p_observed_at, p_observed_at
        ) returning * into v_row;

        return query select
            v_row.id, 'inserted'::text, v_row.status, v_row.current_step, false,
            v_row.provider_last_checked_at, v_row.provider_next_check_at,
            v_row.provider_card_listing_count, v_row.provider_sealed_listing_count;
        return;
    end if;

    if v_existing.provider_last_checked_at is not null
       and p_observed_at < v_existing.provider_last_checked_at then
        return query select
            v_existing.id, 'stale_observation_ignored'::text,
            v_existing.status, v_existing.current_step, true,
            v_existing.provider_last_checked_at, v_existing.provider_next_check_at,
            v_existing.provider_card_listing_count, v_existing.provider_sealed_listing_count;
        return;
    end if;

    update public.pokemon_set_onboarding_jobs as j
       set provider_discovery_json = coalesce(j.provider_discovery_json,'{}'::jsonb) || p_discovery_json,
           provider_last_checked_at = p_observed_at,
           provider_next_check_at = coalesce(p_next_check_at, j.provider_next_check_at),
           provider_card_listing_count = coalesce(p_card_listing_count, j.provider_card_listing_count),
           provider_sealed_listing_count = coalesce(p_sealed_listing_count, j.provider_sealed_listing_count)
     where j.id = v_existing.id
     returning j.* into v_row;

    return query select
        v_row.id, 'observed_existing'::text, v_row.status, v_row.current_step, true,
        v_row.provider_last_checked_at, v_row.provider_next_check_at,
        v_row.provider_card_listing_count, v_row.provider_sealed_listing_count;
end
$$;

create or replace function public.list_pokemon_set_onboarding_rechecks_v2(
    p_source_system text default 'tcgplayer',
    p_limit integer default 25,
    p_as_of timestamptz default now()
) returns table(
    job_id uuid,
    source_system text,
    source_set_id text,
    source_set_name text,
    status text,
    current_step text,
    canonical_key text,
    provider_discovery_json jsonb,
    provider_last_checked_at timestamptz,
    provider_next_check_at timestamptz,
    provider_card_listing_count integer,
    provider_sealed_listing_count integer
)
language sql
stable
security definer
set search_path = pg_catalog
as $$
    select
      j.id, j.source_system, j.source_set_id, j.source_set_name,
      j.status, j.current_step, j.canonical_key,
      j.provider_discovery_json, j.provider_last_checked_at, j.provider_next_check_at,
      j.provider_card_listing_count, j.provider_sealed_listing_count
    from public.pokemon_set_onboarding_jobs j
    where j.source_system = p_source_system
      and j.provider_next_check_at is not null
      and j.provider_next_check_at <= p_as_of
      and j.status <> 'running'
    order by j.provider_next_check_at, j.detected_at, j.id
    limit greatest(1, least(coalesce(p_limit,25),100));
$$;

revoke all on function public.reconcile_pokemon_set_onboarding_discovery_v2(text,text,text,text,jsonb,timestamptz,timestamptz,integer,integer) from public, anon, authenticated;
revoke all on function public.list_pokemon_set_onboarding_rechecks_v2(text,integer,timestamptz) from public, anon, authenticated;
grant execute on function public.reconcile_pokemon_set_onboarding_discovery_v2(text,text,text,text,jsonb,timestamptz,timestamptz,integer,integer) to service_role;
grant execute on function public.list_pokemon_set_onboarding_rechecks_v2(text,integer,timestamptz) to service_role;

comment on column public.pokemon_set_onboarding_jobs.provider_discovery_json is
  'Latest/merged provider-observation evidence. Discovery refreshes this field without mutating workflow metadata_json or workflow timestamps.';
comment on column public.pokemon_set_onboarding_jobs.provider_last_checked_at is
  'Newest accepted provider observation timestamp; older out-of-order observations are ignored by the reconciliation RPC.';
comment on column public.pokemon_set_onboarding_jobs.provider_next_check_at is
  'Explicit next provider recheck time. Null means no catalog recheck is scheduled by the DB contract.';
comment on function public.reconcile_pokemon_set_onboarding_discovery_v2(text,text,text,text,jsonb,timestamptz,timestamptz,integer,integer) is
  'Atomic discovery reconciliation. Inserts genuinely new identities; existing identities receive provider evidence only and never have workflow state, metadata_json, ownership, or workflow updated_at rewound.';
comment on function public.list_pokemon_set_onboarding_rechecks_v2(text,integer,timestamptz) is
  'Bounded service-role-only list of explicitly scheduled provider rechecks; running jobs are excluded.';
