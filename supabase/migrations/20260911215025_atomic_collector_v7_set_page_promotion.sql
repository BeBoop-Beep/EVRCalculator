create or replace function public.promote_pokemon_collector_v7_with_set_page_generation(
  p_model_run_id uuid,
  p_generation_id uuid
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  g public.pokemon_set_page_snapshot_generations%rowtype;
begin
  select * into g
  from public.pokemon_set_page_snapshot_generations
  where id = p_generation_id
  for update;

  if not found
     or g.status not in ('validated', 'published')
     or not g.validation_passed
     or coalesce((g.validation_json->>'passed')::boolean, false) = false then
    raise exception 'generation % is not validated', p_generation_id;
  end if;
  if g.collector_model_run_id is distinct from p_model_run_id then
    raise exception 'generation % does not reference Collector model run %', p_generation_id, p_model_run_id;
  end if;

  perform public.promote_pokemon_collector_appeal_model_run(p_model_run_id);
  perform public.activate_pokemon_set_page_snapshot_generation(p_generation_id);
  return jsonb_build_object('modelRunId', p_model_run_id, 'generationId', p_generation_id);
end
$$;

revoke all on function public.promote_pokemon_collector_v7_with_set_page_generation(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.promote_pokemon_collector_v7_with_set_page_generation(uuid, uuid)
  to service_role;
alter function public.promote_pokemon_collector_v7_with_set_page_generation(uuid, uuid)
  set statement_timeout = '240s';
