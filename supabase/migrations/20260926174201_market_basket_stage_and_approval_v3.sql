BEGIN;
SET LOCAL lock_timeout='1s'; SET LOCAL statement_timeout='12s';
CREATE FUNCTION public.inspect_pokemon_market_basket_v3(p_root uuid,p_scope text,p_version integer)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
 SELECT jsonb_build_object('rootSetId',v.root_set_id,'marketScope',v.market_scope,'basketVersion',v.basket_version,'effectiveFrom',v.effective_from,'state',v.state,'expectedMembers',v.expected_member_count,'expectedCards',v.expected_card_count,'catalogFingerprint',v.catalog_fingerprint,'bindingFingerprint',public.pokemon_market_binding_fingerprint_v3(p_root,p_scope,p_version),
 'resolutionCounts',(SELECT coalesce(jsonb_object_agg(resolution,n),'{}'::jsonb) FROM(SELECT resolution,count(*) AS n FROM public.pokemon_market_basket_bindings_v3 WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version GROUP BY resolution)c),
 'members',(SELECT jsonb_agg(jsonb_build_object('memberSetId',m.member_set_id,'kind',m.member_type,'expectedCards',m.expected_card_count) ORDER BY member_set_id) FROM public.pokemon_market_basket_members_v3 m WHERE m.root_set_id=p_root AND m.market_scope=p_scope AND m.basket_version=p_version))
 FROM public.pokemon_market_basket_versions_v3 v WHERE v.root_set_id=p_root AND v.market_scope=p_scope AND v.basket_version=p_version;
$f$;

CREATE FUNCTION public.stage_pokemon_market_basket_v3(p_root uuid,p_scope text,p_request_key text,p_evidence text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET statement_timeout='8s' SET lock_timeout='1s' AS $f$
DECLARE manifest jsonb;v_version integer;v_existing public.pokemon_market_basket_versions_v3%ROWTYPE;v_count integer;
BEGIN
 IF p_root IS NULL OR p_scope IS NULL OR p_request_key IS NULL OR length(p_request_key) NOT BETWEEN 8 AND 180 OR p_evidence IS NULL OR length(p_evidence) NOT BETWEEN 12 AND 4000 THEN RAISE EXCEPTION 'V3 staging requires an explicit market, request key and evidence'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('market-v3-definition:'||p_root::text||':'||p_scope,0)) THEN RAISE EXCEPTION 'V3 market definition task already active' USING ERRCODE='55P03'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.pokemon_market_registry_v3 WHERE root_set_id=p_root AND market_scope=p_scope) THEN RAISE EXCEPTION 'V3 unknown market: Standard fallback is forbidden'; END IF;
 SELECT * INTO v_existing FROM public.pokemon_market_basket_versions_v3 WHERE request_key=p_request_key;
 IF FOUND THEN
  IF v_existing.root_set_id<>p_root OR v_existing.market_scope<>p_scope THEN RAISE EXCEPTION 'V3 request key already belongs to a different market'; END IF;
  RETURN public.inspect_pokemon_market_basket_v3(p_root,p_scope,v_existing.basket_version);
 END IF;
 manifest:=public.pokemon_market_catalog_manifest_v3(p_root);
 v_count:=jsonb_array_length(manifest->'cards');
 IF v_count<1 OR v_count>2500 THEN RAISE EXCEPTION 'V3 expected card count outside bounded staging range: %',v_count; END IF;
 SELECT coalesce(max(basket_version),0)+1 INTO v_version FROM public.pokemon_market_basket_versions_v3 WHERE root_set_id=p_root AND market_scope=p_scope;
 INSERT INTO public.pokemon_market_basket_versions_v3(root_set_id,market_scope,basket_version,effective_from,definition_basis,expected_member_count,expected_card_count,catalog_fingerprint,request_key,evidence)
 VALUES(p_root,p_scope,v_version,timezone('America/Phoenix',now())::date,'current_catalog_staged_v1',jsonb_array_length(manifest->'members'),v_count,manifest->>'fingerprint',p_request_key,p_evidence);
 INSERT INTO public.pokemon_market_basket_members_v3(root_set_id,market_scope,basket_version,member_set_id,member_type,expected_card_count)
 SELECT p_root,p_scope,v_version,(x->>'member_set_id')::uuid,x->>'member_type',(x->>'expected_card_count')::integer FROM jsonb_array_elements(manifest->'members') x;
 WITH cards AS MATERIALIZED (
  SELECT * FROM jsonb_to_recordset(manifest->'cards') AS c(canonical_card_id uuid,member_set_id uuid,rarity text,canonical_review_status text)
 ), candidates AS MATERIALIZED (
  SELECT DISTINCT c.canonical_card_id,m.card_variant_id,v.edition,v.printing_type,v.special_type,m.identity_basis,
   CASE m.identity_basis WHEN 'explicit_legacy_identity_link' THEN 0 WHEN 'parent_pokemon_tcg_api_id' THEN 1 WHEN 'normalized_name_number_fallback' THEN 2 ELSE 9 END AS identity_priority,
   CASE WHEN c.rarity IN ('Common','Uncommon') THEN CASE v.printing_type WHEN 'non-holo' THEN 0 WHEN 'holo' THEN 1 ELSE 9 END ELSE CASE v.printing_type WHEN 'holo' THEN 0 WHEN 'non-holo' THEN 1 ELSE 9 END END AS printing_priority
  FROM cards c JOIN public.pokemon_market_explorer_card_current_metadata m ON m.canonical_card_id=c.canonical_card_id AND m.set_id=c.member_set_id
  JOIN public.card_variants v ON v.id=m.card_variant_id AND v.card_id=m.legacy_card_id
  WHERE m.identity_basis IN ('explicit_legacy_identity_link','parent_pokemon_tcg_api_id','normalized_name_number_fallback')
    AND m.edition IS NOT DISTINCT FROM v.edition AND m.printing_type IS NOT DISTINCT FROM v.printing_type AND m.special_type IS NOT DISTINCT FROM v.special_type
    AND coalesce(v.special_type,'')='' AND (v.printing_type IS NULL OR v.printing_type IN ('holo','non-holo'))
    AND ((p_scope='first_edition' AND v.edition='1st-edition') OR (p_scope='unlimited' AND v.edition='unlimited') OR (p_scope='shadowless' AND v.edition='shadowless') OR (p_scope='standard' AND coalesce(v.edition,'') IN ('','unlimited')))
 ), ranked AS (
  SELECT *,dense_rank() OVER(PARTITION BY canonical_card_id ORDER BY identity_priority,printing_priority) AS preference FROM candidates
 ), best AS (
  SELECT canonical_card_id,count(*)::integer AS n,jsonb_agg(to_jsonb(r))->0 AS choice FROM ranked r WHERE preference=1 GROUP BY canonical_card_id
 ), resolved AS (
  SELECT c.*,coalesce(b.n,0) AS n,b.choice,CASE WHEN c.canonical_review_status IS DISTINCT FROM 'approved' THEN 'REVIEW_REQUIRED' WHEN coalesce(b.n,0)=0 THEN 'MISSING' WHEN b.n>1 THEN 'AMBIGUOUS' ELSE 'BOUND' END AS resolution FROM cards c LEFT JOIN best b USING(canonical_card_id)
 )
 INSERT INTO public.pokemon_market_basket_bindings_v3(root_set_id,market_scope,basket_version,member_set_id,canonical_card_id,card_variant_id,edition,printing_type,special_type,identity_basis,resolution,candidate_count)
 SELECT p_root,p_scope,v_version,member_set_id,canonical_card_id,
  CASE WHEN resolution='BOUND' THEN (choice->>'card_variant_id')::uuid END,
  CASE WHEN resolution='BOUND' THEN choice->>'edition' END,
  CASE WHEN resolution='BOUND' THEN choice->>'printing_type' END,
  CASE WHEN resolution='BOUND' THEN choice->>'special_type' END,
  CASE WHEN resolution='BOUND' THEN choice->>'identity_basis' END,resolution,n
 FROM resolved;
 RETURN public.inspect_pokemon_market_basket_v3(p_root,p_scope,v_version);
