WITH latest_market_date AS (
  SELECT max(q.market_date)::date market_date
  FROM public.pokemon_market_date_quality q
  WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED')
), already AS (
  SELECT set_id FROM public.pokemon_market_rollout_root_sets_v1
), std_src AS (
  SELECT v.set_id,v.set_value,v.priced_card_count,v.expected_card_count,v.coverage_pct
  FROM public.pokemon_market_root_set_value_latest_v1 v
  JOIN public.sets s ON s.id=v.set_id
  CROSS JOIN latest_market_date d
  WHERE v.market_scope='standard'
    AND s.parent_opening_set_id IS NULL
    AND coalesce(s.catalog_only,false)=false
    AND coalesce(s.ready_for_daily_scrape,false)=true
    AND coalesce(v.coverage_pct,0)>=95
    AND v.set_id NOT IN (SELECT set_id FROM already)
), std_hist AS (
  SELECT h.set_id,h.set_value,h.priced_card_count,h.total_card_count
  FROM public.pokemon_set_value_daily_history h
  CROSS JOIN latest_market_date d
  WHERE h.snapshot_date=d.market_date AND h.value_scope='standard'
), std_exact AS (
  SELECT s.set_id
  FROM std_src s JOIN std_hist h USING(set_id)
  WHERE s.set_value=h.set_value
    AND s.priced_card_count=h.priced_card_count
    AND s.expected_card_count=h.total_card_count
), chase_src AS (
  SELECT t.set_id,t.rank,t.canonical_card_id card_id,t.card_variant_id,t.market_price
  FROM public.pokemon_market_root_set_top10_latest_v1 t
  JOIN std_exact e USING(set_id)
  WHERE t.market_scope='standard' AND t.publishable_100pct AND t.rank BETWEEN 1 AND 10
), chase_hist AS (
  SELECT h.set_id,h.rank,h.card_id,h.card_variant_id,h.market_price
  FROM public.pokemon_set_top_chase_card_daily_history h
  JOIN std_exact e USING(set_id)
  CROSS JOIN latest_market_date d
  WHERE h.snapshot_date=d.market_date
), chase_summary AS (
  SELECT e.set_id,
         (SELECT count(*) FROM chase_src s WHERE s.set_id=e.set_id) src_count,
         (SELECT count(*) FROM chase_hist h WHERE h.set_id=e.set_id) hist_count,
         (SELECT count(*) FROM (
            SELECT coalesce(s.rank,h.rank) rank,
                   s.card_id s_card,h.card_id h_card,
                   s.card_variant_id s_variant,h.card_variant_id h_variant,
                   s.market_price s_price,h.market_price h_price
            FROM (SELECT * FROM chase_src WHERE set_id=e.set_id) s
            FULL JOIN (SELECT * FROM chase_hist WHERE set_id=e.set_id) h USING(rank)
          ) x
          WHERE s_card IS DISTINCT FROM h_card
             OR s_variant IS DISTINCT FROM h_variant
             OR s_price IS DISTINCT FROM h_price) mismatches
  FROM std_exact e
), top10_hist AS (
  SELECT h.set_id,h.set_value,h.priced_card_count,h.total_card_count
  FROM public.pokemon_set_value_daily_history h
  CROSS JOIN latest_market_date d
  WHERE h.snapshot_date=d.market_date AND h.value_scope='top10'
), top10_src AS (
  SELECT set_id,round(sum(market_price)::numeric,2) set_value,count(*)::int card_count
  FROM chase_src GROUP BY set_id HAVING count(*)=10
), safe_roots AS (
  SELECT e.set_id
  FROM std_exact e
  JOIN chase_summary cs USING(set_id)
  JOIN top10_src ts USING(set_id)
  JOIN top10_hist th USING(set_id)
  WHERE cs.src_count=10 AND cs.hist_count=10 AND cs.mismatches=0
    AND ts.set_value=th.set_value
    AND ts.card_count=th.priced_card_count
    AND th.total_card_count=10
)
INSERT INTO public.pokemon_market_set_rollout_v1(set_id,activated_market_date,enabled,notes)
SELECT r.set_id,d.market_date,true,
       'Price Storage V2 cleanup: activated after exact current-date parity for standard Set Value, Top-10 aggregate, and 10/10 chase identity/variant/price rows.'
FROM safe_roots r CROSS JOIN latest_market_date d
ON CONFLICT (set_id) DO UPDATE
SET activated_market_date=EXCLUDED.activated_market_date,
    enabled=true,
    notes=EXCLUDED.notes,
    updated_at=now();