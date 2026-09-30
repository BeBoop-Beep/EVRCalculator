-- FMA-1: immutable, service-only Focused Market Activity read model.
-- Additive only. This migration does not alter canonical pricing authority.

begin;
set local lock_timeout = '2s';
set local statement_timeout = '30s';

create table public.pokemon_market_explorer_query_cache_revisions_v1 (
  revision_id uuid primary key default gen_random_uuid(),
  query_fingerprint text not null references public.pokemon_market_explorer_query_cache(query_fingerprint) on delete restrict,
  computed_through date not null,
  constituent_count integer not null check (constituent_count >= 0),
  build_token uuid not null,
  published_at timestamptz not null default clock_timestamp(),
  unique (query_fingerprint, build_token)
);
create table public.pokemon_market_explorer_query_cache_revision_members_v1 (
  revision_id uuid not null references public.pokemon_market_explorer_query_cache_revisions_v1(revision_id) on delete restrict,
  rank integer not null check (rank >= 1),
  card_variant_id uuid not null,
  item jsonb not null,
  primary key (revision_id, rank),
  unique (revision_id, card_variant_id)
);

create table public.market_activity_generations_v1 (
  activity_generation_id uuid primary key default gen_random_uuid(),
  as_of date not null,
  surface_generation_id uuid null references public.pokemon_market_explorer_surface_generations_v2(generation_id) on delete restrict,
  query_revision_id uuid null references public.pokemon_market_explorer_query_cache_revisions_v1(revision_id) on delete restrict,
  roster_ref jsonb not null,
  contract_version text not null check (contract_version = 'market_activity_v1.1'),
  domain_version text not null check (domain_version = 'market_activity_domain_v1.1.0'),
  policy_version text not null,
  policy jsonb not null,
  fixture_manifest_sha256 text not null check (fixture_manifest_sha256 = 'e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007'),
  evidence_cutoff timestamptz not null,
  evidence_provenance jsonb not null default '{}'::jsonb,
  sold_evidence_through timestamptz,
  supply_run_ids uuid[] not null default '{}',
  state text not null check (state in ('BUILDING','VALIDATED','REJECTED','RETIRED')),
  serving_state text not null default 'RETAINED' check (serving_state in ('SERVING','RETAINED','RETIRED')),
  diagnostics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default clock_timestamp(),
  built_at timestamptz,
  validated_at timestamptz,
  check (num_nonnulls(surface_generation_id, query_revision_id) = 1)
);
create table public.market_activity_serving_v1 (
  singleton smallint primary key default 1 check (singleton = 1),
  activity_generation_id uuid references public.market_activity_generations_v1(activity_generation_id) on delete restrict,
  previous_activity_generation_id uuid references public.market_activity_generations_v1(activity_generation_id) on delete restrict,
  promoted_at timestamptz
);
insert into public.market_activity_serving_v1(singleton) values (1) on conflict do nothing;

create table public.market_activity_rosters_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  market_key text not null,
  roster_type text not null check (roster_type in ('PREPARED_GENERATION','QUERY_CACHE_PUBLISHED_REVISION')),
  roster_revision jsonb not null,
  roster_as_of date not null,
  roster_denominator integer not null check (roster_denominator >= 0),
  primary key (activity_generation_id, market_key)
);
create table public.market_activity_roster_members_v1 (
  activity_generation_id uuid not null,
  market_key text not null,
  rank integer not null check (rank >= 1),
  instrument_key text not null,
  card_variant_id uuid not null,
  primary key (activity_generation_id, market_key, rank),
  unique (activity_generation_id, market_key, instrument_key),
  unique (activity_generation_id, market_key, card_variant_id),
  foreign key (activity_generation_id, market_key) references public.market_activity_rosters_v1(activity_generation_id, market_key) on delete cascade
);

