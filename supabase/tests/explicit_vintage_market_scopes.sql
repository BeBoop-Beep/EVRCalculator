-- Run as a database owner against a database with
-- 20260925161052_explicit_vintage_market_scopes.sql applied.
-- All assertions are read-only; the outer transaction is rolled back.

BEGIN;

DO $test$
DECLARE
  n integer;
BEGIN
  IF to_regclass('public.pokemon_market_set_scope_contract_v1') IS NULL THEN
    RAISE EXCEPTION 'scope contract view is missing';
  END IF;
  IF to_regclass('public.pokemon_market_scoped_history_large_move_reviews_v1') IS NULL THEN
    RAISE EXCEPTION 'large-move review ledger is missing';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='pokemon_explore_set_value_snapshot_latest'
      AND column_name='market_count'
      AND is_nullable='NO'
  ) THEN
    RAISE EXCEPTION 'Global Set Market snapshot market_count contract is missing or nullable';
  END IF;
  IF to_regprocedure('public.normalize_pokemon_explore_set_value_market_count_v1()') IS NULL THEN
    RAISE EXCEPTION 'market_count normalization trigger function is missing';
  END IF;
  IF to_regclass('public.pokemon_market_set_scope_activation_v1') IS NULL THEN
    RAISE EXCEPTION 'scope activation latch table is missing';
  END IF;
  IF to_regprocedure('public.guard_pokemon_market_set_scope_snapshot_v1()') IS NULL THEN
    RAISE EXCEPTION 'scope activation snapshot guard function is missing';
  END IF;
  IF to_regprocedure('public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)') IS NULL THEN
    RAISE EXCEPTION 'scope activation rollback function is missing';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid='public.pokemon_explore_set_value_snapshot_latest'::regclass
      AND tgname='pokemon_explore_set_value_scope_contract_guard'
      AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'scope activation snapshot guard trigger is missing';
  END IF;
  IF has_function_privilege('anon','public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)','EXECUTE')
     OR has_function_privilege('authenticated','public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)','EXECUTE')
     OR NOT has_function_privilege('service_role','public.rollback_pokemon_market_set_scope_activation_v1(timestamptz,text)','EXECUTE') THEN
    RAISE EXCEPTION 'scope activation rollback privileges are incorrect';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid='public.pokemon_explore_set_value_snapshot_latest'::regclass
      AND tgname='pokemon_explore_set_value_normalize_market_count'
      AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'market_count normalization trigger is missing';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='public.pokemon_explore_set_value_snapshot_latest'::regclass
      AND conname='pokemon_explore_set_value_snapshot_market_count_check'
      AND pg_get_constraintdef(oid) LIKE '%market_count = jsonb_array_length%'
  ) THEN
    RAISE EXCEPTION 'market_count payload equality constraint is missing';
  END IF;
  IF has_function_privilege('anon','public.sync_pokemon_market_explorer_set_directory_v1()','EXECUTE')
     OR has_function_privilege('authenticated','public.sync_pokemon_market_explorer_set_directory_v1()','EXECUTE') THEN
    RAISE EXCEPTION 'scoped directory sync is executable by a public API role';
  END IF;

  -- Standard roots remain one Standard market.
  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_scope_contract_v1 c
    WHERE c.profile='standard'
    GROUP BY c.set_id
    HAVING count(*)<>1 OR min(c.market_scope)<>'standard' OR max(c.market_scope)<>'standard'
  ) THEN
    RAISE EXCEPTION 'a Standard root does not publish exactly one standard scope';
  END IF;

  -- edition_split roots publish exactly first_edition + unlimited.
  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_scope_contract_v1 c
    WHERE c.profile='edition_split'
    GROUP BY c.set_id
    HAVING count(*)<>2
       OR array_agg(c.market_scope ORDER BY c.market_scope)
          <> ARRAY['first_edition','unlimited']::text[]
  ) THEN
    RAISE EXCEPTION 'an edition_split root does not publish exactly first_edition + unlimited';
  END IF;

  -- Base publishes the three explicit identities, even while values fail closed.
  SELECT count(*) INTO n
  FROM public.pokemon_market_set_scope_contract_v1 c
  WHERE c.profile='base_three_printings'
    AND c.market_scope IN ('first_edition','shadowless','unlimited');
  IF n<>3 THEN
    RAISE EXCEPTION 'Base scope contract expected 3 rows, found %',n;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_scope_contract_v1 c
    JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=c.set_id
    WHERE c.market_scope='standard'
  ) THEN
    RAISE EXCEPTION 'generic standard market survived for an edition-split root';
  END IF;

  IF EXISTS (
    SELECT market_key
    FROM public.pokemon_market_set_scope_contract_v1
    GROUP BY market_key
    HAVING count(*)<>1
  ) THEN
    RAISE EXCEPTION 'scope contract market_key is not unique';
  END IF;

  -- Fixed physical identity: never more than one variant per canonical+scope.
  IF EXISTS (
    WITH members AS (
      SELECT r.set_id root_set_id,r.set_id member_set_id
      FROM public.pokemon_edition_split_root_sets_v2 r
      UNION ALL
      SELECT r.set_id,s.id
      FROM public.pokemon_edition_split_root_sets_v2 r
      JOIN public.sets s
        ON s.parent_opening_set_id=r.set_id
       AND s.counts_toward_parent_set_value=true
    ), cards AS (
      SELECT m.root_set_id,c.id canonical_card_id,c.set_id
      FROM members m
      JOIN public.pokemon_canonical_cards c ON c.set_id=m.member_set_id
      WHERE c.set_value_eligible=true
    )
    SELECT 1
    FROM cards c
    JOIN public.pokemon_market_explorer_card_current_metadata m
      ON m.canonical_card_id=c.canonical_card_id AND m.set_id=c.set_id
    WHERE m.edition IN ('1st-edition','unlimited','shadowless')
    GROUP BY c.root_set_id,c.canonical_card_id,
      CASE m.edition
        WHEN '1st-edition' THEN 'first_edition'
        WHEN 'unlimited' THEN 'unlimited'
        WHEN 'shadowless' THEN 'shadowless'
      END
    HAVING count(DISTINCT m.card_variant_id)>1
  ) THEN
    RAISE EXCEPTION 'duplicate physical identity exists for canonical+scope';
  END IF;

  -- A certified history market must keep one fixed expected-card count.
  IF EXISTS (
    SELECT h.set_id,h.market_scope
    FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=h.set_id
    WHERE h.market_scope<>'standard' AND h.certified_on_date
    GROUP BY h.set_id,h.market_scope
    HAVING count(DISTINCT h.expected_card_count)>1
       OR bool_or(h.priced_card_count<>h.expected_card_count)
  ) THEN
    RAISE EXCEPTION 'certified scoped history changed basket membership or contains incomplete dates';
  END IF;

  -- Known source-defect histories are deliberately withheld.
  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_scoped_history_market_certification_v1 c
    JOIN public.sets s ON s.id=c.set_id
    WHERE s.name='Neo Discovery' AND c.market_scope='first_edition'
      AND c.history_publishable=false
  ) THEN
    RAISE EXCEPTION 'Neo Discovery 1st Edition source-defect history was not withheld';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_scoped_history_market_certification_v1 c
    JOIN public.sets s ON s.id=c.set_id
    WHERE s.name='Neo Genesis' AND c.market_scope='first_edition'
      AND c.history_publishable=false
  ) THEN
    RAISE EXCEPTION 'Neo Genesis 1st Edition source-defect history was not withheld';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM public.pokemon_market_scoped_history_market_certification_v1 c
    JOIN public.sets s ON s.id=c.set_id
    WHERE s.name='Team Rocket' AND c.market_scope='first_edition'
      AND c.history_publishable=false
  ) THEN
    RAISE EXCEPTION 'Team Rocket 1st Edition source-defect history was not withheld';
  END IF;

  -- Base remains explicit but unavailable rather than fabricated.
  IF EXISTS (
    SELECT 1
    FROM public.pokemon_market_set_scope_contract_v1 c
    WHERE c.profile='base_three_printings'
      AND c.public_current_value IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Base fabricated a publishable scoped value';
  END IF;
END
$test$;

-- Validate the root-count / market-count split directly from the authoritative
-- scope contract even before the application snapshot has activated scoped rows.
DO $test$
DECLARE
  payload jsonb;
  root_count integer;
  market_count integer;
  result jsonb;
BEGIN
  SELECT
    jsonb_build_object(
      'sets',
      coalesce(
        jsonb_agg(
          jsonb_build_object(
            'setId',c.set_id,
            'marketScope',c.market_scope,
            'marketKey',c.market_key,
            'baseSetName',c.base_set_name
          )
          order by c.market_key
        ),
        '[]'::jsonb
      )
    ),
    count(distinct c.set_id)::integer,
    count(*)::integer
  INTO payload,root_count,market_count
  FROM public.pokemon_market_set_scope_contract_v1 c;

  IF market_count < root_count THEN
    RAISE EXCEPTION 'authoritative market_count % is less than root set_count %',
      market_count,root_count;
  END IF;

  result:=public.validate_pokemon_market_set_scope_payload_v1(
    payload,market_count,root_count
  );

  IF (result->>'marketCount')::integer<>market_count
     OR (result->>'rootSetCount')::integer<>root_count THEN
    RAISE EXCEPTION 'scope payload validator returned wrong count contract: %',result;
  END IF;
END
$test$;

-- If the application has activated the scoped snapshot contract, validate the
-- prepared serving generation end-to-end.  Before application cutover this
-- block intentionally skips, so the DB migration can deploy first.
DO $test$
DECLARE
  payload jsonb;
  scoped_active boolean;
  payload_count integer;
  root_count integer;
  declared_set_count integer;
  declared_market_count integer;
  directory_count integer;
BEGIN
  SELECT s.payload_json,s.set_count,s.market_count
    INTO payload,declared_set_count,declared_market_count
  FROM public.pokemon_explore_set_value_snapshot_latest s
  WHERE s.tcg='pokemon' AND s.scope='market'
  LIMIT 1;

  SELECT EXISTS (
    SELECT 1
    FROM jsonb_array_elements(coalesce(payload->'sets','[]'::jsonb)) e
    WHERE coalesce(nullif(e->>'marketScope',''),'standard')<>'standard'
  ) INTO scoped_active;

  IF scoped_active THEN
    IF NOT EXISTS (
      SELECT 1
      FROM public.pokemon_market_set_scope_activation_v1 a
      WHERE a.singleton=true AND a.active=true
        AND a.activated_market_date=(
          SELECT s.market_date
          FROM public.pokemon_explore_set_value_snapshot_latest s
          WHERE s.tcg='pokemon' AND s.scope='market'
          LIMIT 1
        )
    ) THEN
      RAISE EXCEPTION 'scoped serving snapshot did not activate the scope-contract latch';
    END IF;

    -- Once active, a legacy all-Standard payload must fail before it can
    -- overwrite the scoped snapshot or trigger a directory regression.
    DECLARE
      rejected boolean := false;
      legacy_sets jsonb;
    BEGIN
      SELECT coalesce(jsonb_agg(e),'[]'::jsonb)
        INTO legacy_sets
      FROM jsonb_array_elements(payload->'sets') e
      WHERE coalesce(nullif(e->>'marketScope',''),'standard')='standard';

      BEGIN
        UPDATE public.pokemon_explore_set_value_snapshot_latest
        SET payload_json=jsonb_set(payload,'{sets}',legacy_sets,true)
        WHERE tcg='pokemon' AND scope='market';
      EXCEPTION WHEN SQLSTATE 'P0001' THEN
        IF SQLERRM LIKE 'LEGACY_VINTAGE_MARKET_SNAPSHOT_REJECTED:%' THEN
          rejected:=true;
        ELSE
          RAISE;
        END IF;
      END;

      IF NOT rejected THEN
        RAISE EXCEPTION 'active scope-contract latch allowed a legacy snapshot overwrite';
      END IF;
    END;

    payload_count:=jsonb_array_length(payload->'sets');
    SELECT count(distinct (e->>'setId')::uuid)::integer INTO root_count
    FROM jsonb_array_elements(payload->'sets') e;

    IF declared_market_count<>payload_count THEN
      RAISE EXCEPTION 'snapshot market_count % does not match payload market rows %',
        declared_market_count,payload_count;
    END IF;
    IF declared_set_count<>root_count THEN
      RAISE EXCEPTION 'snapshot set_count % does not match distinct root Sets %',
        declared_set_count,root_count;
    END IF;
    IF declared_market_count<declared_set_count THEN
      RAISE EXCEPTION 'snapshot market_count % cannot be less than root set_count %',
        declared_market_count,declared_set_count;
    END IF;

    PERFORM public.validate_pokemon_market_set_scope_payload_v1(
      payload,declared_market_count,declared_set_count
    );
    PERFORM public.validate_pokemon_market_scoped_history_baskets_v1(payload);

    SELECT count(*)::integer INTO directory_count
    FROM public.pokemon_market_explorer_prepared_directory_v1
    WHERE market_type='set';

    IF directory_count<>payload_count THEN
      RAISE EXCEPTION 'prepared Set directory count % does not match snapshot market count %',
        directory_count,payload_count;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_prepared_directory_v1 d
      JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=d.set_id
      WHERE d.market_type='set'
        AND d.market_key='set:'||d.set_id::text
    ) THEN
      RAISE EXCEPTION 'prepared directory retained a generic edition-split market';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_prepared_directory_v1 d
      WHERE d.market_type='set'
        AND (
          nullif(d.metadata->>'marketScope','') IS NULL
          OR nullif(d.metadata->>'baseSetName','') IS NULL
          OR d.metadata->>'scopeContractVersion'<>'pokemon-set-market-scope-v1'
        )
    ) THEN
      RAISE EXCEPTION 'prepared Set directory lost explicit scope metadata';
    END IF;

    -- Every prepared scoped constituent must match its market scope and as-of date.
    IF EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_prepared_constituents_v1 c
      JOIN public.pokemon_market_explorer_prepared_directory_v1 d
        ON d.generation_id=c.generation_id AND d.market_key=c.market_key
      WHERE d.market_type='set'
        AND coalesce(d.metadata->>'marketScope','standard')<>'standard'
        AND (
          c.price_as_of IS DISTINCT FROM d.source_as_of
          OR CASE d.metadata->>'marketScope'
               WHEN 'first_edition' THEN c.item->>'edition'<>'1st-edition'
               WHEN 'unlimited' THEN c.item->>'edition'<>'unlimited'
               WHEN 'shadowless' THEN c.item->>'edition'<>'shadowless'
               ELSE true
             END
        )
    ) THEN
      RAISE EXCEPTION 'prepared scoped constituent crossed edition scope or generation date';
    END IF;

    -- Source-defect histories must remain absent in the new generation.
    IF EXISTS (
      SELECT 1
      FROM public.pokemon_market_explorer_prepared_history_v1 h
      JOIN public.pokemon_market_explorer_prepared_directory_v1 d
        ON d.generation_id=h.generation_id AND d.market_key=h.market_key
      JOIN public.pokemon_market_scoped_history_market_certification_v1 c
        ON c.set_id=d.set_id AND c.market_scope=d.metadata->>'marketScope'
      WHERE c.history_publishable=false
    ) THEN
      RAISE EXCEPTION 'withheld source-defect scoped history was nevertheless published';
    END IF;

    -- v3 serving remains bounded by the existing compact pagination contract.
    IF to_regprocedure('public.get_pokemon_market_explorer_prepared_constituents_v3(text,uuid,integer,integer)') IS NULL THEN
      RAISE EXCEPTION 'v3 prepared constituent serving function is missing';
    END IF;
  END IF;
END
$test$;

-- Deployment contract: the migration ends with
-- NOTIFY pgrst,'reload schema'; so the scoped writer can send market_count
-- immediately after deployment without waiting for schema-cache expiry.

ROLLBACK;
