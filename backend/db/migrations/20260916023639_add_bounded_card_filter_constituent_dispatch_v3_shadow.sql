CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v3_dispatch_shadow(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
  canonical_card_id uuid,
  set_id uuid,
  market_date date,
  market_price numeric,
  card_variant_id uuid,
  source text,
  captured_at date
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ''
SET "TimeZone" = 'America/Phoenix'
AS $function$
DECLARE
  v_roots uuid[];
BEGIN
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date > p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;

  IF p_set_ids IS NOT NULL THEN
    RETURN QUERY
    SELECT *
    FROM public.get_pokemon_cards_daily_constituents_v3_shadow(
      p_set_ids, p_start_date, p_end_date, p_card_ids
    );
    RETURN;
  END IF;

  -- Card-only reads are intentionally bounded for prepared-constituent movement
  -- enrichment. NULL/empty does not mean the entire Pokemon card universe.
  IF p_card_ids IS NULL OR cardinality(p_card_ids) = 0 THEN
    RETURN;
  END IF;
  IF cardinality(p_card_ids) > 100 THEN
    RAISE EXCEPTION 'card-only constituent reads are limited to 100 canonical card ids';
  END IF;

  SELECT coalesce(array_agg(DISTINCT
           CASE
             WHEN s.parent_opening_set_id IS NOT NULL
              AND s.counts_toward_parent_set_value = true
             THEN s.parent_opening_set_id
             ELSE c.set_id
           END
           ORDER BY CASE
             WHEN s.parent_opening_set_id IS NOT NULL
              AND s.counts_toward_parent_set_value = true
             THEN s.parent_opening_set_id
             ELSE c.set_id
           END), ARRAY[]::uuid[])
    INTO v_roots
  FROM public.pokemon_canonical_cards c
  JOIN public.sets s ON s.id = c.set_id
  WHERE c.id = ANY(p_card_ids);

  IF cardinality(v_roots) = 0 THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT *
  FROM public.get_pokemon_cards_daily_constituents_v3_shadow(
    v_roots, p_start_date, p_end_date, p_card_ids
  );
END;
$function$;

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_dispatch_shadow(uuid[],date,date,uuid[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_dispatch_shadow(uuid[],date,date,uuid[]) TO postgres, service_role;
COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents_v3_dispatch_shadow(uuid[],date,date,uuid[]) IS
'Non-serving V3 dispatch acceptance shadow. Preserves normal set-scoped routing and additionally permits service-role-only card-scoped reads when p_set_ids is NULL and 1..100 canonical card ids are supplied; roots are resolved server-side from canonical card/set identity.';
