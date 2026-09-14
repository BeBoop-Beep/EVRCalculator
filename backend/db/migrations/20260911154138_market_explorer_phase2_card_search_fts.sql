create or replace function public.normalize_pokemon_market_explorer_search_text_v2(p_text text)
returns text
language sql
immutable
strict
security invoker
set search_path = ''
as $function$
  select pg_catalog.btrim(
    pg_catalog.regexp_replace(
      pg_catalog.translate(pg_catalog.lower(p_text), 'é', 'e'),
      '[^a-z0-9]+',
      ' ',
      'g'
    )
  )
$function$;

revoke all on function public.normalize_pokemon_market_explorer_search_text_v2(text)
from public, anon, authenticated;
grant execute on function public.normalize_pokemon_market_explorer_search_text_v2(text)
to service_role;

create index idx_pokemon_market_explorer_card_search_fts_v2
on public.pokemon_market_explorer_card_current_metadata
using gin (
  to_tsvector(
    'simple'::regconfig,
    public.normalize_pokemon_market_explorer_search_text_v2(
      coalesce(card_name,'') || ' ' ||
      coalesce(rarity,'') || ' ' ||
      coalesce(edition,'') || ' ' ||
      coalesce(printing_type,'') || ' ' ||
      coalesce(special_type,'')
    )
  )
);
