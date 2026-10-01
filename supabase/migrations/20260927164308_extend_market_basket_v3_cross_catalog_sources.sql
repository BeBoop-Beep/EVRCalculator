BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='15s';

CREATE TABLE public.pokemon_market_scope_source_catalogs_v1 (
  root_set_id uuid NOT NULL,
  market_scope text NOT NULL,
  source_set_id uuid NOT NULL REFERENCES public.sets(id),
  source_edition_key text NOT NULL CHECK (source_edition_key IN ('__NULL__','1st-edition','unlimited','shadowless')),
  source_role text NOT NULL CHECK (length(source_role) BETWEEN 8 AND 120),
  match_policy text NOT NULL CHECK (match_policy IN ('canonical_number_unique','canonical_number_named_exception')),
  required_source_card_name text,
  evidence text NOT NULL CHECK (length(evidence) BETWEEN 12 AND 1800),
  recorded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(root_set_id,market_scope,source_role),
  FOREIGN KEY(root_set_id,market_scope)
    REFERENCES public.pokemon_market_registry_v3(root_set_id,market_scope),
  CHECK (
    (match_policy='canonical_number_unique' AND required_source_card_name IS NULL)
    OR
    (match_policy='canonical_number_named_exception' AND required_source_card_name IS NOT NULL)
  )
);

ALTER TABLE public.pokemon_market_scope_source_catalogs_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_scope_source_catalogs_v1 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.pokemon_market_scope_source_catalogs_v1 TO service_role;

COMMENT ON TABLE public.pokemon_market_scope_source_catalogs_v1 IS
  'Explicit reviewed cross-catalog source semantics for edition-scoped Market baskets. These rows never relabel card_variants; they authorize a specific source catalog/edition interpretation for a specific root market scope.';

ALTER TABLE public.pokemon_market_basket_bindings_v3
  ADD COLUMN source_set_id_override uuid REFERENCES public.sets(id),
  ADD COLUMN source_policy text;

ALTER TABLE public.pokemon_market_basket_bindings_v3
  DROP CONSTRAINT pokemon_market_basket_bindings_v3_check1;

ALTER TABLE public.pokemon_market_basket_bindings_v3
  ADD CONSTRAINT pokemon_market_basket_bindings_v3_cross_source_pair_check
  CHECK (
    (source_set_id_override IS NULL AND source_policy IS NULL)
    OR
    (source_set_id_override IS NOT NULL AND source_policy IS NOT NULL)
  ),
  ADD CONSTRAINT pokemon_market_basket_bindings_v3_unresolved_source_check
  CHECK (
    resolution='BOUND'
    OR (source_set_id_override IS NULL AND source_policy IS NULL)
  ),
  ADD CONSTRAINT pokemon_market_basket_bindings_v3_scope_edition_v2_check
  CHECK (
    resolution<>'BOUND'
    OR source_set_id_override IS NOT NULL
    OR (market_scope='first_edition' AND edition IS NOT DISTINCT FROM '1st-edition')
    OR (market_scope='unlimited' AND edition IS NOT DISTINCT FROM 'unlimited')
    OR (market_scope='shadowless' AND edition IS NOT DISTINCT FROM 'shadowless')
    OR (market_scope='standard' AND coalesce(edition,'') IN ('','unlimited'))
  );

INSERT INTO public.pokemon_market_scope_source_catalogs_v1
(root_set_id,market_scope,source_set_id,source_edition_key,source_role,match_policy,required_source_card_name,evidence)
SELECT b.id,'unlimited',b.id,'__NULL__','base_revised_unlimited_catalog_v1',
       'canonical_number_unique',NULL,
       'TCGplayer Base Set group 604 is the revised Unlimited commercial catalog; its legacy variants are edition-null and are scoped here without relabeling raw variant identity.'
FROM public.sets b WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only
UNION ALL
SELECT b.id,'unlimited',d.id,'1st-edition','base_unlimited_machamp_exception_v1',
       'canonical_number_named_exception','Machamp',
       'Base #8 Machamp is a starter-deck-only checklist exception absent from TCGplayer Base group 604; the regular Deck Exclusives Machamp 8/102 is the reviewed Unlimited checklist source.'
