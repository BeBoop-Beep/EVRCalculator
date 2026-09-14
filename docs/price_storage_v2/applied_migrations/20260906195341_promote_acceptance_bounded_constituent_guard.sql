SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='20s';
DO $check$
BEGIN
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'aa3c9ad29d799d35d022c54f7e022317' THEN
    RAISE EXCEPTION 'Concurrent change detected: constituent hybrid definition changed; revalidate before promotion';
  END IF;
  IF md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure)) <> 'cab2e26e26e61a0fdddc1c2cafe17028' THEN
    RAISE EXCEPTION 'Concurrent change detected: V2 constituent implementation changed';
  END IF;
END;
$check$;
CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(
  p_set_ids uuid[],p_start_date date,p_end_date date,p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,
  card_variant_id uuid,source text,captured_at date)
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path=''
SET "TimeZone"='America/Phoenix'
AS $function$
  SELECT * FROM public.get_pokemon_cards_daily_constituents_v2_guarded(
    p_set_ids,p_start_date,p_end_date,p_card_ids
  );
$function$;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[]) TO service_role;
INSERT INTO public.price_storage_v2_migration_audit(phase,details)
VALUES ('constituent_guard_promoted_20260906',jsonb_build_object(
  'production_entrypoint','get_pokemon_cards_daily_constituents',
  'semantics','NULL card filter means all; empty array means none; V2 only within passing acceptance ranges; other portions remain legacy',
  'validated_scenarios',7,'legacy_only_rows',0,'guarded_only_rows',0,
  'scenario_rows',jsonb_build_object('empty',0,'full_history_plus_new_day',35313,'parent_and_subset',920,'mixed_edition_and_modern',1356,'known_selection_exception',688,'duplicate_set_ids',230,'explicit_subset_card',3),
  'role_validation','service_role','overlapping_set_days',0,'missing_set_days',0,
  'raw_history_deleted',false,'persisted_snapshots_rewritten',false,
  'rollback_definition_phase','constituent_guard_staged_20260906'
));
NOTIFY pgrst,'reload schema';