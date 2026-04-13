-- Daily canonical pricing for card_variant_price_observations.
-- Uniqueness key: (card_variant_id, condition_id, source, captured_date)
-- Business rule: latest scrape wins for same-day conflicts.

BEGIN;

-- 1) Ensure source is usable in uniqueness and conflict targeting.
ALTER TABLE public.card_variant_price_observations
    ALTER COLUMN source SET DEFAULT 'UNKNOWN';

UPDATE public.card_variant_price_observations
SET source = 'UNKNOWN'
WHERE source IS NULL;

ALTER TABLE public.card_variant_price_observations
    ALTER COLUMN source SET NOT NULL;

-- 2) Add captured_date and backfill from captured_at::date.
ALTER TABLE public.card_variant_price_observations
    ADD COLUMN IF NOT EXISTS captured_date date;

UPDATE public.card_variant_price_observations
SET captured_at = COALESCE(captured_at, timezone('utc', now()))
WHERE captured_at IS NULL;

UPDATE public.card_variant_price_observations
SET captured_date = captured_at::date
WHERE captured_date IS NULL;

ALTER TABLE public.card_variant_price_observations
    ALTER COLUMN captured_date SET NOT NULL;

-- 2b) Maintain updated_at and keep captured_date derived from captured_at.
ALTER TABLE public.card_variant_price_observations
    ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT timezone('utc', now());

CREATE OR REPLACE FUNCTION public.sync_card_variant_price_observation_timestamps()
RETURNS trigger AS $$
BEGIN
    NEW.captured_at := COALESCE(NEW.captured_at, timezone('utc', now()));
    NEW.captured_date := NEW.captured_at::date;
    NEW.updated_at := timezone('utc', now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_card_variant_price_observation_timestamps
    ON public.card_variant_price_observations;

CREATE TRIGGER trg_sync_card_variant_price_observation_timestamps
BEFORE INSERT OR UPDATE ON public.card_variant_price_observations
FOR EACH ROW
EXECUTE FUNCTION public.sync_card_variant_price_observation_timestamps();

-- 3) Keep only the latest row per canonical day key before adding unique index.
WITH ranked AS (
    SELECT
        id,
        row_number() OVER (
            PARTITION BY card_variant_id, condition_id, source, captured_date
            ORDER BY captured_at DESC NULLS LAST, id DESC
        ) AS rn
    FROM public.card_variant_price_observations
)
DELETE FROM public.card_variant_price_observations p
USING ranked r
WHERE p.id = r.id
  AND r.rn > 1;

-- 4) Enforce DB-level daily uniqueness for safe upsert conflict targeting.
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_variant_price_observations_daily
    ON public.card_variant_price_observations (card_variant_id, condition_id, source, captured_date);

COMMIT;
