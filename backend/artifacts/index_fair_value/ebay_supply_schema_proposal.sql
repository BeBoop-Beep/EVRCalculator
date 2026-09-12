-- DESIGN ONLY. Do not apply in D1.
create table research.ebay_card_market_source_runs (
  id uuid primary key, source text not null check (source='ebay_browse'), marketplace text not null,
  observed_at timestamptz not null, captured_at timestamptz not null,
  status text not null, query_version text not null, query_fingerprint text not null,
  api_calls integer not null, result_count integer not null, latency_ms integer,
  rate_limit_json jsonb not null default '{}'::jsonb, methodology_version text not null
);
create table research.ebay_card_active_listing_observations (
  run_id uuid not null references research.ebay_card_market_source_runs(id),
  canonical_card_id uuid not null, card_variant_id uuid, item_id text not null,
  observed_at timestamptz not null, captured_at timestamptz not null,
  seller_identifier text, listing_price numeric, shipping_price numeric, currency text,
  source_condition text, buying_options text[], title text,
  match_state text not null, match_confidence numeric not null,
  query_fingerprint text not null, minimal_source_payload jsonb,
  primary key(run_id, canonical_card_id, item_id)
);
create table research.ebay_card_active_listing_aggregates (
  run_id uuid not null references research.ebay_card_market_source_runs(id),
  canonical_card_id uuid not null, observed_at timestamptz not null, captured_at timestamptz not null,
  query_total_estimate integer, returned_count integer, exact_match_listing_count integer,
  unique_seller_count integer, median_listing_price numeric, trimmed_mean_listing_price numeric,
  min_listing_price numeric, p25_listing_price numeric, p75_listing_price numeric,
  listing_price_iqr numeric, listing_price_cv numeric, fixed_price_count integer, auction_count integer,
  contamination_json jsonb not null, primary key(run_id, canonical_card_id)
);
