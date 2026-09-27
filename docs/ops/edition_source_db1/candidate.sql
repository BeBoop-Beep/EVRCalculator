BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='12s';
SELECT pg_advisory_xact_lock(hashtextextended('edition-source-db1-schema',0));

-- Candidate-only additions. No existing authority, writer, basket or pointer changes.
CREATE TABLE public.pokemon_market_source_captures_v1 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_set_id uuid NOT NULL REFERENCES public.sets(id),
 provider text NOT NULL CHECK(provider='tcgplayer'),
 catalog_group_id bigint NOT NULL CHECK(catalog_group_id>0),
 source_reference text NOT NULL,
 captured_at timestamptz NOT NULL,
 body_sha256 text NOT NULL CHECK(body_sha256 ~ '^[0-9a-f]{64}$'),
 row_count integer NOT NULL CHECK(row_count BETWEEN 1 AND 100000),
 artifact_reference text NOT NULL CHECK(length(artifact_reference) BETWEEN 12 AND 2000),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(provider,catalog_group_id,captured_at,body_sha256)
);
CREATE TABLE public.pokemon_market_source_contracts_v1 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 root_set_id uuid NOT NULL,
 market_scope text NOT NULL,
 source_set_id uuid NOT NULL REFERENCES public.sets(id),
 catalog_group_id bigint NOT NULL,
 capture_id uuid NOT NULL REFERENCES public.pokemon_market_source_captures_v1(id),
 contract_version integer NOT NULL CHECK(contract_version>0),
 raw_edition text NOT NULL CHECK(raw_edition IN ('','1st-edition','unlimited','shadowless')),
 normalization_policy text NOT NULL CHECK(normalization_policy IN ('base_604_revised_v1','base_1663_first_v1','base_1663_shadowless_v1','exact_label_v1')),
 allowed_product_ids jsonb NOT NULL CHECK(jsonb_typeof(allowed_product_ids)='array'),
 state text NOT NULL DEFAULT 'DRAFT' CHECK(state IN ('DRAFT','APPROVED')),
 request_key text NOT NULL UNIQUE CHECK(length(request_key) BETWEEN 8 AND 180),
 evidence_note text NOT NULL CHECK(length(evidence_note) BETWEEN 12 AND 4000),
 fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 approved_at timestamptz,
 approved_by text,
 approval_note text,
 FOREIGN KEY(root_set_id,market_scope) REFERENCES public.pokemon_market_registry_v3(root_set_id,market_scope),
 UNIQUE(root_set_id,market_scope,source_set_id,contract_version),
 CHECK((state='DRAFT' AND approved_at IS NULL AND approved_by IS NULL AND approval_note IS NULL) OR
       (state='APPROVED' AND approved_at IS NOT NULL AND approved_by IS NOT NULL AND length(approval_note)>=12))
);
CREATE TABLE public.pokemon_market_identity_resolutions_v1 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 contract_id uuid NOT NULL REFERENCES public.pokemon_market_source_contracts_v1(id),
 canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id),
 card_variant_id uuid NOT NULL REFERENCES public.card_variants(id),
 external_identity_id uuid NOT NULL REFERENCES public.card_variant_external_identities(id),
 capture_id uuid NOT NULL REFERENCES public.pokemon_market_source_captures_v1(id),
 physical_scope text NOT NULL CHECK(physical_scope IN ('first_edition','unlimited','shadowless')),
 language_code text NOT NULL CHECK(language_code='en'),
 identity_payload jsonb NOT NULL CHECK(jsonb_typeof(identity_payload)='object'),
 state text NOT NULL DEFAULT 'DRAFT' CHECK(state IN ('DRAFT','APPROVED')),
 request_key text NOT NULL UNIQUE CHECK(length(request_key) BETWEEN 8 AND 180),
 evidence_note text NOT NULL CHECK(length(evidence_note) BETWEEN 12 AND 4000),
 fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 approved_at timestamptz,
 approved_by text,
 approval_note text,
 UNIQUE(contract_id,canonical_card_id,card_variant_id),
 CHECK((state='DRAFT' AND approved_at IS NULL AND approved_by IS NULL AND approval_note IS NULL) OR
       (state='APPROVED' AND approved_at IS NOT NULL AND approved_by IS NOT NULL AND length(approval_note)>=12))
);
CREATE INDEX pokemon_market_resolution_lookup_v1 ON public.pokemon_market_identity_resolutions_v1(contract_id,state,canonical_card_id);
CREATE INDEX pokemon_market_resolution_variant_v1 ON public.pokemon_market_identity_resolutions_v1(card_variant_id,state);
ALTER TABLE public.pokemon_market_source_captures_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_source_contracts_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_identity_resolutions_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_source_captures_v1,public.pokemon_market_source_contracts_v1,public.pokemon_market_identity_resolutions_v1 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.pokemon_market_source_captures_v1,public.pokemon_market_source_contracts_v1,public.pokemon_market_identity_resolutions_v1 TO service_role;

