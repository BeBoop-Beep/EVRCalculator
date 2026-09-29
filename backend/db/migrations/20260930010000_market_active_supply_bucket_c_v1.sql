BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.market_active_supply_snapshots_v1
  ADD COLUMN seller_concentration_hhi numeric(9,6) CHECK (seller_concentration_hhi BETWEEN 0 AND 1),
  ADD COLUMN lowest_landed_ask numeric(12,2) CHECK (lowest_landed_ask >= 0),
  ADD COLUMN median_landed_ask numeric(12,2) CHECK (median_landed_ask >= 0),
  ADD COLUMN landed_ask_q1 numeric(12,2) CHECK (landed_ask_q1 >= 0),
  ADD COLUMN landed_ask_q3 numeric(12,2) CHECK (landed_ask_q3 >= 0),
  ADD COLUMN landed_ask_mad numeric(12,2) CHECK (landed_ask_mad >= 0),
  ADD COLUMN price_depth_bands jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(price_depth_bands) = 'object');

ALTER TABLE public.market_active_supply_listing_observations_v1
  ADD COLUMN landed_price numeric(12,2) NOT NULL CHECK (landed_price >= 0),
  ADD COLUMN listing_updated_at timestamptz,
  ADD COLUMN provider_snapshot_at timestamptz,
  ADD COLUMN seller_rating numeric,
  ADD COLUMN seller_sales_count bigint CHECK (seller_sales_count >= 0),
  ADD CONSTRAINT market_active_supply_seller_hash_only CHECK (
    source_seller_id IS NULL OR source_seller_id ~ '^hmac-sha256:v1:[0-9a-f]{64}$'
  );

COMMENT ON COLUMN public.market_active_supply_snapshots_v1.captured_quantity IS
  'Quantity captured within the bounded requested depth; never total market inventory.';
COMMENT ON COLUMN public.market_active_supply_snapshots_v1.has_more IS
  'Provider pagination signal. True means this bounded snapshot is truncated.';
COMMENT ON COLUMN public.market_active_supply_listing_observations_v1.source_seller_id IS
  'Stable privacy-safe keyed HMAC only; raw seller names and provider seller IDs are prohibited.';

COMMIT;