create table public.market_activity_instrument_windows_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  instrument_key text not null,
  window_days smallint not null check (window_days in (7,30,90,180)),
  card_variant_id uuid not null,
  tier text not null,
  start_date date not null,
  end_date date not null,
  observation_state text not null check (observation_state in ('OBSERVED','NOT_COLLECTED')),
  observation_basis text check (observation_basis in ('WALK_RECEIPT','COLLECTION_RECORD','STORED_ROWS')),
  readiness_state text not null check (readiness_state in ('PROVEN','PARTIAL','UNPROVEN','NOT_COLLECTED')),
  readiness_reasons text[] not null default '{}',
  proven_lower_bound_date date,
  exhausted boolean not null default false,
  reconciled_through timestamptz,
  observed_count integer check (observed_count >= 0),
  proven_count integer check (proven_count >= 0),
  summary_state text check (summary_state in ('AVAILABLE','THIN','NO_RECORDS')),
  summary_basis text check (summary_basis in ('PROVEN_WINDOW','OBSERVED_ONLY')),
  price_record_count integer,
  median_price numeric(12,2), low_price numeric(12,2), high_price numeric(12,2),
  excluded_record_counts jsonb not null default '{}'::jsonb,
  evidence_fingerprint text not null check (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
  primary key (activity_generation_id, instrument_key, window_days),
  check (proven_count is null or readiness_state = 'PROVEN'),
  check ((observation_state = 'NOT_COLLECTED') = (observed_count is null)),
  check (observation_state = 'OBSERVED' or proven_count is null)
);
create table public.market_activity_instrument_asks_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  card_variant_id uuid not null,
  supply_snapshot_id uuid references public.market_active_supply_snapshots_v1(id) on delete restrict,
  ask_state text not null check (ask_state in ('NOT_COLLECTED','COLLECTION_FAILED','CONFIRMATION_MISSING','CONFIRMATION_INVALID','STALE','PARTIALLY_CONFIRMED','FRESH','ZERO_PROVEN','ZERO_UNPROVEN')),
  ask_reasons text[] not null default '{}',
  provider_confirmed_at timestamptz, collected_at timestamptz, current_until timestamptz,
  offer_qualification text not null check (offer_qualification in ('CURRENT','NOT_CURRENT')),
  captured_listing_count integer, captured_quantity integer, quantity_provenance text,
  depth text check (depth in ('LOWER_BOUND','COMPLETE_AT_SOURCE','UNKNOWN')),
  lowest_ask_basis text check (lowest_ask_basis in ('LANDED_PROVEN','ITEM_ONLY','ITEM_ONLY_LEGACY_UNVERIFIED')),
  lowest_ask_amount numeric(12,2),
  unconfirmed_offers jsonb,
  primary key (activity_generation_id, card_variant_id),
  check (current_until is null or ask_state in ('FRESH','ZERO_PROVEN'))
);
create table public.market_activity_peer_ranks_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  instrument_key text not null,
  window_days smallint not null check (window_days in (7,30,90,180)),
  population_key text not null,
  scope_kind text not null check (scope_kind in ('RESEARCH_PANEL','MARKET_ROSTER')),
  scope_id text not null, cohort_revision text not null, state text not null,
  eligible_other_peer_count integer not null check (eligible_other_peer_count >= 0),
  quarantined_peer_count integer not null default 0,
  duplicate_peer_row_count integer not null default 0,
  activity_percentile numeric(4,1), strict_below_pct numeric(4,1), tie_count integer,
  primary key (activity_generation_id, instrument_key, window_days)
);
create table public.market_activity_daily_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  instrument_key text not null, activity_date date not null,
  observed_count integer not null check (observed_count >= 1),
  proof_state text not null check (proof_state in ('PROVEN','OBSERVED_ONLY')),
  first_ingested_at timestamptz, last_ingested_at timestamptz,
  ingested_after_reconciliation boolean not null default false,
  record_count integer not null check (record_count >= 1),
  low_price numeric(12,2) not null, median_price numeric(12,2) not null, high_price numeric(12,2) not null,
  primary key (activity_generation_id, instrument_key, activity_date)
);
create table public.market_activity_supply_daily_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  card_variant_id uuid not null, activity_date date not null,
  provider_confirmed_at timestamptz not null,
  first_collected_at timestamptz not null, last_collected_at timestamptz not null,
  collection_count integer not null check (collection_count >= 1),
  confirmations_on_date integer not null check (confirmations_on_date >= 1),
  state_at_collection text not null, depth text,
  listing_count integer not null check (listing_count >= 0), listed_quantity integer not null check (listed_quantity >= 0),
  quantity_provenance text not null, lowest_ask_basis text, lowest_ask_amount numeric(12,2),
  primary key (activity_generation_id, card_variant_id, activity_date)
);
create table public.market_activity_instrument_series_meta_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  instrument_key text not null, proven_span_start date, proven_span_end date,
  reconciled_through timestamptz, excluded_supply_snapshots jsonb not null default '{}'::jsonb,
  primary key (activity_generation_id, instrument_key)
);

