create or replace view public.graded_card_market_latest
with (security_invoker=true)
as
select distinct on (gcv.id)
    c.id as card_id,
    c.name,
    c.set_id,
    c.rarity,
    cv.id as variant_id,
    cv.printing_type,
    cv.special_type,
    cv.edition,
    gcv.id as graded_card_variant_id,
    gcv.grade_value,
    gcv.special_label,
    gc.id as grading_company_id,
    gc.name as grading_company_name,
    p.market_price,
    p.low_price,
    p.high_price,
    p.created_at,
    p.captured_at
from public.graded_card_variants gcv
join public.cards c on c.id=gcv.card_id
join public.card_variants cv on cv.id=gcv.card_variant_id
join public.grading_companies gc on gc.id=gcv.grading_company_id
join public.graded_card_variant_price_observations p on p.graded_card_variant_id=gcv.id
order by gcv.id,p.created_at desc;

do $$
declare
  v_def text;
begin
  if to_regprocedure('public.get_nightly_snapshot_pricing_freshness_legacy_shadow(date,integer)') is null then
    select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness(date,integer)'::regprocedure) into v_def;
    v_def:=replace(v_def,'FUNCTION public.get_nightly_snapshot_pricing_freshness(','FUNCTION public.get_nightly_snapshot_pricing_freshness_legacy_shadow(');
    execute v_def;
  end if;

  select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness(date,integer)'::regprocedure) into v_def;
  v_def:=replace(v_def,'FROM public.graded_card_market_latest g','FROM public.graded_card_variant_price_observations g');
  v_def:=replace(v_def,'AND g.captured_at >= v_day_start','AND g.captured_date = v_snapshot_date');
  v_def:=replace(v_def,'AND g.captured_at < v_day_end','AND true');
  v_def:=replace(v_def,'graded_card_market_latest(captured_at)','graded_card_variant_price_observations(captured_date)');
  execute v_def;

  select pg_get_functiondef('public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer)'::regprocedure) into v_def;
  v_def:=replace(v_def,'FROM public.graded_card_market_latest g','FROM public.graded_card_variant_price_observations g');
  v_def:=replace(v_def,'AND g.captured_at >= v_day_start','AND g.captured_date = v_snapshot_date');
  v_def:=replace(v_def,'AND g.captured_at < v_day_end','AND true');
  v_def:=replace(v_def,'graded_card_market_latest(captured_at)','graded_card_variant_price_observations(captured_date)');
  execute v_def;
end
$$;

revoke all on function public.get_nightly_snapshot_pricing_freshness_legacy_shadow(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness_legacy_shadow(date,integer) to postgres,service_role;
revoke all on function public.get_nightly_snapshot_pricing_freshness(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness(date,integer) to postgres,service_role;
revoke all on function public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer) from public,anon,authenticated;
grant execute on function public.get_nightly_snapshot_pricing_freshness_v2_shadow(date,integer) to postgres,service_role;