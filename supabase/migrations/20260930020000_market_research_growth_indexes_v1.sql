BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Pre-growth support indexes for the new market-research evidence paths.
-- These tables are still tiny at introduction; create them before daily/backfill
-- volume makes FK checks and provider/card lookups unnecessarily expensive.

CREATE INDEX IF NOT EXISTS pkmnprices_ebay_sold_evidence_v1_provider_listing_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (provider_card_id, provider_listing_id);

CREATE INDEX IF NOT EXISTS pkmnprices_ebay_sold_evidence_v1_run_listing_idx
  ON public.pkmnprices_ebay_sold_evidence_v1 (run_id, provider_listing_id);

CREATE INDEX IF NOT EXISTS market_active_supply_snapshots_canonical_observed_idx
  ON public.market_active_supply_snapshots_v1 (canonical_card_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS grading_population_provider_identities_variant_idx
  ON public.grading_population_provider_identities_v1 (card_variant_id);

CREATE INDEX IF NOT EXISTS grading_population_provider_identities_canonical_idx
  ON public.grading_population_provider_identities_v1 (canonical_card_id);

COMMIT;
