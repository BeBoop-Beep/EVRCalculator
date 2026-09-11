create or replace function public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text default 'all',
  p_limit integer default 20
)
returns table(
  asset text,
  instrument_id uuid,
  name text,
  set_id uuid,
  set_name text,
  image_url text,
  card_number text,
  rarity text,
  edition text,
  printing_type text,
  special_type text,
  product_family text,
  variant_label text,
  match_kind text,
  relevance_score integer,
  name_similarity real
)
language plpgsql
stable
security invoker
set search_path = ''
set statement_timeout = '1s'
set work_mem = '16MB'
as $function$
declare
  v_asset text := pg_catalog.lower(pg_catalog.btrim(coalesce(p_asset, 'all')));
  v_limit integer := least(greatest(coalesce(p_limit, 20), 1), 50);
  v_norm_query text;
  v_tokens text[];
  v_exact_tsquery tsquery;
  v_prefix_tsquery tsquery;
  v_token_count integer;
  v_fuzzy_enabled boolean;
  v_fuzzy_threshold real;
begin
  if v_asset not in ('all', 'cards', 'sealed') then
    raise exception 'p_asset must be all, cards, or sealed'
      using errcode = '22023';
  end if;

  v_norm_query := public.normalize_pokemon_market_explorer_search_text_v2(coalesce(p_query, ''));
  if v_norm_query is null or pg_catalog.length(v_norm_query) < 2 then
    return;
  end if;

  v_norm_query := public.normalize_pokemon_market_explorer_search_text_v2(
    pg_catalog.regexp_replace(
      ' ' || v_norm_query || ' ',
      ' etb ',
      ' elite trainer box ',
      'g'
    )
  );

  v_tokens := pg_catalog.regexp_split_to_array(v_norm_query, ' +');
  v_token_count := coalesce(pg_catalog.array_length(v_tokens, 1), 0);
  if v_token_count = 0 then
    return;
  end if;

  v_exact_tsquery := pg_catalog.to_tsquery(
    'simple'::regconfig,
    pg_catalog.array_to_string(v_tokens, ' & ')
  );

  select pg_catalog.to_tsquery(
           'simple'::regconfig,
           pg_catalog.string_agg(t.token || ':*', ' & ' order by t.ord)
         )
    into v_prefix_tsquery
  from pg_catalog.unnest(v_tokens) with ordinality as t(token, ord);

  v_fuzzy_enabled := (
    v_token_count = 1
    and pg_catalog.length(v_norm_query) >= 4
    and v_norm_query ~ '[a-z]'
  );

  v_fuzzy_threshold := case
    when pg_catalog.length(v_norm_query) >= 8 then 0.42::real
    when pg_catalog.length(v_norm_query) >= 6 then 0.50::real
    else 0.60::real
  end;

  return query
  with query_tokens as (
    select t.token, t.ord
    from pg_catalog.unnest(v_tokens) with ordinality as t(token, ord)
  ),
  card_direct as (
    select m.card_variant_id
    from public.pokemon_market_explorer_card_current_metadata m
    where v_asset in ('all', 'cards')
      and pg_catalog.to_tsvector(
            'simple'::regconfig,
            public.normalize_pokemon_market_explorer_search_text_v2(
              coalesce(m.card_name, '') || ' ' ||
              coalesce(m.rarity, '') || ' ' ||
              coalesce(m.edition, '') || ' ' ||
              coalesce(m.printing_type, '') || ' ' ||
              coalesce(m.special_type, '')
            )
          ) @@ v_prefix_tsquery
  ),
  set_token_matches as (
    select
      s.id as set_id,
      s.name as set_name,
      qt.token,
      qt.ord,
      (
        pg_catalog.to_tsvector(
          'simple'::regconfig,
          public.normalize_pokemon_market_explorer_search_text_v2(s.name)
        ) @@ pg_catalog.to_tsquery('simple'::regconfig, qt.token || ':*')
      ) as token_matches_set
    from public.sets s
    cross join query_tokens qt
    where v_asset in ('all', 'cards')
  ),
  set_routes as (
    select
      stm.set_id,
      stm.set_name,
      pg_catalog.array_agg(stm.token order by stm.ord)
        filter (where not stm.token_matches_set) as remaining_tokens,
      count(*) filter (where stm.token_matches_set) as matched_set_tokens
    from set_token_matches stm
    group by stm.set_id, stm.set_name
    having count(*) filter (where stm.token_matches_set) > 0
  ),
  set_routes_ready as (
    select
      sr.set_id,
      sr.set_name,
      case
        when coalesce(pg_catalog.cardinality(sr.remaining_tokens), 0) = 0 then null::tsquery
        else pg_catalog.to_tsquery(
          'simple'::regconfig,
          (
            select pg_catalog.string_agg(x.token || ':*', ' & ' order by x.ord)
            from pg_catalog.unnest(sr.remaining_tokens) with ordinality as x(token, ord)
          )
        )
      end as remaining_query
    from set_routes sr
  ),
  card_context as (
    select m.card_variant_id
    from set_routes_ready sr
    join public.pokemon_market_explorer_card_current_metadata m
      on m.set_id = sr.set_id
    where sr.remaining_query is null
       or pg_catalog.to_tsvector(
            'simple'::regconfig,
            public.normalize_pokemon_market_explorer_search_text_v2(
              coalesce(m.card_name, '') || ' ' ||
              coalesce(m.rarity, '') || ' ' ||
              coalesce(m.edition, '') || ' ' ||
              coalesce(m.printing_type, '') || ' ' ||
              coalesce(m.special_type, '')
            )
          ) @@ sr.remaining_query
  ),
  card_collector as (
    select m.card_variant_id
    from public.pokemon_market_explorer_card_current_metadata m
    where v_asset in ('all', 'cards')
      and pg_catalog.lower(pg_catalog.btrim(coalesce(m.card_number, '')))
          = pg_catalog.lower(pg_catalog.btrim(coalesce(p_query, '')))
  ),
  card_fuzzy as (
    select m.card_variant_id
    from public.pokemon_market_explorer_card_current_metadata m
    where v_asset in ('all', 'cards')
      and v_fuzzy_enabled
      and public.normalize_pokemon_market_explorer_search_text_v2(m.card_name)
            operator(extensions.%) v_norm_query
      and extensions.similarity(
            public.normalize_pokemon_market_explorer_search_text_v2(m.card_name),
            v_norm_query
          ) >= v_fuzzy_threshold
  ),
  card_candidate_ids as (
    select card_variant_id from card_direct
    union
    select card_variant_id from card_context
    union
    select card_variant_id from card_collector
    union
    select card_variant_id from card_fuzzy
  ),
  card_features as (
    select
      'cards'::text as asset,
      m.card_variant_id as instrument_id,
      m.card_name as name,
      m.set_id,
      s.name as set_name,
      m.image_url,
      m.card_number,
      m.rarity,
      m.edition,
      m.printing_type,
      m.special_type,
      null::text as product_family,
      null::text as variant_label,
      d.norm_name,
      pg_catalog.to_tsvector('simple'::regconfig, d.norm_name) as name_vector,
      pg_catalog.to_tsvector(
        'simple'::regconfig,
        public.normalize_pokemon_market_explorer_search_text_v2(m.card_name || ' ' || s.name)
      ) as name_set_vector,
      pg_catalog.to_tsvector(
        'simple'::regconfig,
        public.normalize_pokemon_market_explorer_search_text_v2(
          coalesce(m.card_name, '') || ' ' ||
          coalesce(s.name, '') || ' ' ||
          coalesce(m.rarity, '') || ' ' ||
          coalesce(m.edition, '') || ' ' ||
          coalesce(m.printing_type, '') || ' ' ||
          coalesce(m.special_type, '')
        )
      ) as full_vector,
      extensions.similarity(d.norm_name, v_norm_query) as similarity_score
    from card_candidate_ids c
    join public.pokemon_market_explorer_card_current_metadata m
      on m.card_variant_id = c.card_variant_id
    join public.sets s on s.id = m.set_id
    cross join lateral (
      select public.normalize_pokemon_market_explorer_search_text_v2(m.card_name) as norm_name
    ) d
  ),
  card_scored as (
    select
      cf.asset,
      cf.instrument_id,
      cf.name,
      cf.set_id,
      cf.set_name,
      cf.image_url,
      cf.card_number,
      cf.rarity,
      cf.edition,
      cf.printing_type,
      cf.special_type,
      cf.product_family,
      cf.variant_label,
      case
        when cf.norm_name = v_norm_query then 'exact_name'
        when cf.name_vector @@ v_exact_tsquery then 'name_tokens'
        when cf.name_vector @@ v_prefix_tsquery then 'name_prefix'
        when cf.name_set_vector @@ v_prefix_tsquery then 'name_set_context'
        when pg_catalog.lower(pg_catalog.btrim(coalesce(cf.card_number, '')))
             = pg_catalog.lower(pg_catalog.btrim(coalesce(p_query, ''))) then 'collector_number'
        when v_fuzzy_enabled and cf.similarity_score >= v_fuzzy_threshold then 'fuzzy_name'
        else 'metadata'
      end as match_kind,
      case
        when cf.norm_name = v_norm_query then 100000
        when cf.name_vector @@ v_exact_tsquery then 90000
        when cf.name_vector @@ v_prefix_tsquery then 85000
        when cf.name_set_vector @@ v_prefix_tsquery then 76000
        when pg_catalog.lower(pg_catalog.btrim(coalesce(cf.card_number, '')))
             = pg_catalog.lower(pg_catalog.btrim(coalesce(p_query, ''))) then 72000
        when v_fuzzy_enabled and cf.similarity_score >= v_fuzzy_threshold
          then 50000 + pg_catalog.floor(cf.similarity_score * 1000)::integer
        else 30000
      end as relevance_score,
      cf.similarity_score::real as name_similarity
    from card_features cf
    where cf.full_vector @@ v_prefix_tsquery
       or pg_catalog.lower(pg_catalog.btrim(coalesce(cf.card_number, '')))
          = pg_catalog.lower(pg_catalog.btrim(coalesce(p_query, '')))
       or (v_fuzzy_enabled and cf.similarity_score >= v_fuzzy_threshold)
  ),
  sealed_raw as (
    select
      nullif(product.item->>'sealedProductId', '')::uuid as instrument_id,
      coalesce(nullif(product.item->>'name', ''), sp.name) as name,
      snapshot.set_id,
      coalesce(s.name, snapshot.payload_json->'set'->>'name') as set_name,
      coalesce(sp.image_small_url, sp.image_large_url) as image_url,
      coalesce(nullif(product.item->>'productFamily', ''), sp.product_type) as product_family,
      nullif(product.item->>'variantLabel', '') as variant_label,
      nullif(product.item->>'productFamilyLabel', '') as product_family_label,
      sp.product_type,
      snapshot.market_date
    from public.pokemon_set_sealed_market_snapshot_latest snapshot
    cross join lateral pg_catalog.jsonb_array_elements(
      coalesce(snapshot.payload_json->'products', '[]'::jsonb)
    ) product(item)
    left join public.sealed_products sp
      on sp.id = nullif(product.item->>'sealedProductId', '')::uuid
    left join public.sets s on s.id = snapshot.set_id
    where v_asset in ('all', 'sealed')
      and snapshot.tcg = 'pokemon'
      and nullif(product.item->>'sealedProductId', '') is not null
  ),
  sealed_base as (
    select distinct on (sr.instrument_id)
      sr.instrument_id,
      sr.name,
      sr.set_id,
      sr.set_name,
      sr.image_url,
      sr.product_family,
      sr.variant_label,
      sr.product_family_label,
      sr.product_type
    from sealed_raw sr
    order by sr.instrument_id, sr.market_date desc nulls last, sr.set_id
  ),
  sealed_features as (
    select
      'sealed'::text as asset,
      sb.instrument_id,
      sb.name,
      sb.set_id,
      sb.set_name,
      sb.image_url,
      null::text as card_number,
      null::text as rarity,
      null::text as edition,
      null::text as printing_type,
      null::text as special_type,
      sb.product_family,
      sb.variant_label,
      d.norm_name,
      pg_catalog.to_tsvector('simple'::regconfig, d.norm_name) as name_vector,
      pg_catalog.to_tsvector(
        'simple'::regconfig,
        public.normalize_pokemon_market_explorer_search_text_v2(
          coalesce(sb.name, '') || ' ' || coalesce(sb.set_name, '')
        )
      ) as name_set_vector,
      pg_catalog.to_tsvector(
        'simple'::regconfig,
        public.normalize_pokemon_market_explorer_search_text_v2(
          coalesce(sb.name, '') || ' ' ||
          coalesce(sb.set_name, '') || ' ' ||
          coalesce(sb.product_family, '') || ' ' ||
          coalesce(sb.product_family_label, '') || ' ' ||
          coalesce(sb.product_type, '') || ' ' ||
          coalesce(sb.variant_label, '')
        )
      ) as full_vector,
      extensions.word_similarity(v_norm_query, d.norm_name) as similarity_score
    from sealed_base sb
    cross join lateral (
      select public.normalize_pokemon_market_explorer_search_text_v2(coalesce(sb.name, '')) as norm_name
    ) d
  ),
  sealed_scored as (
    select
      sf.asset,
      sf.instrument_id,
      sf.name,
      sf.set_id,
      sf.set_name,
      sf.image_url,
      sf.card_number,
      sf.rarity,
      sf.edition,
      sf.printing_type,
      sf.special_type,
      sf.product_family,
      sf.variant_label,
      case
        when sf.norm_name = v_norm_query then 'exact_name'
        when sf.name_vector @@ v_exact_tsquery then 'name_tokens'
        when sf.name_vector @@ v_prefix_tsquery then 'name_prefix'
        when sf.name_set_vector @@ v_prefix_tsquery then 'name_set_context'
        when v_fuzzy_enabled and sf.similarity_score >= v_fuzzy_threshold then 'fuzzy_name'
        else 'metadata'
      end as match_kind,
      case
        when sf.norm_name = v_norm_query then 100000
        when sf.name_vector @@ v_exact_tsquery then 90000
        when sf.name_vector @@ v_prefix_tsquery then 85000
        when sf.name_set_vector @@ v_prefix_tsquery then 76000
        when v_fuzzy_enabled and sf.similarity_score >= v_fuzzy_threshold
          then 50000 + pg_catalog.floor(sf.similarity_score * 1000)::integer
        else 30000
      end as relevance_score,
      sf.similarity_score::real as name_similarity
    from sealed_features sf
    where sf.full_vector @@ v_prefix_tsquery
       or (v_fuzzy_enabled and sf.similarity_score >= v_fuzzy_threshold)
  ),
  combined as (
    select * from card_scored
    union all
    select * from sealed_scored
  )
  select
    c.asset,
    c.instrument_id,
    c.name,
    c.set_id,
    c.set_name,
    c.image_url,
    c.card_number,
    c.rarity,
    c.edition,
    c.printing_type,
    c.special_type,
    c.product_family,
    c.variant_label,
    c.match_kind,
    c.relevance_score,
    c.name_similarity
  from combined c
  order by
    c.relevance_score desc,
    case when c.match_kind = 'fuzzy_name' then c.name_similarity else 0::real end desc,
    pg_catalog.lower(c.name),
    pg_catalog.lower(coalesce(c.set_name, '')),
    c.asset,
    c.instrument_id
  limit v_limit;
end
$function$;

revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
from public, anon, authenticated;
grant execute on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
to service_role;

comment on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer) is
'Market Explorer Phase 2 canonical bounded leaf-instrument search. Searches only existing Exact-eligible card metadata and sealed snapshot products; token order is insensitive, prefixes are supported, ETB is expanded to Elite Trainer Box, and single-token primary-name typos use bounded pg_trgm fuzzy matching. Service-role only.';