FROM public.sets b CROSS JOIN public.sets d
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND d.name='Deck Exclusives'
UNION ALL
SELECT b.id,'first_edition',sh.id,'1st-edition','base_first_shadowless_catalog_v1',
       'canonical_number_unique',NULL,
       'TCGplayer Base Set (Shadowless) group 1663 separates Printing=1st Edition from Printing=Unlimited; the 1st Edition rows are the reviewed Base First Edition source.'
FROM public.sets b CROSS JOIN public.sets sh
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND sh.name='Base Set (Shadowless)'
UNION ALL
SELECT b.id,'first_edition',sh.id,'1st-edition','base_first_pikachu_regular_v1',
       'canonical_number_named_exception','Pikachu',
       'Base #58 has regular Pikachu and Red Cheeks products in the Shadowless catalog; the canonical one-card checklist slot is pinned to regular Pikachu to prevent UUID/order-driven switching.'
FROM public.sets b CROSS JOIN public.sets sh
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND sh.name='Base Set (Shadowless)'
UNION ALL
SELECT b.id,'first_edition',d.id,'1st-edition','base_first_machamp_shadowless_v1',
       'canonical_number_named_exception','Machamp - 8/102 (Base Set Shadowless)',
       'Base #8 First Edition is a starter-deck-only exception; the Deck Exclusives product explicitly labeled Base Set Shadowless is the reviewed First Edition checklist source.'
FROM public.sets b CROSS JOIN public.sets d
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND d.name='Deck Exclusives'
UNION ALL
SELECT b.id,'shadowless',sh.id,'unlimited','base_shadowless_catalog_v1',
       'canonical_number_unique',NULL,
       'Within TCGplayer Base Set (Shadowless) group 1663, Printing=Unlimited means the non-1st-edition Shadowless printing. The source edition label is preserved rather than rewritten.'
FROM public.sets b CROSS JOIN public.sets sh
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND sh.name='Base Set (Shadowless)'
UNION ALL
SELECT b.id,'shadowless',sh.id,'unlimited','base_shadowless_pikachu_regular_v1',
       'canonical_number_named_exception','Pikachu',
       'Base #58 Shadowless has regular Pikachu and Red Cheeks products; the canonical checklist slot is pinned to regular Pikachu and Red Cheeks remains a separate commercial variation.'
FROM public.sets b CROSS JOIN public.sets sh
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND sh.name='Base Set (Shadowless)'
UNION ALL
SELECT b.id,'shadowless',d.id,'1st-edition','base_shadowless_machamp_v1',
       'canonical_number_named_exception','Machamp - 8/102 (Base Set Shadowless)',
       'Base #8 has no non-stamped Shadowless product; the starter-deck Machamp explicitly labeled Base Set Shadowless is the reviewed checklist exception for the Shadowless basket.'
FROM public.sets b CROSS JOIN public.sets d
WHERE b.name='Base' AND b.parent_opening_set_id IS NULL AND NOT b.catalog_only AND d.name='Deck Exclusives';

