begin;

-- Source-sync of already-live, validated Market Explorer V2 helper contracts.

CREATE OR REPLACE FUNCTION public.assert_pokemon_market_explorer_surface_coherent_v2(p_generation_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET statement_timeout TO '10s'
AS $function$
DECLARE
  g public.pokemon_market_explorer_surface_generations_v2%rowtype;
  v_raw public.pokemon_market_index_daily_history%rowtype;
  v_base_date date;
  v_expected_roots integer;
  v_ready_roots integer;
  v_bad integer;
  v_quicks integer;
BEGIN
  SELECT * INTO g
  FROM public.pokemon_market_explorer_surface_generations_v2
  WHERE generation_id=p_generation_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'SURFACE_GENERATION_NOT_FOUND'; END IF;
  IF g.comparison_as_of IS NULL OR g.comparison_as_of IS DISTINCT FROM g.market_date THEN
    RAISE EXCEPTION 'SURFACE_GENERATION_WATERMARK_INVALID';
  END IF;

  SELECT CASE
    WHEN count(*)>0 AND count(distinct d.comparison_as_of)=1
      THEN max(d.comparison_as_of)
    ELSE null
  END
  INTO v_base_date
  FROM public.pokemon_market_explorer_prepared_directory_generations_v1 d
  WHERE d.generation_id=g.base_prepared_generation_id;
  IF v_base_date IS DISTINCT FROM g.comparison_as_of THEN
    RAISE EXCEPTION 'SURFACE_BASE_PREPARED_WATERMARK_MISMATCH';
  END IF;

  SELECT * INTO v_raw
  FROM public.pokemon_market_index_daily_history h
  WHERE h.tcg='pokemon' AND h.index_key='raw'
    AND h.market_date=g.comparison_as_of
    AND h.methodology_version=g.raw_methodology_version
  ORDER BY h.updated_at DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'SURFACE_RAW_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_card_daily_states_v2_shadow d
    WHERE d.market_date=g.comparison_as_of AND d.market_price>0
  ) THEN RAISE EXCEPTION 'SURFACE_CARD_DAILY_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date=g.comparison_as_of AND d.market_price>0
  ) THEN RAISE EXCEPTION 'SURFACE_SEALED_DAILY_WATERMARK_MISSING'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_rarity_coverage_certification_v1 c
    WHERE c.singleton AND c.certified_through>=g.comparison_as_of
  ) THEN RAISE EXCEPTION 'SURFACE_RARITY_CERTIFICATION_WATERMARK_MISSING'; END IF;

  WITH roots AS (
    SELECT
      (x->>'setId')::uuid root_set_id,
      (x->>'setValue')::numeric expected_value,
      (x->>'includedCardCount')::integer expected_count
    FROM jsonb_array_elements(v_raw.constituents_json) x
  )
  SELECT count(*)::integer,
         count(p.root_set_id) filter(
           where p.status='READY'
             and p.constituent_count=r.expected_count
             and round(p.constituent_value,2)=round(r.expected_value,2)
         )::integer
  INTO v_expected_roots,v_ready_roots
  FROM roots r
  LEFT JOIN public.pokemon_market_set_value_constituent_publications_v1 p
    ON p.root_set_id=r.root_set_id
   AND p.market_date=g.comparison_as_of
   AND p.methodology_version=g.raw_methodology_version;

  IF v_expected_roots<>v_raw.set_count OR v_ready_roots<>v_expected_roots THEN
    RAISE EXCEPTION 'SURFACE_RAW_FROZEN_ROSTER_INCOMPLETE: ready % expected %',
      coalesce(v_ready_roots,0),coalesce(v_expected_roots,0);
  END IF;

  SELECT count(*)::integer INTO v_bad
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.comparison_as_of IS DISTINCT FROM g.comparison_as_of;
  IF v_bad>0 THEN
    RAISE EXCEPTION 'SURFACE_DIRECTORY_WATERMARK_MISMATCH: %',v_bad;
  END IF;

  SELECT count(*)::integer INTO v_bad
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.availability='available'
    AND d.history_available
    AND d.history_end_date IS DISTINCT FROM g.comparison_as_of;
  IF v_bad>0 THEN
    RAISE EXCEPTION 'SURFACE_AVAILABLE_HISTORY_NOT_CURRENT: %',v_bad;
  END IF;

  SELECT count(*)::integer INTO v_quicks
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.asset='sealed' AND d.scope_kind='quick'
    AND d.market_key IN (
      'sealed-quick:obtainable','sealed-quick:intermediate','sealed-quick:premium',
      'sealed-quick:new-releases','sealed-quick:established','sealed-quick:global-top10'
    );
  IF v_quicks<>6 THEN
    RAISE EXCEPTION 'SURFACE_SEALED_QUICK_SET_INCOMPLETE: %',v_quicks;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_explorer_surface_constituents_v2 c
    WHERE c.generation_id=p_generation_id
      AND c.market_key LIKE 'sealed-quick:%'
      AND coalesce((c.item->>'isBulkContainer')::boolean,false)
  ) THEN
    RAISE EXCEPTION 'SURFACE_SEALED_QUICK_CONTAINS_BULK';
  END IF;

  RETURN jsonb_build_object(
    'generationId',p_generation_id,
    'comparisonAsOf',g.comparison_as_of,
    'rawFrozenRoots',v_ready_roots,
    'sealedQuickMarkets',v_quicks,
    'status','COHERENT'
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_performance_screen_v1(p_screen_key text, p_asset text, p_generation_id uuid, p_limit integer DEFAULT 25)
 RETURNS TABLE(rank integer, screen_key text, market_key text, label text, asset text, market_type text, metric_7d_pct numeric, comparison_as_of date, relative_7d_vs_era_pct numeric, current_drawdown_pct numeric, constituent_count integer)
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET statement_timeout TO '1s'
AS $function$
DECLARE
  v_serving uuid;
  v_asset text:=lower(trim(coalesce(p_asset,'all')));
BEGIN
  IF p_screen_key NOT IN ('top-performers','worst-performers') THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_KEY_INVALID';
  END IF;
  IF v_asset NOT IN ('cards','sealed','all') THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_ASSET_INVALID';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>25 THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_LIMIT_INVALID';
  END IF;

  SELECT s.generation_id INTO v_serving
  FROM public.pokemon_market_explorer_surface_serving_v2 s
  WHERE s.singleton=1;

  IF p_generation_id IS DISTINCT FROM v_serving
     AND NOT EXISTS (
       SELECT 1 FROM public.pokemon_market_explorer_surface_generations_v2 g
       WHERE g.generation_id=p_generation_id AND g.state='VALIDATED'
     ) THEN
    RAISE EXCEPTION 'PERFORMANCE_SCREEN_GENERATION_MISMATCH';
  END IF;

  RETURN QUERY
  SELECT
    row_number() over(
      order by
        CASE WHEN p_screen_key='top-performers' THEN d.return_7d_pct END DESC NULLS LAST,
        CASE WHEN p_screen_key='worst-performers' THEN d.return_7d_pct END ASC NULLS LAST,
        d.market_key
    )::integer,
    p_screen_key,
    d.market_key,
    d.label,
    d.asset,
    d.scope_kind,
    d.return_7d_pct,
    d.comparison_as_of,
    null::numeric,
    d.current_drawdown_pct,
    d.constituent_count
  FROM public.pokemon_market_explorer_surface_directory_v2 d
  WHERE d.generation_id=p_generation_id
    AND d.screen_eligible
    AND d.availability='available'
    AND d.history_available
    AND d.return_7d_pct IS NOT NULL
    AND (v_asset='all' OR d.asset=v_asset)
  ORDER BY
    CASE WHEN p_screen_key='top-performers' THEN d.return_7d_pct END DESC NULLS LAST,
    CASE WHEN p_screen_key='worst-performers' THEN d.return_7d_pct END ASC NULLS LAST,
    d.market_key
  LIMIT p_limit;
END;
$function$;

CREATE OR REPLACE FUNCTION public.promote_pokemon_market_explorer_surface_v2(p_generation_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '10s'
AS $function$
DECLARE
  v_old uuid;
  v_receipt jsonb;
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );

  IF NOT EXISTS (
    SELECT 1 FROM public.pokemon_market_explorer_surface_generations_v2
    WHERE generation_id=p_generation_id AND state='VALIDATED'
  ) THEN
    RAISE EXCEPTION 'ONLY_VALIDATED_SURFACE_GENERATIONS_MAY_BE_PROMOTED';
  END IF;

  v_receipt:=public.assert_pokemon_market_explorer_surface_coherent_v2(p_generation_id);

  SELECT generation_id INTO v_old
  FROM public.pokemon_market_explorer_surface_serving_v2
  WHERE singleton=1
  FOR UPDATE;

  INSERT INTO public.pokemon_market_explorer_surface_serving_v2(
    singleton,generation_id,previous_generation_id,promoted_at
  ) VALUES (1,p_generation_id,v_old,clock_timestamp())
  ON CONFLICT(singleton) DO UPDATE
  SET previous_generation_id=public.pokemon_market_explorer_surface_serving_v2.generation_id,
      generation_id=excluded.generation_id,
      promoted_at=excluded.promoted_at;

  RETURN v_receipt||jsonb_build_object(
    'previousGenerationId',v_old,'promoted',true
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.rollback_pokemon_market_explorer_surface_v2()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '10s'
AS $function$
declare v_cur uuid; v_prev uuid;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('pokemon-market-explorer-surface-v2',0)
  );
  select generation_id,previous_generation_id into v_cur,v_prev
  from public.pokemon_market_explorer_surface_serving_v2 where singleton=1
  for update;
  if v_prev is null then raise exception 'NO_SURFACE_ROLLBACK_GENERATION'; end if;
  if not exists (
    select 1 from public.pokemon_market_explorer_surface_generations_v2
    where generation_id=v_prev and state='VALIDATED'
  ) then raise exception 'ROLLBACK_GENERATION_NOT_VALIDATED'; end if;

  update public.pokemon_market_explorer_surface_serving_v2
  set generation_id=v_prev,previous_generation_id=v_cur,promoted_at=clock_timestamp()
  where singleton=1;
  return jsonb_build_object('generationId',v_prev,'previousGenerationId',v_cur);
end;
$function$;

CREATE OR REPLACE FUNCTION public.search_pokemon_market_explorer_leaves_v1(p_asset text, p_query text, p_limit integer DEFAULT 20)
 RETURNS TABLE(asset text, instrument_id text, name text, set_id uuid, set_name text, image_url text, market_price numeric, market_date date, card_variant_id uuid, canonical_card_id uuid, card_number text, rarity text, edition text, printing_type text, special_type text, sealed_product_id text, product_family text, variant_label text, is_bulk_container boolean, relevance_score integer)
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET statement_timeout TO '1s'
 SET work_mem TO '16MB'
AS $function$
declare
  v_asset text:=lower(trim(coalesce(p_asset,'')));
  v_q text:=public.normalize_pokemon_market_explorer_search_text_v2(p_query);
  v_alt text;
  v_date date;
begin
  if v_asset not in ('cards','sealed','graded') then
    raise exception 'LEAF_SEARCH_ASSET_INVALID';
  end if;
  if v_q is null or length(v_q)<2 then return; end if;
  if p_limit is null or p_limit<1 or p_limit>50 then
    raise exception 'LEAF_SEARCH_LIMIT_INVALID';
  end if;
  if v_asset='graded' then return; end if;

  if v_asset='cards' then
    select max(d.computed_through) into v_date
    from public.pokemon_market_explorer_card_daily_coverage_v2_shadow d;
    if v_date is null then
      select max(d.market_date) into v_date
      from public.pokemon_market_explorer_card_daily_states_v2_shadow d
      where d.market_price>0;
    end if;

    return query
    with candidate_ids as materialized (
      (
        select m.card_variant_id
        from public.pokemon_market_explorer_card_current_metadata m
        where public.normalize_pokemon_market_explorer_search_text_v2(m.card_name)
              like '%'||v_q||'%'
        order by
          case
            when public.normalize_pokemon_market_explorer_search_text_v2(m.card_name)=v_q then 0
            when public.normalize_pokemon_market_explorer_search_text_v2(m.card_name) like v_q||'%' then 1
            else 2
          end,
          lower(m.card_name),m.card_variant_id
        limit 200
      )
      union
      (
        select m.card_variant_id
        from public.pokemon_market_explorer_card_current_metadata m
        where pg_catalog.to_tsvector(
          'simple',
          public.normalize_pokemon_market_explorer_search_text_v2(
            coalesce(m.card_name,'')||' '||coalesce(m.rarity,'')||' '||
            coalesce(m.edition,'')||' '||coalesce(m.printing_type,'')||' '||
            coalesce(m.special_type,'')
          )
        ) @@ pg_catalog.plainto_tsquery('simple',v_q)
        limit 200
      )
    ),
    candidates as materialized (
      select
        m.*,s.name resolved_set_name,d.market_price,d.market_date,
        public.normalize_pokemon_market_explorer_search_text_v2(m.card_name) nname,
        extensions.similarity(
          public.normalize_pokemon_market_explorer_search_text_v2(m.card_name),v_q
        ) sim
      from candidate_ids i
      join public.pokemon_market_explorer_card_current_metadata m
        on m.card_variant_id=i.card_variant_id
      join public.pokemon_market_explorer_card_daily_states_v2_shadow d
        on d.card_variant_id=m.card_variant_id
       and d.market_date=v_date
       and d.market_price>0
      left join public.sets s on s.id=m.set_id
    ),
    ranked as (
      select c.*,
        case
          when c.nname=v_q then 1000
          when c.nname like v_q||'%' then 950
          when c.nname like '%'||v_q||'%' then 900
          when pg_catalog.to_tsvector('simple',c.nname)
               @@ pg_catalog.plainto_tsquery('simple',v_q) then 850
          else 700+least(99,(c.sim*100)::integer)
        end score
      from candidates c
    )
    select
      'cards'::text,r.card_variant_id::text,r.card_name,r.set_id,r.resolved_set_name,
      coalesce(cv.image_small_url,cc.image_small_url,cv.image_large_url,cc.image_large_url,r.image_url),
      r.market_price,r.market_date,r.card_variant_id,r.canonical_card_id,r.card_number,
      r.rarity,r.edition,r.printing_type,r.special_type,
      null::text,null::text,null::text,false,r.score
    from ranked r
    left join public.card_variants cv on cv.id=r.card_variant_id
    left join public.pokemon_canonical_cards cc on cc.id=r.canonical_card_id
    order by r.score desc,r.sim desc,lower(r.card_name),r.card_variant_id
    limit p_limit;
    return;
  end if;

  select max(m.latest_market_date) into v_date
  from public.pokemon_market_explorer_sealed_current_metadata_v1 m
  where m.latest_market_price>0;

  v_alt:=case
    when (' '||v_q||' ') like '% three %'
      then pg_catalog.btrim(pg_catalog.replace(' '||v_q||' ',' three ',' 3 '))
    when (' '||v_q||' ') like '% 3 %'
      then pg_catalog.btrim(pg_catalog.replace(' '||v_q||' ',' 3 ',' three '))
    else v_q
  end;

  return query
  with candidates as materialized (
    select m.*,
      public.normalize_pokemon_market_explorer_search_text_v2(m.name) nname,
      greatest(
        extensions.similarity(coalesce(m.search_text,''),v_q),
        extensions.similarity(coalesce(m.search_text,''),v_alt)
      ) sim
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where m.latest_market_date=v_date and m.latest_market_price>0
      and (
        public.normalize_pokemon_market_explorer_search_text_v2(m.name) in (v_q,v_alt)
        or public.normalize_pokemon_market_explorer_search_text_v2(m.name) like v_q||'%'
        or public.normalize_pokemon_market_explorer_search_text_v2(m.name) like v_alt||'%'
        or public.normalize_pokemon_market_explorer_search_text_v2(m.name) like '%'||v_q||'%'
        or public.normalize_pokemon_market_explorer_search_text_v2(m.name) like '%'||v_alt||'%'
        or pg_catalog.to_tsvector('simple',coalesce(m.search_text,''))
           @@ pg_catalog.plainto_tsquery('simple',v_q)
        or pg_catalog.to_tsvector('simple',coalesce(m.search_text,''))
           @@ pg_catalog.plainto_tsquery('simple',v_alt)
        or extensions.similarity(coalesce(m.search_text,''),v_q)>=0.20
        or extensions.similarity(coalesce(m.search_text,''),v_alt)>=0.20
      )
  ),
  ranked as (
    select c.*,
      case
        when c.nname in (v_q,v_alt) then 1000
        when c.nname like v_q||'%' or c.nname like v_alt||'%' then 950
        when c.nname like '%'||v_q||'%' or c.nname like '%'||v_alt||'%' then 900
        when pg_catalog.to_tsvector('simple',c.nname) @@ pg_catalog.plainto_tsquery('simple',v_q)
          or pg_catalog.to_tsvector('simple',c.nname) @@ pg_catalog.plainto_tsquery('simple',v_alt) then 850
        when pg_catalog.to_tsvector('simple',coalesce(c.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_q)
          or pg_catalog.to_tsvector('simple',coalesce(c.search_text,'')) @@ pg_catalog.plainto_tsquery('simple',v_alt) then 800
        else 700+least(99,(c.sim*100)::integer)
      end score
    from candidates c
  )
  select
    'sealed'::text,r.sealed_product_id,r.name,r.set_id,r.set_name,
    coalesce(r.image_small_url,r.image_large_url),r.latest_market_price,r.latest_market_date,
    null::uuid,null::uuid,null::text,null::text,null::text,null::text,null::text,
    r.sealed_product_id,r.product_family,r.variant_label,r.is_bulk_container,r.score
  from ranked r
  order by r.score desc,r.sim desc,lower(r.name),r.sealed_product_id
  limit p_limit;
end;
$function$;

CREATE OR REPLACE FUNCTION public.stage_pokemon_market_explorer_sealed_quick_markets_v2(p_generation_id uuid, p_market_date date)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
 SET statement_timeout TO '120s'
 SET lock_timeout TO '2s'
 SET work_mem TO '64MB'
AS $function$
DECLARE
  v_markets integer;
  v_history integer;
  v_constituents integer;
BEGIN
  IF p_generation_id IS NULL OR p_market_date IS NULL THEN
    RAISE EXCEPTION 'SEALED_QUICK_STAGE_ARGUMENTS_REQUIRED';
  END IF;

  DROP TABLE IF EXISTS pg_temp._mx_quick_dense;
  CREATE TEMP TABLE _mx_quick_dense ON COMMIT DROP AS
  WITH intervals AS (
    SELECT d.*,
      lead(d.market_date,1,p_market_date+1) over(
        partition by d.sealed_product_id order by d.market_date
      ) next_date
    FROM public.pokemon_market_explorer_sealed_daily_v1 d
    WHERE d.market_date<=p_market_date
  )
  SELECT
    i.sealed_product_id,
    g.day::date market_date,
    i.market_price,
    i.set_id,
    i.era_id,
    i.product_family,
    coalesce(meta.is_bulk_container,false) is_bulk_container,
    nullif(to_jsonb(s)->>'release_date','')::date AS release_date
  FROM intervals i
  CROSS JOIN LATERAL generate_series(
    i.market_date,least(p_market_date,i.next_date-1),interval '1 day'
  ) g(day)
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    ON meta.sealed_product_id=i.sealed_product_id
  LEFT JOIN public.sets s ON s.id=i.set_id
  WHERE i.market_price>0;

  CREATE INDEX ON _mx_quick_dense(market_date,sealed_product_id);
  ANALYZE _mx_quick_dense;

  DROP TABLE IF EXISTS pg_temp._mx_quick_members;
  CREATE TEMP TABLE _mx_quick_members ON COMMIT DROP AS
  WITH nonbulk AS MATERIALIZED (
    SELECT * FROM _mx_quick_dense WHERE NOT is_bulk_container
  ),
  ordinary AS (
    SELECT 'sealed-quick:obtainable'::text market_key,d.*
    FROM nonbulk d WHERE d.market_price<100
    UNION ALL
    SELECT 'sealed-quick:intermediate',d.*
    FROM nonbulk d WHERE d.market_price>=100 AND d.market_price<500
    UNION ALL
    SELECT 'sealed-quick:premium',d.*
    FROM nonbulk d WHERE d.market_price>=500
    UNION ALL
    SELECT 'sealed-quick:new-releases',d.*
    FROM nonbulk d
    WHERE d.release_date IS NOT NULL
      AND d.market_date-d.release_date BETWEEN 0 AND 180
    UNION ALL
    SELECT 'sealed-quick:established',d.*
    FROM nonbulk d
    WHERE d.release_date IS NOT NULL
      AND d.market_date-d.release_date>730
      AND d.market_date-d.release_date<=1825
  ),
  top10 AS (
    SELECT 'sealed-quick:global-top10'::text market_key,x.*
    FROM (
      SELECT d.*,
        row_number() over(
          partition by d.market_date
          order by d.market_price desc,d.sealed_product_id
        ) rn
      FROM nonbulk d
    ) x
    WHERE x.rn<=10
  )
  SELECT market_key,sealed_product_id,market_date,market_price,set_id,era_id,product_family
  FROM ordinary
  UNION ALL
  SELECT market_key,sealed_product_id,market_date,market_price,set_id,era_id,product_family
  FROM top10;

  CREATE INDEX ON _mx_quick_members(market_key,market_date,sealed_product_id);
  ANALYZE _mx_quick_members;

  INSERT INTO public.pokemon_market_explorer_surface_directory_v2(
    generation_id,market_key,asset,scope_kind,label,base_label,source_kind,
    taxonomy_key,source_as_of,constituent_count,composition_kind,availability,
    definition_version,screen_group,screen_eligible,metadata
  )
  SELECT
    p_generation_id,r.quick_key,'sealed','quick',r.label,r.label,
    'normalized_sealed_daily_v1',r.quick_key,p_market_date,
    count(m.sealed_product_id)::integer,'index_and_composition',
    case when count(m.sealed_product_id)>0 then 'available' else 'empty' end,
    'sealed-quick-contract-v1','sealed',true,
    r.definition||jsonb_build_object(
      'comparisonAsOf',p_market_date,
      'bulkContainersExcluded',true,
      'membershipIsPointInTime',true
    )
  FROM public.pokemon_market_explorer_sealed_quick_registry_v1 r
  LEFT JOIN _mx_quick_members m
    ON m.market_key=r.quick_key AND m.market_date=p_market_date
  WHERE r.status='APPROVED'
    AND r.quick_key IN (
      'sealed-quick:obtainable','sealed-quick:intermediate','sealed-quick:premium',
      'sealed-quick:new-releases','sealed-quick:established','sealed-quick:global-top10'
    )
  GROUP BY r.quick_key,r.label,r.definition
  ON CONFLICT(generation_id,market_key) DO UPDATE
  SET source_as_of=excluded.source_as_of,
      constituent_count=excluded.constituent_count,
      availability=excluded.availability,
      metadata=excluded.metadata;
  GET DIAGNOSTICS v_markets=ROW_COUNT;

  DROP TABLE IF EXISTS pg_temp._mx_quick_indexed;
  CREATE TEMP TABLE _mx_quick_indexed ON COMMIT DROP AS
  WITH lagged AS (
    SELECT m.*,
      lag(m.market_date) over(
        partition by m.market_key,m.sealed_product_id order by m.market_date
      ) previous_date,
      lag(m.market_price) over(
        partition by m.market_key,m.sealed_product_id order by m.market_date
      ) previous_price
    FROM _mx_quick_members m
  ),
  daily AS (
    SELECT
      market_key,market_date,
      count(*)::integer constituent_count,
      sum(market_price)::numeric basket_value,
      coalesce(sum(market_price) filter(
        where previous_date=market_date-1 and previous_price is not null
      ),0)::numeric current_common,
      coalesce(sum(previous_price) filter(
        where previous_date=market_date-1 and previous_price is not null
      ),0)::numeric previous_common
    FROM lagged
    GROUP BY market_key,market_date
  )
  SELECT d.*,
    100.0*exp(sum(ln(
      case when d.previous_common>0 then d.current_common/d.previous_common else 1.0 end
    )) over(partition by d.market_key order by d.market_date rows unbounded preceding))::numeric
      index_value
  FROM daily d;

  INSERT INTO public.pokemon_market_explorer_surface_history_v2(
    generation_id,market_key,market_date,index_value,tracked_value,constituent_count,chain_segment_id
  )
  SELECT p_generation_id,market_key,market_date,index_value,basket_value,constituent_count,0
  FROM _mx_quick_indexed
  WHERE market_date<=p_market_date
  ORDER BY market_key,market_date;
  GET DIAGNOSTICS v_history=ROW_COUNT;

  INSERT INTO public.pokemon_market_explorer_surface_constituent_totals_v2(
    generation_id,market_key,asset,total_count,availability,availability_reason
  )
  SELECT p_generation_id,r.quick_key,'sealed',
    count(m.sealed_product_id)::integer,
    case when count(m.sealed_product_id)>0 then 'available' else 'empty' end,
    null
  FROM public.pokemon_market_explorer_sealed_quick_registry_v1 r
  LEFT JOIN _mx_quick_members m
    ON m.market_key=r.quick_key AND m.market_date=p_market_date
  WHERE r.status='APPROVED'
    AND r.quick_key LIKE 'sealed-quick:%'
  GROUP BY r.quick_key
  ON CONFLICT(generation_id,market_key) DO UPDATE
  SET total_count=excluded.total_count,availability=excluded.availability,
      availability_reason=excluded.availability_reason;

  INSERT INTO public.pokemon_market_explorer_surface_constituents_v2(
    generation_id,market_key,rank,instrument_id,asset,set_id,market_price,price_as_of,item
  )
  SELECT
    p_generation_id,m.market_key,
    row_number() over(
      partition by m.market_key order by m.market_price desc,m.sealed_product_id
    )::integer,
    m.sealed_product_id,'sealed',m.set_id,m.market_price,m.market_date,
    jsonb_build_object(
      'asset','sealed','instrumentId',m.sealed_product_id,
      'sealedProductId',m.sealed_product_id,
      'setId',meta.set_id,'setName',meta.set_name,
      'name',meta.name,'productName',meta.name,
      'variantLabel',meta.variant_label,
      'productFamily',meta.product_family,
      'productFamilyLabel',meta.product_family_label,
      'marketPrice',m.market_price,'priceAsOf',m.market_date,
      'imageUrl',coalesce(meta.image_small_url,meta.image_large_url),
      'imageSmallUrl',meta.image_small_url,'imageLargeUrl',meta.image_large_url,
      'isBulkContainer',meta.is_bulk_container
    )
  FROM _mx_quick_members m
  JOIN public.pokemon_market_explorer_sealed_current_metadata_v1 meta
    ON meta.sealed_product_id=m.sealed_product_id
  WHERE m.market_date=p_market_date
  ORDER BY m.market_key,m.market_price desc,m.sealed_product_id;
  GET DIAGNOSTICS v_constituents=ROW_COUNT;

  RETURN jsonb_build_object(
    'markets',v_markets,'historyRows',v_history,'constituentRows',v_constituents
  );
END;
$function$


revoke all on function public.search_pokemon_market_explorer_leaves_v1(text,text,integer) from public,anon,authenticated;
grant execute on function public.search_pokemon_market_explorer_leaves_v1(text,text,integer) to service_role;
revoke all on function public.stage_pokemon_market_explorer_sealed_quick_markets_v2(uuid,date) from public,anon,authenticated;
grant execute on function public.stage_pokemon_market_explorer_sealed_quick_markets_v2(uuid,date) to service_role;
revoke all on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer) from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_performance_screen_v1(text,text,uuid,integer) to service_role;
revoke all on function public.assert_pokemon_market_explorer_surface_coherent_v2(uuid) from public,anon,authenticated;
grant execute on function public.assert_pokemon_market_explorer_surface_coherent_v2(uuid) to service_role;
revoke all on function public.promote_pokemon_market_explorer_surface_v2(uuid) from public,anon,authenticated;
grant execute on function public.promote_pokemon_market_explorer_surface_v2(uuid) to service_role;
revoke all on function public.rollback_pokemon_market_explorer_surface_v2() from public,anon,authenticated;
grant execute on function public.rollback_pokemon_market_explorer_surface_v2() to service_role;

commit;
