-- Publish edition-split vintage Sets as explicit market identities.
--
-- Contract:
--   standard roots -> set:<set_id>
--   edition roots  -> set:<set_id>:first_edition / unlimited / shadowless
-- No generic blended Set market is published for an edition-split root.
--
-- This migration rewrites only the currently deployed prepared Set-directory,
-- Set-history, lightweight sync, and prepared constituent-staging sections.
-- Every rewrite is guarded by stable comment markers / function identity and
-- fails closed if the deployed function shape has drifted.

-- 1. Prepared generation builder: scoped Set directory + scoped history.
do $$
declare
  v_sql text;
  v_start integer;
  v_end integer;
  v_old text;
  v_new text;
begin
  select pg_get_functiondef('public.refresh_pokemon_market_explorer_prepared_directory_v1()'::regprocedure)
    into v_sql;

  v_start := position('  -- Sets: the public prepared Set snapshot owns directory membership.' in v_sql);
  v_end := position('  -- Eras, curated Quick Markets and prepared rarity markets all come from the' in v_sql);
  if v_start = 0 or v_end = 0 or v_end <= v_start then
    raise exception 'prepared refresh Set-directory section changed; refusing unsafe rewrite';
  end if;
  v_old := substring(v_sql from v_start for v_end - v_start);
  v_new := $section$
  -- Sets: the public Set Market snapshot already publishes one explicit market
  -- identity per economically distinct scope. Standard roots keep set:<id>;
  -- edition-split roots publish only scoped keys and never a blended generic Set.
  insert into _phase5_dir_stage (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select
    coalesce(
      nullif(e->>'marketKey',''),
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then 'set:' || (e->>'setId')
        else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
      end
    ),
    'set', e->>'name', 'cards',
    (e->>'setId')::uuid, null::uuid, s.era_id,
    'set-cards-market-index:' || (e->>'setId') ||
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then '' else ':' || (e->>'marketScope') end,
    v_comparison_asof, nullif(e->>'setValueAsOf','')::date,
    nullif(e->>'currentSetValue','')::numeric,
    null, false, 'public_set_snapshot', e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey', e->>'canonicalKey',
      'eraName', er.name,
      'logoUrl', e->>'logoUrl',
      'symbolUrl', e->>'symbolUrl',
      'certificationStatus', e->>'certificationStatus',
      'marketScope', coalesce(nullif(e->>'marketScope',''),'standard'),
      'baseSetName', coalesce(nullif(e->>'baseSetName',''),e->>'name'),
      'scopeContractVersion', 'pokemon-set-market-scope-v1'
    )),
    v_generation_id, v_generated_at
  from public.pokemon_explore_set_value_snapshot_latest snap
  cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
  join public.sets s on s.id=(e->>'setId')::uuid
  left join public.eras er on er.id=s.era_id
  where snap.tcg='pokemon' and snap.scope='market';

