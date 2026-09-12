create function public.search_pokemon_sitewide_instruments_v1(
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
  name_similarity real,
  canonical_card_id uuid
)
language sql
stable
security invoker
set search_path to ''
set statement_timeout to '1s'
set work_mem to '16MB'
as $function$
with ranked as materialized (
  select *
  from public.search_pokemon_market_explorer_instruments_v2(
    p_query,
    p_asset,
    p_limit
  )
)
select
  r.asset,
  r.instrument_id,
  r.name,
  r.set_id,
  r.set_name,
  r.image_url,
  r.card_number,
  r.rarity,
  r.edition,
  r.printing_type,
  r.special_type,
  r.product_family,
  r.variant_label,
  r.match_kind,
  r.relevance_score,
  r.name_similarity,
  case when r.asset = 'cards' then m.canonical_card_id else null::uuid end
from ranked r
left join public.pokemon_market_explorer_card_current_metadata m
  on r.asset = 'cards'
 and m.card_variant_id = r.instrument_id
order by
  r.relevance_score desc,
  case when r.match_kind = 'fuzzy_name' then r.name_similarity else 0::real end desc,
  pg_catalog.lower(r.name),
  pg_catalog.lower(coalesce(r.set_name,'')),
  r.asset,
  r.instrument_id
limit least(greatest(coalesce(p_limit,20),1),50)
$function$;

comment on function public.search_pokemon_sitewide_instruments_v1(text,text,integer)
is 'Sitewide navigation companion for canonical V2 discovery. Preserves V2 eligibility/ranking and adds canonical card route identity in the same database round trip.';

revoke all on function public.search_pokemon_sitewide_instruments_v1(text,text,integer)
from public, anon, authenticated;
grant execute on function public.search_pokemon_sitewide_instruments_v1(text,text,integer)
to service_role;
