BEGIN;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='20s';

-- Preserve the established edition-reader behavior: prefer ordinary treatments,
-- but allow an exact special-treatment variant when it is the only valid edition
-- identity (e.g. Jungle Poke Ball, Gym Challenge Master Ball).
DO $$
DECLARE
  v_oid oid;
  v_def text;
  v_old text;
  v_new text;
BEGIN
  SELECT p.oid INTO v_oid
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='stage_pokemon_market_basket_v3'
    AND pg_get_function_identity_arguments(p.oid)='p_root uuid, p_scope text, p_request_key text, p_evidence text';

  IF v_oid IS NULL THEN
    RAISE EXCEPTION 'stage_pokemon_market_basket_v3 not found';
  END IF;

  SELECT pg_get_functiondef(v_oid) INTO v_def;

  IF position('ORDER BY identity_priority,special_priority,printing_priority' IN v_def)=0 THEN
    v_old := 'CASE WHEN c.rarity IN (''Common'',''Uncommon'') THEN CASE v.printing_type WHEN ''non-holo'' THEN 0 WHEN ''holo'' THEN 1 ELSE 9 END ELSE CASE v.printing_type WHEN ''holo'' THEN 0 WHEN ''non-holo'' THEN 1 ELSE 9 END END AS printing_priority';
    v_new := 'CASE WHEN coalesce(v.special_type,'''')='''' THEN 0 ELSE 1 END AS special_priority,' || E'\n ' ||
             'CASE WHEN c.rarity IN (''Common'',''Uncommon'') THEN CASE v.printing_type WHEN ''non-holo'' THEN 0 WHEN ''holo'' THEN 1 ELSE 9 END ELSE CASE v.printing_type WHEN ''holo'' THEN 0 WHEN ''non-holo'' THEN 1 ELSE 9 END END AS printing_priority';
    IF position(v_old IN v_def)=0 THEN
      RAISE EXCEPTION 'V3 printing-priority fragment not found';
    END IF;
    v_def := replace(v_def,v_old,v_new);

    v_old := 'AND coalesce(v.special_type,'''')='''' AND (v.printing_type IS NULL OR v.printing_type IN (''holo'',''non-holo''))';
    v_new := 'AND (v.printing_type IS NULL OR v.printing_type IN (''holo'',''non-holo''))';
    IF position(v_old IN v_def)=0 THEN
      RAISE EXCEPTION 'V3 special-treatment exclusion fragment not found';
    END IF;
    v_def := replace(v_def,v_old,v_new);

    v_old := 'ORDER BY identity_priority,printing_priority';
    v_new := 'ORDER BY identity_priority,special_priority,printing_priority';
    IF position(v_old IN v_def)=0 THEN
      RAISE EXCEPTION 'V3 rank-order fragment not found';
    END IF;
    v_def := replace(v_def,v_old,v_new);
    EXECUTE v_def;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.pokemon_edition_history_authority_fingerprint_v2(
  p_root_set_id uuid,
  p_market_date date
)
RETURNS text
LANGUAGE sql
STABLE
SET search_path=''
AS $f$
WITH root AS (
  SELECT s.id,r.profile,
         CASE WHEN r.profile='base_three_printings' THEN 3 ELSE 2 END AS expected_scopes
  FROM public.sets s
  JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=s.id
  WHERE s.id=p_root_set_id
    AND s.parent_opening_set_id IS NULL
    AND NOT s.catalog_only
    AND p_market_date IS NOT NULL
), active AS (
  SELECT DISTINCT ON (v.market_scope)
         v.market_scope,v.basket_version,v.binding_fingerprint,v.expected_card_count
  FROM public.pokemon_market_basket_versions_v3 v
  JOIN root r ON r.id=v.root_set_id
  WHERE v.state='APPROVED'
    AND v.market_scope<>'standard'
    AND v.effective_from<=p_market_date
  ORDER BY v.market_scope,v.effective_from DESC,v.basket_version DESC
), mode AS (
  SELECT r.expected_scopes,
         (SELECT count(*) FROM active)=r.expected_scopes AS full_v3
  FROM root r
), nm AS (
  SELECT id
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1
), rows_for_hash AS (
  SELECT a.market_scope,a.basket_version,a.binding_fingerprint,
         b.canonical_card_id,b.card_variant_id,
         raw.captured_at,raw.created_at,raw.market_price
  FROM active a
  JOIN public.pokemon_market_basket_bindings_v3 b
    ON b.root_set_id=p_root_set_id
   AND b.market_scope=a.market_scope
   AND b.basket_version=a.basket_version
   AND b.resolution='BOUND'
  CROSS JOIN nm
  LEFT JOIN LATERAL (
    SELECT o.captured_at,o.created_at,o.market_price
    FROM public.card_variant_price_observations o
    WHERE o.card_variant_id=b.card_variant_id
      AND o.condition_id=nm.id
      AND o.source='TCGPlayer'
      AND trim(both '"' FROM upper(coalesce(o.currency,'')))='USD'
      AND o.captured_at<=p_market_date
      AND o.market_price>0
    ORDER BY o.captured_at DESC,o.created_at DESC,o.id DESC
    LIMIT 1
  ) raw ON true
)
SELECT CASE
  WHEN coalesce((SELECT full_v3 FROM mode),false) THEN
    'v3:' || md5(coalesce((
      SELECT string_agg(
        jsonb_build_array(
          market_scope,basket_version,binding_fingerprint,
          canonical_card_id,card_variant_id,captured_at,created_at,market_price
        )::text,
        '|' ORDER BY market_scope,canonical_card_id,card_variant_id
      )
      FROM rows_for_hash
    ),''))
  ELSE 'legacy'
