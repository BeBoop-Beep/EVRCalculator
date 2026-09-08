BEGIN;
CREATE INDEX IF NOT EXISTS card_variant_price_current_v2_event_id_idx
    ON public.card_variant_price_current_v2 (event_id);
COMMIT;