$section$;
  v_sql := overlay(v_sql placing v_new from v_start for v_end - v_start);

  v_start := position('  -- Prepared Set market-index histories, clipped to the continuous chain segment' in v_sql);
  v_end := position('  -- Maintained prepared series are already current-chain normalized histories.' in v_sql);
  if v_start = 0 or v_end = 0 or v_end <= v_start then
    raise exception 'prepared refresh Set-history section changed; refusing unsafe rewrite';
  end if;
  v_old := substring(v_sql from v_start for v_end - v_start);
  v_new := $section$
  -- Prepared Set histories. Standard Sets retain the already-prepared dashboard
  -- Market Index. Edition-scoped markets use the certified canonical root-scope
  -- Set Value history, whose constituent universe is fixed by edition; indexing
  -- that fixed basket to 100 is equivalent to a common-cohort price index and
  -- cannot inherit the old 1st-Edition/Unlimited switching defect.
  insert into _phase5_history_stage
    (market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id)
  with public_markets as (
    select
      coalesce(
        nullif(e->>'marketKey',''),
        case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end
      ) as market_key,
      (e->>'setId')::uuid as set_id,
      coalesce(nullif(e->>'marketScope',''),'standard') as market_scope
    from public.pokemon_explore_set_value_snapshot_latest snap
    cross join lateral jsonb_array_elements(snap.payload_json->'sets') e
    where snap.tcg='pokemon' and snap.scope='market'
  ), standard_dashboards as (
    select p.market_key,d.set_id,d.payload_json->'cardsMarket'->'marketIndex' as mi
    from public.pokemon_set_market_dashboard_snapshot_latest d
    join public_markets p on p.set_id=d.set_id and p.market_scope='standard'
    where d.window_key='365d'
  ), standard_selected as (
    select d.market_key,d.set_id,d.mi,
           (select (x->>'chainSegmentId')::integer
            from jsonb_array_elements(coalesce(d.mi->'history','[]'::jsonb)) x
            where (x->>'date')::date=v_comparison_asof
            limit 1) as segment_id
    from standard_dashboards d
    where jsonb_typeof(d.mi)='object'
  ), standard_history as (
    select s.market_key,(h->>'date')::date as market_date,
           (h->>'indexValue')::numeric as index_value,
           rv.set_value as tracked_value,
           coalesce((h->>'chainSegmentId')::integer,0) as chain_segment_id
    from standard_selected s
    cross join lateral jsonb_array_elements(coalesce(s.mi->'history','[]'::jsonb)) h
    left join public.pokemon_market_root_set_value_daily_history_v2_shadow rv
      on rv.set_id=s.set_id and rv.market_scope='standard' and rv.market_date=(h->>'date')::date
    where s.segment_id is not null
      and (h->>'date')::date <= v_comparison_asof
      and coalesce((h->>'chainSegmentId')::integer,0)=s.segment_id
  ), scoped_values as (
    select p.market_key,rv.market_date,rv.set_value,
           first_value(rv.set_value) over(
             partition by p.market_key order by rv.market_date
             rows between unbounded preceding and unbounded following
           ) as base_value
    from public_markets p
    join public.pokemon_market_root_set_value_daily_history_v2_shadow rv
      on rv.set_id=p.set_id and rv.market_scope=p.market_scope
    where p.market_scope<>'standard'
      and rv.certified_on_date=true
      and rv.set_value>0
      and rv.market_date<=v_comparison_asof
  ), scoped_history as (
    select market_key,market_date,
           100.0 * set_value / nullif(base_value,0) as index_value,
           set_value as tracked_value,
           0::integer as chain_segment_id
    from scoped_values
  )
  select market_key,market_date,index_value,tracked_value,chain_segment_id,v_generation_id
  from standard_history
  union all
  select market_key,market_date,index_value,tracked_value,chain_segment_id,v_generation_id
  from scoped_history;

$section$;
  v_sql := overlay(v_sql placing v_new from v_start for v_end - v_start);

  execute v_sql;
end;
$$;

-- 2. Lightweight Set-directory sync must preserve the same scoped identities
-- between full prepared-generation publications.
create or replace function public.sync_pokemon_market_explorer_set_directory_v1()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_payload jsonb;
  v_market_date date;
  v_snapshot_set_count integer;
  v_payload_set_count integer;
  v_existing_min_comparison date;
  v_existing_max_comparison date;
  v_generation_id uuid;
  v_generated_at timestamptz;
  v_upserted integer := 0;
  v_directory_set_count integer := 0;