END;
$f$;

CREATE OR REPLACE FUNCTION public.get_pokemon_edition_history_card_prices_as_of_v2(
  p_root_set_id uuid,
  p_market_date date,
  p_raw_oracle boolean DEFAULT false
)
RETURNS TABLE(
  canonical_card_id uuid,
  member_set_id uuid,
  market_scope text,
  card_variant_id uuid,
  edition text,
  market_price numeric,
  observed_date date,
  canonical_review_status text
)
LANGUAGE sql
STABLE
SET search_path=''
AS $f$
WITH mode AS (
  SELECT public.pokemon_edition_history_authority_fingerprint_v2(p_root_set_id,p_market_date) LIKE 'v3:%' AS use_v3
)
SELECT p.canonical_card_id,p.member_set_id,p.market_scope,p.card_variant_id,
       p.source_edition AS edition,p.market_price,p.observed_date,p.canonical_review_status
FROM public.get_pokemon_edition_basket_card_prices_as_of_v1(p_root_set_id,p_market_date,p_raw_oracle) p
CROSS JOIN mode
WHERE mode.use_v3
UNION ALL
SELECT p.canonical_card_id,p.member_set_id,p.market_scope,p.card_variant_id,
       p.edition,p.market_price,p.observed_date,p.canonical_review_status
FROM public.get_pokemon_edition_card_prices_as_of_v1(p_root_set_id,p_market_date,p_raw_oracle) p
CROSS JOIN mode
WHERE NOT mode.use_v3
ORDER BY market_scope,canonical_card_id;
$f$;

REVOKE ALL ON FUNCTION public.pokemon_edition_history_authority_fingerprint_v2(uuid,date)
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_edition_history_card_prices_as_of_v2(uuid,date,boolean)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.pokemon_edition_history_authority_fingerprint_v2(uuid,date) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_edition_history_card_prices_as_of_v2(uuid,date,boolean) TO service_role;

DO $$
DECLARE
  v_oid oid;
  v_def text;
  v_old text;
  v_new text;
