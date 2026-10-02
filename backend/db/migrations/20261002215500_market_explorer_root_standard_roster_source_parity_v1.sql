BEGIN;

-- The V2 Standard-roster freezer must preserve the exact physical basket that
-- produced the persisted Raw/Set Value publication. Historical replay remains
-- the primary path. A tightly bounded current-date fallback is allowed only
-- when the persisted history was sourced from the live root snapshot and the
-- live rows reconcile exactly to the persisted count/value with no future-dated
-- component prices. This closes printing-selection drift without changing any
-- published Set Value or Raw Market value.

CREATE OR REPLACE FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(
  p_root_set_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
SET statement_timeout = '30s'
SET lock_timeout = '2s'
AS $function$
DECLARE
  v_methodology text := 'chain_linked_common_cohort_v1';
  v_expected_value numeric;
  v_expected_count integer;
  v_history_source text;
  v_latest_approved_date date;
  v_count integer;
  v_unique_variants integer;
  v_unique_canonical integer;
  v_value numeric;
  v_dates_safe boolean;
  v_items jsonb;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_ARGUMENTS_REQUIRED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_edition_split_root_sets_v2 e
    WHERE e.set_id = p_root_set_id
  ) THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_VINTAGE_STANDARD_FORBIDDEN';
  END IF;

  SELECT h.set_value, h.priced_card_count, h.source
  INTO v_expected_value, v_expected_count, v_history_source
  FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
  WHERE h.set_id = p_root_set_id
    AND h.market_scope = 'standard'
    AND h.market_date = p_market_date;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ROOT_STANDARD_ROSTER_V2_HISTORY_MISSING';
  END IF;

  -- Primary path: date-pinned canonical event replay.
  WITH prices AS MATERIALIZED (
    SELECT *
    FROM public.get_pokemon_market_root_standard_card_prices_as_of_v2(
      p_root_set_id, p_market_date
    )
  )
  SELECT
    count(*)::integer,
    count(DISTINCT card_variant_id)::integer,
    count(DISTINCT canonical_card_id)::integer,
    round(sum(market_price), 2),
    jsonb_agg(
      jsonb_build_object(
        'canonicalCardId', canonical_card_id,
        'cardVariantId', card_variant_id,
        'setId', member_set_id,
        'marketPrice', market_price,
        'capturedAt', observed_date,
        'source', source,
        'printingType', printing_type,
        'specialType', special_type,
        'priceSelectionReason', 'canonical_price_events_v2_root_standard'
      )
      ORDER BY canonical_card_id
    )
  INTO v_count, v_unique_variants, v_unique_canonical, v_value, v_items
  FROM prices;

  IF v_count = v_expected_count
     AND v_unique_variants = v_expected_count
     AND v_unique_canonical = v_expected_count
     AND round(v_value, 2) = round(v_expected_value, 2)
  THEN
    PERFORM public.replace_pokemon_market_set_value_constituents_v1(
      p_root_set_id,
      p_market_date,
      v_methodology,
      v_expected_value,
      v_expected_count,
      'canonical_price_events_v2_root_standard_frozen_v1',
      v_items
    );

    RETURN jsonb_build_object(
      'status', 'frozen',
      'source', 'canonical_price_events_v2_root_standard',
      'setId', p_root_set_id,
      'marketDate', p_market_date,
      'methodologyVersion', v_methodology,
      'constituentCount', v_count,
      'constituentValue', v_value
    );
  END IF;

  -- Current-date fail-closed fallback: the persisted root history is produced
  -- from get_pokemon_market_root_set_card_prices_latest_v1(). When the replay
  -- reader chooses a different physical printing, freeze the exact producer
  -- basket instead, but only while that live producer still proves exact parity
  -- with the already-persisted history and all component dates are <= target.
  SELECT max(q.market_date)
  INTO v_latest_approved_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg = 'pokemon'
    AND q.status IN ('READY', 'LEGACY_VERIFIED');

  IF p_market_date = v_latest_approved_date
     AND v_history_source = 'root_latest_v2_snapshot'
  THEN
    WITH prices AS MATERIALIZED (
      SELECT
        r.member_set_id,
        r.canonical_card_id,
        r.card_variant_id,
        r.market_price,
        r.captured_at,
        r.source,
        r.printing_type,
        r.special_type,
        r.price_selection_reason
      FROM public.get_pokemon_market_root_set_card_prices_latest_v1(p_root_set_id) r
      WHERE r.market_scope = 'standard'
        AND r.canonical_card_id IS NOT NULL
        AND r.card_variant_id IS NOT NULL
        AND r.market_price IS NOT NULL
        AND r.market_price > 0
    )
    SELECT
      count(*)::integer,
      count(DISTINCT card_variant_id)::integer,
      count(DISTINCT canonical_card_id)::integer,
      round(sum(market_price), 2),
      coalesce(
        bool_and(captured_at IS NOT NULL AND captured_at <= p_market_date),
        false
      ),
      jsonb_agg(
        jsonb_build_object(
          'canonicalCardId', canonical_card_id,
          'cardVariantId', card_variant_id,
          'setId', member_set_id,
          'marketPrice', market_price,
          'capturedAt', captured_at,
          'source', source,
          'printingType', printing_type,
          'specialType', special_type,
          'priceSelectionReason',
            coalesce(price_selection_reason, 'root_latest_v2_snapshot_current_fallback')
        )
        ORDER BY canonical_card_id
      )
    INTO
      v_count,
      v_unique_variants,
      v_unique_canonical,
      v_value,
      v_dates_safe,
      v_items
    FROM prices;

    IF v_count = v_expected_count
       AND v_unique_variants = v_expected_count
       AND v_unique_canonical = v_expected_count
       AND round(v_value, 2) = round(v_expected_value, 2)
       AND v_dates_safe
    THEN
      PERFORM public.replace_pokemon_market_set_value_constituents_v1(
        p_root_set_id,
        p_market_date,
        v_methodology,
        v_expected_value,
        v_expected_count,
        'root_latest_v2_snapshot_frozen_fallback_v1',
        v_items
      );

      RETURN jsonb_build_object(
        'status', 'frozen',
        'source', 'root_latest_v2_snapshot_current_fallback',
        'setId', p_root_set_id,
        'marketDate', p_market_date,
        'methodologyVersion', v_methodology,
        'constituentCount', v_count,
        'constituentValue', v_value
      );
    END IF;
  END IF;

  RAISE EXCEPTION
    'ROOT_STANDARD_ROSTER_V2_RECONCILIATION_FAILED: count %/% unique variants % unique canonical % value %/%',
    v_count, v_expected_count, v_unique_variants, v_unique_canonical,
    round(v_value, 2), round(v_expected_value, 2);
END;
$function$;

ALTER FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)
  OWNER TO postgres;
REVOKE ALL ON FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)
  TO service_role;

COMMENT ON FUNCTION public.freeze_pokemon_market_root_standard_roster_v2(uuid,date) IS
'Freezes exact Standard Set Value leaves for Explorer V2. Uses historical event replay first; for the latest approved root_latest_v2_snapshot only, may fall back to the exact live producer basket when count/value/date invariants reconcile exactly.';

COMMIT;
