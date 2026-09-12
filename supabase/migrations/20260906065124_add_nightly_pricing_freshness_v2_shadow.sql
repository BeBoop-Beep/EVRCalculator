do $$
declare
  v_def text;
begin
  select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness(date,integer)'::regprocedure) into v_def;
  v_def:=replace(v_def,'FUNCTION public.get_nightly_snapshot_pricing_freshness(','FUNCTION public.get_nightly_snapshot_pricing_freshness_v2_shadow(');
  v_def:=replace(v_def,'FROM public.card_variant_price_observations o','FROM public.card_variant_price_observation_ranges_v2 o');
  v_def:=replace(v_def,'AND o.captured_date = v_snapshot_date','AND o.observed_from <= v_snapshot_date
          AND o.observed_through >= v_snapshot_date');
  v_def:=replace(v_def,'card_variant_price_observations(captured_date derived from captured_at)','card_variant_price_observation_ranges_v2(observed_from/observed_through)');
  execute v_def;
end
$$;
revoke all on function public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer) to postgres,service_role;