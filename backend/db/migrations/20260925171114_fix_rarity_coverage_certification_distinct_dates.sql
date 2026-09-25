begin;

-- Certification is date-grained. pokemon_market_date_quality may contain more
-- than one accepted row for the same calendar date, so compare distinct dates
-- to the distinct materialized coverage dates.
create or replace function public.certify_pokemon_market_explorer_rarity_coverage_v1(
  p_through date
)
returns jsonb
language plpgsql
volatile
security invoker
set search_path = ''
set statement_timeout = '5s'
set lock_timeout = '1s'
set jit = 'off'
as $function$
declare
  v_from date;
  v_expected integer;
  v_materialized integer;
  v_missing integer;
begin
  if p_through is null then
    raise exception 'RARITY_COVERAGE_CERTIFICATION_DATE_REQUIRED';
  end if;

  select min(d.market_date)
  into v_from
  from public.pokemon_market_explorer_card_daily_states_v2_shadow d
  where d.market_date<=p_through;

  if v_from is null then
    raise exception 'RARITY_COVERAGE_SOURCE_EMPTY';
  end if;

  select count(distinct q.market_date)::integer
  into v_expected
  from public.pokemon_market_date_quality q
  where q.tcg='pokemon'
    and q.status in ('READY','LEGACY_VERIFIED')
    and q.market_date between v_from and p_through;

  select count(distinct c.market_date)::integer
  into v_materialized
  from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
  join public.pokemon_market_date_quality q
    on q.tcg='pokemon' and q.market_date=c.market_date
   and q.status in ('READY','LEGACY_VERIFIED')
  where c.market_date between v_from and p_through;

  select count(*)::integer
  into v_missing
  from public.pokemon_market_date_quality q
  where q.tcg='pokemon'
    and q.status in ('READY','LEGACY_VERIFIED')
    and q.market_date between v_from and p_through
    and not exists (
      select 1
      from public.pokemon_market_explorer_rarity_daily_coverage_v1 c
      where c.market_date=q.market_date
    );

  if v_missing>0 or v_materialized<>v_expected then
    raise exception 'RARITY_COVERAGE_INCOMPLETE: missing % accepted dates (% materialized / % expected)',
      v_missing,v_materialized,v_expected;
  end if;

  insert into public.pokemon_market_explorer_rarity_coverage_certification_v1(
    singleton,source_from,certified_through,accepted_date_count,certified_at
  ) values (
    true,v_from,p_through,v_expected,clock_timestamp()
  )
  on conflict(singleton) do update
  set source_from=excluded.source_from,
      certified_through=excluded.certified_through,
      accepted_date_count=excluded.accepted_date_count,
      certified_at=excluded.certified_at;

  return jsonb_build_object(
    'status','CERTIFIED',
    'sourceFrom',v_from,
    'certifiedThrough',p_through,
    'acceptedDateCount',v_expected
  );
end;
$function$;

revoke all on function public.certify_pokemon_market_explorer_rarity_coverage_v1(date)
from public,anon,authenticated;
grant execute on function public.certify_pokemon_market_explorer_rarity_coverage_v1(date)
to service_role;


commit;
