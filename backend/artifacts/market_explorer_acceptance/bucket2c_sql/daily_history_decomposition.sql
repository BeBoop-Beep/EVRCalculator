-- READ-ONLY. Per-date decomposition of the production (series A) 1-day return into
-- (a) contribution from canonical cards whose selected card_variant_id CHANGED vs D-1 (edition/variant flip)
-- (b) contribution from cards whose selected variant is unchanged (real price movement / stale->fresh).
-- Columns: date|idx|ret%|n|flips|n_1st|n_unl|n_null|switch_contrib_pp|same_variant_contrib_pp|src_count|max_age_days
with r as materialized (
  select x.*, cv.edition from public.get_pokemon_cards_daily_constituents(array['SET_ID']::uuid[], 'START','END', null) x
  join public.card_variants cv on cv.id=x.card_variant_id
), d as (select market_date, row_number() over(order by market_date) n from (select distinct market_date from r) q),
j as (select a.market_date, a.canonical_card_id, a.market_price cur, b.market_price prev,
        (a.card_variant_id<>b.card_variant_id) flip, a.edition, b.edition pedition, a.source, a.market_date-a.captured_at age
      from r a join d da on da.market_date=a.market_date
      join d db on db.n=da.n-1 join r b on b.market_date=db.market_date and b.canonical_card_id=a.canonical_card_id),
agg as (select market_date, sum(cur) cs, sum(prev) ps, count(*) filter (where flip) flips,
        sum(cur-prev) filter (where flip) fd, sum(cur-prev) filter (where not flip) nd, max(age) maxage from j group by 1),
comp as (select market_date, count(*) n, count(*) filter (where edition='1st-edition') n1, count(*) filter (where edition='unlimited') nu, count(*) filter (where edition is null) nn, count(distinct source) srcs from r group by 1),
ix as (select market_date, cs/ps-1 ret, 100*exp(sum(ln(cs/ps)) over(order by market_date)) idx, flips, fd/ps*100 fpp, nd/ps*100 npp, maxage from agg)
select string_agg(concat_ws('|', ix.market_date, round(ix.idx::numeric,3), round((ix.ret*100)::numeric,2), comp.n, ix.flips, comp.n1, comp.nu, comp.nn, round(coalesce(ix.fpp,0)::numeric,2), round(coalesce(ix.npp,0)::numeric,2), comp.srcs, ix.maxage), E'\n' order by ix.market_date) csv
from ix join comp using(market_date);
