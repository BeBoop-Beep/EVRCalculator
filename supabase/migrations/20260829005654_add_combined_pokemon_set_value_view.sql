-- Approve the correctly scraped Black Bolt #80 identity; the malformed API abstraction is already excluded.
update public.pokemon_canonical_cards pcc
set catalog_role='main',
    set_value_eligible=true,
    opening_eligible=true,
    eligibility_reason='corrected_market_identity_for_upstream_api_number_error',
    canonical_review_status='approved',
    updated_at=now()
from public.sets s
where pcc.set_id=s.id
  and s.canonical_key='blackBolt'
  and pcc.number='80'
  and pcc.pokemon_tcg_api_card_id like 'fallback:%';

-- Promo catalog entities can retain their own market values, but their cards are never booster-opening outcomes.
update public.pokemon_canonical_cards pcc
set catalog_role=case when pcc.catalog_role='main' then 'promo' else pcc.catalog_role end,
    opening_eligible=false,
    eligibility_reason=coalesce(pcc.eligibility_reason,'promo_catalog_entity_not_booster_pulled'),
    canonical_review_status=case when pcc.canonical_review_status='needs_review' then 'approved' else pcc.canonical_review_status end,
    updated_at=now()
from public.sets s
where pcc.set_id=s.id
  and (lower(s.name) like '%promo%' or lower(coalesce(s.set_type,''))='promo');

drop view if exists public.pokemon_set_canonical_quality_latest;
create view public.pokemon_set_canonical_quality_latest
with (security_invoker = true)
as
select
  s.id as set_id,
  s.name as set_name,
  s.parent_opening_set_id,
  s.subset_type,
  (select count(*)::integer from public.pokemon_canonical_cards pcc where pcc.set_id=s.id) as canonical_card_rows,
  (select count(*)::integer from public.pokemon_canonical_cards pcc where pcc.set_id=s.id and pcc.set_value_eligible) as set_value_eligible_rows,
  (select count(*)::integer from public.pokemon_canonical_cards pcc where pcc.set_id=s.id and pcc.opening_eligible) as opening_eligible_rows,
  (select count(*)::integer from public.pokemon_canonical_cards pcc where pcc.set_id=s.id and not pcc.set_value_eligible) as excluded_from_set_value_rows,
  (select count(*)::integer from public.pokemon_canonical_cards pcc where pcc.set_id=s.id and pcc.canonical_review_status='needs_review') as needs_review_rows,
  (select count(*)::integer from public.sets child where child.parent_opening_set_id=s.id) as child_subset_count
from public.sets s;

create or replace view public.pokemon_set_combined_market_value_latest
with (security_invoker = true)
as
with roots as (
  select s.id as root_set_id,s.name as root_set_name,s.canonical_key,s.era_id,s.release_date
  from public.sets s
  where s.parent_opening_set_id is null
), members as (
  select r.root_set_id,r.root_set_id as member_set_id,'main'::text as member_type
  from roots r
  union all
  select child.parent_opening_set_id as root_set_id,child.id as member_set_id,coalesce(child.subset_type,'subset') as member_type
  from public.sets child
  where child.parent_opening_set_id is not null
    and child.counts_toward_parent_set_value
), card_rows as (
  select
    m.root_set_id,
    m.member_set_id,
    m.member_type,
    pcc.id as canonical_card_id,
    pcc.catalog_role,
    pcc.canonical_review_status,
    p.market_price,
    p.captured_at
  from members m
  join public.pokemon_canonical_cards pcc
    on pcc.set_id=m.member_set_id
   and pcc.set_value_eligible
  left join public.pokemon_canonical_card_market_prices_latest p
    on p.canonical_card_id=pcc.id
)
select
  r.root_set_id as set_id,
  r.root_set_name as set_name,
  r.canonical_key,
  r.era_id,
  r.release_date,
  round(coalesce(sum(cr.market_price),0),2) as combined_set_value,
  count(cr.canonical_card_id)::integer as eligible_card_count,
  count(cr.market_price)::integer as priced_card_count,
  case when count(cr.canonical_card_id)=0 then null
       else round((count(cr.market_price)::numeric / count(cr.canonical_card_id)::numeric) * 100,2)
  end as coverage_pct,
  min(cr.captured_at) filter (where cr.market_price is not null) as oldest_component_price_date,
  max(cr.captured_at) filter (where cr.market_price is not null) as newest_component_price_date,
  count(distinct cr.member_set_id) filter (where cr.member_set_id<>r.root_set_id)::integer as included_subset_count,
  count(cr.canonical_card_id) filter (where cr.canonical_review_status='needs_review')::integer as needs_review_card_count,
  case
    when count(cr.canonical_card_id)=0 then 'unavailable'
    when count(cr.canonical_card_id) filter (where cr.canonical_review_status='needs_review') > 0 then 'needs_review'
    when count(cr.market_price)=count(cr.canonical_card_id) then 'complete'
    when count(cr.market_price)::numeric / nullif(count(cr.canonical_card_id),0) >= 0.99 then 'high_coverage'
    when count(cr.market_price)::numeric / nullif(count(cr.canonical_card_id),0) >= 0.95 then 'partial'
    else 'incomplete'
  end as quality_status
from roots r
left join card_rows cr on cr.root_set_id=r.root_set_id
group by r.root_set_id,r.root_set_name,r.canonical_key,r.era_id,r.release_date;

comment on view public.pokemon_set_combined_market_value_latest is 'Current parent expansion market value including child subsets flagged counts_toward_parent_set_value; preserves entity-local values separately.';
