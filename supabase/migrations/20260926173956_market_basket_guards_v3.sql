BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='15s';

CREATE FUNCTION public.pokemon_market_catalog_manifest_v3(p_root uuid)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $f$
WITH members AS MATERIALIZED (
 SELECT p_root AS set_id,'root'::text AS member_type
 UNION ALL SELECT id,'counted_subset' FROM public.sets
 WHERE parent_opening_set_id=p_root AND counts_toward_parent_set_value=true
), cards AS MATERIALIZED (
 SELECT c.id AS canonical_card_id,c.set_id AS member_set_id,c.rarity,c.canonical_review_status
 FROM members m JOIN public.pokemon_canonical_cards c ON c.set_id=m.set_id AND c.set_value_eligible=true
), manifest AS (
 SELECT jsonb_build_object(
  'members',(SELECT jsonb_agg(jsonb_build_object('member_set_id',m.set_id,'member_type',m.member_type,'expected_card_count',(SELECT count(*) FROM cards c WHERE c.member_set_id=m.set_id)) ORDER BY m.set_id) FROM members m),
  'cards',coalesce((SELECT jsonb_agg(to_jsonb(c) ORDER BY c.canonical_card_id) FROM cards c),'[]'::jsonb)) AS value
)
SELECT value || jsonb_build_object('fingerprint',encode(sha256(convert_to(value::text,'UTF8')),'hex')) FROM manifest;
$f$;

CREATE FUNCTION public.guard_pokemon_market_registry_v3()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $f$
DECLARE v_profile text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'V3 market identities are immutable; use versioned definitions'; END IF;
 IF NOT EXISTS (SELECT 1 FROM public.sets s JOIN public.pokemon_market_root_authority a ON a.set_id=s.id
   WHERE s.id=NEW.root_set_id AND s.parent_opening_set_id IS NULL AND NOT coalesce(s.catalog_only,false)
   AND a.enabled AND a.activated_market_date<=timezone('America/Phoenix',now())::date
   AND (a.deactivated_market_date IS NULL OR a.deactivated_market_date>timezone('America/Phoenix',now())::date)) THEN
   RAISE EXCEPTION 'V3 market requires an explicitly active root authority';
 END IF;
 SELECT coalesce((SELECT profile FROM public.pokemon_edition_split_root_sets_v2 WHERE set_id=NEW.root_set_id),'standard') INTO v_profile;
 IF NEW.profile IS DISTINCT FROM v_profile THEN RAISE EXCEPTION 'V3 market profile disagrees with registered edition authority'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.conditions WHERE id=NEW.condition_id AND lower(name)='near mint') THEN RAISE EXCEPTION 'V3 price condition must be Near Mint'; END IF;
 RETURN NEW;
END;
$f$;
CREATE TRIGGER guard_pokemon_market_registry_v3 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_registry_v3 FOR EACH ROW EXECUTE FUNCTION public.guard_pokemon_market_registry_v3();

CREATE FUNCTION public.pokemon_market_binding_fingerprint_v3(p_root uuid,p_scope text,p_version integer)
RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $f$
 SELECT encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_object(
  'canonical',canonical_card_id,'member',member_set_id,'variant',card_variant_id,
  'edition',edition,'printing',printing_type,'special',special_type,'identity',identity_basis,
  'resolution',resolution,'candidate_count',candidate_count) ORDER BY canonical_card_id)::text,'[]'),'UTF8')),'hex')
 FROM public.pokemon_market_basket_bindings_v3 WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version;
$f$;

