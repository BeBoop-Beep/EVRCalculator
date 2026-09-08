CREATE TABLE IF NOT EXISTS public.pokemon_edition_split_root_sets_v2 (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    profile text NOT NULL CHECK (profile IN ('edition_split','base_three_printings')),
    seeded_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.pokemon_edition_split_root_sets_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_edition_split_root_sets_v2 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.pokemon_edition_split_root_sets_v2 TO service_role;
GRANT ALL ON TABLE public.pokemon_edition_split_root_sets_v2 TO postgres;

INSERT INTO public.pokemon_edition_split_root_sets_v2(set_id,profile)
SELECT set_id,
       CASE WHEN bool_or(market_scope='shadowless') THEN 'base_three_printings' ELSE 'edition_split' END
FROM public.pokemon_market_root_set_value_latest_v1
GROUP BY set_id
HAVING bool_or(market_scope <> 'standard')
ON CONFLICT (set_id) DO UPDATE SET profile=EXCLUDED.profile;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_legacy_shadow(
    p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,card_variant_id uuid,source text,captured_at date)
LANGUAGE sql STABLE
SET "TimeZone" TO 'America/Phoenix'
SET search_path TO ''
AS $function$
    SELECT raw.canonical_card_id,raw.set_id,raw.market_date,raw.market_price,
           raw.card_variant_id,raw.source,raw.captured_at
    FROM public.get_pokemon_cards_daily_constituents_resolved_universe(
        p_set_ids,p_start_date,p_end_date,p_card_ids
    ) raw
    JOIN public.pokemon_canonical_cards canonical
      ON canonical.id=raw.canonical_card_id
     AND canonical.set_id=raw.set_id
    WHERE canonical.set_value_eligible=true
    ORDER BY raw.market_date,raw.canonical_card_id;
$function$;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_legacy_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_legacy_shadow(uuid[],date,date,uuid[]) TO postgres, service_role;

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
    p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,card_variant_id uuid,source text,captured_at date)
LANGUAGE plpgsql STABLE
SET "TimeZone" TO 'America/Phoenix'
SET search_path TO ''
AS $function$
DECLARE
    v_standard_ids uuid[];
    v_edition_ids uuid[];
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
        RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
    END IF;

    SELECT coalesce(array_agg(DISTINCT x ORDER BY x) FILTER (
               WHERE NOT EXISTS (SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=x)
           ),'{}'::uuid[]),
           coalesce(array_agg(DISTINCT x ORDER BY x) FILTER (
               WHERE EXISTS (SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=x)
           ),'{}'::uuid[])
      INTO v_standard_ids,v_edition_ids
    FROM unnest(p_set_ids) x;

    IF cardinality(v_standard_ids)>0 THEN
        RETURN QUERY
        SELECT * FROM public.get_pokemon_cards_daily_constituents_v2_shadow(
            v_standard_ids,p_start_date,p_end_date,p_card_ids
        );
    END IF;

    IF cardinality(v_edition_ids)>0 THEN
        RETURN QUERY
        SELECT * FROM public.get_pokemon_cards_daily_constituents_legacy_shadow(
            v_edition_ids,p_start_date,p_end_date,p_card_ids
        );
    END IF;
END;
$function$;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) TO postgres, service_role;