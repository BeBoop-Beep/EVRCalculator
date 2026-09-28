begin;

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_surface_freshness_v2()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET statement_timeout TO '3s'
AS $function$
with dates as (
  select
    (select max(q.market_date) from public.pokemon_market_date_quality q
      where q.tcg='pokemon' and q.status in ('READY','LEGACY_VERIFIED')) canonical_date,
    (select max(h.market_date) from public.pokemon_market_index_daily_history h
      where h.tcg='pokemon' and h.index_key='raw') raw_date,
    (select max(d.market_date) from public.pokemon_market_explorer_card_daily_states_v2_shadow d) card_date,
    (select max(d.market_date) from public.pokemon_market_explorer_sealed_daily_v1 d) sealed_date,
    (select max(m.latest_market_date) from public.pokemon_market_explorer_sealed_current_metadata_v1 m) sealed_metadata_date,
    (select g.comparison_as_of
       from public.pokemon_market_explorer_prepared_serving_v1 s
       join public.pokemon_market_explorer_prepared_generations_v1 g on g.generation_id=s.generation_id
       where s.singleton limit 1) prepared_v1_date,
    (select g.comparison_as_of
       from public.pokemon_market_explorer_surface_serving_v2 s
       join public.pokemon_market_explorer_surface_generations_v2 g on g.generation_id=s.generation_id
       where s.singleton=1 limit 1) surface_v2_date
), cache as (
  select
    count(*) filter(where q.cache_kind='maintained')::integer maintained_total,
    count(*) filter(where q.cache_kind='maintained' and q.status='ready'
      and q.computed_through=(select canonical_date from dates))::integer maintained_current,
    count(*) filter(where q.cache_kind='maintained' and (
      q.status<>'ready' or q.computed_through is distinct from (select canonical_date from dates)
    ))::integer maintained_not_current
  from public.pokemon_market_explorer_query_cache q
)
select jsonb_build_object(
  'status',case
    when d.surface_v2_date=d.canonical_date then 'CURRENT'
    when d.canonical_date is null then 'NO_ACCEPTED_MARKET_DATE'
    else 'STALE'
  end,
  'canonicalAcceptedDate',d.canonical_date,
  'rawDate',d.raw_date,
  'cardDailyDate',d.card_date,
  'sealedDailyDate',d.sealed_date,
  'sealedMetadataDate',d.sealed_metadata_date,
  'preparedV1Date',d.prepared_v1_date,
  'surfaceV2Date',d.surface_v2_date,
  'maintainedCacheTotal',c.maintained_total,
  'maintainedCacheCurrent',c.maintained_current,
  'maintainedCacheNotCurrent',c.maintained_not_current,
  'surfaceLagDays',case when d.canonical_date is not null and d.surface_v2_date is not null
    then d.canonical_date-d.surface_v2_date end,
  'reason',case
    when d.surface_v2_date=d.canonical_date then null
    when d.card_date is distinct from d.canonical_date then 'CARD_DAILY_NOT_CURRENT'
    when d.sealed_date is distinct from d.canonical_date then 'SEALED_DAILY_NOT_CURRENT'
    when d.sealed_metadata_date is distinct from d.canonical_date then 'SEALED_METADATA_NOT_CURRENT'
    when d.prepared_v1_date is distinct from d.canonical_date then 'PREPARED_V1_CONVERGENCE_LAG'
    else 'SURFACE_V2_PUBLICATION_LAG'
  end
)
from dates d cross join cache c;
$function$
;

CREATE OR REPLACE FUNCTION public.audit_pokemon_market_explorer_sealed_set_parity_v1(p_generation_id uuid DEFAULT NULL::uuid, p_market_date date DEFAULT NULL::date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET statement_timeout TO '5s'
AS $function$
declare
  v_generation uuid;
  v_date date;
  v_missing integer;
  v_extra integer;
  v_value_mismatches integer;
  v_expected_rows integer;
  v_actual_rows integer;
  v_expected_sets integer;
  v_actual_sets integer;
begin
  v_generation:=p_generation_id;
  if v_generation is null then
    select s.generation_id into v_generation
    from public.pokemon_market_explorer_surface_serving_v2 s
    where s.singleton=1;
  end if;

  if v_generation is null then
    raise exception 'SEALED_SET_PARITY_GENERATION_REQUIRED';
  end if;

  select coalesce(p_market_date,g.comparison_as_of)
  into v_date
  from public.pokemon_market_explorer_surface_generations_v2 g
  where g.generation_id=v_generation;

  if v_date is null then
    raise exception 'SEALED_SET_PARITY_MARKET_DATE_REQUIRED';
  end if;

  with expected as materialized (
    select m.set_id,m.sealed_product_id,m.latest_market_price
    from public.pokemon_market_explorer_sealed_current_metadata_v1 m
    where m.parent_membership
      and not m.is_bulk_container
      and m.set_id is not null
      and m.latest_market_price>0
      and m.latest_market_date>=v_date-30
  ), actual as materialized (
    select c.set_id,c.market_key,c.instrument_id sealed_product_id,c.market_price
    from public.pokemon_market_explorer_surface_constituents_v2 c
    join public.pokemon_market_explorer_surface_directory_v2 d
      on d.generation_id=c.generation_id and d.market_key=c.market_key
    where c.generation_id=v_generation
      and c.asset='sealed'
      and d.scope_kind='set'
  ), actual_sums as materialized (
    select market_key,count(*)::integer n,round(sum(market_price),2) v
    from actual
    group by market_key
  )
  select
    (select count(*) from expected e
      where not exists (
        select 1 from actual a
        where a.set_id=e.set_id and a.sealed_product_id=e.sealed_product_id
      )),
    (select count(*) from actual a
      where not exists (
        select 1 from expected e
        where e.set_id=a.set_id and e.sealed_product_id=a.sealed_product_id
      )),
    (select count(*) from public.pokemon_market_explorer_surface_directory_v2 d
      join actual_sums s on s.market_key=d.market_key
      where d.generation_id=v_generation
        and d.asset='sealed'
        and d.scope_kind='set'
        and (
          d.constituent_count is distinct from s.n
          or round(d.current_tracked_value,2) is distinct from s.v
        )),
    (select count(*) from expected),
    (select count(*) from actual),
    (select count(distinct set_id) from expected),
    (select count(distinct set_id) from actual)
  into v_missing,v_extra,v_value_mismatches,
       v_expected_rows,v_actual_rows,v_expected_sets,v_actual_sets;

  return jsonb_build_object(
    'status',case
      when v_missing=0 and v_extra=0 and v_value_mismatches=0 then 'PASS'
      else 'FAIL'
    end,
    'generationId',v_generation,
    'marketDate',v_date,
    'freshnessDays',30,
    'expectedProductRows',v_expected_rows,
    'actualProductRows',v_actual_rows,
    'expectedSetCount',v_expected_sets,
    'actualSetCount',v_actual_sets,
    'missingFromExplorer',v_missing,
    'extraInExplorer',v_extra,
    'setValueOrCountMismatches',v_value_mismatches
  );
end;
$function$
;

revoke all on function public.audit_pokemon_market_explorer_sealed_set_parity_v1(uuid,date)
from public,anon,authenticated;
grant execute on function public.audit_pokemon_market_explorer_sealed_set_parity_v1(uuid,date)
to service_role;

commit;