CREATE FUNCTION public.guard_pokemon_market_basket_child_v3()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $f$
DECLARE v_root uuid;v_scope text;v_version integer;v_state text;
BEGIN
 IF TG_OP='DELETE' THEN v_root:=OLD.root_set_id;v_scope:=OLD.market_scope;v_version:=OLD.basket_version;
 ELSE v_root:=NEW.root_set_id;v_scope:=NEW.market_scope;v_version:=NEW.basket_version; END IF;
 IF TG_OP='UPDATE' AND (NEW.root_set_id,NEW.market_scope,NEW.basket_version) IS DISTINCT FROM (OLD.root_set_id,OLD.market_scope,OLD.basket_version) THEN
   RAISE EXCEPTION 'V3 basket rows cannot move between definitions';
 END IF;
 SELECT state INTO v_state FROM public.pokemon_market_basket_versions_v3
 WHERE root_set_id=v_root AND market_scope=v_scope AND basket_version=v_version FOR UPDATE;
 IF v_state IS DISTINCT FROM 'DRAFT' THEN RAISE EXCEPTION 'V3 approved basket membership and variants are immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_TABLE_NAME='pokemon_market_basket_members_v3' THEN
  IF NOT ((NEW.member_set_id=NEW.root_set_id AND NEW.member_type='root') OR
   (NEW.member_type='counted_subset' AND EXISTS(SELECT 1 FROM public.sets WHERE id=NEW.member_set_id AND parent_opening_set_id=NEW.root_set_id AND counts_toward_parent_set_value=true))) THEN
   RAISE EXCEPTION 'V3 member does not belong to the intended parent basket'; END IF;
  IF NEW.expected_card_count<>(SELECT count(*) FROM public.pokemon_canonical_cards WHERE set_id=NEW.member_set_id AND set_value_eligible=true) THEN
   RAISE EXCEPTION 'V3 member expected-card count disagrees with catalog'; END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM public.pokemon_canonical_cards c WHERE c.id=NEW.canonical_card_id AND c.set_id=NEW.member_set_id AND c.set_value_eligible=true) THEN
   RAISE EXCEPTION 'V3 binding does not match an eligible canonical card in this member'; END IF;
  IF NEW.resolution='BOUND' AND NOT EXISTS(
   SELECT 1 FROM public.card_variants v
   JOIN public.pokemon_market_explorer_card_current_metadata m ON m.card_variant_id=v.id AND m.legacy_card_id=v.card_id
   JOIN public.pokemon_canonical_cards c ON c.id=m.canonical_card_id
   WHERE v.id=NEW.card_variant_id AND m.canonical_card_id=NEW.canonical_card_id AND m.set_id=NEW.member_set_id
     AND c.canonical_review_status='approved' AND m.identity_basis=NEW.identity_basis
     AND v.edition IS NOT DISTINCT FROM NEW.edition AND v.printing_type IS NOT DISTINCT FROM NEW.printing_type AND v.special_type IS NOT DISTINCT FROM NEW.special_type
     AND m.edition IS NOT DISTINCT FROM v.edition AND m.printing_type IS NOT DISTINCT FROM v.printing_type AND m.special_type IS NOT DISTINCT FROM v.special_type
  ) THEN RAISE EXCEPTION 'V3 exact variant binding disagrees with reviewed catalog identity'; END IF;
 END IF;
 RETURN NEW;
END;
$f$;
CREATE TRIGGER guard_pokemon_market_basket_members_v3 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_basket_members_v3 FOR EACH ROW EXECUTE FUNCTION public.guard_pokemon_market_basket_child_v3();
CREATE TRIGGER guard_pokemon_market_basket_bindings_v3 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_basket_bindings_v3 FOR EACH ROW EXECUTE FUNCTION public.guard_pokemon_market_basket_child_v3();

