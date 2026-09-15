BEGIN;

CREATE TEMP TABLE pokemon_market_root_history_repair_work_v1 ON COMMIT DROP AS
WITH active AS (
  SELECT set_id,activated_market_date,deactivated_market_date
  FROM public.pokemon_market_root_authority
  WHERE enabled
), pairs AS (
  SELECT h.set_id,h.snapshot_date
  FROM public.pokemon_set_value_daily_history h
  JOIN active a ON a.set_id=h.set_id
  JOIN public.pokemon_market_root_set_value_daily_history_v2_shadow r
    ON r.set_id=h.set_id
   AND r.market_scope='standard'
   AND r.market_date=h.snapshot_date
  WHERE h.value_scope='standard'
    AND h.source='card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
    AND r.certified_on_date
    AND h.snapshot_date>=greatest(a.activated_market_date,DATE '2026-09-10')
    AND (a.deactivated_market_date IS NULL OR h.snapshot_date<a.deactivated_market_date)
    AND (round(h.set_value,2),h.priced_card_count,h.total_card_count,round(h.coverage_pct,2))
        IS DISTINCT FROM
        (round(r.set_value,2),r.priced_card_count,r.expected_card_count,round(r.coverage_pct,2))
), members AS (
  SELECT p.set_id AS root_set_id,p.snapshot_date,p.set_id AS member_set_id
  FROM pairs p
  UNION ALL
  SELECT p.set_id,p.snapshot_date,c.id
  FROM pairs p
  JOIN public.sets c
    ON c.parent_opening_set_id=p.set_id
   AND c.counts_toward_parent_set_value=true
), expected AS (
  SELECT m.root_set_id,m.snapshot_date,count(distinct pc.id)::integer AS expected_count
  FROM members m
  JOIN public.pokemon_canonical_cards pc
    ON pc.set_id=m.member_set_id
   AND pc.set_value_eligible=true
  GROUP BY m.root_set_id,m.snapshot_date
), raw_prices AS (
  SELECT m.root_set_id,m.snapshot_date,x.*
  FROM members m
  CROSS JOIN LATERAL public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(
    m.member_set_id,m.snapshot_date
  ) x
), dedup AS (
  SELECT rp.*,
         row_number() OVER (
           PARTITION BY root_set_id,snapshot_date,canonical_card_id
           ORDER BY captured_at DESC NULLS LAST,card_variant_id DESC
         ) AS pick
  FROM raw_prices rp
), picked AS (
  SELECT * FROM dedup WHERE pick=1
), ranked AS (
  SELECT p.*,
         row_number() OVER (
           PARTITION BY root_set_id,snapshot_date
           ORDER BY market_price DESC NULLS LAST,canonical_card_id
         ) AS price_rank
  FROM picked p
)
SELECT r.root_set_id AS set_id,
       r.snapshot_date,
       round(sum(r.market_price),2) AS standard_value,
       count(*)::integer AS priced_count,
       e.expected_count,
       round(count(*)::numeric/nullif(e.expected_count,0)*100,2) AS coverage_pct,
       round(sum(r.market_price) FILTER (WHERE price_rank<=10),2) AS top10_value,
       count(*) FILTER (WHERE price_rank<=10)::integer AS top10_count
FROM ranked r
JOIN expected e
  ON e.root_set_id=r.root_set_id
 AND e.snapshot_date=r.snapshot_date
GROUP BY r.root_set_id,r.snapshot_date,e.expected_count;

DO $repair$
DECLARE
  v_pairs integer;
  v_full integer;
  v_full_top10 integer;
  v_identity_digest text;
  v_computed_digest text;
  v_old_standard_sum numeric;
  v_new_standard_sum numeric;
  v_old_top10_sum numeric;
  v_new_top10_sum numeric;
  v_standard_updated integer;
  v_top10_updated integer;
