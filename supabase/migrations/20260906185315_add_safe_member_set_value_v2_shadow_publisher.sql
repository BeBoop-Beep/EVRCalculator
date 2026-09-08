CREATE OR REPLACE FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(
    p_through_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_shadow_rows bigint:=0;
    v_upserted bigint:=0;
    v_missing bigint:=0;
    v_mismatches bigint:=0;
    v_extra bigint:=0;
BEGIN
    IF p_through_date IS NULL THEN
        RAISE EXCEPTION 'through date is required';
    END IF;

    SELECT count(*) INTO v_shadow_rows
    FROM public.pokemon_set_value_daily_history_v2_shadow
    WHERE snapshot_date<=p_through_date;

    IF v_shadow_rows=0 THEN
        RAISE EXCEPTION 'no shadow rows available through %',p_through_date;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM public.pokemon_set_value_daily_history_v2_backfill_sets q
      WHERE q.through_date=p_through_date AND q.status<>'complete'
    ) THEN
        RAISE EXCEPTION 'member set value V2 backfill is not complete through %',p_through_date;
    END IF;

    INSERT INTO public.pokemon_set_value_daily_history(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source
    )
    SELECT v.set_id,v.snapshot_date,v.value_scope,v.set_value,v.priced_card_count,v.total_card_count,
           v.canonical_card_count,v.linked_card_count,v.included_card_count,v.coverage_pct,
           CASE v.value_scope
             WHEN 'standard' THEN 'card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
             WHEN 'hits' THEN 'card_variant_price_observations_near_mint_latest_as_of_day:hits:canonical_checklist'
             WHEN 'top10' THEN 'card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist'
             ELSE v.source
           END
    FROM public.pokemon_set_value_daily_history_v2_shadow v
    WHERE v.snapshot_date<=p_through_date
    ON CONFLICT (set_id,snapshot_date,value_scope)
    DO UPDATE SET
      set_value=EXCLUDED.set_value,
      priced_card_count=EXCLUDED.priced_card_count,
      total_card_count=EXCLUDED.total_card_count,
      canonical_card_count=EXCLUDED.canonical_card_count,
      linked_card_count=EXCLUDED.linked_card_count,
      included_card_count=EXCLUDED.included_card_count,
      coverage_pct=EXCLUDED.coverage_pct,
      source=EXCLUDED.source;
    GET DIAGNOSTICS v_upserted=ROW_COUNT;

    SELECT count(*) INTO v_missing
    FROM public.pokemon_set_value_daily_history_v2_shadow v
    LEFT JOIN public.pokemon_set_value_daily_history h
      ON h.set_id=v.set_id AND h.snapshot_date=v.snapshot_date AND h.value_scope=v.value_scope
    WHERE v.snapshot_date<=p_through_date
      AND h.set_id IS NULL;

    SELECT count(*) INTO v_mismatches
    FROM public.pokemon_set_value_daily_history_v2_shadow v
    JOIN public.pokemon_set_value_daily_history h
      ON h.set_id=v.set_id AND h.snapshot_date=v.snapshot_date AND h.value_scope=v.value_scope
    WHERE v.snapshot_date<=p_through_date
      AND (h.set_value IS DISTINCT FROM v.set_value
        OR h.priced_card_count IS DISTINCT FROM v.priced_card_count
        OR h.total_card_count IS DISTINCT FROM v.total_card_count
        OR h.canonical_card_count IS DISTINCT FROM v.canonical_card_count
        OR h.linked_card_count IS DISTINCT FROM v.linked_card_count
        OR h.included_card_count IS DISTINCT FROM v.included_card_count
        OR h.coverage_pct IS DISTINCT FROM v.coverage_pct);

    IF v_missing<>0 OR v_mismatches<>0 THEN
        RAISE EXCEPTION 'post-publish member set value parity failed: missing %, mismatches %',v_missing,v_mismatches;
    END IF;

    SELECT count(*) INTO v_extra
    FROM public.pokemon_set_value_daily_history h
    WHERE h.snapshot_date<=p_through_date
      AND EXISTS (SELECT 1 FROM public.pokemon_set_value_daily_history_v2_shadow s WHERE s.set_id=h.set_id)
      AND NOT EXISTS (
        SELECT 1 FROM public.pokemon_set_value_daily_history_v2_shadow v
        WHERE v.set_id=h.set_id AND v.snapshot_date=h.snapshot_date AND v.value_scope=h.value_scope
      );

    RETURN jsonb_build_object(
      'status','complete',
      'through_date',p_through_date,
      'shadow_rows',v_shadow_rows,
      'upserted_rows',v_upserted,
      'missing_shadow_keys',v_missing,
      'metric_mismatches',v_mismatches,
      'preserved_legacy_only_keys',v_extra
    );
END;
$function$;
REVOKE ALL ON FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_set_value_daily_history_v2_shadow(date) TO postgres,service_role;