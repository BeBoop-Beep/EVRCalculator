BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

CREATE INDEX fair_value_shadow_market_bindings_v1_canonical_idx
  ON public.fair_value_shadow_market_bindings_v1 (canonical_card_id);
CREATE INDEX fair_value_shadow_market_bindings_v1_variant_idx
  ON public.fair_value_shadow_market_bindings_v1 (card_variant_id);
CREATE INDEX fair_value_shadow_market_bindings_v1_condition_idx
  ON public.fair_value_shadow_market_bindings_v1 (condition_id);

COMMIT;
