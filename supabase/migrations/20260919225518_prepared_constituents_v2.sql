-- Bounded prepared roster reads. All identities are pinned to the published
-- directory generation; a caller must restart paging after publication.
create or replace function public.get_pokemon_market_explorer_prepared_constituents_v2(
  p_market_key text, p_generation_id uuid, p_after_rank integer default 0,
  p_limit integer default 100
) returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare
  d public.pokemon_market_explorer_prepared_directory_v1%rowtype;
  c public.pokemon_market_explorer_query_cache%rowtype;
  v_snapshot record;
  v_segment jsonb;
  v_items jsonb := '[]'::jsonb;
  v_total integer := 0;
  v_next integer;
  v_count integer;
  v_availability text := 'available';
  v_reason text;
  v_definition text;
begin
  if p_market_key is null or p_market_key = '' or p_generation_id is null
     or p_after_rank is null or p_after_rank < 0 or p_limit is null or p_limit < 1 or p_limit > 100 then
    return jsonb_build_object('availability','unavailable','code','INVALID_CURSOR','availabilityReason','Invalid market identity, cursor, or page limit');
  end if;
  select * into d from public.pokemon_market_explorer_prepared_directory_v1 where market_key = p_market_key;
  if not found then
    return jsonb_build_object('availability','unavailable','code','UNKNOWN_MARKET','availabilityReason','Unknown prepared market');
  end if;
  if d.generation_id <> p_generation_id then
    return jsonb_build_object('marketKey',p_market_key,'generationId',d.generation_id,
      'availability','unavailable','code','GENERATION_MISMATCH','availabilityReason','Prepared generation changed; restart paging');
  end if;
  v_definition := coalesce(d.metadata->>'segmentContractVersion',d.metadata->>'queryFingerprint',d.prepared_series_key);
  if d.source_kind = 'maintained_query_cache' then
    select * into c from public.pokemon_market_explorer_query_cache
      where query_fingerprint = d.prepared_series_key;
    if d.metadata->>'queryFingerprint' is distinct from d.prepared_series_key
       or not found or c.status <> 'ready' or c.computed_through is distinct from d.source_as_of
       or c.last_built_at > d.generated_at or c.asset <> d.asset then
      v_availability := 'unavailable';
      v_reason := 'Maintained roster does not match the published definition and date';
    else
      v_total := c.constituent_count::integer;
      select coalesce(jsonb_agg(item order by rank), '[]'::jsonb) into v_items
      from (select x.rank,x.item from public.pokemon_market_explorer_query_cache_constituents x
        where x.query_fingerprint = d.prepared_series_key and x.rank > p_after_rank
        order by x.rank limit p_limit) page;
    end if;
  elsif d.source_kind = 'public_set_snapshot' and d.market_type = 'set' and d.asset = 'cards' then
    if d.set_id is null then
      v_availability := 'unavailable'; v_reason := 'Prepared Set has no root identity';
    else
      -- The accepted reader resolves ordinary, composite, and mixed-provenance
      -- roots. Never infer membership using cards.set_id = root_id.
      with roster as materialized (
        select r.*, row_number() over (order by r.market_price desc nulls last, r.card_variant_id) as rank
        from public.get_pokemon_cards_daily_constituents(array[d.set_id], d.source_as_of, d.source_as_of, null::uuid[]) r
      ), numbered as (
        select r.rank, jsonb_build_object(
          'rank',r.rank,'instrumentId',r.card_variant_id,'cardVariantId',r.card_variant_id,
          'canonicalCardId',r.canonical_card_id,'cardName',cc.name,'setId',r.set_id,
          'setName',s.name,'cardNumber',cc.printed_number,'rarity',cc.rarity,
          'edition',cv.edition,'printingType',cv.printing_type,'specialType',cv.special_type,
          'marketPrice',r.market_price,'asOf',r.market_date) as item
        from roster r
        left join public.pokemon_canonical_cards cc on cc.id = r.canonical_card_id
        left join public.card_variants cv on cv.id = r.card_variant_id
        left join public.sets s on s.id = r.set_id
      )
      select (select count(*) from roster),
        (select coalesce(jsonb_agg(item order by rank),'[]'::jsonb) from
          (select rank,item from numbered where rank > p_after_rank order by rank limit p_limit) page)
      into v_total,v_items;
    end if;
  elsif d.source_kind = 'prepared_sealed_snapshots' and d.market_type = 'prepared_format' and d.asset = 'sealed' then
    select market_date,updated_at,payload_json into v_snapshot
    from public.pokemon_explore_set_value_snapshot_latest
    where tcg = 'pokemon' and scope = 'market';
    v_segment := v_snapshot.payload_json #> array['marketOverview','sealedSegments','segments',d.metadata->>'segmentKey','currentConstituents'];
    if v_snapshot.market_date is distinct from d.source_as_of or v_snapshot.updated_at > d.generated_at
       or v_segment is null or v_segment->>'isComplete' <> 'true' then
      v_availability := 'unavailable'; v_reason := 'Complete sealed roster is unavailable for this generation';
    else
      v_total := (v_segment->>'totalCount')::integer;
      select coalesce(jsonb_agg(value order by ordinal),'[]'::jsonb) into v_items
      from (select value,ordinal from jsonb_array_elements(v_segment->'topConstituents') with ordinality as e(value,ordinal)
        where ordinal > p_after_rank order by ordinal limit p_limit) page;
      if jsonb_array_length(v_segment->'topConstituents') <> v_total then
        v_availability := 'unavailable'; v_reason := 'Sealed roster is incomplete'; v_items := '[]'::jsonb;
      end if;
    end if;
  else
    v_availability := 'notApplicable'; v_reason := 'This prepared market has no enumerable constituent definition';
  end if;
  v_count := jsonb_array_length(v_items);
  if v_availability = 'available' and v_total = 0 then v_availability := 'empty'; end if;
  if v_availability = 'available' and p_after_rank > v_total then
    return jsonb_build_object('marketKey',p_market_key,'generationId',d.generation_id,
      'availability','unavailable','code','INVALID_CURSOR','availabilityReason','Cursor exceeds roster');
  end if;
  if v_availability = 'available' and p_after_rank + v_count < v_total then
    v_next := p_after_rank + v_count;
  end if;
  return jsonb_build_object('marketKey',d.market_key,'generationId',d.generation_id,
    'sourceKind',d.source_kind,'definitionVersion',v_definition,'asset',d.asset,
    'membershipAsOf',d.source_as_of,'priceAsOf',d.source_as_of,
    'totalCount',v_total,'returnedCount',v_count,'hasMore',v_next is not null,
    'nextCursor',v_next,'availability',v_availability,'availabilityReason',v_reason,
    'rows',v_items);
end;
$$;
revoke all on function public.get_pokemon_market_explorer_prepared_constituents_v2(text,uuid,integer,integer) from public, anon, authenticated;
grant execute on function public.get_pokemon_market_explorer_prepared_constituents_v2(text,uuid,integer,integer) to service_role;
