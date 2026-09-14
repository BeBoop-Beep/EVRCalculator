CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition_legacy_shadow
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
    SELECT DISTINCT ON (cvpo.condition_id)
        cvpo.condition_id,
        cvpo.market_price,
        cvpo.high_price,
        cvpo.low_price,
        cvpo.currency,
        cvpo.source,
        cvpo.captured_at,
        cvpo.created_at
    FROM public.card_variant_price_observations cvpo
    WHERE cvpo.card_variant_id = cv.id
      AND (cvpo.currency = 'USD' OR cvpo.currency = '"USD"')
    ORDER BY cvpo.condition_id, cvpo.captured_at DESC NULLS LAST, cvpo.created_at DESC NULLS LAST, cvpo.id DESC
) latest
LEFT JOIN public.conditions cond ON cond.id = latest.condition_id;

REVOKE ALL ON public.card_market_usd_latest_by_condition_legacy_shadow FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.card_market_usd_latest_by_condition_legacy_shadow TO service_role;

CREATE OR REPLACE VIEW public.card_market_usd_latest_by_condition
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
    latest.last_observed_date AS captured_at,
    latest.last_observation_created_at AS created_at
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
        current_row.last_observed_date,
        current_row.last_observation_created_at,
        current_row.last_observation_id
    FROM public.card_variant_price_current_v2 current_row
    WHERE current_row.card_variant_id = cv.id
      AND current_row.currency = 'USD'
    ORDER BY current_row.condition_id,
             current_row.last_observed_date DESC NULLS LAST,
             current_row.last_observation_created_at DESC NULLS LAST,
             current_row.last_observation_id DESC NULLS LAST
) latest
LEFT JOIN public.conditions cond ON cond.id = latest.condition_id;

COMMENT ON VIEW public.card_market_usd_latest_by_condition IS
'Production latest card price by variant+condition, sourced from Price Storage V2 current state. Legacy raw-backed definition is retained as card_market_usd_latest_by_condition_legacy_shadow for rollback validation.';