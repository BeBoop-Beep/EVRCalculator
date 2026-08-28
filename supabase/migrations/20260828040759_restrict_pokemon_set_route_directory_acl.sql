revoke all on function public.get_pokemon_set_route_directory(integer) from public;
revoke execute on function public.get_pokemon_set_route_directory(integer) from anon, authenticated;
grant execute on function public.get_pokemon_set_route_directory(integer) to service_role;
