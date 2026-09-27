-- Additive repair for the existing edition-history authority. This does NOT
-- activate price_storage_v2_scoped_release_gate or change edition identities.
-- Each call writes ONE root and ONE explicitly approved market date.
SET lock_timeout = '2s';
SET statement_timeout = '15s';

CREATE TABLE public.pokemon_edition_history_refresh_state_v1 (
  set_id uuid NOT NULL REFERENCES public.sets(id),
  market_date date NOT NULL,
  source_fingerprint text NOT NULL,
  history_fingerprint text NOT NULL,
  scope_count integer NOT NULL CHECK (scope_count BETWEEN 2 AND 3),
  certified_scope_count integer NOT NULL CHECK (certified_scope_count BETWEEN 0 AND 3),
  raw_v2_equal boolean NOT NULL CHECK (raw_v2_equal),
  source_completed_at timestamptz NOT NULL,
  completed_at timestamptz NOT NULL DEFAULT now(),
  receipt jsonb NOT NULL,
  PRIMARY KEY (set_id, market_date)
);
ALTER TABLE public.pokemon_edition_history_refresh_state_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_edition_history_refresh_state_v1 FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.pokemon_edition_history_refresh_state_v1 TO service_role;

CREATE FUNCTION public.get_pokemon_edition_card_prices_as_of_v1(
  p_root_set_id uuid, p_market_date date, p_raw_oracle boolean DEFAULT false
) RETURNS TABLE (
  canonical_card_id uuid, member_set_id uuid, market_scope text,
  card_variant_id uuid, edition text, market_price numeric,
  observed_date date, canonical_review_status text
)
LANGUAGE sql STABLE SET search_path = '' AS $fn$
WITH root AS (
  SELECT s.id,r.profile FROM public.sets s
  JOIN public.pokemon_edition_split_root_sets_v2 r ON r.set_id=s.id
  WHERE s.id=p_root_set_id AND s.parent_opening_set_id IS NULL AND NOT s.catalog_only
    AND p_market_date IS NOT NULL
), members AS (
  SELECT id FROM root
  UNION ALL
  SELECT s.id FROM public.sets s JOIN root r ON s.parent_opening_set_id=r.id
  WHERE s.counts_toward_parent_set_value
), checklist AS (
  SELECT c.id,c.set_id,c.rarity,c.canonical_review_status
  FROM public.pokemon_canonical_cards c JOIN members m ON m.id=c.set_id
  WHERE c.set_value_eligible
), scopes AS (
  SELECT unnest(CASE WHEN profile='base_three_printings'
    THEN ARRAY['first_edition','shadowless','unlimited']::text[]
    ELSE ARRAY['first_edition','unlimited']::text[] END) AS market_scope FROM root
), nm AS (
  SELECT id FROM public.conditions WHERE lower(name)='near mint' ORDER BY id LIMIT 1
), candidates AS (
  SELECT c.id AS canonical_card_id,c.set_id AS member_set_id,s.market_scope,
         m.card_variant_id,m.edition,price.market_price,price.observed_date,c.canonical_review_status,
         row_number() OVER (PARTITION BY c.id,s.market_scope ORDER BY
           CASE m.identity_basis WHEN 'explicit_legacy_identity_link' THEN 0
             WHEN 'parent_pokemon_tcg_api_id' THEN 1
             WHEN 'normalized_name_number_fallback' THEN 2 ELSE 9 END,
           CASE WHEN m.special_type IS NULL OR m.special_type='' THEN 0 ELSE 1 END,
           CASE WHEN c.rarity IN ('Common','Uncommon') AND m.printing_type='non-holo' THEN 0
             WHEN c.rarity IN ('Common','Uncommon') AND m.printing_type='holo' THEN 1
             WHEN c.rarity IN ('Common','Uncommon') AND m.printing_type='reverse-holo' THEN 2
             WHEN m.printing_type='holo' THEN 0 WHEN m.printing_type='non-holo' THEN 1
             WHEN m.printing_type='reverse-holo' THEN 2 ELSE 9 END,
           price.observed_date DESC NULLS LAST,m.card_variant_id) AS choice
  FROM checklist c CROSS JOIN scopes s CROSS JOIN nm
  LEFT JOIN public.pokemon_market_explorer_card_current_metadata m
    ON m.canonical_card_id=c.id AND m.set_id=c.set_id
    AND m.edition=CASE s.market_scope WHEN 'first_edition' THEN '1st-edition' ELSE s.market_scope END
  LEFT JOIN LATERAL (
    SELECT ev.market_price,obs.observed_date
    FROM LATERAL (
      SELECT max(least(r.observed_through,p_market_date)) AS observed_date
      FROM public.card_variant_price_observation_ranges_v2 r
      WHERE NOT p_raw_oracle AND r.card_variant_id=m.card_variant_id
        AND r.condition_id=nm.id AND r.source='TCGPlayer' AND r.currency='USD'
        AND r.observed_from<=p_market_date
    ) obs
    JOIN LATERAL (
      SELECT e.market_price FROM public.card_variant_price_events_v2 e
      WHERE NOT p_raw_oracle AND e.card_variant_id=m.card_variant_id
        AND e.condition_id=nm.id AND e.source='TCGPlayer' AND e.currency='USD'
        AND e.effective_date<=p_market_date AND e.market_price>0
      ORDER BY e.effective_date DESC,e.id DESC LIMIT 1
    ) ev ON obs.observed_date IS NOT NULL
    WHERE NOT p_raw_oracle
    UNION ALL
    SELECT raw.market_price,raw.captured_at FROM LATERAL (
      SELECT o.market_price,o.captured_at FROM public.card_variant_price_observations o
      WHERE p_raw_oracle AND o.card_variant_id=m.card_variant_id
        AND o.condition_id=nm.id AND o.source='TCGPlayer'
        AND trim(both '"' FROM upper(coalesce(o.currency,'')))='USD'
        AND o.captured_at<=p_market_date AND o.market_price>0
      ORDER BY o.captured_at DESC,o.created_at DESC,o.id DESC LIMIT 1
    ) raw WHERE p_raw_oracle
  ) price ON true
)
SELECT canonical_card_id,member_set_id,market_scope,card_variant_id,edition,
       market_price,observed_date,canonical_review_status
