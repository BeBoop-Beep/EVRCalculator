revoke all privileges on table public.pokemon_market_explorer_options_snapshots from service_role;
grant select, insert, update on table public.pokemon_market_explorer_options_snapshots to service_role;

revoke all privileges on sequence public.pokemon_market_explorer_options_snapshots_id_seq from service_role;
grant usage, select on sequence public.pokemon_market_explorer_options_snapshots_id_seq to service_role;
