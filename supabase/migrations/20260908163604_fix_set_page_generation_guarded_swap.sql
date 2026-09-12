create or replace function public.activate_pokemon_set_page_snapshot_generation(p_generation_id uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare g public.pokemon_set_page_snapshot_generations%rowtype; prior uuid; n int;
begin
 select * into g from public.pokemon_set_page_snapshot_generations where id=p_generation_id for update;
 if not found or g.status not in('validated','published') or not g.validation_passed or coalesce((g.validation_json->>'passed')::boolean,false)=false then raise exception 'generation % is not validated',p_generation_id; end if;
 select generation_id into prior from public.pokemon_set_page_snapshot_current_generation where scope='pokemon' for update;
 select count(*) into n from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 if n<>g.expected_set_count then raise exception 'generation % became incomplete',p_generation_id; end if;
 delete from public.pokemon_set_page_snapshot_latest where set_id is not null;
 insert into public.pokemon_set_page_snapshot_latest select set_id,set_identity_json,title_card_json,rip_summary_json,market_summary_json,risk_summary_json,concentration_json,desirability_summary_json,set_intelligence_json,payload_json,as_of,source_updated_at,created_at,updated_at,rip_bootstrap_json,rip_simulation_evidence_json,rip_advanced_json from public.pokemon_set_page_snapshot_generation_rows where generation_id=p_generation_id;
 insert into public.pokemon_set_page_snapshot_current_generation(scope,generation_id,activated_at) values('pokemon',p_generation_id,timezone('utc',now())) on conflict(scope) do update set generation_id=excluded.generation_id,activated_at=excluded.activated_at;
 update public.pokemon_set_page_snapshot_generations set status='published',previous_generation_id=case when prior is distinct from p_generation_id then prior else previous_generation_id end,published_at=coalesce(published_at,timezone('utc',now())) where id=p_generation_id;
 return p_generation_id;
end $$;
revoke all on function public.activate_pokemon_set_page_snapshot_generation(uuid) from public,anon,authenticated;
grant execute on function public.activate_pokemon_set_page_snapshot_generation(uuid) to service_role;
alter function public.activate_pokemon_set_page_snapshot_generation(uuid) set statement_timeout='180s';
