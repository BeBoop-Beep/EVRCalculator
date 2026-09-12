create or replace function public.replace_pokemon_set_collector_component_rankings(
  p_model_run_id uuid,
  p_rows jsonb
) returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_input_count integer;
  v_inserted integer;
begin
  if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) = 0 then
    raise exception 'component ranking replacement requires a non-empty row array';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('pokemon_set_collector_component_rankings:' || p_model_run_id::text, 0));

  create temporary table _component_replacement on commit drop as
  select x.model_run_id, x.set_id, x.drivers_json, x.methodology_version
  from jsonb_to_recordset(p_rows) as x(
    model_run_id uuid, set_id uuid, drivers_json jsonb, methodology_version text
  );
  select count(*) into v_input_count from _component_replacement;
  if v_input_count <> jsonb_array_length(p_rows)
     or (select count(distinct set_id) from _component_replacement) <> v_input_count
     or exists(select 1 from _component_replacement where model_run_id <> p_model_run_id)
     or exists(
       select 1 from _component_replacement r
       where not exists (
         select 1 from public.pokemon_set_collector_appeal_scores s
         where s.model_run_id = p_model_run_id and s.set_id = r.set_id
           and s.score_status = 'scored' and s.collector_appeal_score is not null
       )
     ) then
    raise exception 'component ranking replacement failed exact scored Set cohort validation';
  end if;

  delete from public.pokemon_set_collector_component_rankings
  where model_run_id = p_model_run_id;
  insert into public.pokemon_set_collector_component_rankings(
    model_run_id, set_id, drivers_json, methodology_version
  ) select model_run_id, set_id, drivers_json, methodology_version
    from _component_replacement order by set_id;
  get diagnostics v_inserted = row_count;
  if v_inserted <> v_input_count then
    raise exception 'component ranking replacement count mismatch';
  end if;
  return v_inserted;
end;
$$;

revoke all on function public.replace_pokemon_set_collector_component_rankings(uuid, jsonb)
  from public, anon, authenticated;
grant execute on function public.replace_pokemon_set_collector_component_rankings(uuid, jsonb)
  to service_role;
