BEGIN;

-- Rarity history is immutable once it has been validated in a serving V2
-- generation. Reuse that durable history as an anchor and compute only the
-- accepted dates after the serving watermark. Newly eligible rarity markets
-- (which have no prior anchor) still receive a full historical build.
CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(
  p_generation_id uuid,
  p_market_date date
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = ''
SET statement_timeout = '600s'
SET work_mem = '64MB'
AS $function$
DECLARE
  v_markets integer := 0;
  v_history integer := 0;
  v_rows integer := 0;
  v_member_rows integer := 0;
  v_copied_history integer := 0;
  v_computed_history integer := 0;
  v_anchored_markets integer := 0;
  v_full_history_markets integer := 0;
  v_prior_generation uuid;
  v_prior_date date;
BEGIN
  PERFORM public.release_pokemon_market_explorer_pre_rarity_temp_v1();

  SELECT s.generation_id,g.market_date
    INTO v_prior_generation,v_prior_date
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  JOIN public.pokemon_market_explorer_surface_generations_v2 g
    ON g.generation_id=s.generation_id
  WHERE s.singleton=1
    AND g.state='VALIDATED'
  LIMIT 1;

  DROP TABLE IF EXISTS pg_temp._mx_rarity_keys;
  CREATE TEMP TABLE _mx_rarity_keys ON COMMIT DROP AS
  SELECT
    r.rarity_key,
    ('rarity:'||r.rarity_key)::text AS market_key,
    CASE
      WHEN v_prior_generation IS NOT NULL
       AND v_prior_date IS NOT NULL
       AND v_prior_date < p_market_date
       AND h.market_key IS NOT NULL
      THEN v_prior_date
      ELSE NULL::date
    END AS anchor_date,
    CASE
      WHEN v_prior_generation IS NOT NULL
       AND v_prior_date IS NOT NULL
       AND v_prior_date < p_market_date
      THEN h.index_value
      ELSE NULL::numeric
    END AS anchor_index,
    CASE
      WHEN v_prior_generation IS NOT NULL
       AND v_prior_date IS NOT NULL
       AND v_prior_date < p_market_date
      THEN h.chain_segment_id
      ELSE NULL::integer
    END AS anchor_segment
  FROM public.pokemon_market_explorer_rarity_registry_v1 r
  LEFT JOIN public.pokemon_market_explorer_surface_history_v2 h
    ON h.generation_id=v_prior_generation
   AND h.market_key=('rarity:'||r.rarity_key)
   AND h.market_date=v_prior_date
  WHERE r.eligibility_state='CUSTOM_BUILD_AVAILABLE'
    AND r.prepared_market_key IS NULL;

  CREATE UNIQUE INDEX ON _mx_rarity_keys(rarity_key);
  CREATE UNIQUE INDEX ON _mx_rarity_keys(market_key);
  ANALYZE _mx_rarity_keys;

  SELECT
    count(*) FILTER (WHERE anchor_date IS NOT NULL)::integer,
    count(*) FILTER (WHERE anchor_date IS NULL)::integer
  INTO v_anchored_markets,v_full_history_markets
  FROM _mx_rarity_keys;

  DROP TABLE IF EXISTS pg_temp._mx_rarity_members;
  CREATE TEMP TABLE _mx_rarity_members ON COMMIT DROP AS
  SELECT
    k.rarity_key,
    k.market_key,
    d.market_date,
    d.card_variant_id,
    d.set_id,
    d.market_price
  FROM _mx_rarity_keys k
  JOIN public.pokemon_market_explorer_card_current_metadata m
    ON m.filter_rarity_key=k.rarity_key
  JOIN public.pokemon_market_explorer_card_daily_states_v2_shadow d
    ON d.card_variant_id=m.card_variant_id
   AND d.set_id=m.set_id
  WHERE d.market_date<=p_market_date
    AND (k.anchor_date IS NULL OR d.market_date>=k.anchor_date)
    AND d.market_price>0
    AND EXISTS (
      SELECT 1
      FROM public.pokemon_market_date_quality q
      WHERE q.tcg='pokemon'
        AND q.market_date=d.market_date
        AND q.status IN ('READY','LEGACY_VERIFIED')
    );

  GET DIAGNOSTICS v_member_rows=ROW_COUNT;

  CREATE INDEX ON _mx_rarity_members(rarity_key,market_date,card_variant_id);
  CREATE INDEX ON _mx_rarity_members(market_key,market_date,market_price DESC,card_variant_id);
  ANALYZE _mx_rarity_members;

  DROP TABLE IF EXISTS pg_temp._mx_rarity_current;
  CREATE TEMP TABLE _mx_rarity_current ON COMMIT DROP AS
  SELECT *
  FROM _mx_rarity_members
  WHERE market_date=p_market_date;

  CREATE INDEX ON _mx_rarity_current(market_key,market_price DESC,card_variant_id);
  ANALYZE _mx_rarity_current;

  INSERT INTO public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,constituent_count,composition_kind,availability,
    definition_version,screen_group,screen_eligible,metadata
  )
  SELECT
    p_generation_id,
    k.market_key,
    'cards',
    'rarity',
    r.label,
    r.label,
    'rarity_registry_v1',
    r.rarity_key,
    p_market_date,
    r.current_priced_card_count,
    'index_and_composition',
    CASE WHEN r.current_priced_card_count>0 THEN 'available' ELSE 'empty' END,
    r.taxonomy_version,
    'card',
    true,
    jsonb_build_object(
      'rarityKey',r.rarity_key,
      'eligibilityState',r.eligibility_state,
      'qualityGate','25 cards / 3 sets + current positive pricing + >=2 accepted dates',
      'newPreparedCandidate',true,
      'historyBuild','incremental_from_validated_serving_v1',
      'historyAnchorDate',k.anchor_date
    )
  FROM _mx_rarity_keys k
  JOIN public.pokemon_market_explorer_rarity_registry_v1 r
    ON r.rarity_key=k.rarity_key
  WHERE EXISTS (
    SELECT 1
    FROM _mx_rarity_current x
    WHERE x.rarity_key=k.rarity_key
      AND x.market_date=p_market_date
  )
  ON CONFLICT (generation_id,market_key) DO NOTHING;
  GET DIAGNOSTICS v_markets=ROW_COUNT;

  -- Copy immutable history through the validated serving anchor. This is the
  -- key runtime reduction: established rarity markets do not rescan six months
  -- of card/day state on every publication.
  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,
    constituent_count,chain_segment_id
  )
  SELECT
    p_generation_id,
    h.market_key,
    h.market_date,
    h.index_value,
    h.tracked_value,
    h.constituent_count,
    h.chain_segment_id
  FROM _mx_rarity_keys k
  JOIN public.pokemon_market_explorer_surface_history_v2 h
    ON h.generation_id=v_prior_generation
   AND h.market_key=k.market_key
  WHERE k.anchor_date IS NOT NULL
    AND h.market_date<=k.anchor_date
  ON CONFLICT (generation_id,market_key,market_date) DO NOTHING;
  GET DIAGNOSTICS v_copied_history=ROW_COUNT;

  DROP TABLE IF EXISTS pg_temp._mx_rarity_daily;
  CREATE TEMP TABLE _mx_rarity_daily ON COMMIT DROP AS
  WITH dates AS (
    SELECT
      rarity_key,
      market_key,
      market_date,
      lag(market_date) OVER (
        PARTITION BY rarity_key ORDER BY market_date
      ) AS prev_date
    FROM (
      SELECT DISTINCT rarity_key,market_key,market_date
      FROM _mx_rarity_members
    ) q
  ),
  linked AS (
    SELECT
      dt.rarity_key,
      dt.market_key,
      dt.market_date,
      dt.prev_date,
      count(m.card_variant_id)::integer AS constituent_count,
      sum(m.market_price)::numeric AS basket_value,
      count(p.card_variant_id)::integer AS common_count,
      coalesce(
        sum(m.market_price) FILTER (WHERE p.card_variant_id IS NOT NULL),
        0
      )::numeric AS common_current,
      coalesce(sum(p.market_price),0)::numeric AS common_previous
    FROM dates dt
    JOIN _mx_rarity_members m
      ON m.rarity_key=dt.rarity_key
     AND m.market_date=dt.market_date
    LEFT JOIN _mx_rarity_members p
      ON p.rarity_key=m.rarity_key
     AND p.card_variant_id=m.card_variant_id
     AND p.market_date=dt.prev_date
    GROUP BY
      dt.rarity_key,dt.market_key,dt.market_date,dt.prev_date
  ),
  ratios AS (
    SELECT
      l.*,
      k.anchor_date,
      k.anchor_index,
      k.anchor_segment,
      CASE
        WHEN k.anchor_date IS NOT NULL AND l.market_date=k.anchor_date
          THEN NULL::numeric
        WHEN l.prev_date IS NOT NULL
         AND l.common_count>0
         AND l.common_previous>0
          THEN l.common_current/l.common_previous
        ELSE NULL::numeric
      END AS link_ratio,
      CASE
        WHEN k.anchor_date IS NOT NULL AND l.market_date=k.anchor_date THEN 0
        WHEN l.prev_date IS NULL OR l.common_count=0 OR l.common_previous<=0 THEN 1
        ELSE 0
      END AS break_flag
    FROM linked l
    JOIN _mx_rarity_keys k USING(rarity_key)
  ),
  segments AS (
    SELECT
      r.*,
      sum(break_flag) OVER (
        PARTITION BY rarity_key
        ORDER BY market_date
        ROWS UNBOUNDED PRECEDING
      )::integer AS segment_offset
    FROM ratios r
  ),
  indexed AS (
    SELECT
      s.*,
      coalesce(s.anchor_segment,0)+s.segment_offset AS segment_id,
      (
        CASE
          WHEN s.anchor_date IS NOT NULL AND s.segment_offset=0
            THEN coalesce(s.anchor_index,100)
          ELSE 100::numeric
        END
        *
        pg_catalog.exp(
          coalesce(
            sum(pg_catalog.ln(s.link_ratio))
              FILTER (WHERE s.link_ratio IS NOT NULL)
              OVER (
                PARTITION BY s.rarity_key,s.segment_offset
                ORDER BY s.market_date
                ROWS UNBOUNDED PRECEDING
              ),
            0
          )
        )
      )::numeric AS index_value
    FROM segments s
  )
  SELECT *
  FROM indexed;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,
    constituent_count,chain_segment_id
  )
  SELECT
    p_generation_id,
    d.market_key,
    d.market_date,
    d.index_value,
    d.basket_value,
    d.constituent_count,
    d.segment_id
  FROM _mx_rarity_daily d
  JOIN _mx_rarity_keys k USING(rarity_key)
  WHERE k.anchor_date IS NULL OR d.market_date>k.anchor_date
  ON CONFLICT (generation_id,market_key,market_date) DO NOTHING;
  GET DIAGNOSTICS v_computed_history=ROW_COUNT;

  v_history:=v_copied_history+v_computed_history;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability
  )
  SELECT
    p_generation_id,
    d.market_key,
    'cards',
    count(*)::integer,
    CASE WHEN count(*)>0 THEN 'available' ELSE 'empty' END
  FROM _mx_rarity_current d
  JOIN public.pokemon_market_explorer_surface_directory_v2 s
    ON s.generation_id=p_generation_id
   AND s.market_key=d.market_key
  WHERE d.market_date=p_market_date
  GROUP BY d.market_key;

  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,
    market_price,price_as_of,item
  )
  SELECT
    p_generation_id,
    x.market_key,
    row_number() OVER (
      PARTITION BY x.market_key
      ORDER BY x.market_price DESC,x.card_variant_id
    )::integer,
    x.card_variant_id::text,
    'cards',
    x.set_id,
    x.market_price,
    x.market_date,
    jsonb_build_object(
      'asset','cards',
      'instrumentId',x.card_variant_id,
      'cardVariantId',x.card_variant_id,
      'canonicalCardId',m.canonical_card_id,
      'setId',x.set_id,
      'setName',s.name,
      'name',m.card_name,
      'cardName',m.card_name,
      'cardNumber',m.card_number,
      'rarity',m.rarity,
      'edition',m.edition,
      'printingType',m.printing_type,
      'specialType',m.special_type,
      'marketPrice',x.market_price,
      'priceAsOf',x.market_date,
      'imageUrl',coalesce(
        cv.image_small_url,cc.image_small_url,
        cv.image_large_url,cc.image_large_url,m.image_url
      ),
      'imageSmallUrl',coalesce(cv.image_small_url,cc.image_small_url),
      'imageLargeUrl',coalesce(cv.image_large_url,cc.image_large_url)
    )
  FROM _mx_rarity_current x
  JOIN public.pokemon_market_explorer_surface_directory_v2 sd
    ON sd.generation_id=p_generation_id
   AND sd.market_key=x.market_key
  JOIN public.pokemon_market_explorer_card_current_metadata m
    ON m.card_variant_id=x.card_variant_id
   AND m.set_id=x.set_id
   AND m.filter_rarity_key=x.rarity_key
  LEFT JOIN public.card_variants cv ON cv.id=x.card_variant_id
  LEFT JOIN public.pokemon_canonical_cards cc ON cc.id=m.canonical_card_id
  LEFT JOIN public.sets s ON s.id=x.set_id
  WHERE x.market_date=p_market_date;
  GET DIAGNOSTICS v_rows=ROW_COUNT;

  UPDATE public.pokemon_market_explorer_surface_directory_v2 d
  SET constituent_count=t.total_count
  FROM public.pokemon_market_explorer_surface_constituent_totals_v2 t
  WHERE d.generation_id=p_generation_id
    AND t.generation_id=d.generation_id
    AND t.market_key=d.market_key
    AND d.scope_kind='rarity';

  RETURN jsonb_build_object(
    'markets',v_markets,
    'historyRows',v_history,
    'copiedHistoryRows',v_copied_history,
    'computedHistoryRows',v_computed_history,
    'constituentRows',v_rows,
    'memberRowsScanned',v_member_rows,
    'anchoredMarkets',v_anchored_markets,
    'fullHistoryMarkets',v_full_history_markets,
    'priorGenerationId',v_prior_generation,
    'priorMarketDate',v_prior_date
  );
END;
$function$;

ALTER FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
  OWNER TO postgres;
REVOKE ALL ON FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
  TO service_role;

COMMENT ON FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date) IS
'Stages custom rarity markets incrementally from the prior validated V2 serving history. Existing markets scan only the serving anchor date forward; newly eligible markets build full history.';

COMMIT;
