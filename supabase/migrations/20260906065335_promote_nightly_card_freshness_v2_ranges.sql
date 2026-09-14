do $$
declare
  v_def text;
begin
  if to_regprocedure('public.get_nightly_snapshot_pricing_freshness_raw_card_shadow(date,integer)') is null then
    select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness(date,integer)'::regprocedure) into v_def;
    v_def:=replace(v_def,'FUNCTION public.get_nightly_snapshot_pricing_freshness(','FUNCTION public.get_nightly_snapshot_pricing_freshness_raw_card_shadow(');
    execute v_def;
  end if;

  select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer)'::regprocedure) into v_def;
  v_def:=replace(v_def,'FUNCTION public.get_nightly_snapshot_pricing_freshness_v2_shadow(','FUNCTION public.get_nightly_snapshot_pricing_freshness(');
  execute v_def;
end
$$;
revoke all on function public.get_nightly_snapshot_pricing_freshness_raw_card_shadow(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness_raw_card_shadow(date,integer) to postgres,service_role;
revoke all on function public.get_nightly_snapshot_pricing_freshness(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness(date,integer) to postgres,service_role;