begin
  select s.payload_json,s.market_date,s.set_count
    into v_payload,v_market_date,v_snapshot_set_count
  from public.pokemon_explore_set_value_snapshot_latest s
  where s.tcg='pokemon' and s.scope='market'
  limit 1;

  if v_payload is null or v_market_date is null or coalesce(v_snapshot_set_count,0)<1 then
    raise exception 'Global Set Market snapshot unavailable for Explorer Set-directory sync';
  end if;

  v_payload_set_count := jsonb_array_length(coalesce(v_payload->'sets','[]'::jsonb));
  if v_payload_set_count <> v_snapshot_set_count then
    raise exception 'Global Set Market snapshot count mismatch: payload=% row=%',
      v_payload_set_count,v_snapshot_set_count;
  end if;

  select min(d.comparison_as_of),max(d.comparison_as_of)
    into v_existing_min_comparison,v_existing_max_comparison
  from public.pokemon_market_explorer_prepared_directory_v1 d;

  if v_existing_min_comparison is null or v_existing_max_comparison is null
     or v_existing_min_comparison is distinct from v_existing_max_comparison then
    raise exception 'Prepared Explorer directory has no single comparison watermark';
  end if;

  select d.generation_id,d.generated_at
    into v_generation_id,v_generated_at
  from public.pokemon_market_explorer_prepared_directory_v1 d
  order by d.generated_at desc,d.market_key
  limit 1;

  v_generation_id := coalesce(v_generation_id,extensions.gen_random_uuid());
  v_generated_at := coalesce(v_generated_at,clock_timestamp());

  -- Remove superseded generic or retired scoped Set identities before upsert.
  delete from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.market_type='set'
    and not exists (
      select 1
      from jsonb_array_elements(v_payload->'sets') e
      where coalesce(
        nullif(e->>'marketKey',''),
        case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
          then 'set:' || (e->>'setId')
          else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
        end
      )=d.market_key
    );

  insert into public.pokemon_market_explorer_prepared_directory_v1 (
    market_key,market_type,label,asset,set_id,era_id,parent_era_id,
    prepared_series_key,comparison_as_of,source_as_of,current_value,
    screen_group,screen_eligible,source_kind,source_status,metadata,
    generation_id,generated_at
  )
  select
    coalesce(
      nullif(e->>'marketKey',''),
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then 'set:' || (e->>'setId')
        else 'set:' || (e->>'setId') || ':' || (e->>'marketScope')
      end
    ),
    'set',e->>'name','cards',(e->>'setId')::uuid,null::uuid,s.era_id,
    'set-cards-market-index:' || (e->>'setId') ||
      case when coalesce(nullif(e->>'marketScope',''),'standard')='standard'
        then '' else ':' || (e->>'marketScope') end,
    v_existing_min_comparison,nullif(e->>'setValueAsOf','')::date,
    nullif(e->>'currentSetValue','')::numeric,null,false,
    'public_set_snapshot',e->>'valueStatus',
    jsonb_strip_nulls(jsonb_build_object(
      'canonicalKey',e->>'canonicalKey','eraName',er.name,
      'logoUrl',e->>'logoUrl','symbolUrl',e->>'symbolUrl',
      'certificationStatus',e->>'certificationStatus',
      'marketScope',coalesce(nullif(e->>'marketScope',''),'standard'),
      'baseSetName',coalesce(nullif(e->>'baseSetName',''),e->>'name'),
      'scopeContractVersion','pokemon-set-market-scope-v1'
    )),
    v_generation_id,v_generated_at
  from jsonb_array_elements(v_payload->'sets') e
  join public.sets s on s.id=(e->>'setId')::uuid
  left join public.eras er on er.id=s.era_id
  on conflict (market_key) do update
  set label=excluded.label,asset=excluded.asset,set_id=excluded.set_id,
      era_id=excluded.era_id,parent_era_id=excluded.parent_era_id,
      prepared_series_key=excluded.prepared_series_key,
      source_as_of=excluded.source_as_of,current_value=excluded.current_value,
      source_kind=excluded.source_kind,source_status=excluded.source_status,
      metadata=excluded.metadata;
  get diagnostics v_upserted = row_count;

  select count(*)::integer into v_directory_set_count
  from public.pokemon_market_explorer_prepared_directory_v1 d
  where d.market_type='set';

  if v_directory_set_count <> v_snapshot_set_count then
    raise exception 'Prepared Explorer Set-directory count mismatch after sync: directory=% snapshot=%',
      v_directory_set_count,v_snapshot_set_count;
  end if;

  if exists (
    select 1 from public.pokemon_market_explorer_prepared_directory_v1 s
    where s.market_type='set'
      and (s.parent_era_id is null or not exists (
        select 1 from public.pokemon_market_explorer_prepared_directory_v1 e
        where e.market_type='era' and e.era_id=s.parent_era_id
      ))
  ) then
    raise exception 'Prepared Explorer Set directory contains a Set without its parent Era';
  end if;

  return jsonb_build_object(
    'status','complete','marketDate',v_market_date,
    'snapshotSetCount',v_snapshot_set_count,'directorySetCount',v_directory_set_count,
    'rowsUpserted',v_upserted,'comparisonAsOf',v_existing_min_comparison
  );
end;
$function$;

-- 3. Prepared constituent staging: standard Set markets keep the existing
-- date-pinned reader. Explicit edition markets stage only the matching root
-- scope and never allow another edition to substitute.
do $$
declare
  v_sql text;
  v_start integer;
  v_end integer;
  v_new text;
