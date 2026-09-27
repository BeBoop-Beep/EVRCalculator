do $guard$
begin
  if md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[])'::regprocedure)) <> '8e5fdc6a64876a38614136a8f3273a63' then
    raise exception 'public Cards constituent reader changed since V4 validation; refusing cutover';
  end if;
  if md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v4_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'baaa0f87ee4296b5ca1eb297f995fb36' then
    raise exception 'validated V4 shadow definition changed; refusing cutover';
  end if;
end;
$guard$;

create or replace function public.get_pokemon_cards_daily_constituents(
  p_set_ids uuid[],
  p_start_date date,
  p_end_date date,
  p_card_ids uuid[] default null::uuid[]
)
returns table(
  canonical_card_id uuid,
  set_id uuid,
  market_date date,
  market_price numeric,
  card_variant_id uuid,
  source text,
  captured_at date
)
language sql
stable
security invoker
set search_path=''
set "TimeZone"='America/Phoenix'
as $function$
  select *
  from public.get_pokemon_cards_daily_constituents_v4_shadow(
    p_set_ids,p_start_date,p_end_date,p_card_ids
  );
$function$;

revoke all on function public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) from public,anon,authenticated;
grant execute on function public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) to postgres,service_role;
comment on function public.get_pokemon_cards_daily_constituents(uuid[],date,date,uuid[]) is
'Canonical reusable card-day constituent authority. Routing follows persisted standard Set Value provenance per requested root/day. Canonical-root dates use the canonical root+eligible-subset as-of authority; legacy-compatible dates preserve prior semantics but are internally split into <=3-day per-root ranges to avoid statement-timeout pathologies. Service-role only.';
