begin;

create table public.ebay_active_ask_price_estimates_v1 (
  id uuid primary key default gen_random_uuid(),
  pricing_run_id uuid not null,
  canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
  card_variant_id uuid not null references public.card_variants(id),
  condition_id uuid not null references public.conditions(id),
  market_date date not null,
  source text not null default 'eBayActiveAsk' check (source = 'eBayActiveAsk'),
  evidence_kind text not null default 'active_ask' check (evidence_kind = 'active_ask'),
  estimator_version text not null check (estimator_version = 'ebay_active_ask_lower3_seller_median_v1'),
  eligibility_policy_version text not null,
  eligible_listing_count integer not null check (eligible_listing_count >= 5),
  distinct_seller_count integer not null check (distinct_seller_count >= 5),
  landed_ask_min numeric(12,2) not null check (landed_ask_min > 0),
  landed_ask_max numeric(12,2) not null check (landed_ask_max >= landed_ask_min),
  selected_ask_1 numeric(12,2) not null,
  selected_ask_2 numeric(12,2) not null,
  selected_ask_3 numeric(12,2) not null,
  estimated_price numeric(12,2) not null,
  depth_state text not null check (depth_state = 'SUFFICIENT'),
  input_evidence_fingerprint text not null check (length(input_evidence_fingerprint) = 64),
  estimator_fingerprint text not null check (length(estimator_fingerprint) = 64),
  contributing_evidence jsonb not null check (jsonb_typeof(contributing_evidence) = 'array'),
  source_artifact_fingerprint text not null check (length(source_artifact_fingerprint) = 64),
  created_at timestamptz not null default now(),
  unique (card_variant_id, condition_id, market_date, estimator_version),
  check (selected_ask_1 <= selected_ask_2 and selected_ask_2 <= selected_ask_3),
  check (estimated_price = selected_ask_2),
  check (landed_ask_min = selected_ask_1 and landed_ask_max >= selected_ask_3),
  check (jsonb_array_length(contributing_evidence) >= 5)
);

create index ebay_active_ask_estimate_card_date_idx
  on public.ebay_active_ask_price_estimates_v1 (canonical_card_id, market_date desc);
alter table public.ebay_active_ask_price_estimates_v1 enable row level security;
revoke all on public.ebay_active_ask_price_estimates_v1 from public, anon, authenticated;
grant select, insert on public.ebay_active_ask_price_estimates_v1 to service_role;

comment on table public.ebay_active_ask_price_estimates_v1 is
  'Isolated eBay fixed-price active-ask source estimate; never canonical pricing. Insert-only; conflicting day/version evidence fails closed.';

commit;
