-- Serialize prepared constituent staging for concurrent guarded publisher calls.
--
-- Production evidence on 2026-09-24 showed the scheduled publisher and a manual
-- recovery call can enter constituent staging for the same generation at the
-- same time. One caller completed, while the other failed on a duplicate
-- (generation_id, market_key) total row. This forward migration keeps the
-- generation-pinned authority unchanged and adds only a transaction-scoped
-- advisory lock around the staging cycle and the publisher's check-then-stage
-- decision.
--
-- Forward-only correction to 20260924000000_prepared_constituent_authority_v1.

create or replace function public.stage_pokemon_market_explorer_prepared_constituents_v1(p_generation_id uuid)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
as $function$
declare
  d record;
  v_snapshot record;
  v_segment jsonb;
  v_cache public.pokemon_market_explorer_query_cache%rowtype;
  v_found boolean;
  v_total integer;
  v_markets integer := 0;
  v_rows integer := 0;
  v_bad text;
begin
  if p_generation_id is null or not exists (
    select 1 from public.pokemon_market_explorer_prepared_generations_v1 where generation_id = p_generation_id) then
    raise exception 'UNKNOWN_GENERATION' using errcode = 'P0001';
  end if;

  -- Serialize staging for one generation. The guarded publisher can be invoked
  -- concurrently by the scheduled worker and a manual recovery; without a
  -- generation-scoped lock, both callers can observe "no staged totals" and
  -- race into the delete/insert cycle, producing duplicate-key failures.
  perform pg_advisory_xact_lock(hashtext(p_generation_id::text), 17341);

  delete from public.pokemon_market_explorer_prepared_constituent_totals_v1 where generation_id = p_generation_id;

  select market_date, updated_at, payload_json into v_snapshot
    from public.pokemon_explore_set_value_snapshot_latest where tcg = 'pokemon' and scope = 'market';

  for d in
    select * from (
      select x.* from public.pokemon_market_explorer_prepared_directory_v1 x where x.generation_id = p_generation_id
      union all
      select y.* from public.pokemon_market_explorer_prepared_directory_generations_v1 y where y.generation_id = p_generation_id
    ) all_d order by market_key
  loop
    if d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' and d.set_id is not null then
      -- Same membership authority as the v2 reader (root/subset expansion lives in the resolver).
      insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
        (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability)
      values (p_generation_id, d.market_key, 'cards', d.source_kind,
        coalesce(d.metadata->>'segmentContractVersion', d.prepared_series_key), d.source_as_of, 0, 'empty');
      insert into public.pokemon_market_explorer_prepared_constituents_v1
        (generation_id, market_key, rank, instrument_id, asset, market_price, price_as_of, item)
      select p_generation_id, d.market_key, r.rank, r.card_variant_id::text, 'cards', r.market_price, r.market_date,
        jsonb_build_object('rank', r.rank, 'instrumentId', r.card_variant_id, 'cardVariantId', r.card_variant_id,
          'canonicalCardId', r.canonical_card_id, 'cardName', cc.name, 'setId', r.set_id, 'setName', s.name,
          'cardNumber', cc.printed_number, 'rarity', cc.rarity, 'edition', cv.edition,
          'printingType', cv.printing_type, 'specialType', cv.special_type,
          'marketPrice', r.market_price, 'asOf', r.market_date)
      from (
        select q.*, row_number() over (order by q.market_price desc nulls last, q.card_variant_id)::integer as rank
        from public.get_pokemon_cards_daily_constituents(array[d.set_id], d.source_as_of, d.source_as_of, null::uuid[]) q
      ) r
      left join public.pokemon_canonical_cards cc on cc.id = r.canonical_card_id
      left join public.card_variants cv on cv.id = r.card_variant_id
      left join public.sets s on s.id = r.set_id;
      get diagnostics v_total = row_count;
      update public.pokemon_market_explorer_prepared_constituent_totals_v1
        set total_count = v_total, availability = case when v_total = 0 then 'empty' else 'available' end
        where generation_id = p_generation_id and market_key = d.market_key;
    elsif d.source_kind = 'prepared_sealed_snapshots' and d.market_type = 'prepared_format' and d.asset = 'sealed' then
      v_segment := v_snapshot.payload_json #> array['marketOverview','sealedSegments','segments',d.metadata->>'segmentKey','currentConstituents'];
      if v_snapshot.market_date is distinct from d.source_as_of or v_segment is null
         or v_segment->>'isComplete' <> 'true'
         or jsonb_array_length(v_segment->'topConstituents') <> (v_segment->>'totalCount')::integer then
        insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
          (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability, availability_reason)
        values (p_generation_id, d.market_key, 'sealed', d.source_kind, d.metadata->>'segmentContractVersion',
          d.source_as_of, 0, 'unavailable', 'Complete sealed roster was not available at publication');
      else
        v_total := (v_segment->>'totalCount')::integer;
        insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
          (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability)
        values (p_generation_id, d.market_key, 'sealed', d.source_kind, d.metadata->>'segmentContractVersion',
          d.source_as_of, v_total, case when v_total = 0 then 'empty' else 'available' end);
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id, market_key, rank, instrument_id, asset, market_price, price_as_of, item)
        select p_generation_id, d.market_key, e.ordinal::integer, e.value->>'sealedProductId', 'sealed',
          nullif(e.value->>'marketPrice','')::numeric, d.source_as_of, e.value
        from jsonb_array_elements(v_segment->'topConstituents') with ordinality as e(value, ordinal);
      end if;
    elsif d.source_kind = 'maintained_query_cache' then
      select * into v_cache from public.pokemon_market_explorer_query_cache where query_fingerprint = d.prepared_series_key;
      v_found := found;
      if d.metadata->>'queryFingerprint' is distinct from d.prepared_series_key or not v_found
         or v_cache.status <> 'ready' or v_cache.computed_through is distinct from d.source_as_of
         or v_cache.asset <> d.asset then
        insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
          (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability, availability_reason)
        values (p_generation_id, d.market_key, d.asset, d.source_kind, d.prepared_series_key, d.source_as_of, 0,
          'unavailable', 'Maintained roster did not match the published definition and date at publication');
      else
        insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
          (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability)
        values (p_generation_id, d.market_key, d.asset, d.source_kind, d.prepared_series_key, d.source_as_of,
          v_cache.constituent_count::integer, case when v_cache.constituent_count = 0 then 'empty' else 'available' end);
        insert into public.pokemon_market_explorer_prepared_constituents_v1
          (generation_id, market_key, rank, instrument_id, asset, market_price, price_as_of, item)
        select p_generation_id, d.market_key, x.rank,
          coalesce(x.item->>'cardVariantId', x.item->>'sealedProductId', x.item->>'instrumentId'), d.asset,
          nullif(x.item->>'marketPrice','')::numeric, d.source_as_of, x.item
        from public.pokemon_market_explorer_query_cache_constituents x where x.query_fingerprint = d.prepared_series_key;
      end if;
    else
      insert into public.pokemon_market_explorer_prepared_constituent_totals_v1
        (generation_id, market_key, asset, source_kind, definition_version, source_as_of, total_count, availability, availability_reason)
      values (p_generation_id, d.market_key, d.asset, d.source_kind, d.prepared_series_key, d.source_as_of, 0,
        'notApplicable', 'This prepared market has no enumerable constituent definition');
    end if;
    v_markets := v_markets + 1;
  end loop;

  -- Validate: every available/empty market has exactly total_count rows and contiguous ranks 1..n.
  select string_agg(t.market_key, ',') into v_bad
  from public.pokemon_market_explorer_prepared_constituent_totals_v1 t
  left join (select market_key, count(*) n, max(rank) mx, min(rank) mn
             from public.pokemon_market_explorer_prepared_constituents_v1
             where generation_id = p_generation_id group by market_key) c using (market_key)
  where t.generation_id = p_generation_id and t.availability in ('available','empty')
    and (coalesce(c.n,0) <> t.total_count or (t.total_count > 0 and (c.mx <> t.total_count or c.mn <> 1)));
  if v_bad is not null then
    raise exception 'PREPARED_CONSTITUENT_VALIDATION_FAILED: %', v_bad using errcode = 'P0001';
  end if;
  select count(*) into v_rows from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id = p_generation_id;
  return jsonb_build_object('generationId', p_generation_id, 'markets', v_markets, 'rows', v_rows);
