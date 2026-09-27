-- Explicit operator-only bootstrap. Already executed for the 2026-09-26 checkpoint.
-- It is intentionally NOT an unattended price-driven registry refresh.
BEGIN; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='1s';
DO $seed$ BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('pokemon-market-v3-registry-seed',0)) THEN RAISE EXCEPTION 'Another V3 registry seeder is active'; END IF;
 IF (SELECT count(*) FROM public.conditions WHERE lower(name)='near mint')<>1 THEN RAISE EXCEPTION 'Near Mint condition is not unique'; END IF;
END $seed$;
WITH active AS (SELECT a.set_id,min(a.activated_market_date) AS activated_market_date FROM public.pokemon_market_root_authority a JOIN public.sets s ON s.id=a.set_id WHERE a.enabled AND a.activated_market_date<=timezone('America/Phoenix',now())::date AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>timezone('America/Phoenix',now())::date) AND s.parent_opening_set_id IS NULL AND NOT coalesce(s.catalog_only,false) GROUP BY a.set_id), expanded AS (SELECT a.*,coalesce(r.profile,'standard') AS profile,scope.market_scope FROM active a LEFT JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=a.set_id CROSS JOIN LATERAL unnest(CASE r.profile WHEN 'base_three_printings' THEN ARRAY['first_edition','unlimited','shadowless'] WHEN 'edition_split' THEN ARRAY['first_edition','unlimited'] ELSE ARRAY['standard'] END) scope(market_scope))
INSERT INTO public.pokemon_market_registry_v3(root_set_id,market_scope,profile,condition_id,registered_authority_date) SELECT e.set_id,e.market_scope,e.profile,c.id,e.activated_market_date FROM expanded e CROSS JOIN public.conditions c WHERE lower(c.name)='near mint' ON CONFLICT(root_set_id,market_scope) DO NOTHING;
SELECT market_scope,count(*) FROM public.pokemon_market_registry_v3 GROUP BY market_scope ORDER BY market_scope;
COMMIT;
