-- PostgreSQL identifiers are limited to 63 bytes. The previous migration's
-- 64-byte wrapper name was truncated, so PostgREST could not resolve the
-- worker's requested RPC. Keep the validated publisher and use a short name.
create or replace function public.refresh_pokemon_market_explorer_prepared_if_current_v1(
  p_required_market_date date
)
returns jsonb
language plpgsql volatile security invoker set search_path = ''
as $$
declare
  v_result jsonb;
  v_comparison_asof date;
begin
  if p_required_market_date is null then
    raise exception 'required Market Explorer prepared market date must not be null';
  end if;
  v_result := public.refresh_pokemon_market_explorer_prepared_directory_v1();
  v_comparison_asof := nullif(v_result->>'comparisonAsOf','')::date;
  if v_comparison_asof is distinct from p_required_market_date then
    raise exception 'Market Explorer prepared generation not current: comparisonAsOf=% required=%',
      coalesce(v_comparison_asof::text,'null'),p_required_market_date::text;
  end if;
  return v_result;
end;
$$;
revoke all on function public.refresh_pokemon_market_explorer_prepared_if_current_v1(date)
  from public, anon, authenticated;
grant execute on function public.refresh_pokemon_market_explorer_prepared_if_current_v1(date)
  to service_role;
drop function public.refresh_pokemon_market_explorer_prepared_directory_if_current_v(date);
