CREATE OR REPLACE FUNCTION public.get_card_variant_price_observed_history_v2(
    p_card_variant_id uuid,
    p_condition_id uuid,
    p_start_date date DEFAULT NULL,
    p_end_date date DEFAULT NULL,
    p_source text DEFAULT NULL,
    p_currency text DEFAULT 'USD'
)
RETURNS TABLE(
    card_variant_id uuid,
    condition_id uuid,
    source text,
    currency text,
    observed_date date,
    market_price numeric,
    high_price numeric,
    low_price numeric,
    price_effective_date date,
    price_event_id bigint
)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
    WITH bounded_ranges AS MATERIALIZED (
        SELECT r.card_variant_id,
               r.condition_id,
               r.source,
               r.currency,
               greatest(r.observed_from, coalesce(p_start_date, r.observed_from)) AS range_start,
               least(r.observed_through, coalesce(p_end_date, r.observed_through)) AS range_end
        FROM public.card_variant_price_observation_ranges_v2 r
        WHERE r.card_variant_id = p_card_variant_id
          AND r.condition_id = p_condition_id
          AND (p_source IS NULL OR r.source = coalesce(nullif(trim(p_source),''),'UNKNOWN'))
          AND (p_currency IS NULL OR r.currency = coalesce(nullif(trim(both '"' from upper(trim(p_currency))),''),'USD'))
          AND (p_start_date IS NULL OR r.observed_through >= p_start_date)
          AND (p_end_date IS NULL OR r.observed_from <= p_end_date)
    ), observed_days AS MATERIALIZED (
        SELECT r.card_variant_id,
               r.condition_id,
               r.source,
               r.currency,
               gs::date AS observed_date
        FROM bounded_ranges r
        CROSS JOIN LATERAL generate_series(r.range_start,r.range_end,interval '1 day') gs
        WHERE r.range_start <= r.range_end
    )
    SELECT d.card_variant_id,
           d.condition_id,
           d.source,
           d.currency,
           d.observed_date,
           e.market_price,
           e.high_price,
           e.low_price,
           e.effective_date AS price_effective_date,
           e.id AS price_event_id
    FROM observed_days d
    JOIN LATERAL (
        SELECT ev.id,
               ev.market_price,
               ev.high_price,
               ev.low_price,
               ev.effective_date
        FROM public.card_variant_price_events_v2 ev
        WHERE ev.card_variant_id=d.card_variant_id
          AND ev.condition_id=d.condition_id
          AND ev.source=d.source
          AND ev.currency=d.currency
          AND ev.effective_date<=d.observed_date
          AND ev.market_price IS NOT NULL
          AND ev.market_price>0
        ORDER BY ev.effective_date DESC,ev.id DESC
        LIMIT 1
    ) e ON true
    ORDER BY d.observed_date,d.source,d.currency;
$function$;

REVOKE ALL ON FUNCTION public.get_card_variant_price_observed_history_v2(uuid,uuid,date,date,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_card_variant_price_observed_history_v2(uuid,uuid,date,date,text,text) TO service_role;

COMMENT ON FUNCTION public.get_card_variant_price_observed_history_v2(uuid,uuid,date,date,text,text) IS
'Backend-only lossless observed-date price history reconstructed from Price Storage V2 change events plus compressed observation-presence ranges. Returns rows only for dates on which a positive-price raw observation existed.';