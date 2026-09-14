CREATE TABLE IF NOT EXISTS public.card_variant_price_monthly_rollups_v2_shadow (
    card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE CASCADE,
    condition_id uuid NOT NULL REFERENCES public.conditions(id),
    source text NOT NULL,
    currency text NOT NULL,
    rollup_month date NOT NULL,
    open_market_price numeric,
    close_market_price numeric,
    avg_market_price numeric,
    min_market_price numeric,
    max_market_price numeric,
    avg_high_price numeric,
    avg_low_price numeric,
    observation_count integer NOT NULL,
    first_captured_at date,
    last_captured_at date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(card_variant_id,condition_id,source,rollup_month)
);
ALTER TABLE public.card_variant_price_monthly_rollups_v2_shadow ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.card_variant_price_monthly_rollups_v2_shadow FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.card_variant_price_monthly_rollups_v2_shadow TO service_role;

CREATE OR REPLACE FUNCTION public.rebuild_card_variant_price_monthly_rollups_v2_shadow_for_set(
    p_set_id uuid,
    p_rollup_month date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_month date;
    v_month_end date;
    v_rows bigint:=0;
BEGIN
    IF p_set_id IS NULL OR p_rollup_month IS NULL THEN
        RAISE EXCEPTION 'set_id and rollup_month are required';
    END IF;
    v_month:=date_trunc('month',p_rollup_month::timestamp)::date;
    v_month_end:=(v_month+interval '1 month - 1 day')::date;

    DELETE FROM public.card_variant_price_monthly_rollups_v2_shadow shadow
    USING public.card_variants cv,public.cards c
    WHERE shadow.card_variant_id=cv.id
      AND cv.card_id=c.id
      AND c.set_id=p_set_id
      AND shadow.rollup_month=v_month;

    WITH observed_days AS MATERIALIZED (
        SELECT r.card_variant_id,
               r.condition_id,
               r.source,
               r.currency,
               gs::date AS observed_date
        FROM public.card_variant_price_observation_ranges_v2 r
        JOIN public.card_variants cv ON cv.id=r.card_variant_id
        JOIN public.cards c ON c.id=cv.card_id
        CROSS JOIN LATERAL generate_series(
            greatest(r.observed_from,v_month),
            least(r.observed_through,v_month_end),
            interval '1 day'
        ) gs
        WHERE c.set_id=p_set_id
          AND r.observed_through>=v_month
          AND r.observed_from<=v_month_end
    ), daily_state AS MATERIALIZED (
        SELECT d.card_variant_id,d.condition_id,d.source,d.currency,d.observed_date,
               e.market_price,e.high_price,e.low_price
        FROM observed_days d
        JOIN LATERAL (
            SELECT ev.market_price,ev.high_price,ev.low_price
            FROM public.card_variant_price_events_v2 ev
            WHERE ev.card_variant_id=d.card_variant_id
              AND ev.condition_id=d.condition_id
              AND ev.source=d.source
              AND ev.currency=d.currency
              AND ev.effective_date<=d.observed_date
            ORDER BY ev.effective_date DESC,ev.id DESC
            LIMIT 1
        ) e ON true
    ), ranked AS MATERIALIZED (
        SELECT s.*,
               row_number() OVER (
                   PARTITION BY s.card_variant_id,s.condition_id,s.source
                   ORDER BY s.observed_date ASC
               ) rn_open,
               row_number() OVER (
                   PARTITION BY s.card_variant_id,s.condition_id,s.source
                   ORDER BY s.observed_date DESC
               ) rn_close
        FROM daily_state s
    ), aggregated AS (
        SELECT card_variant_id,condition_id,source,
               max(currency) currency,
               v_month rollup_month,
               max(CASE WHEN rn_open=1 THEN market_price END) open_market_price,
               max(CASE WHEN rn_close=1 THEN market_price END) close_market_price,
               avg(market_price) avg_market_price,
               min(market_price) min_market_price,
               max(market_price) max_market_price,
               avg(high_price) avg_high_price,
               avg(low_price) avg_low_price,
               count(*)::integer observation_count,
               min(observed_date) first_captured_at,
               max(observed_date) last_captured_at
        FROM ranked
        GROUP BY card_variant_id,condition_id,source
    )
    INSERT INTO public.card_variant_price_monthly_rollups_v2_shadow(
        card_variant_id,condition_id,source,currency,rollup_month,
        open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,
        avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at,
        created_at,updated_at
    )
    SELECT card_variant_id,condition_id,source,currency,rollup_month,
           open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,
           avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at,
           now(),now()
    FROM aggregated;

    GET DIAGNOSTICS v_rows=ROW_COUNT;
    RETURN jsonb_build_object('set_id',p_set_id,'rollup_month',v_month,'rows',v_rows);
END;
$function$;

REVOKE ALL ON FUNCTION public.rebuild_card_variant_price_monthly_rollups_v2_shadow_for_set(uuid,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_card_variant_price_monthly_rollups_v2_shadow_for_set(uuid,date) TO service_role;

COMMENT ON TABLE public.card_variant_price_monthly_rollups_v2_shadow IS
'Backend-only parity shadow for monthly card price aggregates reconstructed from V2 price events plus exact observed-date ranges.';