CREATE OR REPLACE FUNCTION public.pokemon_market_binding_is_valid_v3(
  p_root uuid,
  p_scope text,
  p_member_set uuid,
  p_canonical uuid,
  p_variant uuid,
  p_source_set_override uuid,
  p_source_policy text,
  p_identity_basis text,
  p_edition text,
  p_printing_type text,
  p_special_type text
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path=pg_catalog,pg_temp
AS $f$
WITH canon AS (
  SELECT c.id,c.set_id,
         regexp_replace(split_part(lower(coalesce(c.number,c.printed_number,'')),'/',1),'^0+','') AS normalized_number,
         c.canonical_review_status,c.set_value_eligible
  FROM public.pokemon_canonical_cards c
  WHERE c.id=p_canonical
), variant AS (
  SELECT v.id,v.card_id,v.edition,v.printing_type,v.special_type,
         src.set_id AS source_set_id,src.name AS source_card_name,
         regexp_replace(split_part(lower(coalesce(src.card_number,'')),'/',1),'^0+','') AS normalized_number
  FROM public.card_variants v
  JOIN public.cards src ON src.id=v.card_id
  WHERE v.id=p_variant
), legacy_ok AS (
  SELECT EXISTS(
    SELECT 1
    FROM canon c
    JOIN variant v ON true
    JOIN public.pokemon_market_explorer_card_current_metadata m
      ON m.card_variant_id=v.id
     AND m.legacy_card_id=v.card_id
     AND m.canonical_card_id=c.id
     AND m.set_id=p_member_set
    WHERE p_source_set_override IS NULL
      AND p_source_policy IS NULL
      AND c.set_id=p_member_set
      AND c.set_value_eligible
      AND c.canonical_review_status='approved'
      AND v.source_set_id=p_member_set
      AND m.identity_basis=p_identity_basis
      AND v.edition IS NOT DISTINCT FROM p_edition
      AND v.printing_type IS NOT DISTINCT FROM p_printing_type
      AND v.special_type IS NOT DISTINCT FROM p_special_type
      AND m.edition IS NOT DISTINCT FROM v.edition
      AND m.printing_type IS NOT DISTINCT FROM v.printing_type
      AND m.special_type IS NOT DISTINCT FROM v.special_type
      AND (
        (p_scope='first_edition' AND v.edition='1st-edition')
        OR (p_scope='unlimited' AND v.edition='unlimited')
        OR (p_scope='shadowless' AND v.edition='shadowless')
        OR (p_scope='standard' AND coalesce(v.edition,'') IN ('','unlimited'))
      )
  ) AS ok
), cross_ok AS (
  SELECT EXISTS(
    SELECT 1
    FROM canon c
    JOIN variant v ON true
    JOIN public.pokemon_market_scope_source_catalogs_v1 p
      ON p.root_set_id=p_root
     AND p.market_scope=p_scope
     AND p.source_set_id=p_source_set_override
     AND p.source_role=p_source_policy
     AND p.source_edition_key=coalesce(v.edition,'__NULL__')
    WHERE p_source_set_override IS NOT NULL
      AND p_source_policy IS NOT NULL
      AND c.set_id=p_member_set
      AND c.set_value_eligible
      AND c.canonical_review_status='approved'
      AND v.source_set_id=p_source_set_override
      AND v.edition IS NOT DISTINCT FROM p_edition
      AND v.printing_type IS NOT DISTINCT FROM p_printing_type
      AND v.special_type IS NOT DISTINCT FROM p_special_type
      AND c.normalized_number=v.normalized_number
      AND (
        (
          p.match_policy='canonical_number_unique'
          AND (
            SELECT count(*)
            FROM public.cards sx
            WHERE sx.set_id=v.source_set_id
              AND regexp_replace(split_part(lower(coalesce(sx.card_number,'')),'/',1),'^0+','')=v.normalized_number
          )=1
        )
        OR
        (
          p.match_policy='canonical_number_named_exception'
          AND v.source_card_name=p.required_source_card_name
        )
      )
  ) AS ok
)
SELECT CASE WHEN p_source_set_override IS NULL
            THEN (SELECT ok FROM legacy_ok)
            ELSE (SELECT ok FROM cross_ok)
       END;
$f$;

CREATE OR REPLACE FUNCTION public.pokemon_market_binding_fingerprint_v3(p_root uuid,p_scope text,p_version integer)
RETURNS text
LANGUAGE sql
STABLE
SET search_path=pg_catalog,pg_temp
AS $f$
WITH flags AS (
  SELECT bool_or(source_set_id_override IS NOT NULL OR source_policy IS NOT NULL) AS has_cross_source
  FROM public.pokemon_market_basket_bindings_v3
  WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version
)
SELECT encode(sha256(convert_to(coalesce(
  jsonb_agg(
    CASE WHEN (SELECT has_cross_source FROM flags) THEN
      jsonb_build_object(
        'canonical',canonical_card_id,'member',member_set_id,'variant',card_variant_id,
        'edition',edition,'printing',printing_type,'special',special_type,'identity',identity_basis,
        'resolution',resolution,'candidate_count',candidate_count,
        'source_set_override',source_set_id_override,'source_policy',source_policy
      )
    ELSE
      jsonb_build_object(
        'canonical',canonical_card_id,'member',member_set_id,'variant',card_variant_id,
        'edition',edition,'printing',printing_type,'special',special_type,'identity',identity_basis,
        'resolution',resolution,'candidate_count',candidate_count
      )
    END
    ORDER BY canonical_card_id
  )::text,'[]'),'UTF8')),'hex')
FROM public.pokemon_market_basket_bindings_v3
WHERE root_set_id=p_root AND market_scope=p_scope AND basket_version=p_version;
$f$;

CREATE OR REPLACE FUNCTION public.guard_pokemon_market_basket_child_v3()
RETURNS trigger
LANGUAGE plpgsql
SET search_path=pg_catalog,pg_temp
AS $f$
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
  IF NEW.resolution='BOUND' AND NOT public.pokemon_market_binding_is_valid_v3(
       NEW.root_set_id,NEW.market_scope,NEW.member_set_id,NEW.canonical_card_id,NEW.card_variant_id,
       NEW.source_set_id_override,NEW.source_policy,NEW.identity_basis,NEW.edition,NEW.printing_type,NEW.special_type
     ) THEN
   RAISE EXCEPTION 'V3 exact variant binding disagrees with reviewed scoped catalog identity';
  END IF;
 END IF;
 RETURN NEW;
END;
$f$;

CREATE OR REPLACE FUNCTION public.guard_pokemon_market_basket_version_v3()
RETURNS trigger
LANGUAGE plpgsql
SET search_path=pg_catalog,pg_temp
AS $f$
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
   FROM public.pokemon_market_basket_bindings_v3
   WHERE root_set_id=NEW.root_set_id AND market_scope=NEW.market_scope AND basket_version=NEW.basket_version;
   IF v_slots<>v_cards OR v_bound<>v_cards THEN RAISE EXCEPTION 'V3 approval requires every intended card resolved exactly once'; END IF;
   IF (SELECT count(*) FROM public.pokemon_market_basket_members_v3 WHERE root_set_id=NEW.root_set_id AND market_scope=NEW.market_scope AND basket_version=NEW.basket_version)<>v_members
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'members') x WHERE NOT EXISTS(
     SELECT 1 FROM public.pokemon_market_basket_members_v3 m
     WHERE m.root_set_id=NEW.root_set_id AND m.market_scope=NEW.market_scope AND m.basket_version=NEW.basket_version
       AND m.member_set_id=(x->>'member_set_id')::uuid AND m.member_type=x->>'member_type' AND m.expected_card_count=(x->>'expected_card_count')::integer))
   OR EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'cards') x WHERE NOT EXISTS(
     SELECT 1 FROM public.pokemon_market_basket_bindings_v3 b
     WHERE b.root_set_id=NEW.root_set_id AND b.market_scope=NEW.market_scope AND b.basket_version=NEW.basket_version
       AND b.canonical_card_id=(x->>'canonical_card_id')::uuid AND b.member_set_id=(x->>'member_set_id')::uuid)) THEN
      RAISE EXCEPTION 'V3 approval found omitted or substituted members/cards'; END IF;
   IF EXISTS(
     SELECT 1
     FROM public.pokemon_market_basket_bindings_v3 b
     WHERE b.root_set_id=NEW.root_set_id AND b.market_scope=NEW.market_scope AND b.basket_version=NEW.basket_version
       AND (
         b.resolution<>'BOUND'
         OR NOT public.pokemon_market_binding_is_valid_v3(
           b.root_set_id,b.market_scope,b.member_set_id,b.canonical_card_id,b.card_variant_id,
           b.source_set_id_override,b.source_policy,b.identity_basis,b.edition,b.printing_type,b.special_type
         )
       )
   ) THEN
     RAISE EXCEPTION 'V3 approval detects changed or unreviewed scoped variant identities'; END IF;
   v_fp:=public.pokemon_market_binding_fingerprint_v3(NEW.root_set_id,NEW.market_scope,NEW.basket_version);
   IF NEW.binding_fingerprint IS DISTINCT FROM v_fp THEN RAISE EXCEPTION 'V3 binding fingerprint changed since review'; END IF;
   NEW.approved_at:=now();
 END IF;
 RETURN NEW;
END;
$f$;

REVOKE ALL ON FUNCTION public.pokemon_market_binding_is_valid_v3(uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,text),
                       public.pokemon_market_binding_fingerprint_v3(uuid,text,integer),
                       public.guard_pokemon_market_basket_child_v3(),
                       public.guard_pokemon_market_basket_version_v3()
FROM PUBLIC,anon,authenticated,service_role;

COMMENT ON COLUMN public.pokemon_market_basket_bindings_v3.source_set_id_override IS
  'Optional reviewed source catalog override. NULL preserves the original same-member identity contract; non-NULL requires an explicit scoped source policy.';
COMMENT ON COLUMN public.pokemon_market_basket_bindings_v3.source_policy IS
  'Reviewed source_role from pokemon_market_scope_source_catalogs_v1 when a cross-catalog source override is used.';

COMMIT;