CREATE FUNCTION public.guard_pokemon_market_basket_version_v3()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $f$
DECLARE manifest jsonb;v_members integer;v_cards integer;v_bound integer;v_slots integer;v_fp text;
BEGIN
 IF TG_OP='DELETE' THEN
   IF OLD.state='APPROVED' THEN RAISE EXCEPTION 'V3 approved definitions are immutable'; END IF;
   RETURN OLD;
 END IF;
 IF TG_OP='UPDATE' THEN
   IF OLD.state='APPROVED' THEN RAISE EXCEPTION 'V3 approved definitions are immutable'; END IF;
   IF (to_jsonb(NEW)-ARRAY['state','approved_at','binding_fingerprint','evidence']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','approved_at','binding_fingerprint','evidence']) THEN
     RAISE EXCEPTION 'V3 draft definition identity cannot change; stage a new version'; END IF;
 END IF;
 manifest:=public.pokemon_market_catalog_manifest_v3(NEW.root_set_id);
 v_members:=jsonb_array_length(manifest->'members');v_cards:=jsonb_array_length(manifest->'cards');
 IF NEW.catalog_fingerprint IS DISTINCT FROM manifest->>'fingerprint' OR NEW.expected_member_count<>v_members OR NEW.expected_card_count<>v_cards THEN
   RAISE EXCEPTION 'V3 definition does not match complete current catalog membership'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'DRAFT' OR NEW.effective_from<>timezone('America/Phoenix',now())::date THEN
   RAISE EXCEPTION 'V3 initial definition must be a current-day draft, not a fabricated historical basket'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.state='APPROVED' THEN
   SELECT count(*),count(*) FILTER(WHERE resolution='BOUND') INTO v_slots,v_bound
   FROM public.pokemon_market_basket_bindings_v3 WHERE root_set_id=NEW.root_set_id AND market_scope=NEW.market_scope AND basket_version=NEW.basket_version;
   IF v_slots<>v_cards OR v_bound<>v_cards THEN RAISE EXCEPTION 'V3 approval requires every intended card resolved exactly once'; END IF;
   IF (SELECT count(*) FROM public.pokemon_market_basket_members_v3 WHERE root_set_id=NEW.root_set_id AND market_scope=NEW.market_scope AND basket_version=NEW.basket_version)<>v_members
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'members') x WHERE NOT EXISTS(
     SELECT 1 FROM public.pokemon_market_basket_members_v3 m WHERE m.root_set_id=NEW.root_set_id AND m.market_scope=NEW.market_scope AND m.basket_version=NEW.basket_version
      AND m.member_set_id=(x->>'member_set_id')::uuid AND m.member_type=x->>'member_type' AND m.expected_card_count=(x->>'expected_card_count')::integer))
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'cards') x WHERE NOT EXISTS(
     SELECT 1 FROM public.pokemon_market_basket_bindings_v3 b WHERE b.root_set_id=NEW.root_set_id AND b.market_scope=NEW.market_scope AND b.basket_version=NEW.basket_version
      AND b.canonical_card_id=(x->>'canonical_card_id')::uuid AND b.member_set_id=(x->>'member_set_id')::uuid)) THEN
      RAISE EXCEPTION 'V3 approval found omitted or substituted members/cards'; END IF;
   IF EXISTS(SELECT 1 FROM public.pokemon_market_basket_bindings_v3 b
     LEFT JOIN public.card_variants v ON v.id=b.card_variant_id
     LEFT JOIN public.pokemon_canonical_cards c ON c.id=b.canonical_card_id
     WHERE b.root_set_id=NEW.root_set_id AND b.market_scope=NEW.market_scope AND b.basket_version=NEW.basket_version AND (
       v.id IS NULL OR c.canonical_review_status IS DISTINCT FROM 'approved' OR c.set_id IS DISTINCT FROM b.member_set_id
       OR v.edition IS DISTINCT FROM b.edition OR v.printing_type IS DISTINCT FROM b.printing_type OR v.special_type IS DISTINCT FROM b.special_type
       OR NOT EXISTS(SELECT 1 FROM public.pokemon_market_explorer_card_current_metadata m WHERE m.card_variant_id=b.card_variant_id AND m.legacy_card_id=v.card_id AND m.canonical_card_id=b.canonical_card_id AND m.set_id=b.member_set_id AND m.identity_basis=b.identity_basis))) THEN
     RAISE EXCEPTION 'V3 approval detects changed or unreviewed variant identities'; END IF;
   v_fp:=public.pokemon_market_binding_fingerprint_v3(NEW.root_set_id,NEW.market_scope,NEW.basket_version);
   IF NEW.binding_fingerprint IS DISTINCT FROM v_fp THEN RAISE EXCEPTION 'V3 binding fingerprint changed since review'; END IF;
   NEW.approved_at:=now();
 END IF;
 RETURN NEW;
END;
$f$;
CREATE TRIGGER guard_pokemon_market_basket_version_v3 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_basket_versions_v3 FOR EACH ROW EXECUTE FUNCTION public.guard_pokemon_market_basket_version_v3();

REVOKE ALL ON FUNCTION public.pokemon_market_catalog_manifest_v3(uuid),public.guard_pokemon_market_registry_v3(),public.pokemon_market_binding_fingerprint_v3(uuid,text,integer),public.guard_pokemon_market_basket_child_v3(),public.guard_pokemon_market_basket_version_v3() FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
