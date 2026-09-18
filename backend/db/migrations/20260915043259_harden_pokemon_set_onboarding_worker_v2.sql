alter table public.pokemon_set_onboarding_jobs
  add column if not exists lease_token uuid;

create index if not exists idx_pokemon_set_onboarding_claim_v2
  on public.pokemon_set_onboarding_jobs (next_attempt_at, detected_at, id)
  where status in ('detected','ready','retry','waiting','manual_review');

create or replace function public.claim_next_pokemon_set_onboarding_job_v2(
    p_worker_id text,
    p_lease_seconds integer default 1800,
    p_job_id uuid default null,
    p_include_waiting boolean default false,
    p_force_retry boolean default false
) returns setof public.pokemon_set_onboarding_jobs
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_job public.pokemon_set_onboarding_jobs;
begin
    if nullif(btrim(p_worker_id), '') is null then
        raise exception 'worker_id is required';
    end if;

    update public.pokemon_set_onboarding_jobs
       set status = 'retry',
           next_attempt_at = now(),
           worker_id = null,
           lease_token = null,
           lease_expires_at = null,
           heartbeat_at = null,
           last_error_code = 'lease_expired',
           last_error_message = 'Worker lease expired before completion',
           updated_at = now(),
           completed_at = null
     where status = 'running'
       and lease_expires_at < now();

    update public.pokemon_set_onboarding_jobs
       set status = 'failed',
           completed_at = now(),
           updated_at = now(),
           worker_id = null,
           lease_token = null,
           lease_expires_at = null,
           heartbeat_at = null
     where status = 'retry'
       and attempt_count >= max_attempts;

    select *
      into v_job
      from public.pokemon_set_onboarding_jobs
     where status <> 'ignored'
       and (
            status in ('detected','ready','retry')
            or (p_include_waiting and status = 'waiting')
            or (p_force_retry and status in ('waiting','manual_review'))
       )
       and (p_job_id is null or id = p_job_id)
       and (p_force_retry or next_attempt_at <= now())
       and (status <> 'retry' or attempt_count < max_attempts)
     order by
       case
         when status in ('detected','ready','retry') then 0
         when status = 'waiting' then 1
         else 2
       end,
       next_attempt_at,
       detected_at,
       id
     for update skip locked
     limit 1;

    if not found then
        return;
    end if;

    update public.pokemon_set_onboarding_jobs
       set status = 'running',
           worker_id = p_worker_id,
           lease_token = gen_random_uuid(),
           attempt_count = attempt_count + case when status = 'retry' then 1 else 0 end,
           lease_expires_at = now() + make_interval(secs => greatest(60, p_lease_seconds)),
           heartbeat_at = now(),
           updated_at = now()
     where id = v_job.id
     returning * into v_job;

    return next v_job;
end
$$;

create or replace function public.heartbeat_pokemon_set_onboarding_job_v2(
    p_job_id uuid,
    p_worker_id text,
    p_lease_token uuid,
    p_lease_seconds integer default 1800
) returns setof public.pokemon_set_onboarding_jobs
language sql
security definer
set search_path = pg_catalog
as $$
    update public.pokemon_set_onboarding_jobs
       set heartbeat_at = now(),
           lease_expires_at = now() + make_interval(secs => greatest(60, p_lease_seconds)),
           updated_at = now()
     where id = p_job_id
       and status = 'running'
       and worker_id = p_worker_id
       and lease_token = p_lease_token
       and lease_expires_at >= now()
     returning *;
$$;

create or replace function public.transition_pokemon_set_onboarding_job_v2(
    p_job_id uuid,
    p_worker_id text,
    p_lease_token uuid,
    p_expected_step text,
    p_fields jsonb
) returns setof public.pokemon_set_onboarding_jobs
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_status text;
    v_unknown_key text;
    v_next_attempt timestamptz;
