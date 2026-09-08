begin;
do $$
declare prior uuid; after_id uuid; bad uuid; ids uuid[];
begin
 select generation_id into prior from public.pokemon_set_page_snapshot_current_generation where scope='pokemon';
 select expected_set_ids into ids from public.pokemon_set_page_snapshot_generations where id=prior;
 insert into public.pokemon_set_page_snapshot_generations(expected_set_ids,expected_set_count) values(ids,cardinality(ids)) returning id into bad;
 begin perform public.activate_pokemon_set_page_snapshot_generation(bad); raise exception 'expected invalid activation failure'; exception when others then if sqlerrm='expected invalid activation failure' then raise; end if; end;
 select generation_id into after_id from public.pokemon_set_page_snapshot_current_generation where scope='pokemon';
 if after_id<>prior then raise exception 'failed activation changed active generation'; end if;

 perform public.activate_pokemon_set_page_snapshot_generation('43993358-02cf-409d-8e16-74145b7803b7');
 if (select count(*) from public.pokemon_set_page_snapshot_latest)<>210 then raise exception 'activation did not swap complete cohort'; end if;
 perform public.activate_pokemon_set_page_snapshot_generation(prior);
 select generation_id into after_id from public.pokemon_set_page_snapshot_current_generation where scope='pokemon';
 if after_id<>prior or (select count(*) from public.pokemon_set_page_snapshot_latest)<>210 then raise exception 'rollback did not restore complete prior generation'; end if;
end $$;
rollback;
