-- Market Explorer variant-level Near Mint execution authority. Corrected
-- before deployment: card_variant_id is the traded instrument; canonical IDs
-- remain metadata and Pokemon-membership authority only.
BEGIN;

CREATE OR REPLACE FUNCTION public.market_explorer_rarity_segment(p_rarity text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = ''
AS $function$
SELECT CASE lower(regexp_replace(replace(replace(trim(coalesce(p_rarity,'')),'_',' '),'-',' '),'[[:space:]]+',' ','g'))
 WHEN 'special illustration rare' THEN 'specialIllustrationRare'
 WHEN 'illustration rare' THEN 'illustrationRare'
 WHEN 'ultra rare' THEN 'ultraRare'
 WHEN 'hyper rare' THEN 'hyperRare'
 WHEN 'double rare' THEN 'doubleRare'
 WHEN 'rare ultra' THEN 'rareUltra'
 WHEN 'rare secret' THEN 'rareSecret'
 WHEN 'rare rainbow' THEN 'rareRainbow'
 WHEN 'rare holo' THEN 'rareHolo'
 ELSE NULL END;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_variant_authority(
    p_set_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
    canonical_card_id uuid, legacy_card_id uuid, card_variant_id uuid,
    set_id uuid, card_name text, card_number text, rarity text,
    edition text, printing_type text, special_type text, image_url text,
    identity_basis text
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
WITH canonical_scope AS (
    SELECT pcc.* FROM public.pokemon_canonical_cards pcc
    WHERE p_set_ids IS NULL OR cardinality(p_set_ids) = 0
       OR pcc.set_id = ANY(p_set_ids)
), candidates AS (
    SELECT pcc.id canonical_card_id, link.legacy_card_id, pcc.set_id,
           'explicit_legacy_identity_link'::text identity_basis, 0 identity_rank
    FROM canonical_scope pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = pcc.id
    UNION ALL
    SELECT pcc.id, card.id, pcc.set_id, 'parent_pokemon_tcg_api_id', 1
    FROM canonical_scope pcc JOIN public.cards card
      ON card.set_id = pcc.set_id
     AND card.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    UNION ALL
    SELECT pcc.id, card.id, pcc.set_id, 'variant_pokemon_tcg_api_id', 2
    FROM canonical_scope pcc
    JOIN public.card_variants matched
      ON matched.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    JOIN public.cards card ON card.id = matched.card_id AND card.set_id = pcc.set_id
    UNION ALL
    -- Compatibility fallback retained from the existing canonical resolver;
    -- it cannot win over an explicit or API identity.
    SELECT pcc.id, card.id, pcc.set_id, 'normalized_name_number_fallback', 3
    FROM canonical_scope pcc JOIN public.cards card
      ON card.set_id = pcc.set_id
     AND lower(regexp_replace(trim(card.name), '[[:space:]]+', ' ', 'g')) =
         lower(regexp_replace(trim(pcc.name), '[[:space:]]+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(card.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', ''))
), resolved AS (
    SELECT DISTINCT ON (canonical_card_id)
           canonical_card_id, legacy_card_id, set_id, identity_basis
    FROM candidates
    ORDER BY canonical_card_id, identity_rank, legacy_card_id
)
SELECT resolved.canonical_card_id, resolved.legacy_card_id, variant.id,
       resolved.set_id, canonical.name,
       coalesce(canonical.number, canonical.printed_number, legacy.card_number),
       canonical.rarity, variant.edition, variant.printing_type,
       variant.special_type,
       coalesce(variant.image_small_url, canonical.image_small_url, legacy.image_small_url),
       resolved.identity_basis
FROM resolved
JOIN public.pokemon_canonical_cards canonical ON canonical.id = resolved.canonical_card_id
JOIN public.cards legacy ON legacy.id = resolved.legacy_card_id
JOIN public.card_variants variant ON variant.card_id = resolved.legacy_card_id;
$function$;

CREATE TABLE IF NOT EXISTS public.pokemon_card_variant_market_price_intervals (
    observation_id uuid PRIMARY KEY,
    card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE CASCADE,
    canonical_card_id uuid NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE CASCADE,
    legacy_card_id uuid NOT NULL REFERENCES public.cards(id) ON DELETE CASCADE,
    set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    condition_id uuid NOT NULL REFERENCES public.conditions(id),
    market_price numeric NOT NULL CHECK (market_price > 0),
    valid_from date NOT NULL, valid_to date, source_date date NOT NULL,
    source text, card_name text, card_number text, rarity text,
    edition text, printing_type text, special_type text, image_url text,
    identity_basis text NOT NULL, refreshed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_card_variant_market_price_intervals_validity
      CHECK (valid_to IS NULL OR valid_to > valid_from)
);
COMMENT ON TABLE public.pokemon_card_variant_market_price_intervals IS
'Backend-only Near Mint USD validity intervals. Market Explorer constituent identity is card_variant_id.';

CREATE INDEX IF NOT EXISTS idx_pokemon_variant_market_intervals_set_validity
 ON public.pokemon_card_variant_market_price_intervals(set_id, valid_from, valid_to)
 INCLUDE(card_variant_id, canonical_card_id, market_price, rarity);
CREATE INDEX IF NOT EXISTS idx_pokemon_variant_market_intervals_variant_validity
 ON public.pokemon_card_variant_market_price_intervals(card_variant_id, valid_from, valid_to)
 INCLUDE(market_price, set_id, canonical_card_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_variant_market_intervals_canonical_validity
 ON public.pokemon_card_variant_market_price_intervals(canonical_card_id, valid_from, valid_to)
 INCLUDE(card_variant_id, market_price, set_id);

ALTER TABLE public.pokemon_card_variant_market_price_intervals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_card_variant_market_price_intervals FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, DELETE ON TABLE public.pokemon_card_variant_market_price_intervals TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_card_variant_market_price_intervals(
    p_card_variant_ids uuid[] DEFAULT NULL::uuid[]
) RETURNS bigint
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
DECLARE v_nm uuid; v_inserted bigint;
BEGIN
  -- A missing scope is deliberately a no-op. Historical publication is driven
  -- by the resumable backend script in bounded batches; this function must
  -- never turn an omitted PostgREST argument into a full-market transaction.
  IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 THEN
    RETURN 0;
  END IF;
  SELECT id INTO v_nm FROM public.conditions
   WHERE lower(name) = 'near mint' AND upper(abbreviation) = 'NM'
   ORDER BY id LIMIT 1;
  IF v_nm IS NULL THEN
    RAISE EXCEPTION 'Market Explorer requires authoritative Near Mint (NM) condition';
  END IF;
  DELETE FROM public.pokemon_card_variant_market_price_intervals interval_row
   WHERE interval_row.card_variant_id = ANY(p_card_variant_ids);
  WITH requested_variants AS MATERIALIZED (
    SELECT DISTINCT variant.id card_variant_id, card.set_id
    FROM public.card_variants variant
    JOIN public.cards card ON card.id = variant.card_id
    WHERE variant.id = ANY(p_card_variant_ids)
  ), requested_sets AS MATERIALIZED (
    SELECT array_agg(DISTINCT set_id ORDER BY set_id) set_ids
    FROM requested_variants
  ), authority AS MATERIALIZED (
    SELECT authority.*
    FROM requested_sets scope
    CROSS JOIN LATERAL public.get_pokemon_canonical_card_variant_authority(scope.set_ids) authority
    JOIN requested_variants requested
      ON requested.card_variant_id = authority.card_variant_id
  ), candidates AS (
    SELECT authority.*, observation.id observation_id,
           observation.condition_id, observation.market_price,
           observation.captured_at source_date, observation.source,
           row_number() OVER (
             PARTITION BY authority.card_variant_id, observation.captured_at
             ORDER BY observation.created_at DESC NULLS LAST, observation.id DESC) day_rank
    FROM authority JOIN public.card_variant_price_observations observation
      ON observation.card_variant_id = authority.card_variant_id
    WHERE observation.condition_id = v_nm AND observation.market_price > 0
      AND observation.captured_at IS NOT NULL
      AND trim(both '"' from upper(coalesce(observation.currency, ''))) = 'USD'
  ), winners AS MATERIALIZED (
    SELECT * FROM candidates WHERE day_rank = 1
  ), intervals AS (
    SELECT winners.*,
           lead(source_date) OVER (PARTITION BY card_variant_id ORDER BY source_date) valid_to
    FROM winners
  )
  INSERT INTO public.pokemon_card_variant_market_price_intervals(
    observation_id, card_variant_id, canonical_card_id, legacy_card_id, set_id,
    condition_id, market_price, valid_from, valid_to, source_date, source,
    card_name, card_number, rarity, edition, printing_type, special_type,
    image_url, identity_basis, refreshed_at)
  SELECT observation_id, card_variant_id, canonical_card_id, legacy_card_id, set_id,
         condition_id, market_price, source_date, valid_to, source_date, source,
         card_name, card_number, rarity, edition, printing_type, special_type,
         image_url, identity_basis, now()
  FROM intervals;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RETURN v_inserted;
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_card_variant_market_price_intervals(uuid[])
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_card_variant_market_price_intervals(uuid[]) TO service_role;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_card_variant_market_price_intervals_for_sets(
    p_set_ids uuid[]
) RETURNS bigint
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
DECLARE v_variant_ids uuid[];
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids) = 0 THEN
    RETURN 0;
  END IF;
  SELECT array_agg(authority.card_variant_id ORDER BY authority.card_variant_id)
    INTO v_variant_ids
  FROM public.get_pokemon_canonical_card_variant_authority(p_set_ids) authority;
  RETURN public.refresh_pokemon_card_variant_market_price_intervals(v_variant_ids);
END;
$function$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[])
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_card_variant_market_price_intervals_for_sets(uuid[])
 TO service_role;

-- A preview environment may have installed the superseded pending signature;
-- remove it so PostgREST cannot expose two ambiguous cohort overloads.
DROP FUNCTION IF EXISTS public.get_pokemon_market_explorer_filtered_cohort(
 uuid[],date,date,uuid[],text[],text[],integer);

CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort(
 p_set_ids uuid[], p_start_date date, p_end_date date,
 p_card_ids uuid[] DEFAULT NULL::uuid[],
 p_segment_ids text[] DEFAULT NULL::text[],
 p_pokemon_ids bigint[] DEFAULT NULL::bigint[],
 p_price_segment_ids text[] DEFAULT NULL::text[],
 p_release_age_cohort_ids text[] DEFAULT NULL::text[],
 p_top_n integer DEFAULT NULL::integer
)
RETURNS TABLE(market_date date, constituent_count bigint,
 eligible_universe_count bigint, basket_value numeric, common_count bigint,
 common_current_value numeric, common_previous_value numeric,
 current_constituents jsonb)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
WITH market_dates AS MATERIALIZED (
 SELECT DISTINCT quality.market_date FROM public.pokemon_market_date_quality quality
 WHERE quality.tcg = 'pokemon' AND quality.status IN ('READY','LEGACY_VERIFIED')
   AND quality.market_date BETWEEN p_start_date AND p_end_date
), panel AS MATERIALIZED (
 SELECT dates.market_date, fact.*
 FROM market_dates dates
 JOIN public.pokemon_card_variant_market_price_intervals fact
   ON fact.set_id = ANY(p_set_ids) AND fact.valid_from <= dates.market_date
  AND (fact.valid_to IS NULL OR dates.market_date < fact.valid_to)
 JOIN public.sets set_row ON set_row.id = fact.set_id
 WHERE (p_card_ids IS NULL OR cardinality(p_card_ids)=0 OR fact.canonical_card_id=ANY(p_card_ids))
 AND (p_segment_ids IS NULL OR cardinality(p_segment_ids)=0
      OR public.market_explorer_rarity_segment(fact.rarity)=ANY(p_segment_ids))
 AND (p_pokemon_ids IS NULL OR cardinality(p_pokemon_ids)=0 OR EXISTS (
      SELECT 1 FROM public.pokemon_card_desirability_links pokemon_link
      WHERE pokemon_link.pokemon_canonical_card_id=fact.canonical_card_id
        AND pokemon_link.pokemon_reference_id=ANY(p_pokemon_ids)))
 AND (p_price_segment_ids IS NULL OR cardinality(p_price_segment_ids)=0
   OR ('obtainable'=ANY(p_price_segment_ids) AND fact.market_price<10)
   OR ('intermediate'=ANY(p_price_segment_ids) AND fact.market_price>=10 AND fact.market_price<100)
   OR ('premium'=ANY(p_price_segment_ids) AND fact.market_price>=100))
 AND (p_release_age_cohort_ids IS NULL OR cardinality(p_release_age_cohort_ids)=0
   OR (set_row.release_date IS NOT NULL AND dates.market_date>=set_row.release_date AND (
      ('new'=ANY(p_release_age_cohort_ids) AND dates.market_date-set_row.release_date<=180)
   OR ('recent'=ANY(p_release_age_cohort_ids) AND dates.market_date-set_row.release_date BETWEEN 181 AND 730)
   OR ('established'=ANY(p_release_age_cohort_ids) AND dates.market_date-set_row.release_date BETWEEN 731 AND 1825)
   OR ('legacy'=ANY(p_release_age_cohort_ids) AND dates.market_date-set_row.release_date>1825))))
), ranked AS (
 SELECT panel.*, row_number() OVER(PARTITION BY market_date
   ORDER BY market_price DESC, card_variant_id) market_rank FROM panel
), selected AS MATERIALIZED (
 SELECT * FROM ranked WHERE p_top_n IS NULL OR market_rank<=p_top_n
), dates AS (
 SELECT market_date, lag(market_date) OVER(ORDER BY market_date) previous_market_date,
        max(market_date) OVER() latest_market_date
 FROM (SELECT DISTINCT market_date FROM panel) observed
), eligible AS (
 SELECT market_date,count(*) eligible_universe_count FROM panel GROUP BY market_date
)
SELECT dates.market_date, count(cur.card_variant_id)::bigint,
 eligible.eligible_universe_count::bigint, coalesce(sum(cur.market_price),0)::numeric,
 count(prev.card_variant_id)::bigint,
 coalesce(sum(cur.market_price) FILTER(WHERE prev.card_variant_id IS NOT NULL),0)::numeric,
 coalesce(sum(prev.market_price),0)::numeric,
 CASE WHEN dates.market_date=dates.latest_market_date THEN coalesce(jsonb_agg(jsonb_build_object(
   'card_variant_id',cur.card_variant_id,'canonical_card_id',cur.canonical_card_id,
   'legacy_card_id',cur.legacy_card_id,'set_id',cur.set_id,'card_name',cur.card_name,
   'card_number',cur.card_number,'rarity',cur.rarity,'edition',cur.edition,
   'printing_type',cur.printing_type,'special_type',cur.special_type,'image_url',cur.image_url,
   'market_date',cur.market_date,'market_price',cur.market_price,'rank',cur.market_rank)
   ORDER BY cur.market_rank) FILTER(WHERE cur.card_variant_id IS NOT NULL),'[]'::jsonb) ELSE NULL END
FROM dates JOIN eligible ON eligible.market_date=dates.market_date
LEFT JOIN selected cur ON cur.market_date=dates.market_date
LEFT JOIN selected prev ON prev.market_date=dates.previous_market_date
 AND prev.card_variant_id=cur.card_variant_id
GROUP BY dates.market_date,dates.previous_market_date,dates.latest_market_date,
 eligible.eligible_universe_count ORDER BY dates.market_date;
$function$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) IS
'Variant-correct Market Explorer cohort over prepared Near Mint USD validity intervals; filter first, rank and common-link by card_variant_id.';
REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_variant_authority(uuid[]) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.market_explorer_rarity_segment(text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_variant_authority(uuid[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.market_explorer_rarity_segment(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_filtered_cohort(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer) TO service_role;

-- Historical population is intentionally NOT part of this migration. Production
-- history exceeds one statement's safe deployment budget. Publish it afterward
-- with backend/scripts/backfill_market_explorer_variant_intervals.py, beginning
-- with one small set and using bounded, resumable variant batches.
COMMIT;
