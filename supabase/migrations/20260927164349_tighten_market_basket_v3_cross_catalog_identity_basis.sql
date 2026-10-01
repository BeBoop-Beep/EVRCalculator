BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='8s';

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
      AND p_identity_basis = CASE p.match_policy
        WHEN 'canonical_number_unique' THEN 'scoped_source_catalog_number_v1'
        ELSE 'scoped_source_catalog_named_exception_v1'
      END
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

REVOKE ALL ON FUNCTION public.pokemon_market_binding_is_valid_v3(uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,text)
FROM PUBLIC,anon,authenticated,service_role;

COMMIT;
