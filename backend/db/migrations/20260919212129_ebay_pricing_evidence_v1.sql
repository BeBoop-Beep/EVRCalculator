begin;

create table public.ebay_pricing_runs_v1 (
  run_id uuid primary key,
  market_date date not null,
  status text not null check (status in ('PLANNED','RUNNING','COMPLETE','PARTIAL','FAILED')),
  selector_version text not null,
  selector_fingerprint text not null check (length(selector_fingerprint) = 64),
  collector_version text not null,
  query_strategy_version text not null,
  target_count integer not null check (target_count >= 0),
  planned_request_count integer not null check (planned_request_count between 0 and 1000),
  requests_attempted integer not null default 0 check (requests_attempted >= 0),
  requests_successful integer not null default 0 check (requests_successful >= 0),
  requests_failed integer not null default 0 check (requests_failed >= 0),
  retry_count integer not null default 0 check (retry_count >= 0),
  raw_listing_count integer not null default 0 check (raw_listing_count >= 0),
  deduped_listing_count integer not null default 0 check (deduped_listing_count >= 0),
  identity_qualified_count integer not null default 0 check (identity_qualified_count >= 0),
  english_eligible_count integer not null default 0 check (english_eligible_count >= 0),
  language_unresolved_count integer not null default 0 check (language_unresolved_count >= 0),
  identity_rejected_count integer not null default 0 check (identity_rejected_count >= 0),
  non_english_excluded_count integer not null default 0 check (non_english_excluded_count >= 0),
  persisted_listing_count integer not null default 0 check (persisted_listing_count >= 0),
  started_at timestamptz not null,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  artifact_manifest_path text not null,
  artifact_run_id text not null,
  run_fingerprint text not null check (length(run_fingerprint) = 64),
  production_authority boolean not null default false check (production_authority = false)
);

create table public.ebay_card_listing_evidence_v1 (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.ebay_pricing_runs_v1(run_id),
  market_date date not null,
  captured_at timestamptz not null,
  canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
  card_variant_id uuid references public.card_variants(id),
  condition_id uuid references public.conditions(id),
  listing_item_id text not null,
  marketplace text not null check (marketplace = 'EBAY_US'),
  evidence_kind text not null check (evidence_kind = 'active_ask'),
  query_formulation text not null,
  query_strategy_version text not null,
  currency text not null check (currency = 'USD'),
  item_price_usd numeric(12,2) not null check (item_price_usd >= 0),
  shipping_price_usd numeric(12,2) check (shipping_price_usd >= 0),
  landed_ask_usd numeric(12,2),
  title text not null,
  buying_options text[] not null default '{}',
  condition_text text,
  seller_key_sha256 text check (seller_key_sha256 is null or length(seller_key_sha256) = 64),
  listing_url text,
  image_url text,
  identity_state text not null check (identity_state = 'HIGH_CONFIDENCE'),
  language_state text not null check (language_state in ('LANGUAGE_MATCH','LANGUAGE_UNVERIFIED')),
  english_market_eligibility_state text not null check (english_market_eligibility_state in ('ENGLISH_ELIGIBLE','LANGUAGE_UNRESOLVED')),
  identity_reason text,
  language_reason text,
  eligibility_reason text,
  matcher_version text not null,
  matcher_fingerprint text not null,
  language_policy_version text not null,
  language_policy_fingerprint text not null,
  created_at timestamptz not null default now(),
  unique (run_id, canonical_card_id, listing_item_id),
  check (landed_ask_usd is null or (shipping_price_usd is not null and landed_ask_usd = item_price_usd + shipping_price_usd)),
  check ((language_state = 'LANGUAGE_MATCH' and english_market_eligibility_state = 'ENGLISH_ELIGIBLE')
      or (language_state = 'LANGUAGE_UNVERIFIED' and english_market_eligibility_state = 'LANGUAGE_UNRESOLVED'))
);

create table public.ebay_card_pricing_run_summary_v1 (
  run_id uuid not null references public.ebay_pricing_runs_v1(run_id),
  canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
  card_variant_id uuid references public.card_variants(id),
  raw_count integer not null check (raw_count >= 0),
  deduped_count integer not null check (deduped_count >= 0),
  identity_qualified_count integer not null check (identity_qualified_count >= 0),
  english_eligible_count integer not null check (english_eligible_count >= 0),
  language_unresolved_count integer not null check (language_unresolved_count >= 0),
  identity_rejected_count integer not null check (identity_rejected_count >= 0),
  non_english_excluded_count integer not null check (non_english_excluded_count >= 0),
  persisted_count integer not null check (persisted_count >= 0),
  min_eligible_landed_ask numeric(12,2),
  median_eligible_landed_ask numeric(12,2),
  max_eligible_landed_ask numeric(12,2),
  eligible_seller_count integer,
  query_count integer not null check (query_count >= 0),
  evidence_fingerprint text not null check (length(evidence_fingerprint) = 64),
  primary key (run_id, canonical_card_id)
);

create index ebay_listing_card_date_idx on public.ebay_card_listing_evidence_v1(canonical_card_id, market_date desc);
create index ebay_listing_variant_date_idx on public.ebay_card_listing_evidence_v1(card_variant_id, market_date desc)
  where card_variant_id is not null;
create index ebay_listing_eligibility_date_idx on public.ebay_card_listing_evidence_v1(english_market_eligibility_state, market_date desc);
create index ebay_listing_item_idx on public.ebay_card_listing_evidence_v1(listing_item_id);

alter table public.ebay_pricing_runs_v1 enable row level security;
alter table public.ebay_card_listing_evidence_v1 enable row level security;
alter table public.ebay_card_pricing_run_summary_v1 enable row level security;
revoke all on public.ebay_pricing_runs_v1, public.ebay_card_listing_evidence_v1,
  public.ebay_card_pricing_run_summary_v1 from public, anon, authenticated;
grant select, insert, update on public.ebay_pricing_runs_v1, public.ebay_card_listing_evidence_v1,
  public.ebay_card_pricing_run_summary_v1 to service_role;

commit;
