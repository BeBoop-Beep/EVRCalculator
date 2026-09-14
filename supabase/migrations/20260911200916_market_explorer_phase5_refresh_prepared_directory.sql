create or replace function public.refresh_pokemon_market_explorer_prepared_directory_v1()
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '300s'
set work_mem = '64MB'
as $$
declare
  v_generation_id uuid := gen_random_uuid();
  v_generated_at timestamptz := clock_timestamp();
  v_set_source_asof date;
  v_sealed_source_asof date;
  v_comparison_asof date;
  v_snapshot_set_count integer;
  v_cache_count integer;
  v_set_count integer;
  v_era_count integer;
  v_curated_count integer;
  v_rarity_count integer;
  v_format_count integer;
  v_history_count integer;
begin
  drop table if exists pg_temp._phase5_cache_def;
  drop table if exists pg_temp._phase5_dir_stage;
  drop table if exists pg_temp._phase5_history_stage;

  create temp table _phase5_cache_def (
    market_key text,
    market_type text,
    label text,
    asset text,
    era_id uuid,
    prepared_series_key text,
    source_as_of date,
    current_value numeric,
    screen_group text,
    screen_eligible boolean,
    source_status text,
    metadata jsonb,
    series_payload jsonb
  ) on commit drop;

  -- Public prepared Era markets: exactly the maintained global all-mode Era series.
  insert into _phase5_cache_def
  select
    'era:' || (q.normalized_spec->'eraIds'->>0),
    'era',
    e.name,
    'cards',
    (q.normalized_spec->'eraIds'->>0)::uuid,
    q.query_fingerprint,
    (q.series_payload->>'asOf')::date,
    nullif(q.series_payload->>'trackedValue','')::numeric,
    null,
    false,
    q.status,
    jsonb_build_object(
      'queryFingerprint', q.query_fingerprint,
      'queryKey', q.series_payload->>'queryKey',
      'sourceComputedThrough', q.computed_through
    ),
    q.series_payload
  from public.pokemon_market_explorer_query_cache q
  join public.eras e on e.id=(q.normalized_spec->'eraIds'->>0)::uuid
  where q.cache_kind='maintained' and q.asset='cards'
    and q.series_payload is not null
    and q.normalized_spec->>'mode'='all'
    and q.normalized_spec->>'topN' is null
    and jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=1
    and jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'segmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'pokemonIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'priceSegmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'releaseAgeCohortIds','[]'::jsonb))=0;

  -- Curated Quick Markets are real maintained prepared series, never Builder templates.
  insert into _phase5_cache_def
  select
    case q.normalized_spec->'priceSegmentIds'->>0
      when 'obtainable' then 'curated:obtainable'
      when 'intermediate' then 'curated:intermediate'
      when 'premium' then 'curated:premium'
    end,
    'curated',
    case q.normalized_spec->'priceSegmentIds'->>0
      when 'obtainable' then 'Obtainable'
      when 'intermediate' then 'Intermediate'
      when 'premium' then 'Premium'
    end,
    'cards', null::uuid, q.query_fingerprint,
    (q.series_payload->>'asOf')::date,
    nullif(q.series_payload->>'trackedValue','')::numeric,
    'card', true, q.status,
    jsonb_build_object(
      'quickMarket', q.normalized_spec->'priceSegmentIds'->>0,
      'queryFingerprint', q.query_fingerprint,
      'queryKey', q.series_payload->>'queryKey',
      'sourceComputedThrough', q.computed_through
    ),
    q.series_payload
  from public.pokemon_market_explorer_query_cache q
  where q.cache_kind='maintained' and q.asset='cards' and q.series_payload is not null
    and q.normalized_spec->>'mode'='all' and q.normalized_spec->>'topN' is null
    and jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'segmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'pokemonIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'priceSegmentIds','[]'::jsonb))=1
    and q.normalized_spec->'priceSegmentIds'->>0 in ('obtainable','intermediate','premium')
    and jsonb_array_length(coalesce(q.normalized_spec->'releaseAgeCohortIds','[]'::jsonb))=0;

  insert into _phase5_cache_def
  select
    case q.normalized_spec->'releaseAgeCohortIds'->>0
      when 'new' then 'curated:new-releases'
      when 'established' then 'curated:established'
    end,
    'curated',
    case q.normalized_spec->'releaseAgeCohortIds'->>0
      when 'new' then 'New Releases'
      when 'established' then 'Established'
    end,
    'cards', null::uuid, q.query_fingerprint,
    (q.series_payload->>'asOf')::date,
    nullif(q.series_payload->>'trackedValue','')::numeric,
    'card', true, q.status,
    jsonb_build_object(
      'quickMarket', q.normalized_spec->'releaseAgeCohortIds'->>0,
      'queryFingerprint', q.query_fingerprint,
      'queryKey', q.series_payload->>'queryKey',
      'sourceComputedThrough', q.computed_through
    ),
    q.series_payload
  from public.pokemon_market_explorer_query_cache q
  where q.cache_kind='maintained' and q.asset='cards' and q.series_payload is not null
    and q.normalized_spec->>'mode'='all' and q.normalized_spec->>'topN' is null
    and jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'segmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'pokemonIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'priceSegmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'releaseAgeCohortIds','[]'::jsonb))=1
    and q.normalized_spec->'releaseAgeCohortIds'->>0 in ('new','established');

  insert into _phase5_cache_def
  select
    'curated:global-top10', 'curated', 'Global Top 10', 'cards', null::uuid,
    q.query_fingerprint, (q.series_payload->>'asOf')::date,
    nullif(q.series_payload->>'trackedValue','')::numeric,
    'card', true, q.status,
    jsonb_build_object(
      'quickMarket', 'globalTop10',
      'queryFingerprint', q.query_fingerprint,
      'queryKey', q.series_payload->>'queryKey',
      'sourceComputedThrough', q.computed_through
    ),
    q.series_payload
  from public.pokemon_market_explorer_query_cache q
  where q.cache_kind='maintained' and q.asset='cards' and q.series_payload is not null
    and q.normalized_spec->>'mode'='chase'
    and (q.normalized_spec->>'topN')::integer=10
    and jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'segmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'pokemonIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'priceSegmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'releaseAgeCohortIds','[]'::jsonb))=0;

  -- Only already-maintained rarity series become prepared Screen children.
  insert into _phase5_cache_def
  select
    'rarity:' || (q.normalized_spec->'segmentIds'->>0),
    'prepared_rarity',
    coalesce(
      nullif(regexp_replace(regexp_replace(q.series_payload->>'displayLabel','^Global · ',''),' · All$',''),''),
      q.normalized_spec->'segmentIds'->>0
    ),
    'cards', null::uuid, q.query_fingerprint,
    (q.series_payload->>'asOf')::date,
    nullif(q.series_payload->>'trackedValue','')::numeric,
    'card', true, q.status,
    jsonb_build_object(
      'segmentId', q.normalized_spec->'segmentIds'->>0,
      'queryFingerprint', q.query_fingerprint,
      'queryKey', q.series_payload->>'queryKey',
      'sourceComputedThrough', q.computed_through
    ),
    q.series_payload
  from public.pokemon_market_explorer_query_cache q
  where q.cache_kind='maintained' and q.asset='cards' and q.series_payload is not null
    and q.normalized_spec->>'mode'='all' and q.normalized_spec->>'topN' is null
    and jsonb_array_length(coalesce(q.normalized_spec->'eraIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'setIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'segmentIds','[]'::jsonb))=1
    and jsonb_array_length(coalesce(q.normalized_spec->'pokemonIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'priceSegmentIds','[]'::jsonb))=0
    and jsonb_array_length(coalesce(q.normalized_spec->'releaseAgeCohortIds','[]'::jsonb))=0;

  select market_date, set_count
  into v_set_source_asof, v_snapshot_set_count
  from public.pokemon_explore_set_value_snapshot_latest
  where tcg='pokemon' and scope='market';

  if v_set_source_asof is null or v_snapshot_set_count is null or v_snapshot_set_count < 1 then
    raise exception 'public prepared Set snapshot unavailable';
  end if;

  select count(*) into v_cache_count from _phase5_cache_def;
  if v_cache_count < 1 then
    raise exception 'prepared maintained cache definitions unavailable';
  end if;

  select min(family_max)
  into v_sealed_source_asof
  from (
    select segment_key, max((h->>'date')::date) as family_max
    from (
      select
        case p->>'productFamily'
          when 'booster_box' then 'boosterBox'
          when 'elite_trainer_box' then 'eliteTrainerBox'
          when 'pokemon_center_elite_trainer_box' then 'pokemonCenterEliteTrainerBox'
          when 'booster_bundle' then 'boosterBundle'
          when 'loose_booster_pack' then 'packs'
          when 'sleeved_booster_pack' then 'packs'
        end as segment_key,
        p
      from public.pokemon_set_sealed_market_snapshot_latest s
      cross join lateral jsonb_array_elements(coalesce(s.payload_json->'products','[]'::jsonb)) p
      where s.tcg='pokemon' and s.product_count > 0
    ) sp
    cross join lateral jsonb_array_elements(coalesce(sp.p->'history','[]'::jsonb)) h
    where sp.segment_key is not null
      and nullif(h->>'marketPrice','')::numeric > 0
    group by segment_key
  ) family_dates;

  if v_sealed_source_asof is null then
    raise exception 'prepared sealed-family history unavailable';
  end if;

  -- Latest date present in EVERY required maintained prepared series, bounded
  -- by the current public Set generation and the sealed-family source horizon.
  select max(d.market_date)
  into v_comparison_asof
  from (
    select (p->>0)::date as market_date, count(distinct c.prepared_series_key) as series_count
    from _phase5_cache_def c
    cross join lateral jsonb_array_elements(coalesce(c.series_payload->'trend','[]'::jsonb)) p
    where (p->>0)::date <= least(v_set_source_asof, v_sealed_source_asof)
    group by (p->>0)::date
  ) d
  where d.series_count = v_cache_count;

  if v_comparison_asof is null then
    raise exception 'no coherent prepared comparison watermark';
  end if;

  create temp table _phase5_dir_stage
  (like public.pokemon_market_explorer_prepared_directory_v1 including defaults)
  on commit drop;
  create temp table _phase5_history_stage
  (like public.pokemon_market_explorer_prepared_history_v1 including defaults)
  on commit drop;

  -- Sets: the public prepared Set snapshot owns directory membership. Era ids
  -- come from the canonical Set catalogue; analytical history comes from the
  -- already-prepared dashboard Market Index, not a card-level reconstruction.
  insert into _phase5_dir_stage (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select
    'set:' || (e->>'setId'), 'set', e->>'name', 'cards',
    (e->>'setId')::uuid, null::uuid, s.era_id,
    'set-cards-market-index:' || (e->>'setId'),
    v_comparison_asof, nullif(e->>'setValueAsOf','')::date,
    nullif(e->>'currentSetValue','')::numeric,
    null, false, 'public_set_snapshot', e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey', e->>'canonicalKey',
      'eraName', er.name,
      'logoUrl', e->>'logoUrl',
      'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus'
    )),
    v_generation_id, v_generated_at
  from public.pokemon_explore_set_value_snapshot_latest snap
  cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
  join public.sets s on s.id=(e->>'setId')::uuid
  left join public.eras er on er.id=s.era_id
  where snap.tcg='pokemon' and snap.scope='market';

  -- Eras, curated Quick Markets and prepared rarity markets all come from the
  -- maintained-prepared authority only; custom cache rows cannot enter.
  insert into _phase5_dir_stage (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select c.market_key,c.market_type,c.label,c.asset,null::uuid,c.era_id,null::uuid,
         c.prepared_series_key,v_comparison_asof,c.source_as_of,c.current_value,
         c.screen_group,c.screen_eligible,'maintained_query_cache',c.source_status,c.metadata,
         v_generation_id,v_generated_at
  from _phase5_cache_def c;

  -- Canonical published sealed-format children. Their histories are built below
  -- from the same prepared product histories and productFamily classifications
  -- used by the published Global Sealed service.
  insert into _phase5_dir_stage (
    market_key,market_type,label,asset,prepared_series_key,
    comparison_as_of,source_as_of,current_value,screen_group,screen_eligible,
    source_kind,source_status,metadata,generation_id,generated_at
  )
  with definitions(segment_key,label) as (
    values
      ('boosterBox','Booster Boxes'),
      ('eliteTrainerBox','Elite Trainer Boxes'),
      ('pokemonCenterEliteTrainerBox','Pokémon Center ETBs'),
      ('boosterBundle','Booster Bundles'),
      ('packs','Packs')
  ), products as (
    select
      case p->>'productFamily'
        when 'booster_box' then 'boosterBox'
        when 'elite_trainer_box' then 'eliteTrainerBox'
        when 'pokemon_center_elite_trainer_box' then 'pokemonCenterEliteTrainerBox'
        when 'booster_bundle' then 'boosterBundle'
        when 'loose_booster_pack' then 'packs'
        when 'sleeved_booster_pack' then 'packs'
      end as segment_key,
      p
    from public.pokemon_set_sealed_market_snapshot_latest s
    cross join lateral jsonb_array_elements(coalesce(s.payload_json->'products','[]'::jsonb)) p
    where s.tcg='pokemon' and s.product_count > 0
  ), latest_prices as (
    select pr.segment_key, pr.p->>'sealedProductId' as product_id,
           lp.price
    from products pr
    cross join lateral (
      select (h->>'marketPrice')::numeric as price
      from jsonb_array_elements(coalesce(pr.p->'history','[]'::jsonb)) h
      where (h->>'date')::date <= v_sealed_source_asof
        and nullif(h->>'marketPrice','')::numeric > 0
      order by (h->>'date')::date desc
      limit 1
    ) lp
    where pr.segment_key is not null
  ), latest_by_segment as (
    select segment_key,sum(price) as current_value
    from latest_prices group by segment_key
  )
  select 'sealed-format:'||d.segment_key,'prepared_format',d.label,'sealed',
         'sealed-segment:'||d.segment_key,v_comparison_asof,v_sealed_source_asof,
         l.current_value,'sealed',true,'prepared_sealed_snapshots','ready',
         jsonb_build_object('segmentKey',d.segment_key,'segmentContractVersion','pokemon-sealed-segments-v1'),
         v_generation_id,v_generated_at
  from definitions d left join latest_by_segment l using(segment_key);

  -- Prepared Set market-index histories, clipped to the continuous chain segment
  -- containing the common comparison watermark.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with public_sets as (
    select (e->>'setId')::uuid set_id
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
  ), dashboards as (
    select d.set_id,d.payload_json->'cardsMarket'->'marketIndex' as mi
    from public.pokemon_set_market_dashboard_snapshot_latest d
    join public_sets p using(set_id)
    where d.window_key='365d'
  ), selected as (
    select d.set_id,d.mi,
           (select (x->>'chainSegmentId')::integer
            from jsonb_array_elements(coalesce(d.mi->'history','[]'::jsonb)) x
            where (x->>'date')::date=v_comparison_asof
            limit 1) as segment_id
    from dashboards d
    where jsonb_typeof(d.mi)='object'
  )
  select 'set:'||s.set_id::text,(h->>'date')::date,
         (h->>'indexValue')::numeric,
         rv.set_value,
         coalesce((h->>'chainSegmentId')::integer,0),v_generation_id
  from selected s
  cross join lateral jsonb_array_elements(coalesce(s.mi->'history','[]'::jsonb)) h
  left join public.pokemon_market_root_set_value_daily_history_v2_shadow rv
    on rv.set_id=s.set_id and rv.market_scope='standard' and rv.market_date=(h->>'date')::date
  where s.segment_id is not null
    and (h->>'date')::date <= v_comparison_asof
    and coalesce((h->>'chainSegmentId')::integer,0)=s.segment_id;

  -- Maintained prepared series are already current-chain normalized histories.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  select c.market_key,(p->>0)::date,(p->>1)::numeric,
         tv.tracked_value,0,v_generation_id
  from _phase5_cache_def c
  cross join lateral jsonb_array_elements(coalesce(c.series_payload->'trend','[]'::jsonb)) p
  left join lateral (
    select nullif(th->>'value','')::numeric as tracked_value
    from jsonb_array_elements(coalesce(c.series_payload->'trackedValueHistory','[]'::jsonb)) th
    where (th->>'date')::date=(p->>0)::date
    limit 1
  ) tv on true
  where (p->>0)::date <= v_comparison_asof;

  -- Rebuild the five published sealed-family indexes from prepared product
  -- histories. Every product is forward-filled from its first real observation;
  -- new entrants affect tracked value immediately but are excluded from that
  -- day's common-cohort return, matching chain_linked_common_cohort_v1.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with products as (
    select
      case p->>'productFamily'
        when 'booster_box' then 'boosterBox'
        when 'elite_trainer_box' then 'eliteTrainerBox'
        when 'pokemon_center_elite_trainer_box' then 'pokemonCenterEliteTrainerBox'
        when 'booster_bundle' then 'boosterBundle'
        when 'loose_booster_pack' then 'packs'
        when 'sleeved_booster_pack' then 'packs'
      end as segment_key,
      p->>'sealedProductId' as product_id,
      p->'history' as history
    from public.pokemon_set_sealed_market_snapshot_latest s
    cross join lateral jsonb_array_elements(coalesce(s.payload_json->'products','[]'::jsonb)) p
    where s.tcg='pokemon' and s.product_count > 0
  ), firsts as (
    select segment_key,product_id,history,
           (select min((h->>'date')::date)
            from jsonb_array_elements(coalesce(history,'[]'::jsonb)) h
            where nullif(h->>'marketPrice','')::numeric > 0) as first_date
    from products
    where segment_key is not null and product_id is not null
  ), dense as (
    select f.segment_key,f.product_id,d::date as market_date,
           lp.price
    from firsts f
    cross join lateral generate_series(f.first_date,v_comparison_asof,interval '1 day') d
    cross join lateral (
      select (h->>'marketPrice')::numeric as price
      from jsonb_array_elements(coalesce(f.history,'[]'::jsonb)) h
      where (h->>'date')::date <= d::date
        and nullif(h->>'marketPrice','')::numeric > 0
      order by (h->>'date')::date desc
      limit 1
    ) lp
    where f.first_date is not null and f.first_date <= v_comparison_asof
  ), lagged as (
    select d.*,
           lag(d.price) over(partition by d.segment_key,d.product_id order by d.market_date) as previous_price
    from dense d
  ), daily as (
    select segment_key,market_date,sum(price) as basket_value,
           sum(price) filter(where previous_price is not null) as current_common,
           sum(previous_price) filter(where previous_price is not null) as previous_common
    from lagged
    group by segment_key,market_date
  ), indexed as (
    select segment_key,market_date,basket_value,
           100.0 * exp(sum(ln(case when previous_common is not null and previous_common > 0
                                   then current_common/previous_common else 1.0 end))
                       over(partition by segment_key order by market_date rows unbounded preceding)) as index_value
    from daily
  )
  select 'sealed-format:'||segment_key,market_date,index_value,basket_value,0,v_generation_id
  from indexed
  where market_date <= v_comparison_asof;

  -- Derive every analytical metric from the normalized compact history at ONE
  -- watermark. Exact elapsed-calendar boundary observations are required.
  with running as (
    select h.*,
           max(h.index_value) over(partition by h.market_key order by h.market_date rows unbounded preceding) as running_high
    from _phase5_history_stage h
  ), stats as (
    select market_key,
      min(market_date) as history_start,
      max(market_date) as history_end,
      count(*)::integer as point_count,
      max(index_value) filter(where market_date=v_comparison_asof) as end_index,
      max(tracked_value) filter(where market_date=v_comparison_asof) as end_tracked,
      max(index_value) filter(where market_date=v_comparison_asof-7) as b7,
      max(index_value) filter(where market_date=v_comparison_asof-30) as b30,
      max(index_value) filter(where market_date=v_comparison_asof-90) as b90,
      max(index_value) filter(where market_date=v_comparison_asof-365) as b365,
      max(index_value) as since_high,
      min((index_value/nullif(running_high,0)-1.0)*100.0) as max_drawdown
    from running
    group by market_key
  )
  update _phase5_dir_stage d
  set comparison_value=s.end_tracked,
      comparison_index_value=s.end_index,
      history_available=(s.end_index is not null),
      history_start_date=s.history_start,
      history_end_date=s.history_end,
      history_point_count=s.point_count,
      return_7d_pct=case when s.end_index is not null and s.b7 is not null then (s.end_index/s.b7-1.0)*100.0 end,
      return_30d_pct=case when s.end_index is not null and s.b30 is not null then (s.end_index/s.b30-1.0)*100.0 end,
      return_90d_pct=case when s.end_index is not null and s.b90 is not null then (s.end_index/s.b90-1.0)*100.0 end,
      return_1y_pct=case when s.end_index is not null and s.b365 is not null then (s.end_index/s.b365-1.0)*100.0 end,
      current_drawdown_pct=case when s.end_index is not null and s.since_high > 0 then (s.end_index/s.since_high-1.0)*100.0 end,
      max_drawdown_pct=s.max_drawdown
  from stats s
  where s.market_key=d.market_key;

  -- Relative performance is arithmetic excess return against the prepared
  -- parent Era over the exact same comparison window and watermark.
  update _phase5_dir_stage s
  set relative_7d_vs_era_pct=case when s.return_7d_pct is not null and e.return_7d_pct is not null then s.return_7d_pct-e.return_7d_pct end,
      relative_30d_vs_era_pct=case when s.return_30d_pct is not null and e.return_30d_pct is not null then s.return_30d_pct-e.return_30d_pct end,
      relative_90d_vs_era_pct=case when s.return_90d_pct is not null and e.return_90d_pct is not null then s.return_90d_pct-e.return_90d_pct end,
      relative_1y_vs_era_pct=case when s.return_1y_pct is not null and e.return_1y_pct is not null then s.return_1y_pct-e.return_1y_pct end
  from _phase5_dir_stage e
  where s.market_type='set' and e.market_type='era' and e.era_id=s.parent_era_id;

  select count(*) filter(where market_type='set'),
         count(*) filter(where market_type='era'),
         count(*) filter(where market_type='curated'),
         count(*) filter(where market_type='prepared_rarity'),
         count(*) filter(where market_type='prepared_format')
  into v_set_count,v_era_count,v_curated_count,v_rarity_count,v_format_count
  from _phase5_dir_stage;
  select count(*) into v_history_count from _phase5_history_stage;

  if v_set_count <> v_snapshot_set_count then
    raise exception 'prepared Set directory count mismatch: % vs %',v_set_count,v_snapshot_set_count;
  end if;
  if v_era_count < 1 or v_era_count <> (select count(*) from _phase5_cache_def where market_type='era') then
    raise exception 'prepared Era directory count mismatch';
  end if;
  if v_curated_count <> 6 then
    raise exception 'expected 6 curated Quick Markets, found %',v_curated_count;
  end if;
  if v_rarity_count < 1 or v_rarity_count <> (select count(*) from _phase5_cache_def where market_type='prepared_rarity') then
    raise exception 'prepared rarity directory count mismatch';
  end if;
  if v_format_count <> 5 then
    raise exception 'expected 5 prepared sealed formats, found %',v_format_count;
  end if;
  if exists(select 1 from _phase5_dir_stage where market_type='set' and parent_era_id is null) then
    raise exception 'prepared Set without Era relationship';
  end if;
  if exists(
    select 1 from _phase5_dir_stage s
    where s.market_type='set'
      and not exists(select 1 from _phase5_dir_stage e where e.market_type='era' and e.era_id=s.parent_era_id)
  ) then
    raise exception 'prepared Set parent Era missing from directory';
  end if;
  if exists(select 1 from _phase5_dir_stage group by market_key having count(*)<>1) then
    raise exception 'duplicate prepared directory key';
  end if;
  if exists(select 1 from _phase5_history_stage where market_date>v_comparison_asof) then
    raise exception 'prepared comparison history exceeded common watermark';
  end if;
  if exists(
    select 1 from _phase5_cache_def c
    where not exists(
      select 1 from _phase5_history_stage h
      where h.market_key=c.market_key and h.market_date=v_comparison_asof
    )
  ) then
    raise exception 'maintained prepared series missing common comparison observation';
  end if;
  if exists(
    select 1 from _phase5_dir_stage d
    where d.market_type='prepared_format'
      and not exists(select 1 from _phase5_history_stage h where h.market_key=d.market_key and h.market_date=v_comparison_asof)
  ) then
    raise exception 'sealed prepared format missing common comparison observation';
  end if;

  -- Transactional replacement: on any error, the previous generation remains.
  delete from public.pokemon_market_explorer_prepared_directory_v1;
  insert into public.pokemon_market_explorer_prepared_directory_v1
  select * from _phase5_dir_stage;
  insert into public.pokemon_market_explorer_prepared_history_v1
  select * from _phase5_history_stage;

  return jsonb_build_object(
    'generationId',v_generation_id,
    'generatedAt',v_generated_at,
    'comparisonAsOf',v_comparison_asof,
    'sourceAsOf',jsonb_build_object('sets',v_set_source_asof,'sealed',v_sealed_source_asof),
    'counts',jsonb_build_object(
      'sets',v_set_count,'eras',v_era_count,'curated',v_curated_count,
      'rarities',v_rarity_count,'sealedFormats',v_format_count,'historyRows',v_history_count
    )
  );
end;
$$;

revoke all on function public.refresh_pokemon_market_explorer_prepared_directory_v1() from public, anon, authenticated;
grant execute on function public.refresh_pokemon_market_explorer_prepared_directory_v1() to service_role;

comment on function public.refresh_pokemon_market_explorer_prepared_directory_v1() is
'Phase 5 prepared-market publisher. Reads only public/prepared Set, maintained cache, dashboard and sealed snapshot authorities; never claims or writes custom query-cache leases. Atomically replaces compact directory/history at one common comparison watermark.';