-- Exact contract payloads are persisted for bounded request-time reads. Their
-- component facts remain queryable in the normalized projection tables above.
create table public.market_activity_instrument_payloads_v1 (
  activity_generation_id uuid not null references public.market_activity_generations_v1(activity_generation_id) on delete cascade,
  instrument_key text not null, payload jsonb not null,
  primary key (activity_generation_id, instrument_key)
);
create table public.market_activity_group_payloads_v1 (
  activity_generation_id uuid not null,
  market_key text not null,
  window_days smallint not null check (window_days in (7,30,90,180)),
  payload jsonb not null,
  primary key (activity_generation_id, market_key, window_days),
  foreign key (activity_generation_id, market_key) references public.market_activity_rosters_v1(activity_generation_id, market_key) on delete cascade
);

-- Immutable after validation. Deletes are still possible only through an
-- explicit generation retirement/cleanup operation.
create or replace function public.guard_market_activity_immutable_v1() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
  if exists (select 1 from public.market_activity_generations_v1 g
             where g.activity_generation_id = coalesce(old.activity_generation_id, new.activity_generation_id)
               and g.state in ('VALIDATED','RETIRED')) then
    raise exception 'validated market activity generations are immutable';
  end if;
  return new;
end $$;
do $$ declare t text; begin
  foreach t in array array['market_activity_rosters_v1','market_activity_roster_members_v1','market_activity_instrument_windows_v1','market_activity_instrument_asks_v1','market_activity_peer_ranks_v1','market_activity_daily_v1','market_activity_supply_daily_v1','market_activity_instrument_series_meta_v1','market_activity_instrument_payloads_v1','market_activity_group_payloads_v1'] loop
    execute format('create trigger %I before update on public.%I for each row execute function public.guard_market_activity_immutable_v1()', 'trg_'||t||'_immutable', t);
  end loop;
end $$;

create or replace function public.promote_market_activity_generation_v1(p_activity_generation_id uuid)
returns boolean language plpgsql security definer set search_path = public, pg_temp as $$
declare old_id uuid; pinned_surface uuid; served_surface uuid;
begin
  select activity_generation_id into old_id from public.market_activity_serving_v1 where singleton=1 for update;
  select surface_generation_id into pinned_surface from public.market_activity_generations_v1
   where activity_generation_id=p_activity_generation_id and state='VALIDATED' for update;
  if not found then return false; end if;
  if pinned_surface is not null then
    select generation_id into served_surface from public.pokemon_market_explorer_surface_serving_v2 where singleton=1;
    if served_surface is distinct from pinned_surface then return false; end if;
  end if;
  update public.market_activity_generations_v1 set serving_state='RETAINED'
   where activity_generation_id=old_id and activity_generation_id<>p_activity_generation_id;
  update public.market_activity_generations_v1 set serving_state='SERVING'
   where activity_generation_id=p_activity_generation_id;
  update public.market_activity_serving_v1 set activity_generation_id=p_activity_generation_id,
   previous_activity_generation_id=case when old_id<>p_activity_generation_id then old_id else previous_activity_generation_id end,
   promoted_at=clock_timestamp() where singleton=1;
  return true;
end $$;

-- Replace the existing publisher atomically: READY publication and immutable
-- revision membership now share one transaction and one build token.
create or replace function public.publish_pokemon_market_explorer_query_cache_build(
 p_query_fingerprint text,p_build_token uuid,p_computed_from date,p_computed_through date,
 p_series_payload jsonb,p_current_value numeric,p_constituent_count bigint,
 p_eligible_universe_count bigint,p_current_constituents jsonb) returns boolean
language plpgsql security invoker set search_path=public,pg_temp as $$
declare rev uuid; item jsonb; pos integer:=0; cache_asset text;
begin
  select asset into cache_asset from public.pokemon_market_explorer_query_cache
   where query_fingerprint=p_query_fingerprint and status='building' and build_token=p_build_token and build_expires_at>clock_timestamp() for update;
  if cache_asset is null then return false; end if;
  if cache_asset='cards' then
    if jsonb_typeof(p_current_constituents)<>'array' or jsonb_array_length(p_current_constituents)<>p_constituent_count then return false; end if;
    insert into public.pokemon_market_explorer_query_cache_revisions_v1(query_fingerprint,computed_through,constituent_count,build_token)
    values(p_query_fingerprint,p_computed_through,p_constituent_count::integer,p_build_token) returning revision_id into rev;
    for item in select value from jsonb_array_elements(p_current_constituents) loop
      pos:=pos+1;
      insert into public.pokemon_market_explorer_query_cache_revision_members_v1 values(rev,pos,(item->>'cardVariantId')::uuid,item);
    end loop;
  end if;
  update public.pokemon_market_explorer_query_cache set status='ready',computed_from=p_computed_from,computed_through=p_computed_through,
    series_payload=p_series_payload,current_value=p_current_value,constituent_count=p_constituent_count,eligible_universe_count=p_eligible_universe_count,
    current_constituents=p_current_constituents,last_built_at=clock_timestamp(),updated_at=clock_timestamp(),build_token=null,build_started_at=null,build_expires_at=null
   where query_fingerprint=p_query_fingerprint and status='building' and build_token=p_build_token;
  return found;
