-- READ ONLY. Produces the exact JSON consumed by audit_pokemon_level_schema_parity.py.
WITH wanted_tables(name) AS (VALUES
 ('pokemon_market_index_daily_history'), ('pokemon_rip_stats_snapshots'),
 ('pokemon_rip_stats_snapshot_sets'), ('pokemon_rip_stats_snapshot_latest')
), table_inventory AS (
 SELECT c.relname AS name, jsonb_build_object(
   'columns', (SELECT jsonb_agg(jsonb_build_object('name',a.attname,'udt',t.typname,
      'nullable',NOT a.attnotnull,'default',pg_get_expr(ad.adbin,ad.adrelid)) ORDER BY a.attnum)
     FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
     LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum
     WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
   'constraints', (SELECT COALESCE(jsonb_agg(pg_get_constraintdef(co.oid,true) ORDER BY co.contype,co.oid),'[]'::jsonb)
     FROM pg_constraint co WHERE co.conrelid=c.oid),
   'indexes', (SELECT COALESCE(jsonb_agg(pg_get_indexdef(i.indexrelid) ORDER BY i.indexrelid),'[]'::jsonb)
     FROM pg_index i WHERE i.indrelid=c.oid),
   'rlsEnabled', c.relrowsecurity) AS value
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN wanted_tables w ON w.name=c.relname
 WHERE n.nspname='public'
), policy_inventory AS (
 SELECT COALESCE(jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,
   'roles',to_jsonb(roles),'command',cmd,'using',qual) ORDER BY tablename,policyname),'[]'::jsonb) AS value
 FROM pg_policies WHERE schemaname='public' AND tablename IN (SELECT name FROM wanted_tables)
), grant_inventory AS (
 SELECT COALESCE(jsonb_agg(jsonb_build_object('table',table_name,'grantee',grantee,'privileges',privileges)
   ORDER BY table_name,grantee),'[]'::jsonb) AS value FROM (
   SELECT table_name,grantee,jsonb_agg(privilege_type ORDER BY privilege_type) AS privileges
   FROM information_schema.table_privileges WHERE table_schema='public' AND table_name IN (SELECT name FROM wanted_tables)
   GROUP BY table_name,grantee) grants
), trigger_inventory AS (
 SELECT COALESCE((SELECT jsonb_build_object('table',event_object_table,'timing',action_timing,
   'events',jsonb_agg(event_manipulation ORDER BY event_manipulation),
   'function',regexp_replace(action_statement,'.*EXECUTE FUNCTION ([^(]+)\(\).*','\1'))
   FROM information_schema.triggers WHERE trigger_schema='public'
     AND event_object_table='pokemon_market_index_daily_history'
     AND trigger_name='trg_pokemon_market_index_updated_at'
   GROUP BY event_object_table,action_timing,action_statement),'{}'::jsonb) AS value
), function_inventory AS (
 SELECT COALESCE((SELECT jsonb_build_object('prosecdef',p.prosecdef,
   'securityType',CASE WHEN p.prosecdef THEN 'DEFINER' ELSE 'INVOKER' END,
   'definition',pg_get_functiondef(p.oid),'executeRoles',COALESCE((SELECT jsonb_agg(grantee ORDER BY grantee)
      FROM information_schema.routine_privileges rp WHERE rp.specific_schema='public'
        AND rp.routine_name='publish_pokemon_rip_stats_snapshot' AND rp.privilege_type='EXECUTE'),'[]'::jsonb))
   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND p.proname='publish_pokemon_rip_stats_snapshot'
     AND pg_get_function_identity_arguments(p.oid)='p_snapshot jsonb, p_constituents jsonb'),'{}'::jsonb) AS value
), migration_inventory AS (
 SELECT COALESCE(jsonb_agg(version ORDER BY version),'[]'::jsonb) AS value
 FROM supabase_migrations.schema_migrations WHERE version IN ('20260818032645','20260818032648')
)
SELECT jsonb_pretty(jsonb_build_object(
 'tables',(SELECT jsonb_object_agg(name,value) FROM table_inventory),
 'policies',(SELECT value FROM policy_inventory), 'grants',(SELECT value FROM grant_inventory),
 'trigger',(SELECT value FROM trigger_inventory), 'function',(SELECT value FROM function_inventory),
 'migrationVersions',(SELECT value FROM migration_inventory)));
