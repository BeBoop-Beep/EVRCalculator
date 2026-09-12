WITH latest_market_date AS (
    SELECT max(q.market_date)::date AS market_date
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED')
), already AS (
    SELECT set_id FROM public.pokemon_market_rollout_root_sets_v1
), standard_candidates AS (
    SELECT v.set_id,v.set_value,v.priced_card_count,v.expected_card_count,v.coverage_pct
    FROM public.pokemon_market_root_set_value_latest_v1 v
    JOIN public.sets s ON s.id=v.set_id
    JOIN latest_market_date d ON true
    JOIN public.pokemon_set_value_daily_history h
      ON h.set_id=v.set_id
     AND h.snapshot_date=d.market_date
     AND h.value_scope='standard'
    WHERE v.market_scope='standard'
      AND s.parent_opening_set_id IS NULL
      AND coalesce(s.catalog_only,false)=false
      AND coalesce(s.ready_for_daily_scrape,false)=true
      AND coalesce(v.coverage_pct,0)>=95
      AND v.set_id NOT IN (SELECT set_id FROM already)
      AND v.set_value=h.set_value
      AND v.priced_card_count=h.priced_card_count
      AND v.expected_card_count=h.total_card_count
), safe_roots AS (
    SELECT c.set_id
    FROM standard_candidates c
    CROSS JOIN latest_market_date d
    WHERE (SELECT count(*) FROM public.pokemon_market_root_set_top10_latest_v1 t
           WHERE t.set_id=c.set_id AND t.market_scope='standard'
             AND t.publishable_100pct AND t.rank BETWEEN 1 AND 10)=10
      AND (SELECT count(*) FROM public.pokemon_set_top_chase_card_daily_history h
           WHERE h.set_id=c.set_id AND h.snapshot_date=d.market_date)=10
      AND NOT EXISTS (
          SELECT 1
          FROM public.pokemon_market_root_set_top10_latest_v1 t
          FULL JOIN public.pokemon_set_top_chase_card_daily_history h
            ON h.set_id=t.set_id
           AND h.rank=t.rank
           AND h.snapshot_date=d.market_date
          WHERE coalesce(t.set_id,h.set_id)=c.set_id
            AND (t.set_id IS NULL OR h.set_id IS NULL
                 OR t.market_scope<>'standard'
                 OR NOT t.publishable_100pct
                 OR t.rank NOT BETWEEN 1 AND 10
                 OR t.canonical_card_id IS DISTINCT FROM h.card_id
                 OR t.card_variant_id IS DISTINCT FROM h.card_variant_id
                 OR t.market_price IS DISTINCT FROM h.market_price)
      )
      AND EXISTS (
          SELECT 1
          FROM public.pokemon_set_value_daily_history th
          WHERE th.set_id=c.set_id
            AND th.snapshot_date=d.market_date
            AND th.value_scope='top10'
            AND th.priced_card_count=10
            AND th.total_card_count=10
            AND th.set_value=(
                SELECT round(sum(t.market_price)::numeric,2)
                FROM public.pokemon_market_root_set_top10_latest_v1 t
                WHERE t.set_id=c.set_id
                  AND t.market_scope='standard'
                  AND t.publishable_100pct
                  AND t.rank BETWEEN 1 AND 10
            )
      )
)
INSERT INTO public.pokemon_market_set_rollout_v1(set_id,activated_market_date,enabled,notes)
SELECT r.set_id,d.market_date,true,
       'Price Storage V2 cleanup: automatically activated only after exact current-date parity for standard Set Value, Top-10 aggregate, and 10/10 chase identity/variant/price rows.'
FROM safe_roots r CROSS JOIN latest_market_date d
ON CONFLICT (set_id) DO UPDATE
SET activated_market_date=EXCLUDED.activated_market_date,
    enabled=true,
    notes=EXCLUDED.notes,
    updated_at=now();