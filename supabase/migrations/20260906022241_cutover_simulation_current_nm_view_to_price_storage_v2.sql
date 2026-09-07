BEGIN;

CREATE OR REPLACE VIEW public.simulation_input_cards_with_near_mint_price_legacy_shadow
WITH (security_invoker=true) AS
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
    SELECT observation.market_price, observation.captured_at, observation.source
    FROM public.card_variant_price_observations observation
    WHERE observation.card_variant_id = sic.card_variant_id
      AND observation.condition_id = sic.condition_id
      AND observation.market_price > 0
      AND trim(both '"' from upper(coalesce(observation.currency,''))) = 'USD'
    ORDER BY observation.captured_at DESC NULLS LAST,
             observation.created_at DESC NULLS LAST,
             observation.id DESC
    LIMIT 1
) current_nm ON true;

REVOKE ALL ON public.simulation_input_cards_with_near_mint_price_legacy_shadow FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.simulation_input_cards_with_near_mint_price_legacy_shadow TO service_role;

CREATE OR REPLACE VIEW public.simulation_input_cards_with_near_mint_price
WITH (security_invoker=true) AS
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
    current_nm.last_observed_date AS current_near_mint_price_captured_at,
    current_nm.source AS current_near_mint_price_source
FROM public.simulation_input_cards sic
LEFT JOIN LATERAL (
    SELECT current_row.market_price,
           current_row.last_observed_date,
           current_row.source,
           current_row.last_observation_created_at,
           current_row.last_observation_id
    FROM public.card_variant_price_current_v2 current_row
    WHERE current_row.card_variant_id = sic.card_variant_id
      AND current_row.condition_id = sic.condition_id
      AND current_row.market_price > 0
      AND current_row.currency = 'USD'
    ORDER BY current_row.last_observed_date DESC NULLS LAST,
             current_row.last_observation_created_at DESC NULLS LAST,
             current_row.last_observation_id DESC NULLS LAST
    LIMIT 1
) current_nm ON true;

COMMIT;