end $$;

-- Service-only bounded readers. Payloads are already computed; these never
-- touch provider or canonical query code.
create or replace function public.get_market_activity_group_v1(p_activity_generation_id uuid,p_market_key text,p_window_days smallint)
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select case when g.state='RETIRED' then jsonb_build_object('unavailableReason','ACTIVITY_GENERATION_EXPIRED') else p.payload end
 from public.market_activity_generations_v1 g left join public.market_activity_group_payloads_v1 p using(activity_generation_id)
 where g.activity_generation_id=p_activity_generation_id and p.market_key=p_market_key and p.window_days=p_window_days
$$;
create or replace function public.get_market_activity_instrument_v1(p_activity_generation_id uuid,p_instrument_key text)
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select case when g.state='RETIRED' then jsonb_build_object('unavailableReason','ACTIVITY_GENERATION_EXPIRED') else p.payload end
 from public.market_activity_generations_v1 g left join public.market_activity_instrument_payloads_v1 p using(activity_generation_id)
 where g.activity_generation_id=p_activity_generation_id and p.instrument_key=p_instrument_key
$$;
create or replace function public.get_market_activity_constituent_page_v1(p_activity_generation_id uuid,p_market_key text,p_after_rank integer,p_limit integer)
returns table(rank integer,instrument_key text,card_variant_id uuid,payload jsonb) language sql stable security definer set search_path=public,pg_temp as $$
 select m.rank,m.instrument_key,m.card_variant_id,p.payload from public.market_activity_roster_members_v1 m
 join public.market_activity_generations_v1 g using(activity_generation_id)
 join public.market_activity_instrument_payloads_v1 p using(activity_generation_id,instrument_key)
 where m.activity_generation_id=p_activity_generation_id and m.market_key=p_market_key and m.rank>greatest(p_after_rank,0)
   and g.state in ('VALIDATED') and g.serving_state in ('SERVING','RETAINED') order by m.rank limit least(greatest(p_limit,1),100)
$$;

do $$ declare t text; begin
  foreach t in array array['pokemon_market_explorer_query_cache_revisions_v1','pokemon_market_explorer_query_cache_revision_members_v1','market_activity_generations_v1','market_activity_serving_v1','market_activity_rosters_v1','market_activity_roster_members_v1','market_activity_instrument_windows_v1','market_activity_instrument_asks_v1','market_activity_peer_ranks_v1','market_activity_daily_v1','market_activity_supply_daily_v1','market_activity_instrument_series_meta_v1','market_activity_instrument_payloads_v1','market_activity_group_payloads_v1'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on table public.%I from public,anon,authenticated,service_role',t);
    execute format('grant select,insert on table public.%I to service_role',t);
  end loop;
end $$;
grant update(state,serving_state,diagnostics,built_at,validated_at) on public.market_activity_generations_v1 to service_role;
grant update(activity_generation_id,previous_activity_generation_id,promoted_at) on public.market_activity_serving_v1 to service_role;
revoke all on function public.promote_market_activity_generation_v1(uuid) from public,anon,authenticated;
revoke all on function public.get_market_activity_group_v1(uuid,text,smallint) from public,anon,authenticated;
revoke all on function public.get_market_activity_instrument_v1(uuid,text) from public,anon,authenticated;
revoke all on function public.get_market_activity_constituent_page_v1(uuid,text,integer,integer) from public,anon,authenticated;
grant execute on function public.promote_market_activity_generation_v1(uuid) to service_role;
grant execute on function public.get_market_activity_group_v1(uuid,text,smallint) to service_role;
grant execute on function public.get_market_activity_instrument_v1(uuid,text) to service_role;
grant execute on function public.get_market_activity_constituent_page_v1(uuid,text,integer,integer) to service_role;

commit;
