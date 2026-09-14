BEGIN;

CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition_v2_shadow
WITH (security_invoker=true) AS
SELECT
    c.id AS card_id,
    c.set_id,
    s.name AS set_name,
    c.name AS card_name,
    c.card_number,
    c.rarity,
    cv.id AS variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.condition_id,
    cond.name AS condition,
    latest.market_price,
    latest.high_price,
    latest.low_price,
    latest.currency,
    latest.source,
    latest.captured_at,
    latest.created_at
FROM public.card_variants cv
JOIN public.cards c ON c.id = cv.card_id
LEFT JOIN public.sets s ON s.id = c.set_id
CROSS JOIN LATERAL (
    SELECT DISTINCT ON (current_row.condition_id)
        current_row.condition_id,
        current_row.market_price,
        current_row.high_price,
        current_row.low_price,
        current_row.currency,
        current_row.source,
        current_row.last_observed_date AS captured_at,
        current_row.last_observation_created_at AS created_at
    FROM public.card_variant_price_current_v2 current_row
    WHERE current_row.card_variant_id = cv.id
      AND current_row.currency = 'USD'
    ORDER BY current_row.condition_id,
             current_row.last_observed_date DESC NULLS LAST,
             current_row.last_observation_created_at DESC NULLS LAST,
             current_row.last_observation_id DESC NULLS LAST
) latest
LEFT JOIN public.conditions cond ON cond.id = latest.condition_id;

REVOKE ALL ON public.card_market_usd_latest_by_condition_v2_shadow FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.card_market_usd_latest_by_condition_v2_shadow TO service_role;

COMMIT;