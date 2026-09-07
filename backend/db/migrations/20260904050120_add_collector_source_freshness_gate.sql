create view public.pokemon_collector_source_latest_valid_v
with (security_invoker = true)
as
select distinct on (s.source_name)
    s.id as source_run_id,
    s.source_name,
    s.source_kind,
    s.run_key,
    s.capture_version,
    s.status,
    s.source_url,
    s.geo,
    s.anchor_term,
    s.window_start,
    s.window_end,
    s.started_at,
    s.completed_at,
    s.captured_at,
    s.source_fingerprint,
    s.item_count,
    s.diagnostics_json
from public.pokemon_collector_source_runs s
where s.status in ('success','partial_failure')
order by
    s.source_name,
    coalesce(s.captured_at, s.completed_at) desc,
    s.completed_at desc,
    s.id;

revoke all on table public.pokemon_collector_source_latest_valid_v from public, anon, authenticated;
grant select on table public.pokemon_collector_source_latest_valid_v to service_role;

create or replace function public.is_pokemon_collector_source_refresh_due(
    p_source_name text,
    p_max_age interval default interval '7 days'
)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_latest timestamptz;
begin
    if p_source_name is null or btrim(p_source_name) = '' then
        raise exception 'source_name is required';
    end if;
    if p_max_age is null or p_max_age <= interval '0 seconds' then
        raise exception 'p_max_age must be positive';
    end if;

    select max(coalesce(captured_at, completed_at)) into v_latest
    from public.pokemon_collector_source_runs
    where source_name = p_source_name
      and status in ('success','partial_failure');

    return v_latest is null or v_latest < timezone('utc', now()) - p_max_age;
end;
$$;

revoke all on function public.is_pokemon_collector_source_refresh_due(text, interval) from public, anon, authenticated;
grant execute on function public.is_pokemon_collector_source_refresh_due(text, interval) to service_role;

comment on function public.is_pokemon_collector_source_refresh_due(text, interval) is
'DB-backed freshness gate for Collector Appeal sources. Defaults to seven days but accepts another positive interval. Failed/aborted/running source runs never satisfy freshness.';