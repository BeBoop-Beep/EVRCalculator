CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents(
    p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,card_variant_id uuid,source text,captured_at date)
LANGUAGE sql STABLE
SET "TimeZone" TO 'America/Phoenix'
SET search_path TO ''
AS $function$
    SELECT *
    FROM public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
        p_set_ids,p_start_date,p_end_date,p_card_ids
    );
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) TO postgres, service_role;