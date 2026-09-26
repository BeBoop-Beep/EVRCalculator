begin;
set local lock_timeout = '5s';

-- ebay_api_budget_policy_v2: provider-aware, resource-bucket-aware request budget. Additive: the V1 ledger
-- (ebay_browse_request_ledger_v1 / reserve_ebay_browse_request_v1) and its history are untouched.
--
-- Two authorities:
--   * provider analytics VERIFY the ceiling and the window (register_ebay_api_budget_window_v2);
--   * this table does per-request ACCOUNTING across every host (reserve_ebay_api_request_v2).
-- The window is the provider's own reset window, NOT a Phoenix calendar day.
create table public.ebay_api_request_budget_v2 (
  id uuid primary key default gen_random_uuid(),
  provider_keyset_identity text not null check (length(provider_keyset_identity) between 10 and 128),
  api_name text not null check (api_name in ('Browse')),
  resource_bucket text not null check (resource_bucket in ('BUY_BROWSE_STANDARD', 'BUY_BROWSE_BULK_ITEMS')),
  provider_window_start timestamptz not null,
  provider_window_end timestamptz not null,
  provider_reset_at timestamptz not null,
  provider_limit integer not null check (provider_limit between 1 and 5000),
  policy_version text not null check (policy_version = 'ebay_api_budget_policy_v2'),
  safety_reserve integer not null check (safety_reserve >= 0),
  usable_limit integer not null check (usable_limit >= 0),
  requests_reserved integer not null default 0 check (requests_reserved >= 0),
  provider_usage_state text not null check (provider_usage_state in
    ('PROVIDER_USAGE_OK', 'DERIVED_FROM_LAST_VERIFIED')),
  provider_reported_used integer,
  provider_reported_remaining integer,
  last_provider_check_at timestamptz,
  verified_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider_keyset_identity, api_name, resource_bucket, provider_window_start, provider_window_end),
  check (provider_window_end > provider_window_start),
  check (provider_reset_at = provider_window_end),
  check (usable_limit = provider_limit - safety_reserve)
);

create index ebay_api_request_budget_v2_lookup_idx
  on public.ebay_api_request_budget_v2 (provider_keyset_identity, api_name, resource_bucket, provider_window_end desc);

alter table public.ebay_api_request_budget_v2 enable row level security;
revoke all on public.ebay_api_request_budget_v2 from public, anon, authenticated, service_role;
grant select on public.ebay_api_request_budget_v2 to service_role;

comment on table public.ebay_api_request_budget_v2 is
  'Per-provider-window eBay API request accounting (policy ebay_api_budget_policy_v2). Mutated only through the register/reserve RPCs.';

-- The reserve is decided HERE from the provider limit (10%, at least 100: 500 of 5000) so no caller can raise the
-- effective ceiling. The provider limit is capped at the 5000 recognised for this policy version.
create function public.register_ebay_api_budget_window_v2(
  p_keyset text, p_api text, p_bucket text, p_window_start timestamptz, p_reset_at timestamptz,
  p_provider_limit integer, p_provider_used integer default null, p_provider_remaining integer default null)
returns integer
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_limit integer := least(p_provider_limit, 5000);
  v_reserve integer;
  v_reserved integer;
begin
  if p_keyset is null or p_window_start is null or p_reset_at is null or p_reset_at <= p_window_start
     or p_provider_limit is null or p_provider_limit < 1 then
    raise exception 'invalid eBay budget window registration' using errcode = '22023';
  end if;
  v_reserve := greatest(100, floor(v_limit * 0.10)::integer);
  if v_reserve >= v_limit then
    raise exception 'provider limit too small for the safety reserve' using errcode = '22023';
  end if;
  insert into public.ebay_api_request_budget_v2 as b (
    provider_keyset_identity, api_name, resource_bucket, provider_window_start, provider_window_end, provider_reset_at,
    provider_limit, policy_version, safety_reserve, usable_limit, provider_usage_state,
    provider_reported_used, provider_reported_remaining, last_provider_check_at, verified_at)
  values (p_keyset, p_api, p_bucket, p_window_start, p_reset_at, p_reset_at, v_limit, 'ebay_api_budget_policy_v2',
          v_reserve, v_limit - v_reserve, 'PROVIDER_USAGE_OK', p_provider_used, p_provider_remaining, now(), now())
  on conflict (provider_keyset_identity, api_name, resource_bucket, provider_window_start, provider_window_end) do update
    set provider_limit = excluded.provider_limit, safety_reserve = excluded.safety_reserve, usable_limit = excluded.usable_limit,
        provider_usage_state = 'PROVIDER_USAGE_OK', provider_reported_used = excluded.provider_reported_used,
        provider_reported_remaining = excluded.provider_reported_remaining, last_provider_check_at = now(),
        verified_at = now(), updated_at = now()
  returning requests_reserved into v_reserved;
  -- provider analytics lag: this NEVER reconciles requests_reserved downward.
  return v_reserved;
