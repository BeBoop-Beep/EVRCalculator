CREATE OR REPLACE FUNCTION public.rebuild_pokemon_card_variant_price_monthly_rollups(
    p_card_variant_ids uuid[],
    p_start_month date,
    p_end_month date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
SET work_mem TO '64MB'
AS $function$
DECLARE
    v_deleted bigint := 0;
    v_inserted bigint := 0;
BEGIN
    IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids)=0 THEN RAISE EXCEPTION 'p_card_variant_ids required'; END IF;
    IF p_start_month IS NULL OR p_end_month IS NULL OR p_start_month > p_end_month THEN RAISE EXCEPTION 'valid month range required'; END IF;

    DELETE FROM public.card_variant_price_monthly_rollups
     WHERE card_variant_id=ANY(p_card_variant_ids)
       AND rollup_month BETWEEN p_start_month AND p_end_month;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    WITH ranked AS (
      SELECT
        o.card_variant_id,
        o.condition_id,
        coalesce(o.source, '') AS source,
        coalesce(o.currency, '"USD"') AS currency,
        date_trunc('month', o.captured_at::timestamp)::date AS rollup_month,
        o.captured_at,
        o.created_at,
        o.market_price,
        o.high_price,
        o.low_price,
        row_number() OVER (
          PARTITION BY o.card_variant_id,o.condition_id,coalesce(o.source,''),date_trunc('month',o.captured_at::timestamp)::date
          ORDER BY o.captured_at ASC,o.created_at ASC,o.id ASC
        ) AS rn_open,
        row_number() OVER (
          PARTITION BY o.card_variant_id,o.condition_id,coalesce(o.source,''),date_trunc('month',o.captured_at::timestamp)::date
          ORDER BY o.captured_at DESC,o.created_at DESC,o.id DESC
        ) AS rn_close
      FROM public.card_variant_price_observations o
      WHERE o.card_variant_id=ANY(p_card_variant_ids)
        AND o.captured_at IS NOT NULL
        AND date_trunc('month',o.captured_at::timestamp)::date BETWEEN p_start_month AND p_end_month
    ), aggregated AS (
      SELECT
        card_variant_id,condition_id,source,max(currency) currency,rollup_month,
        max(CASE WHEN rn_open=1 THEN market_price END) open_market_price,
        max(CASE WHEN rn_close=1 THEN market_price END) close_market_price,
        avg(market_price) avg_market_price,
        min(market_price) min_market_price,
        max(market_price) max_market_price,
        avg(high_price) avg_high_price,
        avg(low_price) avg_low_price,
        count(*)::integer observation_count,
        min(captured_at) first_captured_at,
        max(captured_at) last_captured_at
      FROM ranked
      GROUP BY card_variant_id,condition_id,source,rollup_month
    )
    INSERT INTO public.card_variant_price_monthly_rollups(
      card_variant_id,condition_id,source,currency,rollup_month,
      open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,
      avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at,created_at,updated_at
    )
    SELECT card_variant_id,condition_id,source,currency,rollup_month,
           open_market_price,close_market_price,avg_market_price,min_market_price,max_market_price,
           avg_high_price,avg_low_price,observation_count,first_captured_at,last_captured_at,now(),now()
    FROM aggregated;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    RETURN jsonb_build_object('deletedRows',v_deleted,'insertedRows',v_inserted,'startMonth',p_start_month,'endMonth',p_end_month,'variantCount',cardinality(p_card_variant_ids));
END;
$function$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_card_variant_price_monthly_rollups(uuid[],date,date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_card_variant_price_monthly_rollups(uuid[],date,date) TO service_role;
