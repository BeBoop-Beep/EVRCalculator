begin;
set local lock_timeout = '5s';

-- P5B derived multi-source card price authority (shadow). NOT a provider source: rows are derived
-- decisions over TCGPlayer canonical prices and frozen eBayActiveAsk estimates. Never inserted into
-- card_variant_price_observations/events/current and never read by public pricing consumers.
create table public.pokemon_multi_source_card_prices_v1 (
  id uuid primary key default gen_random_uuid(),
  canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
  card_variant_id uuid not null references public.card_variants(id),
  condition_id uuid not null references public.conditions(id),
  market_date date not null,
  pipeline_run_id uuid not null references public.pokemon_multi_source_pricing_runs_v1(run_id),
  ebay_estimate_id uuid references public.ebay_active_ask_price_estimates_v1(id),
  policy_version text not null check (policy_version = 'pokemon_multi_source_card_price_v1'),
  selected_price numeric(12,2) check (selected_price > 0),
  selected_price_source text check (selected_price_source in ('TCGPLAYER', 'EBAY_ACTIVE_ASK')),
  decision_state text not null check (decision_state in (
    'TCGPLAYER_PRIMARY', 'TCGPLAYER_PRIMARY_EBAY_CORROBORATED',
    'TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT', 'TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT',
    'TCGPLAYER_AGING_RETAINED', 'TCGPLAYER_STALE_RETAINED', 'EBAY_ACTIVE_ASK_FALLBACK', 'UNPRICED')),
  decision_reason text not null,
  tcgplayer_price numeric(12,2) check (tcgplayer_price > 0),
  tcgplayer_date date,
  tcgplayer_age_days integer,
  tcgplayer_freshness_state text not null check (tcgplayer_freshness_state in ('FRESH', 'AGING', 'STALE', 'MISSING')),
  ebay_price numeric(12,2) check (ebay_price > 0),
  ebay_market_date date,
  ebay_seller_count integer,
  ebay_listing_count integer,
  ebay_depth_state text check (ebay_depth_state in ('SUFFICIENT', 'THIN', 'INSUFFICIENT')),
  ebay_estimator_version text,
  source_ratio numeric(12,4),
  source_difference_pct numeric(12,4),
  source_agreement_state text not null check (source_agreement_state in (
    'AGREE', 'MODERATE_DISAGREEMENT', 'SEVERE_DISAGREEMENT', 'SINGLE_SOURCE_ONLY')),
  input_fingerprint text not null check (length(input_fingerprint) = 64),
  decision_fingerprint text not null check (length(decision_fingerprint) = 64),
  created_at timestamptz not null default now(),
  unique (card_variant_id, condition_id, market_date, policy_version),
  -- No numeric blend: the selected price is exactly one provider value, or absent.
  check ((selected_price is null) = (selected_price_source is null)),
  check ((decision_state = 'UNPRICED') = (selected_price is null)),
  check (selected_price_source is distinct from 'TCGPLAYER' or selected_price = tcgplayer_price),
  check (selected_price_source is distinct from 'EBAY_ACTIVE_ASK' or selected_price = ebay_price),
  -- eBay may only fill when TCGplayer is absent and depth is SUFFICIENT.
  check (decision_state <> 'EBAY_ACTIVE_ASK_FALLBACK' or
         (tcgplayer_price is null and ebay_depth_state = 'SUFFICIENT' and selected_price_source = 'EBAY_ACTIVE_ASK')),
  check (selected_price_source is distinct from 'EBAY_ACTIVE_ASK' or decision_state = 'EBAY_ACTIVE_ASK_FALLBACK'),
  check (ebay_price is null or ebay_depth_state = 'SUFFICIENT'),
  -- every numeric eBay value is traceable to one frozen estimate row.
  check ((ebay_price is null) = (ebay_estimate_id is null))
);

create index pokemon_multi_source_card_prices_v1_card_date_idx
  on public.pokemon_multi_source_card_prices_v1 (canonical_card_id, market_date desc);

alter table public.pokemon_multi_source_card_prices_v1 enable row level security;
-- Supabase default privileges grant ALL to service_role on new tables; strip them so the grant below is truly insert-only.
revoke all on public.pokemon_multi_source_card_prices_v1 from public, anon, authenticated, service_role;
grant select, insert on public.pokemon_multi_source_card_prices_v1 to service_role;

comment on table public.pokemon_multi_source_card_prices_v1 is
  'Derived multi-source (TCGplayer + eBayActiveAsk) card price decisions, policy pokemon_multi_source_card_price_v1. Shadow only; insert-only; not a provider source and not read by public pricing.';

commit;
