begin;

create function pg_temp.c6a_fail() returns trigger language plpgsql as $$
begin raise exception 'C6A injected publication failure'; end $$;

-- A validation/incomplete-output failure must not touch the pointer.
do $$
declare before_id uuid; after_id uuid; fixture uuid;
begin
 select model_run_id into before_id from public.pokemon_collector_appeal_current where scope='pokemon';
 insert into public.pokemon_collector_appeal_model_runs(model_version,status,as_of_date,source_run_ids,input_fingerprint,scoring_config_json,validation_passed,validation_json)
 values('c6a_atomicity_invalid_fixture','validated',current_date,array['b3997343-1363-45aa-b1b0-9a6de1ce3793'::uuid],'fixture-invalid',jsonb_build_object('topLevelInputFingerprint','fixture-invalid'),true,'{"passed":true}') returning id into fixture;
 begin perform public.promote_pokemon_collector_appeal_model_run(fixture); raise exception 'expected incomplete-output failure'; exception when others then if sqlerrm='expected incomplete-output failure' then raise; end if; end;
 select model_run_id into after_id from public.pokemon_collector_appeal_current where scope='pokemon';
 if before_id is distinct from after_id then raise exception 'pointer changed on validation/output failure'; end if;
end $$;

-- Inject a history failure while promoting the real validated shadow. The
-- function's earlier status update must roll back with it.
create trigger c6a_fail_history before insert on public.pokemon_set_collector_appeal_history for each statement execute function pg_temp.c6a_fail();
do $$
declare before_id uuid; after_id uuid; before_history bigint; after_history bigint; shadow_status text;
begin
 select model_run_id into before_id from public.pokemon_collector_appeal_current where scope='pokemon';
 select count(*) into before_history from public.pokemon_set_collector_appeal_history;
 begin perform public.promote_pokemon_collector_appeal_model_run('0efa3c8f-918d-49d7-ad5e-3ae37278058f'); raise exception 'expected history failure'; exception when others then if sqlerrm='expected history failure' then raise; end if; end;
 select model_run_id into after_id from public.pokemon_collector_appeal_current where scope='pokemon'; select count(*) into after_history from public.pokemon_set_collector_appeal_history;
 select status into shadow_status from public.pokemon_collector_appeal_model_runs where id='0efa3c8f-918d-49d7-ad5e-3ae37278058f';
 if before_id is distinct from after_id or before_history<>after_history or shadow_status<>'validated' then raise exception 'history failure left partial publication'; end if;
end $$;
drop trigger c6a_fail_history on public.pokemon_set_collector_appeal_history;

-- Inject failure at the final pointer write. History and published state must
-- both roll back, leaving the old pointer readable.
create trigger c6a_fail_current before insert or update on public.pokemon_collector_appeal_current for each statement execute function pg_temp.c6a_fail();
do $$
declare before_id uuid; after_id uuid; before_history bigint; after_history bigint; shadow_status text;
begin
 select model_run_id into before_id from public.pokemon_collector_appeal_current where scope='pokemon'; select count(*) into before_history from public.pokemon_set_collector_appeal_history;
 begin perform public.promote_pokemon_collector_appeal_model_run('0efa3c8f-918d-49d7-ad5e-3ae37278058f'); raise exception 'expected pointer failure'; exception when others then if sqlerrm='expected pointer failure' then raise; end if; end;
 select model_run_id into after_id from public.pokemon_collector_appeal_current where scope='pokemon'; select count(*) into after_history from public.pokemon_set_collector_appeal_history;
 select status into shadow_status from public.pokemon_collector_appeal_model_runs where id='0efa3c8f-918d-49d7-ad5e-3ae37278058f';
 if before_id is distinct from after_id or before_history<>after_history or shadow_status<>'validated' then raise exception 'pointer failure left partial publication'; end if;
end $$;

rollback;
