do $$
declare
  v_oid oid;
  v_def text;
  v_old text := E'FROM public.pokemon_canonical_cards pcc\n        JOIN requested_sets s ON s.id = pcc.set_id\n    )';
  v_new text := E'FROM public.pokemon_canonical_cards pcc\n        JOIN requested_sets s ON s.id = pcc.set_id\n        WHERE pcc.set_value_eligible = true\n    )';
begin
  select p.oid into v_oid
  from pg_proc p
  join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public'
    and p.proname='refresh_pokemon_set_value_daily_history'
    and p.prokind='f'
  order by p.oid
  limit 1;

  if v_oid is null then
    raise exception 'refresh_pokemon_set_value_daily_history not found';
  end if;

  select pg_get_functiondef(v_oid) into v_def;
  if position(v_old in v_def)=0 then
    raise exception 'Expected canonical_checklist fragment not found; refusing unsafe function rewrite';
  end if;

  v_def := replace(v_def,v_old,v_new);
  execute v_def;
end $$;

create or replace view public.pokemon_set_combined_value_daily_history
with (security_invoker = true)
as
with roots as (
  select s.id root_set_id,s.name root_set_name,s.canonical_key,s.era_id,s.release_date
  from public.sets s
  where s.parent_opening_set_id is null
), members as (
  select r.root_set_id,r.root_set_id member_set_id
  from roots r
  union all
  select s.parent_opening_set_id root_set_id,s.id member_set_id
  from public.sets s
  where s.parent_opening_set_id is not null
    and s.counts_toward_parent_set_value
), expected as (
  select root_set_id,count(*)::integer expected_member_count
  from members
  group by root_set_id
), daily as (
  select
    m.root_set_id,
    h.snapshot_date,
    count(distinct m.member_set_id)::integer observed_member_count,
    round(sum(h.set_value),2) combined_set_value,
    sum(h.priced_card_count)::integer priced_card_count,
    sum(h.total_card_count)::integer total_card_count,
    sum(coalesce(h.included_card_count,h.priced_card_count))::integer included_card_count,
    min(h.source) source_sample
  from members m
  join public.pokemon_set_value_daily_history h
    on h.set_id=m.member_set_id
   and h.value_scope='standard'
  group by m.root_set_id,h.snapshot_date
)
select
  r.root_set_id as set_id,
  r.root_set_name as set_name,
  r.canonical_key,
  r.era_id,
  r.release_date,
  d.snapshot_date,
  'combined'::text as value_scope,
  d.combined_set_value as set_value,
  d.priced_card_count,
  d.total_card_count,
  d.included_card_count,
  case when d.total_card_count=0 then null
       else round((d.priced_card_count::numeric/d.total_card_count::numeric)*100,2)
  end as coverage_pct,
  d.observed_member_count,
  e.expected_member_count,
  (d.observed_member_count=e.expected_member_count) as complete_member_coverage,
  'combined_parent_plus_child_subsets_from_standard_history'::text as source
from daily d
join expected e on e.root_set_id=d.root_set_id
join roots r on r.root_set_id=d.root_set_id
where d.observed_member_count=e.expected_member_count;

comment on view public.pokemon_set_combined_value_daily_history is 'Historical parent expansion values formed only on dates where the parent and every included child subset each have a standard history row.';