CREATE FUNCTION public.market_identity_number_v1(p_number text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path='pg_catalog','pg_temp' AS $$
 SELECT regexp_replace(regexp_replace(lower(btrim(p_number)),'^0+',''),'/0+','/');
$$;
CREATE FUNCTION public.market_identity_payload_v1(p_product text,p_payload jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path='pg_catalog','pg_temp' AS $$
 SELECT jsonb_build_object('productID',p_product,'productName',p_payload->>'productName',
   'number',p_payload->>'number','printing',p_payload->>'printing',
   'set',p_payload->>'set','setAbbrv',p_payload->>'setAbbrv');
$$;
CREATE FUNCTION public.market_identity_fingerprint_v1(p_row jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path='pg_catalog','pg_temp' AS $$
 SELECT encode(sha256(convert_to((p_row-ARRAY['state','approved_at','approved_by','approval_note','fingerprint'])::text,'UTF8')),'hex');
$$;
CREATE FUNCTION public.guard_market_source_capture_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path='pg_catalog','pg_temp' AS $$
DECLARE expected text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'source evidence is immutable'; END IF;
 SELECT card_details_url INTO expected FROM public.sets WHERE id=NEW.source_set_id;
 IF expected IS DISTINCT FROM NEW.source_reference OR
    substring(expected from '/priceguide/set/([0-9]+)/') IS DISTINCT FROM NEW.catalog_group_id::text THEN
  RAISE EXCEPTION 'source capture does not match registered source catalog';
 END IF;
 IF NEW.captured_at>clock_timestamp()+interval '1 minute' THEN RAISE EXCEPTION 'future source capture is forbidden'; END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER market_source_capture_guard_v1 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_source_captures_v1 FOR EACH ROW EXECUTE FUNCTION public.guard_market_source_capture_v1();

CREATE FUNCTION public.guard_market_identity_candidate_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path='pg_catalog','pg_temp' AS $$
DECLARE cap public.pokemon_market_source_captures_v1%ROWTYPE;
 con public.pokemon_market_source_contracts_v1%ROWTYPE;
 ext public.card_variant_external_identities%ROWTYPE;
 var public.card_variants%ROWTYPE;
 card public.cards%ROWTYPE;
 canonical public.pokemon_canonical_cards%ROWTYPE;
 root_key text; source_key text; source_url text; raw_finish text; raw_tag text;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'identity candidates are append-only; create a replacement version'; END IF;
 IF TG_OP='INSERT' AND NEW.state<>'DRAFT' THEN RAISE EXCEPTION 'new candidates must start in DRAFT'; END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.state<>'DRAFT' OR NEW.state<>'APPROVED' THEN RAISE EXCEPTION 'only reviewed DRAFT to APPROVED transitions are allowed'; END IF;
  IF (to_jsonb(NEW)-ARRAY['state','approved_at','approved_by','approval_note']) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['state','approved_at','approved_by','approval_note']) THEN
   RAISE EXCEPTION 'candidate evidence cannot change during approval';
  END IF;
  IF NEW.approval_note IS NULL OR length(NEW.approval_note)<12 THEN RAISE EXCEPTION 'approval requires an explicit review note'; END IF;
  NEW.approved_at:=clock_timestamp(); NEW.approved_by:=current_user;
 END IF;
 IF TG_TABLE_NAME='pokemon_market_source_contracts_v1' THEN
  SELECT * INTO STRICT cap FROM public.pokemon_market_source_captures_v1 WHERE id=NEW.capture_id;
  SELECT canonical_key,card_details_url INTO source_key,source_url FROM public.sets WHERE id=NEW.source_set_id;
  SELECT canonical_key INTO root_key FROM public.sets WHERE id=NEW.root_set_id;
  IF cap.source_set_id<>NEW.source_set_id OR cap.catalog_group_id<>NEW.catalog_group_id OR source_url IS DISTINCT FROM cap.source_reference THEN
   RAISE EXCEPTION 'source contract catalog/evidence mismatch'; END IF;
  IF jsonb_array_length(NEW.allowed_product_ids) NOT BETWEEN 1 AND 2500 OR EXISTS(
     SELECT 1 FROM jsonb_array_elements(NEW.allowed_product_ids) e WHERE jsonb_typeof(e)<>'string' OR (e#>>'{}') !~ '^[0-9]+$') OR
     (SELECT count(DISTINCT e#>>'{}') FROM jsonb_array_elements(NEW.allowed_product_ids) e)<>jsonb_array_length(NEW.allowed_product_ids) THEN
   RAISE EXCEPTION 'source contract requires a nonempty unique product allowlist'; END IF;
  IF NOT CASE NEW.normalization_policy
    WHEN 'base_604_revised_v1' THEN root_key='base' AND source_key='base' AND NEW.catalog_group_id=604 AND NEW.market_scope='unlimited' AND NEW.raw_edition=''
    WHEN 'base_1663_first_v1' THEN root_key='base' AND source_key='baseSetShadowless' AND NEW.catalog_group_id=1663 AND NEW.market_scope='first_edition' AND NEW.raw_edition='1st-edition'
    WHEN 'base_1663_shadowless_v1' THEN root_key='base' AND source_key='baseSetShadowless' AND NEW.catalog_group_id=1663 AND NEW.market_scope='shadowless' AND NEW.raw_edition='unlimited'
    WHEN 'exact_label_v1' THEN root_key<>'base' AND NEW.source_set_id=NEW.root_set_id AND NEW.market_scope IN ('first_edition','unlimited') AND NEW.raw_edition=CASE NEW.market_scope WHEN 'first_edition' THEN '1st-edition' ELSE 'unlimited' END
    ELSE false END THEN RAISE EXCEPTION 'unreviewed catalog to physical-scope interpretation'; END IF;
 ELSE
  SELECT * INTO STRICT con FROM public.pokemon_market_source_contracts_v1 WHERE id=NEW.contract_id FOR KEY SHARE;
  SELECT * INTO STRICT cap FROM public.pokemon_market_source_captures_v1 WHERE id=NEW.capture_id;
  SELECT * INTO STRICT ext FROM public.card_variant_external_identities WHERE id=NEW.external_identity_id FOR KEY SHARE;
  SELECT * INTO STRICT var FROM public.card_variants WHERE id=NEW.card_variant_id FOR KEY SHARE;
  SELECT * INTO STRICT card FROM public.cards WHERE id=var.card_id FOR KEY SHARE;
  SELECT * INTO STRICT canonical FROM public.pokemon_canonical_cards WHERE id=NEW.canonical_card_id FOR KEY SHARE;
  SELECT card_details_url INTO source_url FROM public.sets WHERE id=con.source_set_id;
  IF NEW.physical_scope<>con.market_scope OR cap.source_set_id<>con.source_set_id OR cap.catalog_group_id<>con.catalog_group_id OR
     source_url IS DISTINCT FROM cap.source_reference OR card.set_id<>con.source_set_id OR canonical.set_id<>con.root_set_id OR
     canonical.set_value_eligible IS DISTINCT FROM true OR canonical.canonical_review_status IS DISTINCT FROM 'approved' THEN
   RAISE EXCEPTION 'physical resolution does not belong to approved canonical/source scope'; END IF;
  IF ext.card_variant_id<>var.id OR ext.provider<>'tcgplayer' OR NOT(con.allowed_product_ids ? ext.external_product_id) OR
     coalesce(var.edition,'')<>con.raw_edition OR coalesce(var.special_type,'')<>'' OR var.printing_type NOT IN ('holo','non-holo') THEN
   RAISE EXCEPTION 'physical resolution provider/variant mismatch'; END IF;
  IF NEW.identity_payload IS DISTINCT FROM public.market_identity_payload_v1(ext.external_product_id,ext.source_payload) OR
     NEW.identity_payload->>'productID' IS DISTINCT FROM ext.external_product_id OR
     NEW.identity_payload->>'productName' IS NULL OR NEW.identity_payload->>'number' IS NULL OR NEW.identity_payload->>'printing' IS NULL THEN
   RAISE EXCEPTION 'physical resolution does not match frozen external identity evidence'; END IF;
  IF public.market_identity_number_v1(NEW.identity_payload->>'number') IS DISTINCT FROM public.market_identity_number_v1(card.card_number) OR
     split_part(public.market_identity_number_v1(NEW.identity_payload->>'number'),'/',1) IS DISTINCT FROM public.market_identity_number_v1(canonical.number) OR
     (canonical.printed_number IS NOT NULL AND public.market_identity_number_v1(NEW.identity_payload->>'number') IS DISTINCT FROM public.market_identity_number_v1(canonical.printed_number)) OR
     lower(btrim(NEW.identity_payload->>'productName')) IS DISTINCT FROM lower(btrim(card.name)) OR
     lower(btrim(card.name)) IS DISTINCT FROM lower(btrim(canonical.name)) THEN
   RAISE EXCEPTION 'canonical name/number evidence mismatch or special-card policy required'; END IF;
  raw_finish:=CASE WHEN lower(NEW.identity_payload->>'printing') LIKE '%holofoil%' THEN 'holo' ELSE 'non-holo' END;
  raw_tag:=CASE WHEN lower(NEW.identity_payload->>'printing') LIKE '%1st edition%' THEN '1st-edition'
               WHEN lower(NEW.identity_payload->>'printing') LIKE '%shadowless%' THEN 'shadowless'
               WHEN lower(NEW.identity_payload->>'printing') LIKE '%unlimited%' THEN 'unlimited' ELSE '' END;
  IF raw_finish IS DISTINCT FROM var.printing_type OR raw_tag<>con.raw_edition OR lower(NEW.identity_payload->>'printing') LIKE '%reverse%' OR
     ext.external_variant_key IS DISTINCT FROM ('edition='||coalesce(var.edition,'')||'|printing_type='||var.printing_type||'|special_type=') THEN
   RAISE EXCEPTION 'source printing differs from exact stored variant'; END IF;
  -- Named edge cases need DB-2 roster policy, not a convenient candidate.
  IF con.normalization_policy LIKE 'base_%' AND split_part(public.market_identity_number_v1(NEW.identity_payload->>'number'),'/',1) IN ('8','58') AND NEW.state='APPROVED' THEN
   RAISE EXCEPTION 'Machamp/Pikachu require explicit versioned roster policy before approval'; END IF;
  IF NEW.state='APPROVED' AND con.state<>'APPROVED' THEN RAISE EXCEPTION 'source contract is not approved'; END IF;
  IF NEW.state='APPROVED' AND EXISTS(SELECT 1 FROM public.pokemon_market_identity_resolutions_v1 r WHERE r.id<>NEW.id AND r.card_variant_id=NEW.card_variant_id AND r.state='APPROVED' AND (r.physical_scope<>NEW.physical_scope OR r.canonical_card_id<>NEW.canonical_card_id)) THEN
   RAISE EXCEPTION 'conflicting approved physical identity'; END IF;
 END IF;
 IF TG_OP='INSERT' THEN NEW.fingerprint:=public.market_identity_fingerprint_v1(to_jsonb(NEW)); END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER market_source_contract_guard_v1 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_source_contracts_v1 FOR EACH ROW EXECUTE FUNCTION public.guard_market_identity_candidate_v1();
CREATE TRIGGER market_identity_resolution_guard_v1 BEFORE INSERT OR UPDATE OR DELETE ON public.pokemon_market_identity_resolutions_v1 FOR EACH ROW EXECUTE FUNCTION public.guard_market_identity_candidate_v1();

CREATE FUNCTION public.approve_market_source_contract_v1(p_id uuid,p_expected_fingerprint text,p_note text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path='pg_catalog','pg_temp' SET statement_timeout='5s' SET lock_timeout='1s' AS $$
DECLARE r public.pokemon_market_source_contracts_v1%ROWTYPE;
BEGIN
 SELECT * INTO STRICT r FROM public.pokemon_market_source_contracts_v1 WHERE id=p_id FOR UPDATE;
 IF r.fingerprint IS DISTINCT FROM p_expected_fingerprint THEN RAISE EXCEPTION 'source contract changed since review'; END IF;
 IF r.state='APPROVED' THEN RETURN r.fingerprint; END IF;
 UPDATE public.pokemon_market_source_contracts_v1 SET state='APPROVED',approval_note=p_note WHERE id=p_id;
 RETURN r.fingerprint;
END;
$$;
CREATE FUNCTION public.approve_market_identity_resolution_v1(p_id uuid,p_expected_fingerprint text,p_note text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path='pg_catalog','pg_temp' SET statement_timeout='5s' SET lock_timeout='1s' AS $$
DECLARE r public.pokemon_market_identity_resolutions_v1%ROWTYPE;
BEGIN
 SELECT * INTO STRICT r FROM public.pokemon_market_identity_resolutions_v1 WHERE id=p_id FOR UPDATE;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('physical-identity-resolution:'||r.card_variant_id::text,0)) THEN RAISE EXCEPTION 'physical identity approval already active' USING ERRCODE='55P03'; END IF;
 IF r.fingerprint IS DISTINCT FROM p_expected_fingerprint THEN RAISE EXCEPTION 'identity resolution changed since review'; END IF;
 IF r.state='APPROVED' THEN RETURN r.fingerprint; END IF;
 UPDATE public.pokemon_market_identity_resolutions_v1 SET state='APPROVED',approval_note=p_note WHERE id=p_id;
 RETURN r.fingerprint;
END;
$$;
REVOKE ALL ON FUNCTION public.market_identity_number_v1(text),public.market_identity_payload_v1(text,jsonb),public.market_identity_fingerprint_v1(jsonb),public.guard_market_source_capture_v1(),public.guard_market_identity_candidate_v1(),public.approve_market_source_contract_v1(uuid,text,text),public.approve_market_identity_resolution_v1(uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
COMMENT ON TABLE public.pokemon_market_source_contracts_v1 IS 'Operator-reviewed source ownership candidates, not collection enrollment or serving activation. Raw source edition is separate from physical market scope.';
COMMENT ON TABLE public.pokemon_market_identity_resolutions_v1 IS 'Evidence-pinned physical identity candidates. Approval does not bind a V3 basket, certify prices or publish data. No current consumer is changed by this migration.';
COMMIT;