begin
  select pg_get_functiondef('public.stage_pokemon_market_explorer_prepared_constituents_v1(uuid)'::regprocedure)
    into v_sql;
  v_start := position('    if d.source_kind = ''public_set_snapshot'' and d.market_type = ''set'' and d.asset = ''cards'' and d.set_id is not null then' in v_sql);
  v_end := position('    elsif d.source_kind = ''prepared_sealed_snapshots'' and d.market_type = ''prepared_format'' and d.asset = ''sealed'' then' in v_sql);
  if v_start=0 or v_end=0 or v_end<=v_start then
    raise exception 'prepared constituent Set staging section changed; refusing unsafe rewrite';
  end if;

  v_new := $section$
    if d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' and d.set_id is not null then
      insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
        (generation_id,market_key,asset,source_kind,definition_version,source_as_of,total_count,availability)
      values (
        p_generation_id,d.market_key,'cards',d.source_kind,
        coalesce(d.metadata->>'scopeContractVersion',d.prepared_series_key),
        d.source_as_of,0,'empty'
      );

      if coalesce(d.metadata->>'marketScope','standard')='standard' then
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id,market_key,rank,instrument_id,asset,market_price,price_as_of,item)
        select p_generation_id,d.market_key,r.rank,r.card_variant_id::text,'cards',
          r.market_price,r.market_date,
          jsonb_build_object(
            'rank',r.rank,'instrumentId',r.card_variant_id,'cardVariantId',r.card_variant_id,
            'canonicalCardId',r.canonical_card_id,'cardName',cc.name,'setId',r.set_id,
            'setName',s.name,'cardNumber',cc.printed_number,'rarity',cc.rarity,
            'edition',cv.edition,'printingType',cv.printing_type,'specialType',cv.special_type,
            'marketPrice',r.market_price,'asOf',r.market_date
          )
        from (
          select q.*,row_number() over(order by q.market_price desc nulls last,q.card_variant_id)::integer as rank
          from public.get_pokemon_cards_daily_constituents(
            array[d.set_id],d.source_as_of,d.source_as_of,null::uuid[]
          ) q
        ) r
        left join public.pokemon_canonical_cards cc on cc.id=r.canonical_card_id
        left join public.card_variants cv on cv.id=r.card_variant_id
        left join public.sets s on s.id=r.set_id;
        get diagnostics v_total = row_count;
      elsif d.source_status='current' and d.source_as_of is not null then
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id,market_key,rank,instrument_id,asset,market_price,price_as_of,item)
        select p_generation_id,d.market_key,r.rank,r.card_variant_id::text,'cards',
          r.market_price,d.source_as_of,
          jsonb_build_object(
            'rank',r.rank,'instrumentId',r.card_variant_id,'cardVariantId',r.card_variant_id,
            'canonicalCardId',r.canonical_card_id,'cardName',r.card_name,
            'setId',r.member_set_id,'setName',r.member_set_name,'cardNumber',r.card_number,
            'rarity',r.rarity,'edition',r.edition,'printingType',r.printing_type,
            'specialType',r.special_type,'marketPrice',r.market_price,'asOf',d.source_as_of,
            'sourceDate',r.captured_at,'marketScope',r.market_scope
          )
        from (
          select q.*,row_number() over(order by q.market_price desc nulls last,q.card_variant_id)::integer as rank
          from public.get_pokemon_market_root_set_card_prices_latest_v1(d.set_id) q
          where q.market_scope=d.metadata->>'marketScope'
            and q.market_price>0
        ) r;
        get diagnostics v_total = row_count;
      else
        v_total := 0;
      end if;

      update public.pokemon_market_explorer_prepared_constituent_totals_v1
      set total_count=v_total,
          availability=case
            when coalesce(d.metadata->>'marketScope','standard')<>'standard'
                 and d.source_status<>'current' then 'unavailable'
            when v_total=0 then 'empty'
            else 'available'
          end,
          availability_reason=case
            when coalesce(d.metadata->>'marketScope','standard')<>'standard'
                 and d.source_status<>'current'
              then 'Edition-scoped market is not current for this prepared generation'
            else null
          end
      where generation_id=p_generation_id and market_key=d.market_key;
$section$;

  v_sql := overlay(v_sql placing v_new from v_start for v_end-v_start);
  execute v_sql;
end;
$$;
