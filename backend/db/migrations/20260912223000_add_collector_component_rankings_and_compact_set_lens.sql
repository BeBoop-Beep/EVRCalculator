begin;

create table if not exists public.pokemon_set_collector_component_rankings (
  model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
  set_id uuid not null references public.pokemon_sets(id),
  drivers_json jsonb not null,
  methodology_version text not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (model_run_id, set_id)
);
create index if not exists pokemon_set_collector_component_rankings_current_idx
  on public.pokemon_set_collector_component_rankings(model_run_id, set_id);
alter table public.pokemon_set_collector_component_rankings enable row level security;
revoke all on public.pokemon_set_collector_component_rankings from public, anon, authenticated;
grant select, insert on public.pokemon_set_collector_component_rankings to service_role;

create or replace view public.pokemon_set_collector_component_rankings_current_v
with (security_invoker=true) as
select r.*
from public.pokemon_collector_appeal_current c
join public.pokemon_set_collector_component_rankings r on r.model_run_id=c.model_run_id
where c.scope='pokemon';
revoke all on public.pokemon_set_collector_component_rankings_current_v from public, anon, authenticated;
grant select on public.pokemon_set_collector_component_rankings_current_v to service_role;

create or replace function public.project_pokemon_rankings_set_target(p_target jsonb)
returns jsonb language sql immutable parallel safe set search_path=public,pg_temp as $$
select public.project_rankings_json_keys(p_target, array[
 'target_type','target_id','set_id','id','name','slug','era','era_id','canonical_key','pokemon_api_set_id',
 'hero_image_url','logo_image_url','symbol_image_url','publicAnalyticsStatus','mean_value','median_value',
 'pack_cost','prob_profit','expected_loss_when_losing','mean_value_to_cost_ratio','p95_value_to_cost_ratio',
 'p99_value_to_cost_ratio','previousOverallRipRank1d','overallRipRankComparisonStatus1d',
 'previousFinancialRipRank1d','financialRipRankComparisonStatus1d'
]) || jsonb_strip_nulls(jsonb_build_object(
 'setRipV1', public.project_rankings_json_keys(p_target->'setRipV1', array[
   'publicScore','score','rank','tier','cohortSize','rankable','methodologyVersion','participatingFamilyCount',
   'participatingFamilies','skuEvidenceCount','familyScores','chaseAccessibility'
 ]),
 'overallRipV12', public.project_rankings_json_keys(p_target->'overallRipV12', array[
   'relativeScore','leaderNormalizedScore','rank','cohortSize','rankedSetCount','tier','status','statusReason'
 ]),
 'financialRipV4', public.project_rankings_json_keys(p_target->'financialRipV4', array[
   'relativeScore','leaderNormalizedScore','rank','cohortSize','rankedSetCount','tier','status','statusReason'
 ]),
 'publicCollectorAppealContractV1', jsonb_strip_nulls(jsonb_build_object(
   'contractVersion',p_target#>'{publicCollectorAppealContractV1,contractVersion}',
   'collectorAppeal',public.project_rankings_json_keys(p_target#>'{publicCollectorAppealContractV1,collectorAppeal}',array[
     'score','relativeScore','rank','rankedSetCount','cohortSize','tier','status','statusReason','modelVersion'
   ]),
   'components',jsonb_build_object(
     'rosterDesirability',public.project_rankings_json_keys(p_target#>'{publicCollectorAppealContractV1,components,rosterDesirability}',array['score','rank','rankedSetCount']),
     'desirableOutcomeFrequency',public.project_rankings_json_keys(p_target#>'{publicCollectorAppealContractV1,components,desirableOutcomeFrequency}',array['rawValue','displayPercent','status','statusReason','isFinancialMetric'])
   ),
   'drivers',coalesce(p_target#>'{publicCollectorAppealContractV1,drivers}','{}'::jsonb),
   'financialDistinction',p_target#>'{publicCollectorAppealContractV1,financialDistinction}'
 )),
 'rankingsChase',public.project_rankings_json_keys(p_target->'rankingsChase',array['cardName','currentMarketPrice','impliedOddsOneInN','packsFor50PercentChance'])
)); $$;
revoke all on function public.project_pokemon_rankings_set_target(jsonb) from public,anon,authenticated;
grant execute on function public.project_pokemon_rankings_set_target(jsonb) to service_role;

commit;
