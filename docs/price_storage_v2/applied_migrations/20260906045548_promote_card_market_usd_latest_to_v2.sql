create or replace view public.card_market_usd_latest_legacy_shadow
with (security_invoker=true) as
select card_id,name,set_id,rarity,variant_id,printing_type,special_type,edition,market_price,currency,source,captured_at,created_at
from (
    select c.id as card_id,c.name,c.set_id,c.rarity,cv.id as variant_id,cv.printing_type,cv.special_type,cv.edition,
           cvpo.market_price,cvpo.currency,cvpo.source,cvpo.captured_at,cvpo.created_at,cvpo.id as price_observation_id,
           row_number() over (partition by cv.id order by cvpo.captured_at desc nulls last, cvpo.created_at desc nulls last, cvpo.id desc) as rn
    from public.card_variant_price_observations cvpo
    join public.card_variants cv on cv.id=cvpo.card_variant_id
    join public.cards c on c.id=cv.card_id
    where cvpo.currency in ('USD','"USD"')
) x where rn=1;
revoke all on public.card_market_usd_latest_legacy_shadow from public,anon,authenticated;
grant select on public.card_market_usd_latest_legacy_shadow to service_role;

create or replace view public.card_market_usd_latest
with (security_invoker=true) as
select
    c.id as card_id,
    c.name,
    c.set_id,
    c.rarity,
    cv.id as variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    latest.market_price,
    latest.currency,
    latest.source,
    latest.last_observed_date as captured_at,
    latest.last_observation_created_at as created_at
from public.card_variants cv
join public.cards c on c.id=cv.card_id
cross join lateral (
    select current_row.*
    from public.card_variant_price_current_v2 current_row
    where current_row.card_variant_id=cv.id and current_row.currency='USD'
    order by current_row.last_observed_date desc nulls last,
             current_row.last_observation_created_at desc nulls last,
             current_row.last_observation_id desc nulls last
    limit 1
) latest;