end;
$function$;

-- Per-request reservation inside the provider window that covers now(). If analytics has been unavailable, the next
-- window is derived from the last verified window (same limit, contiguous 86400s) but only while the last
-- verification is younger than 36 hours; otherwise fail closed. Pools never borrow from each other.
create function public.reserve_ebay_api_request_v2(p_keyset text, p_api text, p_bucket text)
returns integer
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_row public.ebay_api_request_budget_v2%rowtype;
  v_last public.ebay_api_request_budget_v2%rowtype;
  v_len interval;
  v_start timestamptz;
  v_count integer;
begin
  select * into v_row from public.ebay_api_request_budget_v2
   where provider_keyset_identity = p_keyset and api_name = p_api and resource_bucket = p_bucket
     and provider_window_start <= now() and now() < provider_window_end
   order by provider_window_end desc limit 1 for update;
  if not found then
    select * into v_last from public.ebay_api_request_budget_v2
     where provider_keyset_identity = p_keyset and api_name = p_api and resource_bucket = p_bucket
     order by provider_window_end desc limit 1;
    if not found then
      raise exception 'EBAY_BUDGET_WINDOW_UNKNOWN' using errcode = 'P0002';
    end if;
    if now() - v_last.verified_at > interval '36 hours' then
      raise exception 'EBAY_BUDGET_VERIFICATION_STALE' using errcode = 'P0003';
    end if;
    v_len := v_last.provider_window_end - v_last.provider_window_start;
    v_start := v_last.provider_window_end
      + v_len * floor(extract(epoch from (now() - v_last.provider_window_end)) / extract(epoch from v_len));
    insert into public.ebay_api_request_budget_v2 (
      provider_keyset_identity, api_name, resource_bucket, provider_window_start, provider_window_end, provider_reset_at,
      provider_limit, policy_version, safety_reserve, usable_limit, provider_usage_state, verified_at)
    values (p_keyset, p_api, p_bucket, v_start, v_start + v_len, v_start + v_len, v_last.provider_limit,
            'ebay_api_budget_policy_v2', v_last.safety_reserve, v_last.usable_limit, 'DERIVED_FROM_LAST_VERIFIED', v_last.verified_at)
    on conflict (provider_keyset_identity, api_name, resource_bucket, provider_window_start, provider_window_end) do nothing;
    select * into v_row from public.ebay_api_request_budget_v2
     where provider_keyset_identity = p_keyset and api_name = p_api and resource_bucket = p_bucket
       and provider_window_start <= now() and now() < provider_window_end
     order by provider_window_end desc limit 1 for update;
    if not found then
      raise exception 'EBAY_BUDGET_WINDOW_UNKNOWN' using errcode = 'P0002';
    end if;
  end if;
  if now() - v_row.verified_at > interval '36 hours' then
    raise exception 'EBAY_BUDGET_VERIFICATION_STALE' using errcode = 'P0003';
  end if;
  if v_row.requests_reserved >= v_row.usable_limit then
    raise exception 'EBAY_BUDGET_EXHAUSTED' using errcode = 'P0001';
  end if;
  update public.ebay_api_request_budget_v2 set requests_reserved = requests_reserved + 1, updated_at = now()
   where id = v_row.id returning requests_reserved into v_count;
  return v_count;
end;
$function$;

revoke all on function public.register_ebay_api_budget_window_v2(text, text, text, timestamptz, timestamptz, integer, integer, integer) from public, anon, authenticated;
grant execute on function public.register_ebay_api_budget_window_v2(text, text, text, timestamptz, timestamptz, integer, integer, integer) to service_role;
revoke all on function public.reserve_ebay_api_request_v2(text, text, text) from public, anon, authenticated;
grant execute on function public.reserve_ebay_api_request_v2(text, text, text) to service_role;

-- V2 pipelines plan against a 4500-request pool. The V1 caps of 1000 were self-imposed; relax them additively
-- (V1 runs remain valid under the wider check, and V1 code still refuses to exceed 1000 by its own constant).
alter table public.pokemon_multi_source_pricing_runs_v1 drop constraint pokemon_multi_source_pricing_runs_v1_request_cap_check;
alter table public.pokemon_multi_source_pricing_runs_v1
  add constraint pokemon_multi_source_pricing_runs_v1_request_cap_check check (request_cap between 1 and 5000);
alter table public.ebay_pricing_runs_v1 drop constraint ebay_pricing_runs_v1_planned_request_count_check;
alter table public.ebay_pricing_runs_v1
  add constraint ebay_pricing_runs_v1_planned_request_count_check check (planned_request_count between 0 and 5000);

commit;