BEGIN
  SELECT p.oid INTO v_oid
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
    AND p.proname='refresh_pokemon_edition_history_day_v1'
    AND pg_get_function_identity_arguments(p.oid)='p_root_set_id uuid, p_market_date date, p_force boolean';

  IF v_oid IS NULL THEN
    RAISE EXCEPTION 'refresh_pokemon_edition_history_day_v1 not found';
  END IF;

  SELECT pg_get_functiondef(v_oid) INTO v_def;

  IF position('get_pokemon_edition_history_card_prices_as_of_v2' IN v_def)=0 THEN
    v_def := replace(
      v_def,
      'get_pokemon_edition_card_prices_as_of_v1',
      'get_pokemon_edition_history_card_prices_as_of_v2'
    );
  END IF;

  v_old := 'v_source_fp:=md5(v_sources::text||v_identity||v_profile||' || E'\n' ||
           '    pg_get_functiondef(''public.get_pokemon_edition_history_card_prices_as_of_v2(uuid,date,boolean)''::regprocedure));';
  v_new := 'v_source_fp:=md5(v_sources::text||v_identity||v_profile||' || E'\n' ||
           '    public.pokemon_edition_history_authority_fingerprint_v2(p_root_set_id,p_market_date)||' || E'\n' ||
           '    pg_get_functiondef(''public.get_pokemon_edition_history_card_prices_as_of_v2(uuid,date,boolean)''::regprocedure));';

  IF position('pokemon_edition_history_authority_fingerprint_v2(p_root_set_id,p_market_date)' IN v_def)=0 THEN
    IF position(v_old IN v_def)=0 THEN
      RAISE EXCEPTION 'edition history source-fingerprint fragment not found';
    END IF;
    v_def := replace(v_def,v_old,v_new);
  END IF;

  v_def := replace(
    v_def,
    '''pricing_policy'',''edition_exact_asof_v1''',
    '''pricing_policy'',''edition_authority_dispatch_v2'''
  );

  EXECUTE v_def;
END $$;

