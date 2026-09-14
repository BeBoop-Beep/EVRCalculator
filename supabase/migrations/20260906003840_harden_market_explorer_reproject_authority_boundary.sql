CREATE OR REPLACE FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
SET work_mem TO '64MB'
AS $function$
DECLARE
    v_expected_coverage integer;
    v_actual_coverage integer;
    v_bad_through integer;
    v_deleted bigint := 0;
    v_inserted bigint := 0;
    v_updated_coverage bigint := 0;
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN RAISE EXCEPTION 'p_set_ids required'; END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date > p_end_date THEN RAISE EXCEPTION 'valid date range required'; END IF;

    SELECT cardinality(array_agg(DISTINCT x)) INTO v_expected_coverage FROM unnest(p_set_ids) x;
    SELECT count(*) INTO v_actual_coverage FROM public.pokemon_market_explorer_card_daily_coverage WHERE set_id=ANY(p_set_ids);
    IF v_actual_coverage <> v_expected_coverage THEN
        RAISE EXCEPTION 'repair projection requires existing coverage for every set: expected %, found %', v_expected_coverage, v_actual_coverage;
    END IF;
    SELECT count(*) INTO v_bad_through FROM public.pokemon_market_explorer_card_daily_coverage WHERE set_id=ANY(p_set_ids) AND computed_through < p_end_date;
    IF v_bad_through <> 0 THEN
        RAISE EXCEPTION 'repair end date % exceeds computed_through for % sets', p_end_date, v_bad_through;
    END IF;

    DELETE FROM public.pokemon_market_explorer_card_daily_states
     WHERE set_id=ANY(p_set_ids) AND market_date BETWEEN p_start_date AND p_end_date;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    WITH authority AS MATERIALIZED (
        SELECT DISTINCT a.card_variant_id, a.set_id
        FROM public.get_pokemon_canonical_card_variant_authority(p_set_ids) a
    )
    INSERT INTO public.pokemon_market_explorer_card_daily_states(market_date,card_variant_id,set_id,market_price)
    SELECT q.market_date, i.card_variant_id, i.set_id, i.market_price
      FROM public.pokemon_market_date_quality q
      JOIN public.pokemon_card_variant_market_price_intervals i
        ON i.set_id=ANY(p_set_ids)
       AND i.valid_from <= q.market_date
       AND (i.valid_to IS NULL OR q.market_date < i.valid_to)
      JOIN authority a
        ON a.card_variant_id = i.card_variant_id
       AND a.set_id = i.set_id
     WHERE q.tcg='pokemon'
       AND q.status IN ('READY','LEGACY_VERIFIED')
       AND q.market_date BETWEEN p_start_date AND p_end_date;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    WITH stats AS (
        SELECT set_id, min(market_date) first_market_date, count(*) row_count
        FROM public.pokemon_market_explorer_card_daily_states
        WHERE set_id=ANY(p_set_ids)
        GROUP BY set_id
    )
    UPDATE public.pokemon_market_explorer_card_daily_coverage c
       SET first_market_date=s.first_market_date,
           row_count=s.row_count,
           refreshed_at=clock_timestamp()
      FROM stats s
     WHERE c.set_id=s.set_id;
    GET DIAGNOSTICS v_updated_coverage = ROW_COUNT;

    RETURN jsonb_build_object(
        'deletedRows',v_deleted,
        'insertedRows',v_inserted,
        'coverageRowsUpdated',v_updated_coverage,
        'startDate',p_start_date,
        'endDate',p_end_date,
        'authorityFiltered',true
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date) TO service_role;