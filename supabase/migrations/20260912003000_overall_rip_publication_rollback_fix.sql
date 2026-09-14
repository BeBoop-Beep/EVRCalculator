-- Keep publication-run and generation lifecycles aligned so an immutable prior
-- authority can be promoted again without recomputation.
create or replace function public.promote_pokemon_overall_rip_publication(p_publication_run_id uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare r public.pokemon_overall_rip_publication_runs%rowtype; rg uuid; sg uuid; prior uuid; n integer;
begin
  if auth.role() <> 'service_role' then raise exception 'service_role required'; end if;
  select * into strict r from public.pokemon_overall_rip_publication_runs where id=p_publication_run_id for update;
  if r.status not in ('validated','superseded') or coalesce((r.validation_json->>'passed')::boolean,false)=false then
    raise exception 'publication % is not validated',p_publication_run_id;
  end if;
  select id into strict rg from public.pokemon_overall_rip_publication_generations where publication_run_id=r.id and generation_kind='rankings' and status in ('validated','superseded','published') and coalesce((validation_json->>'passed')::boolean,false)=true;
  select id into strict sg from public.pokemon_overall_rip_publication_generations where publication_run_id=r.id and generation_kind='set_page' and status in ('validated','superseded','published') and coalesce((validation_json->>'passed')::boolean,false)=true;
  select count(*) into n from public.pokemon_overall_rip_publication_rows where publication_run_id=r.id;
  if n<>r.expected_row_count then raise exception 'publication row count mismatch'; end if;
  select publication_run_id into prior from public.pokemon_overall_rip_current_publication where scope='pokemon' for update;
  if prior is not null and prior<>r.id then
    update public.pokemon_overall_rip_publication_runs set status='superseded' where id=prior;
    update public.pokemon_overall_rip_publication_generations set status='superseded' where publication_run_id=prior and status='published';
  end if;
  update public.pokemon_overall_rip_publication_runs set status='published',published_at=timezone('utc',now()),previous_publication_run_id=coalesce(previous_publication_run_id,prior) where id=r.id;
  update public.pokemon_overall_rip_publication_generations set status='published',published_at=timezone('utc',now()) where id in(rg,sg);
  insert into public.pokemon_overall_rip_current_publication(scope,publication_run_id,rankings_generation_id,set_page_generation_id,activated_at)
  values('pokemon',r.id,rg,sg,timezone('utc',now())) on conflict(scope) do update set publication_run_id=excluded.publication_run_id,rankings_generation_id=excluded.rankings_generation_id,set_page_generation_id=excluded.set_page_generation_id,activated_at=excluded.activated_at;
  return r.id;
end $$;
revoke all on function public.promote_pokemon_overall_rip_publication(uuid) from public,anon,authenticated;
grant execute on function public.promote_pokemon_overall_rip_publication(uuid) to service_role;