END;
$f$;

CREATE FUNCTION public.approve_pokemon_market_basket_v3(p_root uuid,p_scope text,p_version integer,p_catalog_fingerprint text,p_binding_fingerprint text,p_review_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET statement_timeout='8s' SET lock_timeout='1s' AS $f$
DECLARE v public.pokemon_market_basket_versions_v3%ROWTYPE;
BEGIN
 IF p_review_note IS NULL OR length(p_review_note) NOT BETWEEN 12 AND 1800 OR p_catalog_fingerprint IS NULL OR p_binding_fingerprint IS NULL THEN RAISE EXCEPTION 'V3 approval requires both reviewed fingerprints and a review note'; END IF;
 SELECT * INTO v FROM public.pokemon_market_basket_versions_v3 WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'V3 basket version not found'; END IF;
 IF v.catalog_fingerprint IS DISTINCT FROM p_catalog_fingerprint OR public.pokemon_market_binding_fingerprint_v3(p_root,p_scope,p_version) IS DISTINCT FROM p_binding_fingerprint THEN RAISE EXCEPTION 'V3 approval fingerprint mismatch'; END IF;
 IF v.state='APPROVED' THEN RETURN public.inspect_pokemon_market_basket_v3(p_root,p_scope,p_version); END IF;
 UPDATE public.pokemon_market_basket_versions_v3 SET state='APPROVED',binding_fingerprint=p_binding_fingerprint,approved_at=now(),evidence=evidence||E'\nAPPROVAL: '||p_review_note WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version;
 RETURN public.inspect_pokemon_market_basket_v3(p_root,p_scope,p_version);
END;
$f$;
REVOKE ALL ON FUNCTION public.inspect_pokemon_market_basket_v3(uuid,text,integer),public.stage_pokemon_market_basket_v3(uuid,text,text,text),public.approve_pokemon_market_basket_v3(uuid,text,integer,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.inspect_pokemon_market_basket_v3(uuid,text,integer) TO service_role;
COMMENT ON FUNCTION public.stage_pokemon_market_basket_v3(uuid,text,text,text) IS 'Operator-only bounded staging from current catalog. Does not select by price/date; unresolved top-priority ties remain unbound. No production publication.';
COMMENT ON FUNCTION public.approve_pokemon_market_basket_v3(uuid,text,integer,text,text,text) IS 'Operator-only complete identity approval with compare-and-set fingerprints. All approved members/bindings become immutable.';
COMMIT;
