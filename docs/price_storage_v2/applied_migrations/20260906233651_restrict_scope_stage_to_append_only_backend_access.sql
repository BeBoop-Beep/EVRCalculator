SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='15s';
-- Explicitly remove Supabase's inherited service-role defaults on these NEW objects.
REVOKE ALL ON public.price_storage_v2_scope_stage_runs,public.price_storage_v2_scoped_value_candidates,public.price_storage_v2_history_scope_inventory FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.price_storage_v2_scope_stage_runs,public.price_storage_v2_scoped_value_candidates TO service_role;
GRANT SELECT ON public.price_storage_v2_history_scope_inventory TO service_role;
REVOKE ALL ON SEQUENCE public.price_storage_v2_scope_stage_runs_id_seq FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE,SELECT ON SEQUENCE public.price_storage_v2_scope_stage_runs_id_seq TO service_role;
COMMENT ON VIEW public.price_storage_v2_history_scope_inventory IS 'Read-only classification of legacy scope and methodology. No guessed relabeling or recalculation of unresolved historical contracts.';
INSERT INTO public.price_storage_v2_migration_audit(phase,details) VALUES('scope_stage_backend_defaults_restricted',jsonb_build_object('new_stage_objects_only',true,'inventory_view_read_only',true,'candidate_tables_service_insert_select_only',true,'existing_history_privileges_unchanged',true,'production_data_rewritten',false));