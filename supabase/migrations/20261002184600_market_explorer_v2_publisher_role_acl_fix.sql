-- Fix the unattended Market Explorer V2 serving handoff.
--
-- The maintained-cache worker connects through the dedicated
-- market_explorer_publisher database role. The V2 current publisher is a
-- no-argument bounded wrapper owned by postgres with an empty search_path,
-- but it was SECURITY INVOKER and executable only by service_role. That made
-- the direct worker fail with SQLSTATE 42501 after the prepared generation
-- had refreshed, leaving the public V2 serving generation one market day
-- behind.
--
-- Keep the lower-level core publisher private. Only elevate this bounded
-- no-argument wrapper and grant the dedicated publisher role access.

alter function public.publish_pokemon_market_explorer_surface_current_v2()
  owner to postgres;

alter function public.publish_pokemon_market_explorer_surface_current_v2()
  security definer;

revoke all on function public.publish_pokemon_market_explorer_surface_current_v2()
  from public, anon, authenticated;

grant execute on function public.publish_pokemon_market_explorer_surface_current_v2()
  to service_role, market_explorer_publisher;