CREATE OR REPLACE FUNCTION public.list_pokemon_market_edition_gaps_v1(
  p_as_of date DEFAULT (timezone('America/Phoenix',now()))::date
)
RETURNS TABLE(
  root_set_id uuid,
  root_set_name text,
  market_scope text,
  basket_version integer,
  gap_type text,
  canonical_card_id uuid,
  card_name text,
  card_number text,
  rarity text,
  card_variant_id uuid,
  source_set_id uuid,
  source_set_name text,
  source_policy text,
  source_edition text,
  last_tcgplayer_nm_date date,
  notes text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path=''
AS $f$
WITH nm AS MATERIALIZED (
  SELECT id
  FROM public.conditions
  WHERE lower(name)='near mint'
  ORDER BY id
  LIMIT 1
), latest_any AS MATERIALIZED (
  SELECT DISTINCT ON (v.root_set_id,v.market_scope)
         v.root_set_id,v.market_scope,v.basket_version,v.state,v.effective_from
  FROM public.pokemon_market_basket_versions_v3 v
  WHERE v.market_scope IN ('first_edition','unlimited','shadowless')
  ORDER BY v.root_set_id,v.market_scope,v.basket_version DESC
), active_approved AS MATERIALIZED (
  SELECT DISTINCT ON (v.root_set_id,v.market_scope)
         v.root_set_id,v.market_scope,v.basket_version,v.effective_from
  FROM public.pokemon_market_basket_versions_v3 v
  WHERE v.state='APPROVED'
    AND v.market_scope IN ('first_edition','unlimited','shadowless')
    AND v.effective_from<=p_as_of
  ORDER BY v.root_set_id,v.market_scope,v.effective_from DESC,v.basket_version DESC
), approved_bindings AS MATERIALIZED (
  SELECT a.root_set_id,a.market_scope,a.basket_version,
         b.member_set_id,b.canonical_card_id,b.card_variant_id,
         coalesce(b.source_set_id_override,b.member_set_id) AS source_set_id,
         coalesce(b.source_policy,'same_member_catalog_v1') AS source_policy,
         b.edition AS source_edition
  FROM active_approved a
  JOIN public.pokemon_market_basket_bindings_v3 b
    ON b.root_set_id=a.root_set_id
   AND b.market_scope=a.market_scope
   AND b.basket_version=a.basket_version
  WHERE b.resolution='BOUND'
    AND public.pokemon_market_binding_is_valid_v3(
      b.root_set_id,b.market_scope,b.member_set_id,b.canonical_card_id,b.card_variant_id,
      b.source_set_id_override,b.source_policy,b.identity_basis,b.edition,b.printing_type,b.special_type
    )
), price_gaps AS (
  SELECT ab.*
  FROM approved_bindings ab
  WHERE NOT EXISTS (
    SELECT 1
    FROM public.card_variant_price_observations o
    CROSS JOIN nm
    WHERE o.card_variant_id=ab.card_variant_id
      AND o.condition_id=nm.id
      AND o.source='TCGPlayer'
      AND trim(both '"' FROM upper(coalesce(o.currency,'')))='USD'
      AND o.captured_at<=p_as_of
      AND o.market_price>0
  )
), identity_gaps AS (
  SELECT l.root_set_id,l.market_scope,l.basket_version,b.canonical_card_id
  FROM latest_any l
  JOIN public.pokemon_market_basket_bindings_v3 b
    ON b.root_set_id=l.root_set_id
   AND b.market_scope=l.market_scope
   AND b.basket_version=l.basket_version
  WHERE l.state='DRAFT'
    AND b.resolution IN ('MISSING','AMBIGUOUS','REVIEW_REQUIRED')
)
SELECT *
FROM (
  SELECT pg.root_set_id,rs.name,pg.market_scope,pg.basket_version,
         'MISSING_NEAR_MINT_PRICE'::text,
         pg.canonical_card_id,c.name,c.number,c.rarity,
         pg.card_variant_id,pg.source_set_id,src.name,
         pg.source_policy,pg.source_edition,NULL::date,
         'Exact approved edition-basket variant has no positive TCGPlayer Near Mint observation as of the requested date; variant-specific eBay active-ask backfill candidate.'::text
  FROM price_gaps pg
  JOIN public.sets rs ON rs.id=pg.root_set_id
  JOIN public.pokemon_canonical_cards c ON c.id=pg.canonical_card_id
  JOIN public.sets src ON src.id=pg.source_set_id

  UNION ALL

  SELECT ig.root_set_id,rs.name,ig.market_scope,ig.basket_version,
         'MISSING_VARIANT_IDENTITY'::text,
         ig.canonical_card_id,c.name,c.number,c.rarity,
         NULL::uuid,NULL::uuid,NULL::text,NULL::text,NULL::text,NULL::date,
         'Latest V3 edition basket cannot resolve an exact accepted variant; identity review is required before automated price backfill or basket approval.'::text
  FROM identity_gaps ig
  JOIN public.sets rs ON rs.id=ig.root_set_id
  JOIN public.pokemon_canonical_cards c ON c.id=ig.canonical_card_id
) q
ORDER BY 2,3,8,7,5;
$f$;

REVOKE ALL ON FUNCTION public.list_pokemon_market_edition_gaps_v1(date)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.list_pokemon_market_edition_gaps_v1(date)
TO service_role;

COMMENT ON FUNCTION public.get_pokemon_edition_history_card_prices_as_of_v2(uuid,date,boolean) IS
  'Edition-history reader that uses complete approved V3 exact-variant baskets when all required scopes are frozen for the date, otherwise preserves the legacy exact-edition reader.';
COMMENT ON FUNCTION public.pokemon_edition_history_authority_fingerprint_v2(uuid,date) IS
  'Fingerprint for edition-history authority; includes active V3 basket identities and latest positive raw TCGPlayer Near Mint evidence for exact bound variants so same-day source refreshes invalidate history no-op state.';
COMMENT ON FUNCTION public.list_pokemon_market_edition_gaps_v1(date) IS
  'Variant-specific edition market gap authority. Price gaps are exact approved basket variants with no positive TCGPlayer Near Mint observation and are safe eBay backfill candidates; identity gaps remain fail-closed until exact variant identity is reviewed.';

COMMIT;
