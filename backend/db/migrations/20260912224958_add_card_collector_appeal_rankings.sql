begin;

create table public.pokemon_card_collector_appeal_rankings (
  model_run_id uuid not null references public.pokemon_collector_appeal_model_runs(id),
  pokemon_canonical_card_id uuid not null references public.pokemon_canonical_cards(id),
  collector_appeal_score numeric not null,
  rank integer not null check (rank > 0),
  cohort_size integer not null check (cohort_size > 0 and rank <= cohort_size),
  status text not null check (status = 'scored'),
  methodology_version text not null,
  created_at timestamptz not null default timezone('utc', now()),
  primary key (model_run_id, pokemon_canonical_card_id)
);
create unique index pokemon_card_collector_appeal_rankings_run_rank_uq
  on public.pokemon_card_collector_appeal_rankings(model_run_id, rank);
create index pokemon_card_collector_appeal_rankings_run_score_idx
  on public.pokemon_card_collector_appeal_rankings(model_run_id, collector_appeal_score desc, pokemon_canonical_card_id);
create index pokemon_card_collector_scores_run_subject_idx
  on public.pokemon_card_collector_appeal_scores(model_run_id, subject_policy, subject_baseline_score desc, pokemon_canonical_card_id)
  where score_status='scored';
create index pokemon_card_collector_scores_run_artist_idx
  on public.pokemon_card_collector_appeal_scores(model_run_id, artist_recognition_score desc nulls last, pokemon_canonical_card_id)
  where score_status='scored';
create index pokemon_card_collector_scores_run_playability_idx
  on public.pokemon_card_collector_appeal_scores(model_run_id, playability_score desc nulls last, pokemon_canonical_card_id)
  where score_status='scored';
alter table public.pokemon_card_collector_appeal_rankings enable row level security;
revoke all on public.pokemon_card_collector_appeal_rankings from public, anon, authenticated;
grant select, insert, update on public.pokemon_card_collector_appeal_rankings to service_role;

insert into public.pokemon_card_collector_appeal_rankings(
  model_run_id, pokemon_canonical_card_id, collector_appeal_score,
  rank, cohort_size, status, methodology_version
)
select model_run_id, pokemon_canonical_card_id, collector_card_appeal_score,
       row_number() over (partition by model_run_id order by collector_card_appeal_score desc, pokemon_canonical_card_id)::integer,
       count(*) over (partition by model_run_id)::integer,
       'scored', 'card_collector_appeal_global_ordinal_v1'
from public.pokemon_card_collector_appeal_scores
where model_run_id = (select model_run_id from public.pokemon_collector_appeal_current where scope='pokemon')
  and score_status='scored' and collector_card_appeal_score is not null
on conflict (model_run_id, pokemon_canonical_card_id) do update set
  collector_appeal_score=excluded.collector_appeal_score,
  rank=excluded.rank, cohort_size=excluded.cohort_size,
  status=excluded.status, methodology_version=excluded.methodology_version;

create view public.pokemon_card_collector_appeal_rankings_current_v
with (security_invoker=true) as
select r.model_run_id, cur.model_version, cur.as_of_date,
       r.pokemon_canonical_card_id, s.set_id, st.name as set_name,
       st.canonical_key as set_canonical_key, st.era_id,
       e.name as era_name, e.canonical_key as era_canonical_key,
       cc.name as card_name, cc.rarity, cc.image_small_url,
       r.collector_appeal_score, r.rank, r.cohort_size, r.status,
       r.methodology_version,
       s.subject_policy, s.subject_baseline_score,
       s.component_inputs_json->>'subjectType' as subject_type,
       s.component_inputs_json->>'subjectIdentity' as subject_identity,
       s.artist_recognition_score,
       s.component_inputs_json->>'artistEvidenceStatus' as artist_status,
       s.component_inputs_json->'artistNames' as artist_names,
       s.playability_score,
       case when s.playability_score is not null then 'scored' else 'unavailable' end as playability_status,
       s.confidence as playability_confidence,
       s.component_inputs_json#>>'{treatmentDiagnostic,treatmentKey}' as treatment_category,
       s.component_inputs_json#>>'{treatmentDiagnostic,status}' as treatment_status,
       case when jsonb_typeof(s.component_inputs_json->'pullScarcityDiagnostic')='object'
            then case
              when coalesce(s.component_inputs_json#>>'{pullScarcityDiagnostic,probability}',
                            s.component_inputs_json#>>'{pullScarcityDiagnostic,modeledProbability}')
                   ~ '^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'
              then coalesce(s.component_inputs_json#>>'{pullScarcityDiagnostic,probability}',
                            s.component_inputs_json#>>'{pullScarcityDiagnostic,modeledProbability}')::numeric
              else null end
            else null end as modeled_pull_probability
from public.pokemon_collector_appeal_current cur
join public.pokemon_card_collector_appeal_rankings r on r.model_run_id=cur.model_run_id
join public.pokemon_card_collector_appeal_scores s
  on s.model_run_id=r.model_run_id and s.pokemon_canonical_card_id=r.pokemon_canonical_card_id
join public.pokemon_canonical_cards cc on cc.id=r.pokemon_canonical_card_id
join public.sets st on st.id=s.set_id
left join public.eras e on e.id=st.era_id
where cur.scope='pokemon' and r.status='scored';
revoke all on public.pokemon_card_collector_appeal_rankings_current_v from public, anon, authenticated;
grant select on public.pokemon_card_collector_appeal_rankings_current_v to service_role;

commit;
