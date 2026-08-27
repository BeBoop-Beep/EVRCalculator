BEGIN;
ALTER TABLE public.pokemon_card_chase_efficiency_rows
    ADD COLUMN IF NOT EXISTS chase_spend_50 NUMERIC
        GENERATED ALWAYS AS ((milestones_json->'50'->>'spend')::NUMERIC) STORED,
    ADD COLUMN IF NOT EXISTS cost_multiple_50 NUMERIC
        GENERATED ALWAYS AS (((milestones_json->'50'->>'spend')::NUMERIC / current_near_mint_market_price)) STORED;
CREATE INDEX IF NOT EXISTS pokemon_card_chase_efficiency_rows_spend50_idx
    ON public.pokemon_card_chase_efficiency_rows(snapshot_id, chase_spend_50, card_variant_id);
CREATE INDEX IF NOT EXISTS pokemon_card_chase_efficiency_rows_multiple50_idx
    ON public.pokemon_card_chase_efficiency_rows(snapshot_id, cost_multiple_50, card_variant_id);
COMMIT;
