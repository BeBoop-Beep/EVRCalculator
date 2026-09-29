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

-- The authorized Bucket C smoke ran against the Bucket A schema before this
-- additive migration was deployed. Preserve those already-persisted facts by
-- promoting the compatibility JSONB fields into their typed columns.
UPDATE public.market_active_supply_snapshots_v1
SET seller_concentration_hhi = NULLIF(source_payload->>'seller_concentration_hhi','')::numeric,
    lowest_landed_ask = NULLIF(source_payload->>'lowest_landed_ask','')::numeric,
    median_landed_ask = NULLIF(source_payload->>'median_landed_ask','')::numeric,
    landed_ask_q1 = NULLIF(source_payload->>'landed_ask_q1','')::numeric,
    landed_ask_q3 = NULLIF(source_payload->>'landed_ask_q3','')::numeric,
    landed_ask_mad = NULLIF(source_payload->>'landed_ask_mad','')::numeric,
    price_depth_bands = COALESCE(source_payload->'price_depth_bands','{}'::jsonb)
WHERE source_payload->>'schema_compatibility' = 'bucket_a_jsonb';

ALTER TABLE public.market_active_supply_listing_observations_v1
  ADD COLUMN landed_price numeric(12,2) CHECK (landed_price >= 0),
  ADD COLUMN listing_updated_at timestamptz,
  ADD COLUMN provider_snapshot_at timestamptz,
  ADD COLUMN seller_rating numeric,
  ADD COLUMN seller_sales_count bigint CHECK (seller_sales_count >= 0);

UPDATE public.market_active_supply_listing_observations_v1
SET landed_price = COALESCE(
      NULLIF(source_payload->>'landed_price','')::numeric,
      item_price + COALESCE(shipping_price,0)
    ),
    listing_updated_at = NULLIF(source_payload->>'listing_updated_at','')::timestamptz,
    provider_snapshot_at = NULLIF(source_payload->>'provider_snapshot_at','')::timestamptz,
    seller_rating = NULLIF(source_payload->>'seller_rating','')::numeric,
    seller_sales_count = NULLIF(source_payload->>'seller_sales_count','')::bigint
WHERE source_payload->>'schema_compatibility' = 'bucket_a_jsonb';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.market_active_supply_listing_observations_v1
    WHERE landed_price IS NULL
  ) THEN
    RAISE EXCEPTION 'MARKET_ACTIVE_SUPPLY_LANDED_PRICE_BACKFILL_INCOMPLETE';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.market_active_supply_listing_observations_v1
    WHERE source_seller_id IS NOT NULL
      AND source_seller_id !~ '^hmac-sha256:v1:[0-9a-f]{64}$'
  ) THEN
    RAISE EXCEPTION 'MARKET_ACTIVE_SUPPLY_UNSAFE_SELLER_IDENTITY_PRESENT';
  END IF;
END
$$;

ALTER TABLE public.market_active_supply_listing_observations_v1
  ALTER COLUMN landed_price SET NOT NULL,
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
