-- Add the actual current Near Mint observation clock to the simulation-card
-- projection. Existing columns and their order are preserved; the two new
-- columns come from the same lateral row that supplies current_near_mint_price.
--
-- The Supabase CLI was unavailable in the implementation environment, so this
-- migration follows the repository's manually-applied, idempotent convention.

BEGIN;

CREATE OR REPLACE VIEW public.simulation_input_cards_with_near_mint_price AS
SELECT
    sic.id,
    sic.calculation_run_id,
    sic.card_id,
    sic.card_variant_id,
    sic.condition_id,
    sic.card_name,
    sic.rarity_bucket,
    sic.price_source,
    sic.price_used,
    sic.captured_at,
    sic.effective_pull_rate,
    sic.ev_contribution,
    sic.created_at,
    current_nm.market_price AS current_near_mint_price,
    current_nm.captured_at AS current_near_mint_price_captured_at,
    current_nm.source AS current_near_mint_price_source
FROM public.simulation_input_cards sic
LEFT JOIN LATERAL (
    SELECT
        observation.market_price,
        observation.captured_at,
        observation.source
    FROM public.card_variant_price_observations observation
    WHERE observation.card_variant_id = sic.card_variant_id
      AND observation.condition_id = sic.condition_id
      AND observation.market_price > 0
      AND trim(both '"' from upper(coalesce(observation.currency, ''))) = 'USD'
    ORDER BY
        observation.captured_at DESC NULLS LAST,
        observation.created_at DESC NULLS LAST,
        observation.id DESC
    LIMIT 1
) current_nm ON true;

COMMENT ON VIEW public.simulation_input_cards_with_near_mint_price IS
    'Run-frozen simulation inputs plus the latest current Near Mint USD price. '
    'current_near_mint_price, current_near_mint_price_captured_at, and '
    'current_near_mint_price_source always originate from the same observation row.';

COMMIT;
