-- READ-ONLY research query. Replace :SET_ID / dates. Never publishes anything.
-- series: A = prod identity (canonical_card_id, selected variant's price)
--         B = physical card_variant_id of the prod-selected row as identity
--         C_unl / C_1st = one fixed edition variant per canonical card, priced as-of from events
with r as materialized (
  select * from public.get_pokemon_cards_daily_constituents(array['SET_ID']::uuid[], 'START','END', null)
), nm as (select id from public.conditions where name='Near Mint' and abbreviation='NM' order by id limit 1),
dates as (select market_date, row_number() over(order by market_date) n from (select distinct market_date from r) x),
pairs as (select distinct canonical_card_id c, card_variant_id v from r),
vd as (select p.c, p.v, d.market_date, d.n, cv.edition,
  (select e.market_price from public.card_variant_price_events_v2 e, nm where e.card_variant_id=p.v and e.condition_id=nm.id and e.currency='USD' and e.source='TCGPlayer' and e.effective_date<=d.market_date and e.market_price>0 order by e.effective_date desc, e.id desc limit 1) price
  from pairs p cross join dates d join public.card_variants cv on cv.id=p.v),
s as (
  select 'A' series, dt.n, r.canonical_card_id::text k, r.market_price price from r join dates dt using(market_date)
  union all select 'B', dt.n, r.card_variant_id::text, r.market_price from r join dates dt using(market_date)
  union all select 'C_unl', n, c::text, price from vd where edition='unlimited' and price is not null
  union all select 'C_1st', n, c::text, price from vd where edition='1st-edition' and price is not null
), pr as (
  select a.series, a.n, sum(a.price) cur, sum(b.price) prev, count(*) common
  from s a join s b on b.series=a.series and b.k=a.k and b.n=a.n-1 group by 1,2
), rt as (select series, n, common, cur/prev-1 ret from pr),
ix as (select series, n, ret, common, 100*exp(sum(ln(1+ret)) over(partition by series order by n)) idx from rt)
select series, count(*) days, round(max(abs(ret))*100,2) max_abs_pct, round(stddev(ret)*100,2) sd_pct,
  count(*) filter (where abs(ret)>0.10) gt10, count(*) filter (where abs(ret)>0.20) gt20,
  round((array_agg(idx order by n desc))[1]::numeric,2) end_idx, round(min(idx)::numeric,2) min_idx, round(max(idx)::numeric,2) max_idx, min(common) min_common
from ix group by 1 order by 1;
