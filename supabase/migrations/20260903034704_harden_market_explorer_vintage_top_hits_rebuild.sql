CREATE OR REPLACE FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition()
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
SET statement_timeout TO '300s'
AS $function$
DECLARE
    v_metrics jsonb;
    v_hits jsonb;
    v_set_edition jsonb := NULL;
    v_set_edition_status text := 'skipped_missing_relation';
BEGIN
    v_metrics := public.refresh_card_variant_market_metrics_latest();
    v_hits := public.refresh_card_market_top_hits_by_edition_latest();

    IF to_regclass('public.set_market_metrics_by_edition_latest') IS NOT NULL THEN
        v_set_edition := public.refresh_set_market_metrics_by_edition_latest();
        v_set_edition_status := 'refreshed';
    END IF;

    RETURN jsonb_build_object(
        'cardMetrics', v_metrics,
        'topHitsByEdition', v_hits,
        'setMetricsByEdition', v_set_edition,
        'setMetricsByEditionStatus', v_set_edition_status
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_card_market_top_hits_by_edition() TO service_role;