end;
$function$;

revoke all on function public.stage_pokemon_market_explorer_prepared_constituents_v1(uuid) from public, anon, authenticated;
grant execute on function public.stage_pokemon_market_explorer_prepared_constituents_v1(uuid) to service_role;

create or replace function public.run_market_explorer_guarded_publisher_v1(p_required_market_date date)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_existing uuid;
  v_result jsonb;
  v_generation uuid;
  v_staged jsonb := null;
begin
  if p_required_market_date is null then
    raise exception 'required Market Explorer prepared market date must not be null';
  end if;

  select g.generation_id
    into v_existing
  from public.pokemon_market_explorer_prepared_serving_v1 p
  join public.pokemon_market_explorer_prepared_generations_v1 g
    on g.generation_id = p.generation_id
  join public.pokemon_explore_set_value_snapshot_latest s
    on s.tcg = 'pokemon' and s.scope = 'market'
  where g.comparison_as_of = p_required_market_date
    and g.source_as_of->>'sets' = s.market_date::text
    and g.source_as_of->>'sealed' = s.market_date::text
    and s.updated_at <= g.generated_at
    and not exists (
      select 1
      from public.pokemon_market_explorer_query_cache c
      where c.cache_kind = 'maintained'
        and c.last_built_at > g.generated_at
    )
    and not exists (
      select 1
      from public.pokemon_set_market_dashboard_snapshot_latest d
      where d.updated_at > g.generated_at
    )
    and not exists (
      select 1
      from public.pokemon_set_sealed_market_snapshot_latest d
      where d.updated_at > g.generated_at
    )
  limit 1;

  if v_existing is not null then
    v_generation := v_existing;

    -- Serialize the "check then stage" path so concurrent publisher calls do
    -- not both decide the same serving generation needs constituent staging.
    perform pg_advisory_xact_lock(hashtext(v_generation::text), 17341);

    if not exists (select 1 from public.pokemon_market_explorer_prepared_constituent_totals_v1
                   where generation_id = v_generation) then
      v_staged := public.stage_pokemon_market_explorer_prepared_constituents_v1(v_generation);
    end if;
    return jsonb_build_object(
      'status','already_current',
      'generationId',v_existing,
      'comparisonAsOf',p_required_market_date,
      'constituents',v_staged
    );
  end if;

  v_result := public.refresh_pokemon_market_explorer_prepared_if_current_v1(p_required_market_date);

  select generation_id into v_generation from public.pokemon_market_explorer_prepared_serving_v1 where singleton;
  if v_generation is not null then
    perform pg_advisory_xact_lock(hashtext(v_generation::text), 17341);
    if not exists (select 1 from public.pokemon_market_explorer_prepared_constituent_totals_v1
                   where generation_id = v_generation) then
      v_staged := public.stage_pokemon_market_explorer_prepared_constituents_v1(v_generation);
    end if;
  end if;

  return jsonb_build_object(
    'status','refreshed',
    'result',v_result,
    'constituents',v_staged
  );
end;
$function$;
