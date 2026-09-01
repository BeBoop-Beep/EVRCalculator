-- Round 24 research-only grouped exact shared-date audit. No interpolation or nearest-date matching.
with candidate_ladders(identity_key, set_name, treatment_a, treatment_b, variant_a, variant_b, edition_a, edition_b, finish_a, finish_b) as (
  values /* bind frozen Round 24 candidate rows here */
), a as (
  select l.*, o.condition_id, o.captured_date, o.market_price
  from candidate_ladders l join card_variant_price_observations o on o.card_variant_id=l.variant_a
  where o.market_price>0
), b as (
  select l.identity_key, l.variant_a, l.variant_b, o.condition_id, o.captured_date, o.market_price
  from candidate_ladders l join card_variant_price_observations o on o.card_variant_id=l.variant_b
  where o.market_price>0
), shared as (
  select a.identity_key,a.set_name,a.treatment_a,a.treatment_b,a.variant_a,a.variant_b,a.edition_a,a.edition_b,a.finish_a,a.finish_b,a.condition_id,a.captured_date
  from a join b using(identity_key,variant_a,variant_b,condition_id,captured_date)
)
select l.*, s.condition_id, min(s.captured_date) first_shared_date, max(s.captured_date) last_shared_date,
 count(distinct s.captured_date) shared_date_count,
 (select count(distinct captured_date) from a where a.identity_key=l.identity_key and a.variant_a=l.variant_a and a.condition_id=s.condition_id) observation_count_a,
 (select count(distinct captured_date) from b where b.identity_key=l.identity_key and b.variant_b=l.variant_b and b.condition_id=s.condition_id) observation_count_b,
 (select count(*) from (select captured_date from a where a.identity_key=l.identity_key and a.condition_id=s.condition_id except select captured_date from b where b.identity_key=l.identity_key and b.condition_id=s.condition_id) q) dates_a_only,
 (select count(*) from (select captured_date from b where b.identity_key=l.identity_key and b.condition_id=s.condition_id except select captured_date from a where a.identity_key=l.identity_key and a.condition_id=s.condition_id) q) dates_b_only
from candidate_ladders l left join shared s using(identity_key,variant_a,variant_b)
group by l.identity_key,l.set_name,l.treatment_a,l.treatment_b,l.variant_a,l.variant_b,l.edition_a,l.edition_b,l.finish_a,l.finish_b,s.condition_id;