FROM candidates WHERE choice=1
ORDER BY market_scope,canonical_card_id;
$fn$;
REVOKE ALL ON FUNCTION public.get_pokemon_edition_card_prices_as_of_v1(uuid,date,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_edition_card_prices_as_of_v1(uuid,date,boolean) TO service_role;

CREATE FUNCTION public.refresh_pokemon_edition_history_day_v1(
  p_root_set_id uuid,p_market_date date,p_force boolean DEFAULT false
) RETURNS jsonb LANGUAGE plpgsql SET search_path = '' SET lock_timeout='1s' AS $fn$
DECLARE
  v_profile text; v_members uuid[]; v_expected_scopes integer;
  v_sources jsonb; v_bad integer; v_source_completed timestamptz;
  v_identity text; v_source_fp text; v_history_fp text;
  v_old public.pokemon_edition_history_refresh_state_v1%rowtype;
  v_v2 jsonb; v_raw jsonb; v_values jsonb; v_result jsonb;
  v_existing_fp text; v_certified integer; v_rows integer;
BEGIN
  IF p_root_set_id IS NULL OR p_market_date IS NULL
    OR p_market_date>timezone('America/Phoenix',now())::date THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='An explicit nonfuture root/date is required';
  END IF;
  SELECT r.profile INTO v_profile FROM public.pokemon_edition_split_root_sets_v2 r
  JOIN public.sets s ON s.id=r.set_id
  WHERE r.set_id=p_root_set_id AND s.parent_opening_set_id IS NULL AND NOT s.catalog_only;
  IF v_profile IS NULL OR v_profile NOT IN ('base_three_printings','edition_split') THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Root must have an accepted explicit edition profile';
  END IF;
  v_expected_scopes:=CASE WHEN v_profile='base_three_printings' THEN 3 ELSE 2 END;
  IF NOT EXISTS (SELECT 1 FROM public.pokemon_market_date_quality
    WHERE tcg='pokemon' AND market_date=p_market_date AND status IN ('READY','LEGACY_VERIFIED')) THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Target Market quality date is not approved';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.pokemon_scrape_batches
    WHERE market_date=p_market_date AND status='complete' AND promoted_at IS NOT NULL
      AND expected_set_count>0 AND succeeded_set_count=expected_set_count
      AND coalesce(failed_set_count,0)=0 AND coalesce(missing_set_count,0)=0) THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Target scrape batch is not complete/promoted';
  END IF;
  IF NOT pg_try_advisory_xact_lock(hashtextextended('edition-history-day-v1',0)) THEN
    RAISE EXCEPTION USING ERRCODE='55P03',MESSAGE='Another edition-history writer is active';
  END IF;
  SELECT array_agg(id ORDER BY id) INTO v_members FROM public.sets
    WHERE id=p_root_set_id OR (parent_opening_set_id=p_root_set_id AND counts_toward_parent_set_value);
  WITH sources AS (
    SELECT m.id,j.id AS job_id,j.completed_at,q.source_completed_at,q.completed_at AS projected_at,
      coalesce(j.status='completed' AND j.completed_at IS NOT NULL
        AND q.status='complete' AND q.source_completed_at>=j.completed_at
        AND q.completed_at>=j.completed_at,false) AS ready
    FROM unnest(v_members) m(id)
    LEFT JOIN LATERAL (SELECT id,status,completed_at FROM public.scrape_jobs
      WHERE set_id=m.id AND market_date=p_market_date ORDER BY created_at DESC,id DESC LIMIT 1) j ON true
    LEFT JOIN public.price_storage_v2_shadow_queue q ON q.set_id=m.id AND q.market_date=p_market_date
  ) SELECT jsonb_agg(to_jsonb(s) ORDER BY id),count(*) FILTER(WHERE NOT ready),max(completed_at)
    INTO v_sources,v_bad,v_source_completed FROM sources s;
  IF v_bad>0 OR v_source_completed IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Exact-date member price projections are incomplete';
  END IF;
  SELECT md5(coalesce(string_agg(jsonb_build_array(c.id,c.set_id,c.rarity,c.canonical_review_status,
      m.card_variant_id,m.edition,m.printing_type,m.special_type,m.identity_basis)::text,
      '|' ORDER BY c.id,m.card_variant_id),'')) INTO v_identity
    FROM public.pokemon_canonical_cards c
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata m ON m.canonical_card_id=c.id AND m.set_id=c.set_id
    WHERE c.set_id=ANY(v_members) AND c.set_value_eligible;
  v_source_fp:=md5(v_sources::text||v_identity||v_profile||
    pg_get_functiondef('public.get_pokemon_edition_card_prices_as_of_v1(uuid,date,boolean)'::regprocedure));
  SELECT * INTO v_old FROM public.pokemon_edition_history_refresh_state_v1
    WHERE set_id=p_root_set_id AND market_date=p_market_date;
  SELECT md5(coalesce(string_agg(jsonb_build_array(h.market_scope,h.set_value,h.expected_card_count,
    h.priced_card_count,h.coverage_pct,h.certified_on_date)::text,'|' ORDER BY h.market_scope),''))
    INTO v_existing_fp FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.set_id=p_root_set_id AND h.market_date=p_market_date AND h.market_scope<>'standard';
  IF NOT p_force AND v_old.source_fingerprint=v_source_fp AND v_old.history_fingerprint=v_existing_fp THEN
    RETURN v_old.receipt||jsonb_build_object('status','noop');
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY market_scope,canonical_card_id),'[]'::jsonb)
    INTO v_v2 FROM public.get_pokemon_edition_card_prices_as_of_v1(p_root_set_id,p_market_date,false) x;
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY market_scope,canonical_card_id),'[]'::jsonb)
    INTO v_raw FROM public.get_pokemon_edition_card_prices_as_of_v1(p_root_set_id,p_market_date,true) x;
  IF v_v2 IS DISTINCT FROM v_raw THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Edition as-of raw/V2 price or provenance mismatch; no history written';
  END IF;
  IF jsonb_array_length(v_v2)=0 THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='No eligible canonical checklist for edition history';
  END IF;
  SELECT jsonb_agg(to_jsonb(a) ORDER BY market_scope),count(*) FILTER(WHERE certified_on_date)
    INTO v_values,v_certified FROM (
      SELECT x.market_scope,round(coalesce(sum(x.market_price),0),2) AS set_value,
        count(*)::integer AS expected_card_count,count(x.market_price)::integer AS priced_card_count,
        round(100*count(x.market_price)::numeric/count(*),2) AS coverage_pct,
        (count(*)>0 AND count(x.market_price)=count(*)
          AND count(*) FILTER(WHERE x.canonical_review_status='needs_review')=0) AS certified_on_date
      FROM jsonb_to_recordset(v_v2) x(market_scope text,market_price numeric,canonical_review_status text)
      GROUP BY x.market_scope
    ) a;
  IF jsonb_array_length(v_values)<>v_expected_scopes THEN
    RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Edition scope membership is incomplete';
  END IF;
  INSERT INTO public.pokemon_market_root_set_value_daily_history_v2_shadow
    (set_id,market_scope,market_date,set_value,expected_card_count,priced_card_count,coverage_pct,certified_on_date,source,updated_at)
  SELECT p_root_set_id,x.market_scope,p_market_date,x.set_value,x.expected_card_count,
    x.priced_card_count,x.coverage_pct,x.certified_on_date,'edition_exact_asof_raw_v2_verified_v1',now()
  FROM jsonb_to_recordset(v_values) x(market_scope text,set_value numeric,expected_card_count integer,
    priced_card_count integer,coverage_pct numeric,certified_on_date boolean)
  ON CONFLICT (set_id,market_scope,market_date) DO UPDATE SET
    set_value=excluded.set_value,expected_card_count=excluded.expected_card_count,
    priced_card_count=excluded.priced_card_count,coverage_pct=excluded.coverage_pct,
    certified_on_date=excluded.certified_on_date,source=excluded.source,updated_at=excluded.updated_at;
  GET DIAGNOSTICS v_rows=ROW_COUNT;
  SELECT md5(string_agg(jsonb_build_array(h.market_scope,h.set_value,h.expected_card_count,
    h.priced_card_count,h.coverage_pct,h.certified_on_date)::text,'|' ORDER BY h.market_scope))
    INTO v_history_fp FROM public.pokemon_market_root_set_value_daily_history_v2_shadow h
    WHERE h.set_id=p_root_set_id AND h.market_date=p_market_date AND h.market_scope<>'standard';
  v_result:=jsonb_build_object('status','complete','root_set_id',p_root_set_id,'market_date',p_market_date,
    'raw_v2_equal',true,'scope_count',v_rows,'certified_scope_count',v_certified,
    'source_fingerprint',v_source_fp,'history_fingerprint',v_history_fp,'scopes',v_values,
    'pricing_policy','edition_exact_asof_v1','completed_at',now());
  INSERT INTO public.pokemon_edition_history_refresh_state_v1
    (set_id,market_date,source_fingerprint,history_fingerprint,scope_count,certified_scope_count,
     raw_v2_equal,source_completed_at,completed_at,receipt)
  VALUES (p_root_set_id,p_market_date,v_source_fp,v_history_fp,v_rows,v_certified,true,v_source_completed,now(),v_result)
  ON CONFLICT (set_id,market_date) DO UPDATE SET source_fingerprint=excluded.source_fingerprint,
    history_fingerprint=excluded.history_fingerprint,scope_count=excluded.scope_count,
    certified_scope_count=excluded.certified_scope_count,raw_v2_equal=true,
    source_completed_at=excluded.source_completed_at,completed_at=excluded.completed_at,receipt=excluded.receipt;
  RETURN v_result;
END;
$fn$;
REVOKE ALL ON FUNCTION public.refresh_pokemon_edition_history_day_v1(uuid,date,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_edition_history_day_v1(uuid,date,boolean) TO service_role;

COMMENT ON FUNCTION public.refresh_pokemon_edition_history_day_v1(uuid,date,boolean) IS
'One-root exact-date history refresh. Requires approved/promoted source date, member projection provenance, exact raw/V2 parity; never borrows another edition or relabels latest prices.';
NOTIFY pgrst,'reload schema';
RESET statement_timeout;
RESET lock_timeout;
