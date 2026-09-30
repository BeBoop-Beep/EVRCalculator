begin;

-- Additive seven-window sealed constituent movement contract. V1 remains in
-- place for compatibility. Fixed windows use the same true-elapsed targets as
-- backend.domain.pokemon.market_index.resolve_window_baselines: as-of minus N
-- calendar days, with the latest trustworthy observation on or before target.
create or replace function public.get_pokemon_market_explorer_sealed_constituent_movement_v2(
  p_sealed_product_ids uuid[],
  p_as_of date
)
returns table(
  sealed_product_id uuid,
  as_of date,
  end_price numeric,
  baseline_1d_date date,
  movement_1d_pct numeric,
  baseline_7d_date date,
  movement_7d_pct numeric,
  baseline_30d_date date,
  movement_30d_pct numeric,
  baseline_3m_date date,
  movement_3m_pct numeric,
  baseline_6m_date date,
  movement_6m_pct numeric,
  baseline_1y_date date,
  movement_1y_pct numeric,
  baseline_since_tracking_date date,
  movement_since_tracking_pct numeric
)
language plpgsql stable security invoker
set search_path=''
set statement_timeout='2s'
as $function$
begin
  if p_sealed_product_ids is null
     or cardinality(p_sealed_product_ids)<1
     or cardinality(p_sealed_product_ids)>100
     or p_as_of is null then
    raise exception 'SEALED_MOVEMENT_REQUIRES_1_TO_100_IDS_AND_AS_OF';
  end if;

  return query
  with ids as materialized (
    select distinct x.id
    from pg_catalog.unnest(p_sealed_product_ids) x(id)
  ), endpoint as materialized (
    select i.id,e.market_price end_price
    from ids i
    left join lateral (
      select o.market_price
      from public.sealed_product_price_observations o
      where o.sealed_product_id=i.id
        and o.captured_at>=p_as_of::timestamptz
        and o.captured_at<(p_as_of+1)::timestamptz
        and o.market_price>0
        and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
      order by o.captured_at desc,o.id desc
      limit 1
    ) e on true
  )
  select e.id,p_as_of,e.end_price,
    b1.d,case when e.end_price>0 and b1.p>0 then (e.end_price/b1.p-1.0)*100.0 end,
    b7.d,case when e.end_price>0 and b7.p>0 then (e.end_price/b7.p-1.0)*100.0 end,
    b30.d,case when e.end_price>0 and b30.p>0 then (e.end_price/b30.p-1.0)*100.0 end,
    b90.d,case when e.end_price>0 and b90.p>0 then (e.end_price/b90.p-1.0)*100.0 end,
    b180.d,case when e.end_price>0 and b180.p>0 then (e.end_price/b180.p-1.0)*100.0 end,
    b365.d,case when e.end_price>0 and b365.p>0 then (e.end_price/b365.p-1.0)*100.0 end,
    blt.d,case when e.end_price>0 and blt.p>0 then (e.end_price/blt.p-1.0)*100.0 end
  from endpoint e
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<p_as_of::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b1 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-7+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b7 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-30+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b30 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-90+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b90 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-180+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b180 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of-365+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at desc,o.id desc limit 1
  ) b365 on true
  left join lateral (
    select o.captured_at::date d,o.market_price p
    from public.sealed_product_price_observations o
    where o.sealed_product_id=e.id and o.captured_at<(p_as_of+1)::timestamptz
      and o.market_price>0 and pg_catalog.upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'
    order by o.captured_at::date asc,o.captured_at desc,o.id desc limit 1
  ) blt on true
  order by pg_catalog.array_position(p_sealed_product_ids,e.id);
end;
$function$;

revoke all on function public.get_pokemon_market_explorer_sealed_constituent_movement_v2(uuid[],date)
from public,anon,authenticated;
grant execute on function public.get_pokemon_market_explorer_sealed_constituent_movement_v2(uuid[],date)
to service_role;

commit;