BEGIN
  SELECT count(*)::integer,
         count(*) FILTER (WHERE w.priced_count=w.expected_count)::integer,
         count(*) FILTER (WHERE w.top10_count=10)::integer,
         md5(string_agg(w.set_id::text||':'||w.snapshot_date::text,',' ORDER BY w.set_id,w.snapshot_date)),
         md5(string_agg(w.set_id::text||':'||w.snapshot_date::text||':'||w.standard_value::text||':'||w.top10_value::text,',' ORDER BY w.set_id,w.snapshot_date)),
         round(sum(hs.set_value),2),round(sum(w.standard_value),2),
         round(sum(ht.set_value),2),round(sum(w.top10_value),2)
    INTO v_pairs,v_full,v_full_top10,v_identity_digest,v_computed_digest,
         v_old_standard_sum,v_new_standard_sum,v_old_top10_sum,v_new_top10_sum
  FROM pg_temp.pokemon_market_root_history_repair_work_v1 w
  JOIN public.pokemon_set_value_daily_history hs
    ON hs.set_id=w.set_id AND hs.snapshot_date=w.snapshot_date AND hs.value_scope='standard'
  JOIN public.pokemon_set_value_daily_history ht
    ON ht.set_id=w.set_id AND ht.snapshot_date=w.snapshot_date AND ht.value_scope='top10'
  WHERE hs.source='card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist'
    AND ht.source='card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist';

  -- Data-less/fixture branches have no production repair cohort; replay there is a no-op.
  IF v_pairs=0 THEN
    RAISE NOTICE 'No certified post-cutover generic root-history cohort to repair';
    RETURN;
  END IF;

  IF v_pairs<>113 OR v_full<>113 OR v_full_top10<>113
     OR v_identity_digest<>'a4d1cd357c3a73999e08e2b5f5b6bc22'
     OR v_computed_digest<>'c404f7946b8239254ee087964b3143d0'
     OR v_old_standard_sum<>150493.27 OR v_new_standard_sum<>185501.53
     OR v_old_top10_sum<>112890.55 OR v_new_top10_sum<>133801.88 THEN
    RAISE EXCEPTION 'Canonical historical repair cohort changed: pairs=% full=% top10=% identity=% computed=% std=%->% top10=%->%',
      v_pairs,v_full,v_full_top10,v_identity_digest,v_computed_digest,
      v_old_standard_sum,v_new_standard_sum,v_old_top10_sum,v_new_top10_sum;
  END IF;

  UPDATE public.pokemon_set_value_daily_history h
  SET set_value=w.standard_value,
      priced_card_count=w.priced_count,
      total_card_count=w.expected_count,
      source='canonical_root_standard_backfill_v1',
      canonical_card_count=w.expected_count,
      linked_card_count=w.expected_count,
      included_card_count=w.priced_count,
      coverage_pct=w.coverage_pct,
      updated_at=now()
  FROM pg_temp.pokemon_market_root_history_repair_work_v1 w
  WHERE h.set_id=w.set_id
    AND h.snapshot_date=w.snapshot_date
    AND h.value_scope='standard'
    AND h.source='card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist';
  GET DIAGNOSTICS v_standard_updated=ROW_COUNT;

  UPDATE public.pokemon_set_value_daily_history h
  SET set_value=w.top10_value,
      priced_card_count=10,
      total_card_count=10,
      source='canonical_root_top10_backfill_v1',
      canonical_card_count=10,
      linked_card_count=10,
      included_card_count=10,
      coverage_pct=100.00,
      updated_at=now()
  FROM pg_temp.pokemon_market_root_history_repair_work_v1 w
  WHERE h.set_id=w.set_id
    AND h.snapshot_date=w.snapshot_date
    AND h.value_scope='top10'
    AND h.source='card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist';
  GET DIAGNOSTICS v_top10_updated=ROW_COUNT;

  IF v_standard_updated<>113 OR v_top10_updated<>113 THEN
    RAISE EXCEPTION 'Canonical historical repair wrote standard=% top10=%; expected 113 each',
      v_standard_updated,v_top10_updated;
  END IF;

  INSERT INTO public.price_storage_v2_migration_audit(phase,details)
  VALUES (
    'certified_post_cutover_standard_top10_canonical_asof_repair_20260915',
    jsonb_build_object(
      'pairsRepaired',v_pairs,
      'standardRowsUpdated',v_standard_updated,
      'top10RowsUpdated',v_top10_updated,
      'identityDigest',v_identity_digest,
      'computedDigest',v_computed_digest,
      'oldStandardValueSum',v_old_standard_sum,
      'newStandardValueSum',v_new_standard_sum,
      'oldTop10ValueSum',v_old_top10_sum,
      'newTop10ValueSum',v_new_top10_sum,
      'priceAuthority','get_pokemon_set_value_canonical_prices_as_of_v2_shadow',
      'standardSourceAfter','canonical_root_standard_backfill_v1',
      'top10SourceAfter','canonical_root_top10_backfill_v1',
      'rootAuthorityCutover','2026-09-10',
      'certifiedShadowGate',true
    )
  );
END;
$repair$;

COMMIT;
