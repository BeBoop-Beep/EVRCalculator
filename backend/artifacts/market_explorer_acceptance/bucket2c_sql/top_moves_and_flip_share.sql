-- READ-ONLY. Output 1 row: aggregates + top-10 abs-move dates with flip / same-variant decomposition.
with r as materialized (
  select x.*, cv.edition from public.get_pokemon_cards_daily_constituents(array['SET_ID']::uuid[], 'START','END', null) x
  join public.card_variants cv on cv.id=x.card_variant_id
), d as (select market_date, row_number() over(order by market_date) n from (select distinct market_date from r) q),
j as (select a.market_date, a.canonical_card_id, a.market_price cur, b.market_price prev, (a.card_variant_id<>b.card_variant_id) flip,
        a.edition, b.edition pe, a.source, b.source ps_, a.market_date-a.captured_at age
      from r a join d da on da.market_date=a.market_date join d db on db.n=da.n-1 join r b on b.market_date=db.market_date and b.canonical_card_id=a.canonical_card_id),
agg as (select market_date, sum(cur) cs, sum(prev) ps, count(*) filter (where flip) flips, count(*) filter (where flip and pe='1st-edition' and edition='unlimited') f2u,
        count(*) filter (where flip and pe='unlimited' and edition='1st-edition') u2f, count(*) filter (where source<>ps_) srcchg,
        sum(cur-prev) filter (where flip) fd, sum(cur-prev) filter (where not flip) nd,
        count(*) filter (where not flip and cur<>prev) real_moves, count(*) filter (where not flip and age=0 and cur<>prev) fresh_moves, max(age) maxage from j group by 1),
t as (select market_date, (cs/ps-1)*100 ret, flips, f2u, u2f, srcchg, fd/ps*100 fpp, nd/ps*100 npp, real_moves, maxage from agg),
top as (select * from t order by abs(ret) desc limit 10)
select (select round((sum(fpp*fpp)/nullif(sum(ret*ret),0))::numeric,4) from t) flip_var_share_of_sumsq,
       (select count(*) from t where flips>0) days_with_flips, (select count(*) from t) days,
       (select max(abs(ret)) from t where flips=0) max_abs_ret_when_no_flips,
       (select max(abs(npp)) from t) max_abs_same_variant_contrib_pp, (select sum(srcchg) from t) total_source_changes,
       (select min(market_date) from t where flips>0) first_flip_date,
       (select string_agg(concat_ws('|',market_date,round(ret::numeric,2),flips,f2u,u2f,round(fpp::numeric,2),round(npp::numeric,2),real_moves,srcchg), E'\n' order by abs(ret) desc) from top) top10;
