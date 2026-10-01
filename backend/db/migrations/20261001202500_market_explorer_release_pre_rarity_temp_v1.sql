begin;

-- Candidate builds are one outer transaction. Earlier staging functions keep
-- publication-only temp tables with ON COMMIT DROP, so those tables survive
-- until the entire candidate finishes. By the time rarity staging materializes
-- ~2.5M historical membership rows, those completed scoped/standard/raw temp
-- relations are dead weight and materially slow temp I/O.
--
-- None of these temp relations is part of a cross-stage contract: each owning
-- stage has already persisted its directory/history/constituent output before
-- returning. Release them before the large rarity materialization while
-- preserving the candidate's single atomic transaction.
create or replace function public.release_pokemon_market_explorer_pre_rarity_temp_v1()
returns void
language plpgsql
volatile
security invoker
set search_path=''
as $function$
begin
  drop table if exists pg_temp._mx_scoped_current;
  drop table if exists pg_temp._mx_scoped_roster;
  drop table if exists pg_temp._mx_scoped_leaves;
  drop table if exists pg_temp._mx_standard_markets;
  drop table if exists pg_temp._mx_standard_perf;
  drop table if exists pg_temp._mx_raw_stable_leaves;
end;
$function$;

revoke all on function public.release_pokemon_market_explorer_pre_rarity_temp_v1()
from public,anon,authenticated;
grant execute on function public.release_pokemon_market_explorer_pre_rarity_temp_v1()
to service_role;

-- Inject the cleanup at the start of the already-optimized rarity function
-- without changing its data contract.
do $body$
declare
  v_def text;
  v_old text := 'begin' || chr(10) ||
                '  drop table if exists pg_temp._mx_rarity_members;';
  v_new text := 'begin' || chr(10) ||
                '  perform public.release_pokemon_market_explorer_pre_rarity_temp_v1();' || chr(10) ||
                '  drop table if exists pg_temp._mx_rarity_members;';
begin
  select pg_get_functiondef(
    'public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)'::regprocedure
  ) into v_def;

  if position(v_new in v_def)>0 then
    return;
  end if;
  if position(v_old in v_def)=0 then
    raise exception 'RARITY_STAGE_CLEANUP_PATCH_TARGET_NOT_FOUND';
  end if;

  execute replace(v_def,v_old,v_new);
end;
$body$;

commit;
