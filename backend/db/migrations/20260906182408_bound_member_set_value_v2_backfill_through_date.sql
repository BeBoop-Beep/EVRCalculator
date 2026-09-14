CREATE OR REPLACE FUNCTION public.rebuild_pokemon_set_value_daily_history_v2_shadow_for_set(
    p_set_id uuid,
    p_through_date date
)
RETURNS integer
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_rows integer:=0;
BEGIN
    DELETE FROM public.pokemon_set_value_daily_history_v2_shadow WHERE set_id=p_set_id;
    INSERT INTO public.pokemon_set_value_daily_history_v2_shadow(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,built_at
    )
    SELECT r.set_id,r.snapshot_date,r.value_scope,r.set_value,r.priced_card_count,r.total_card_count,
           r.canonical_card_count,r.linked_card_count,r.included_card_count,r.coverage_pct,r.source,now()
    FROM public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(
      p_set_id,date '1900-01-01',p_through_date
    ) r;
    GET DIAGNOSTICS v_rows=ROW_COUNT;
    RETURN v_rows;
END;
$function$;

UPDATE public.pokemon_set_value_daily_history_v2_backfill_sets
SET status='pending',attempts=0,last_error=NULL,started_at=NULL,completed_at=NULL,updated_at=now()
WHERE status='complete';