begin
    if p_job_id is null or nullif(btrim(p_worker_id), '') is null or p_lease_token is null then
        raise exception 'job_id, worker_id, and lease_token are required';
    end if;
    if nullif(btrim(p_expected_step), '') is null then
        raise exception 'expected_step is required';
    end if;
    if p_fields is null or jsonb_typeof(p_fields) <> 'object' then
        raise exception 'fields must be a JSON object';
    end if;

    select k into v_unknown_key
      from jsonb_object_keys(p_fields) as t(k)
     where k not in (
       'status','current_step','next_attempt_at','metadata_json',
       'last_error_code','last_error_message','canonical_key','pokemon_api_set_id',
       'era_folder','source_branch','source_pr_number','source_pr_url',
       'source_commit_sha','pull_model_status','latest_market_date','completed_at'
     )
     limit 1;
    if v_unknown_key is not null then
        raise exception 'unsupported transition field: %', v_unknown_key;
    end if;

    v_status := nullif(btrim(p_fields ->> 'status'), '');
    if v_status not in ('ready','waiting','manual_review','retry','completed','failed') then
        raise exception 'unsupported transition status: %', coalesce(v_status, '<null>');
    end if;

    if v_status in ('ready','waiting','retry')
       and nullif(btrim(coalesce(p_fields ->> 'current_step','')), '') is null then
        raise exception 'current_step is required for status %', v_status;
    end if;

    if p_fields ? 'next_attempt_at' and p_fields ->> 'next_attempt_at' is not null then
        v_next_attempt := (p_fields ->> 'next_attempt_at')::timestamptz;
    end if;

    if v_status = 'waiting' and (v_next_attempt is null or v_next_attempt <= now()) then
        raise exception 'waiting transition requires next_attempt_at in the future';
    end if;

    return query
    update public.pokemon_set_onboarding_jobs j
       set status = v_status,
           current_step = case when p_fields ? 'current_step'
                               then p_fields ->> 'current_step' else j.current_step end,
           next_attempt_at = case
               when p_fields ? 'next_attempt_at' and p_fields ->> 'next_attempt_at' is not null
                   then (p_fields ->> 'next_attempt_at')::timestamptz
               when v_status = 'ready' then now()
               else j.next_attempt_at
           end,
           metadata_json = case when p_fields ? 'metadata_json'
                                then coalesce(p_fields -> 'metadata_json', '{}'::jsonb)
                                else j.metadata_json end,
           last_error_code = case when p_fields ? 'last_error_code'
                                  then p_fields ->> 'last_error_code' else j.last_error_code end,
           last_error_message = case when p_fields ? 'last_error_message'
                                     then p_fields ->> 'last_error_message' else j.last_error_message end,
           canonical_key = case when p_fields ? 'canonical_key'
                                then p_fields ->> 'canonical_key' else j.canonical_key end,
           pokemon_api_set_id = case when p_fields ? 'pokemon_api_set_id'
                                     then p_fields ->> 'pokemon_api_set_id' else j.pokemon_api_set_id end,
           era_folder = case when p_fields ? 'era_folder'
                             then p_fields ->> 'era_folder' else j.era_folder end,
           source_branch = case when p_fields ? 'source_branch'
                                then p_fields ->> 'source_branch' else j.source_branch end,
           source_pr_number = case when p_fields ? 'source_pr_number' and p_fields ->> 'source_pr_number' is not null
                                   then (p_fields ->> 'source_pr_number')::integer else j.source_pr_number end,
           source_pr_url = case when p_fields ? 'source_pr_url'
                                then p_fields ->> 'source_pr_url' else j.source_pr_url end,
           source_commit_sha = case when p_fields ? 'source_commit_sha'
                                    then p_fields ->> 'source_commit_sha' else j.source_commit_sha end,
           pull_model_status = case when p_fields ? 'pull_model_status'
                                    then p_fields ->> 'pull_model_status' else j.pull_model_status end,
           latest_market_date = case when p_fields ? 'latest_market_date' and p_fields ->> 'latest_market_date' is not null
                                     then (p_fields ->> 'latest_market_date')::date else j.latest_market_date end,
           completed_at = case
               when v_status in ('completed','failed') then coalesce(
                   case when p_fields ? 'completed_at' and p_fields ->> 'completed_at' is not null
                        then (p_fields ->> 'completed_at')::timestamptz end,
                   now()
               )
               else null
           end,
           worker_id = null,
           lease_token = null,
           lease_expires_at = null,
           heartbeat_at = null,
           updated_at = now()
     where j.id = p_job_id
       and j.status = 'running'
       and j.worker_id = p_worker_id
       and j.lease_token = p_lease_token
       and j.lease_expires_at >= now()
       and j.current_step = p_expected_step
     returning j.*;
end
$$;

revoke all on function public.claim_next_pokemon_set_onboarding_job_v2(text,integer,uuid,boolean,boolean) from public, anon, authenticated;
revoke all on function public.heartbeat_pokemon_set_onboarding_job_v2(uuid,text,uuid,integer) from public, anon, authenticated;
revoke all on function public.transition_pokemon_set_onboarding_job_v2(uuid,text,uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.claim_next_pokemon_set_onboarding_job_v2(text,integer,uuid,boolean,boolean) to service_role;
grant execute on function public.heartbeat_pokemon_set_onboarding_job_v2(uuid,text,uuid,integer) to service_role;
grant execute on function public.transition_pokemon_set_onboarding_job_v2(uuid,text,uuid,text,jsonb) to service_role;

comment on column public.pokemon_set_onboarding_jobs.lease_token is
  'Per-claim fencing token for onboarding worker v2. A transition or heartbeat must present the token issued by the current claim.';
comment on function public.claim_next_pokemon_set_onboarding_job_v2(text,integer,uuid,boolean,boolean) is
  'Lease-token claim contract: actionable work outranks waiting work; waiting participates only in resume sweeps; manual_review requires explicit force.';
comment on function public.heartbeat_pokemon_set_onboarding_job_v2(uuid,text,uuid,integer) is
  'Extends only a currently unexpired onboarding lease owned by worker_id plus lease_token.';
comment on function public.transition_pokemon_set_onboarding_job_v2(uuid,text,uuid,text,jsonb) is
  'CAS-style onboarding transition fenced by job, worker, lease token, unexpired lease, and expected current_step.';
