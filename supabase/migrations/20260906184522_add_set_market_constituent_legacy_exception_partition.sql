CREATE TABLE IF NOT EXISTS public.pokemon_set_market_constituent_legacy_exceptions_v2 (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    reason text NOT NULL,
    mismatch_rows bigint,
    mismatch_cards bigint,
    first_mismatch date,
    last_mismatch date,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.pokemon_set_market_constituent_legacy_exceptions_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_set_market_constituent_legacy_exceptions_v2 FROM PUBLIC,anon,authenticated;
GRANT SELECT ON TABLE public.pokemon_set_market_constituent_legacy_exceptions_v2 TO service_role;
GRANT ALL ON TABLE public.pokemon_set_market_constituent_legacy_exceptions_v2 TO postgres;

INSERT INTO public.pokemon_set_market_constituent_legacy_exceptions_v2(
  set_id,reason,mismatch_rows,mismatch_cards,first_mismatch,last_mismatch,updated_at
)
SELECT e.set_id,'edition_split_vintage_root',NULL,NULL,NULL,NULL,now()
FROM public.pokemon_edition_split_root_sets_v2 e
ON CONFLICT (set_id) DO UPDATE SET reason=EXCLUDED.reason,updated_at=now();

INSERT INTO public.pokemon_set_market_constituent_legacy_exceptions_v2(
  set_id,reason,mismatch_rows,mismatch_cards,first_mismatch,last_mismatch,updated_at
)
SELECT a.set_id,'full_history_variant_selection_mismatch',a.mismatches,a.mismatch_cards,a.first_mismatch,a.last_mismatch,now()
FROM public.pokemon_set_market_constituent_v2_acceptance a
WHERE a.status='complete' AND (coalesce(a.missing_side,0)>0 OR coalesce(a.mismatches,0)>0)
ON CONFLICT (set_id) DO UPDATE SET
  reason=EXCLUDED.reason,mismatch_rows=EXCLUDED.mismatch_rows,mismatch_cards=EXCLUDED.mismatch_cards,
  first_mismatch=EXCLUDED.first_mismatch,last_mismatch=EXCLUDED.last_mismatch,updated_at=now();

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,card_variant_id uuid,source text,captured_at date)
LANGUAGE plpgsql STABLE
SET "TimeZone" TO 'America/Phoenix'
SET search_path TO ''
AS $function$
DECLARE
    v_v2_ids uuid[];
    v_legacy_ids uuid[];
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
    END IF;

    SELECT coalesce(array_agg(DISTINCT x ORDER BY x) FILTER (
               WHERE NOT EXISTS (
                 SELECT 1 FROM public.pokemon_set_market_constituent_legacy_exceptions_v2 e WHERE e.set_id=x
               )
           ),'{}'::uuid[]),
           coalesce(array_agg(DISTINCT x ORDER BY x) FILTER (
               WHERE EXISTS (
                 SELECT 1 FROM public.pokemon_set_market_constituent_legacy_exceptions_v2 e WHERE e.set_id=x
               )
           ),'{}'::uuid[])
      INTO v_v2_ids,v_legacy_ids
    FROM unnest(p_set_ids) x;

    IF cardinality(v_v2_ids)>0 THEN
        RETURN QUERY
        SELECT * FROM public.get_pokemon_cards_daily_constituents_v2_shadow(
            v_v2_ids,p_start_date,p_end_date,p_card_ids
        );
    END IF;

    IF cardinality(v_legacy_ids)>0 THEN
        RETURN QUERY
        SELECT * FROM public.get_pokemon_cards_daily_constituents_legacy_shadow(
            v_legacy_ids,p_start_date,p_end_date,p_card_ids
        );
    END IF;
END;
$function$;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) TO postgres,service_role;