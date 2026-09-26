begin;
set local lock_timeout = '5s';

-- P6: one explicit pipeline run identity per market date and policy version. The manifest is stored here so a
-- resumed run rebuilds nothing from mutable inputs; provider artifacts stay on the VM state directory.
create table public.pokemon_multi_source_pricing_runs_v1 (
  run_id uuid primary key default gen_random_uuid(),
  market_date date not null,
  policy_version text not null check (policy_version = 'pokemon_multi_source_card_price_v1'),
  pipeline_version text not null,
  status text not null check (status in ('RUNNING', 'WAITING', 'COMPLETE', 'PARTIAL', 'FAILED')),
  stage text not null check (stage in (
    'INIT', 'TARGETS_BUILT', 'COLLECTION_RUNNING', 'COLLECTION_COMPLETE', 'EVIDENCE_PERSISTED',
    'ESTIMATES_BUILT', 'MULTI_SOURCE_BUILT', 'VALIDATED', 'COMPLETE')),
  failure_code text,
  failure_detail text,
  target_count integer not null default 0 check (target_count >= 0),
  target_fingerprint text check (target_fingerprint is null or length(target_fingerprint) = 64),
  manifest jsonb,
  ebay_pricing_run_id uuid references public.ebay_pricing_runs_v1(run_id),
  request_cap integer not null check (request_cap between 1 and 1000),
  requests_attempted integer not null default 0 check (requests_attempted >= 0),
  requests_failed integer not null default 0 check (requests_failed >= 0),
  retries integer not null default 0 check (retries >= 0),
  metrics jsonb not null default '{}'::jsonb,
  receipt jsonb,
  started_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  unique (market_date, policy_version),
  check ((status = 'COMPLETE') = (stage = 'COMPLETE')),
  check (status <> 'COMPLETE' or finished_at is not null)
);

create index pokemon_multi_source_pricing_runs_v1_date_idx
  on public.pokemon_multi_source_pricing_runs_v1 (market_date desc);

alter table public.pokemon_multi_source_pricing_runs_v1 enable row level security;
revoke all on public.pokemon_multi_source_pricing_runs_v1 from public, anon, authenticated, service_role;
grant select, insert, update on public.pokemon_multi_source_pricing_runs_v1 to service_role;

comment on table public.pokemon_multi_source_pricing_runs_v1 is
  'Operational run/stage state for the daily eBay + multi-source shadow pricing pipeline. Not a pricing authority.';

-- P6: shared eBay Browse request-budget authority. A per-host sqlite file cannot bound requests when more than one
-- host (VM and a developer machine) calls Browse with the same application key, so the count lives here and every
-- request reserves atomically before it is sent. Restarts cannot reset it; exhaustion raises.
create table public.ebay_browse_request_ledger_v1 (
  budget_day date primary key,
  requests_reserved integer not null default 0 check (requests_reserved >= 0),
  daily_limit integer not null check (daily_limit between 1 and 1000),
  updated_at timestamptz not null default now(),
  check (requests_reserved <= daily_limit)
);

alter table public.ebay_browse_request_ledger_v1 enable row level security;
revoke all on public.ebay_browse_request_ledger_v1 from public, anon, authenticated, service_role;
grant select on public.ebay_browse_request_ledger_v1 to service_role;

comment on table public.ebay_browse_request_ledger_v1 is
  'Daily eBay Browse request counter keyed by America/Phoenix day. Mutated only through reserve_ebay_browse_request_v1.';

create function public.reserve_ebay_browse_request_v1(p_day date, p_limit integer default 1000)
returns integer
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_count integer;
begin
  if p_day is null or p_limit is null or p_limit < 1 or p_limit > 1000 then
    raise exception 'invalid eBay Browse budget reservation' using errcode = '22023';
  end if;
  insert into public.ebay_browse_request_ledger_v1 as ledger (budget_day, requests_reserved, daily_limit)
  values (p_day, 1, p_limit)
  on conflict (budget_day) do update
    set requests_reserved = ledger.requests_reserved + 1, updated_at = now()
    where ledger.requests_reserved < least(ledger.daily_limit, p_limit)
  returning requests_reserved into v_count;
  if v_count is null then
    raise exception 'EBAY_BROWSE_BUDGET_EXHAUSTED' using errcode = 'P0001';
  end if;
  return v_count;
end;
$function$;

revoke all on function public.reserve_ebay_browse_request_v1(date, integer) from public, anon, authenticated;
grant execute on function public.reserve_ebay_browse_request_v1(date, integer) to service_role;

commit;
