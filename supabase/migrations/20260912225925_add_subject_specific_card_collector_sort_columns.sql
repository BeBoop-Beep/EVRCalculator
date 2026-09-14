create or replace view public.pokemon_card_collector_appeal_rankings_current_v
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
            else null end as modeled_pull_probability,
       case when s.subject_policy='pokemon' then s.subject_baseline_score else null end as pokemon_appeal,
       case when s.subject_policy='trainer' then s.subject_baseline_score else null end as trainer_appeal
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
