create or replace view public.card_market_usd_latest_v2_shadow
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
    where current_row.card_variant_id=cv.id
      and current_row.currency='USD'
    order by current_row.last_observed_date desc nulls last,
             current_row.last_observation_created_at desc nulls last,
             current_row.last_observation_id desc nulls last
    limit 1
) latest;
revoke all on public.card_market_usd_latest_v2_shadow from public, anon, authenticated;
grant select on public.card_market_usd_latest_v2_shadow to service_role;