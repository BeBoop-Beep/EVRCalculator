alter function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
  rename to search_pokemon_market_explorer_instruments_v2_unfiltered_phase2;

revoke all on function public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(text,text,integer) from public;
revoke all on function public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(text,text,integer) from anon;
revoke all on function public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(text,text,integer) from authenticated;
grant execute on function public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(text,text,integer) to service_role;

create function public.search_pokemon_market_explorer_instruments_v2(
  p_query text,
  p_asset text default 'all'::text,
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
language sql
stable
security invoker
set search_path to ''
set statement_timeout to '1s'
set work_mem to '16MB'
as $function$
with latest as materialized (
  select max(q.market_date) as market_date
  from public.pokemon_market_date_quality q
  where q.tcg = 'pokemon'
    and q.status in ('READY','LEGACY_VERIFIED')
),
base as materialized (
  select *
  from public.search_pokemon_market_explorer_instruments_v2_unfiltered_phase2(
    p_query,
    p_asset,
    50
  )
),
eligible as (
  select b.*
  from base b
  cross join latest l
  where (
    b.asset = 'cards'
    and exists (
      select 1
      from public.pokemon_market_explorer_card_daily_states_v2_shadow d
      where d.card_variant_id = b.instrument_id
        and d.market_date = l.market_date
        and d.market_price > 0
    )
  ) or (
    b.asset = 'sealed'
    and exists (
      select 1
      from public.pokemon_set_sealed_market_snapshot_latest snap
      cross join lateral pg_catalog.jsonb_array_elements(
        coalesce(snap.payload_json->'products','[]'::jsonb)
      ) p(item)
      where snap.tcg = 'pokemon'
        and snap.set_id = b.set_id
        and nullif(p.item->>'sealedProductId','')::uuid = b.instrument_id
        and coalesce((p.item->>'currentPrice')::numeric,0) > 0
        and exists (
          select 1
          from pg_catalog.jsonb_array_elements(coalesce(p.item->'history','[]'::jsonb)) h(item)
          where coalesce((h.item->>'marketPrice')::numeric,0) > 0
        )
    )
  )
)
select
  e.asset, e.instrument_id, e.name, e.set_id, e.set_name, e.image_url,
  e.card_number, e.rarity, e.edition, e.printing_type, e.special_type,
  e.product_family, e.variant_label, e.match_kind, e.relevance_score,
  e.name_similarity
from eligible e
order by
  e.relevance_score desc,
  case when e.match_kind = 'fuzzy_name' then e.name_similarity else 0::real end desc,
  pg_catalog.lower(e.name),
  pg_catalog.lower(coalesce(e.set_name,'')),
  e.asset,
  e.instrument_id
limit least(greatest(coalesce(p_limit,20),1),50)
$function$;

comment on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer)
is 'Canonical Phase-2 Exact Basket discovery authority. Preserves search ranking but only returns leaf IDs executable by Exact Basket: Cards require a positive price on the latest approved market date; Sealed products require a positive prepared current price and non-empty positive prepared history.';

revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer) from public;
revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer) from anon;
revoke all on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer) from authenticated;
grant execute on function public.search_pokemon_market_explorer_instruments_v2(text,text,integer) to service_role;
