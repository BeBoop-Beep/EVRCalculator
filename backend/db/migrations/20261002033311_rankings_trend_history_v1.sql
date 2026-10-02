-- Bounded, service-role-only Rankings Trend history.
-- Canonical snapshots are materialized once; duplicate market dates choose latest
-- published_at then id. Snapshot-set/run evidence is materialized once before joins.
create or replace function public.get_pokemon_rankings_trend_history_v1(
  p_entities jsonb,
  p_start_date date,
  p_end_date date
)
returns table (
  market_date date, entity_type text, entity_id uuid,
  financial_rip numeric, financial_rank integer, financial_cohort_size integer,
  overall_financial_rip numeric, expected_value_per_pack numeric,
  overall_expected_value_per_pack numeric, chance_to_beat_pack numeric,
  overall_chance_to_beat_pack numeric, chance_to_recover_cost numeric,
  overall_chance_to_recover_cost numeric, source_snapshot_id uuid
)
language sql stable security invoker set search_path = ''
as $$
with requested as materialized (
  select x.entity_type, x.entity_id::uuid
  from jsonb_to_recordset(coalesce(p_entities, '[]'::jsonb))
       as x(entity_type text, entity_id text)
  where x.entity_type in ('set','era')
  limit 22
), guard as (
  select case
    when jsonb_array_length(coalesce(p_entities, '[]'::jsonb)) between 1 and 22
     and p_start_date <= p_end_date and p_end_date - p_start_date <= 3660
    then true else false end ok
), canonical as materialized (
  select distinct on (s.market_date)
    s.id, s.market_date, s.payload_json
  from public.pokemon_rip_stats_snapshots s, guard g
  where g.ok and s.publication_status = 'published'
    and s.contract_version = 'pokemon-rip-stats-v3'
    and s.methodology_version = 'hierarchical_product_per_pack_empirical_v1'
    and s.weighting_version = 'equal-set_equal-family_equal-sku-v1'
    and s.market_date between p_start_date and p_end_date
  order by s.market_date, s.published_at desc nulls last, s.id desc
), snapshot_set_runs as materialized (
  select ss.snapshot_id, ss.set_id, st.era_id, sr.prob_profit
  from public.pokemon_rip_stats_snapshot_sets ss
  join canonical c on c.id = ss.snapshot_id
  join public.sets st on st.id = ss.set_id
  left join public.simulation_run_summary sr on sr.calculation_run_id = ss.calculation_run_id
), set_opening as materialized (
  select c.id snapshot_id, c.market_date,
    (j->>'setId')::uuid set_id,
    nullif(j->>'averageModelBreakEvenPerPack','')::numeric ev,
    nullif(j->>'chanceToRecoverCost','')::numeric recover
  from canonical c
  cross join lateral jsonb_array_elements(coalesce(c.payload_json#>'{openingEconomics,sets}','[]'::jsonb)) j
), global_opening as materialized (
  select c.id snapshot_id, c.market_date,
    nullif(c.payload_json#>>'{openingEconomics,global,averageModelBreakEvenPerPack}','')::numeric ev,
    nullif(c.payload_json#>>'{openingEconomics,global,chanceToRecoverCost}','')::numeric recover,
    nullif(c.payload_json#>>'{packEconomics,chanceToBeatCost}','')::numeric beat
  from canonical c
), opening_rows as (
  select so.market_date, 'set'::text entity_type, so.set_id entity_id,
    so.ev, ssr.prob_profit beat, so.recover, so.snapshot_id
  from set_opening so join snapshot_set_runs ssr
    on ssr.snapshot_id=so.snapshot_id and ssr.set_id=so.set_id
  union all
  select so.market_date, 'era', ssr.era_id,
    avg(so.ev), avg(ssr.prob_profit), avg(so.recover), so.snapshot_id
  from set_opening so join snapshot_set_runs ssr
    on ssr.snapshot_id=so.snapshot_id and ssr.set_id=so.set_id
  group by so.market_date, ssr.era_id, so.snapshot_id
), financial as materialized (
  select f.market_date, f.entity_type, f.entity_id, f.absolute_financial_rip_score,
    f.rank, f.cohort_size, f.overall_financial_rip_reference
  from public.pokemon_financial_rip_history_rows_v1 f
  where f.market_date between p_start_date and p_end_date
)
select o.market_date, o.entity_type, o.entity_id,
  f.absolute_financial_rip_score, f.rank, f.cohort_size,
  f.overall_financial_rip_reference, o.ev, g.ev, o.beat, g.beat,
  o.recover, g.recover, o.snapshot_id
from opening_rows o
join requested r using(entity_type,entity_id)
join global_opening g on g.snapshot_id=o.snapshot_id
left join financial f using(market_date,entity_type,entity_id)
order by o.market_date,o.entity_type,o.entity_id
$$;

revoke execute on function public.get_pokemon_rankings_trend_history_v1(jsonb,date,date)
  from public, anon, authenticated;
grant execute on function public.get_pokemon_rankings_trend_history_v1(jsonb,date,date)
  to service_role;

