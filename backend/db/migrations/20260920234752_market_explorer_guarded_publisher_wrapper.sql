-- Narrow SECURITY DEFINER bridge for the VM's dedicated Market Explorer
-- publisher login. The login itself is operational secret state and is not
-- created or passworded by repository migration source.

create or replace function public.run_market_explorer_guarded_publisher_v1(
  p_required_market_date date
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if p_required_market_date is null then
    raise exception 'required Market Explorer prepared market date must not be null';
  end if;
  return public.refresh_pokemon_market_explorer_prepared_if_current_v1(
    p_required_market_date
  );
end;
$function$;

alter function public.run_market_explorer_guarded_publisher_v1(date) owner to postgres;

revoke all on function public.run_market_explorer_guarded_publisher_v1(date) from public;
revoke all on function public.run_market_explorer_guarded_publisher_v1(date) from anon;
revoke all on function public.run_market_explorer_guarded_publisher_v1(date) from authenticated;
revoke all on function public.run_market_explorer_guarded_publisher_v1(date) from service_role;
