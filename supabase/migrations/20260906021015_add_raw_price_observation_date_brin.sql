BEGIN;

CREATE INDEX IF NOT EXISTS idx_cvpo_captured_at_brin
ON public.card_variant_price_observations
USING brin (captured_at)
WITH (pages_per_range = 32);

COMMIT;