CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_rollout_daily_snapshots_v1(
    p_market_date date DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $function$
DECLARE
    v_market_date date;
    v_latest_approved date;
    v_standard_rows integer := 0;
    v_top10_value_rows integer := 0;
    v_top10_deleted integer := 0;
    v_top10_rows integer := 0;
BEGIN
    SELECT max(q.market_date)::date
      INTO v_latest_approved
    FROM public.pokemon_market_date_quality q
    WHERE q.tcg = 'pokemon'
      AND q.status IN ('READY','LEGACY_VERIFIED');

    v_market_date := coalesce(p_market_date, v_latest_approved);
    IF v_market_date IS NULL THEN
        RAISE EXCEPTION 'No approved Pokemon market date exists';
    END IF;
    IF v_market_date IS DISTINCT FROM v_latest_approved THEN
        RAISE EXCEPTION 'Rollout snapshot refresh is current-date only: requested %, latest approved %',
            v_market_date, v_latest_approved;
    END IF;

    WITH roots AS MATERIALIZED (
        SELECT r.set_id
        FROM public.pokemon_market_rollout_root_sets_v1 r
        WHERE r.activated_market_date <= v_market_date
          AND (r.release_date IS NULL OR r.release_date <= v_market_date)
    ), canonical AS MATERIALIZED (
        SELECT v.set_id,
               v.set_value,
               v.expected_card_count,
               v.priced_card_count,
               v.coverage_pct
        FROM public.pokemon_market_root_set_value_latest_v1 v
        JOIN roots r ON r.set_id = v.set_id
        WHERE v.market_scope = 'standard'
          AND coalesce(v.coverage_pct, 0) >= 95
    )
    INSERT INTO public.pokemon_set_value_daily_history(
        set_id, snapshot_date, value_scope, set_value,
        priced_card_count, total_card_count, source,
        canonical_card_count, linked_card_count, included_card_count,
        coverage_pct, created_at, updated_at
    )
    SELECT c.set_id, v_market_date, 'standard', c.set_value,
           c.priced_card_count, c.expected_card_count,
           'canonical_root_set_rollout_v1',
           c.expected_card_count, c.expected_card_count, c.priced_card_count,
           c.coverage_pct, now(), now()
    FROM canonical c
    ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
    SET set_value = EXCLUDED.set_value,
        priced_card_count = EXCLUDED.priced_card_count,
        total_card_count = EXCLUDED.total_card_count,
        source = EXCLUDED.source,
        canonical_card_count = EXCLUDED.canonical_card_count,
        linked_card_count = EXCLUDED.linked_card_count,
        included_card_count = EXCLUDED.included_card_count,
        coverage_pct = EXCLUDED.coverage_pct,
        updated_at = now();
    GET DIAGNOSTICS v_standard_rows = ROW_COUNT;

    WITH roots AS MATERIALIZED (
        SELECT r.set_id
        FROM public.pokemon_market_rollout_root_sets_v1 r
        WHERE r.activated_market_date <= v_market_date
          AND (r.release_date IS NULL OR r.release_date <= v_market_date)
    ), grouped AS MATERIALIZED (
        SELECT t.set_id,
               sum(t.market_price)::numeric AS set_value,
               count(*)::integer AS card_count
        FROM public.pokemon_market_root_set_top10_latest_v1 t
        JOIN roots r ON r.set_id = t.set_id
        WHERE t.market_scope = 'standard'
          AND t.publishable_100pct
          AND t.rank BETWEEN 1 AND 10
        GROUP BY t.set_id
        HAVING count(*) = 10
    )
    INSERT INTO public.pokemon_set_value_daily_history(
        set_id, snapshot_date, value_scope, set_value,
        priced_card_count, total_card_count, source,
        canonical_card_count, linked_card_count, included_card_count,
        coverage_pct, created_at, updated_at
    )
    SELECT g.set_id, v_market_date, 'top10', g.set_value,
           g.card_count, 10, 'canonical_root_top10_rollout_v1',
           10, 10, g.card_count, 100.00, now(), now()
    FROM grouped g
    ON CONFLICT (set_id, snapshot_date, value_scope) DO UPDATE
    SET set_value = EXCLUDED.set_value,
        priced_card_count = EXCLUDED.priced_card_count,
        total_card_count = EXCLUDED.total_card_count,
        source = EXCLUDED.source,
        canonical_card_count = EXCLUDED.canonical_card_count,
        linked_card_count = EXCLUDED.linked_card_count,
        included_card_count = EXCLUDED.included_card_count,
        coverage_pct = EXCLUDED.coverage_pct,
        updated_at = now();
    GET DIAGNOSTICS v_top10_value_rows = ROW_COUNT;

    DELETE FROM public.pokemon_set_top_chase_card_daily_history h
    WHERE h.snapshot_date = v_market_date
      AND h.set_id IN (
          SELECT r.set_id
          FROM public.pokemon_market_rollout_root_sets_v1 r
          WHERE r.activated_market_date <= v_market_date
            AND (r.release_date IS NULL OR r.release_date <= v_market_date)
      );
    GET DIAGNOSTICS v_top10_deleted = ROW_COUNT;

    INSERT INTO public.pokemon_set_top_chase_card_daily_history(
        set_id, snapshot_date, card_id, card_variant_id, rank,
        name, rarity, image_url, image_small_url, image_large_url,
        market_price, source, source_date, created_at, updated_at
    )
    SELECT t.set_id,
           v_market_date,
           t.canonical_card_id,
           t.card_variant_id,
           t.rank,
           t.card_name,
           t.rarity,
           coalesce(pcc.image_small_url, pcc.image_large_url),
           pcc.image_small_url,
           pcc.image_large_url,
           t.market_price,
           t.source,
           t.captured_at::date,
           now(), now()
    FROM public.pokemon_market_root_set_top10_latest_v1 t
    JOIN public.pokemon_market_rollout_root_sets_v1 r ON r.set_id = t.set_id
    JOIN public.pokemon_canonical_cards pcc ON pcc.id = t.canonical_card_id
    WHERE t.market_scope = 'standard'
      AND t.publishable_100pct
      AND t.rank BETWEEN 1 AND 10
      AND r.activated_market_date <= v_market_date
      AND (r.release_date IS NULL OR r.release_date <= v_market_date)
    ON CONFLICT (set_id, snapshot_date, rank) DO UPDATE
    SET card_id = EXCLUDED.card_id,
        card_variant_id = EXCLUDED.card_variant_id,
        name = EXCLUDED.name,
        rarity = EXCLUDED.rarity,
        image_url = EXCLUDED.image_url,
        image_small_url = EXCLUDED.image_small_url,
        image_large_url = EXCLUDED.image_large_url,
        market_price = EXCLUDED.market_price,
        source = EXCLUDED.source,
        source_date = EXCLUDED.source_date,
        updated_at = now();
    GET DIAGNOSTICS v_top10_rows = ROW_COUNT;

    RETURN jsonb_build_object(
        'marketDate', v_market_date,
        'rolloutRootCount', (
            SELECT count(*) FROM public.pokemon_market_rollout_root_sets_v1 r
            WHERE r.activated_market_date <= v_market_date
              AND (r.release_date IS NULL OR r.release_date <= v_market_date)
        ),
        'standardRowsUpserted', v_standard_rows,
        'top10ValueRowsUpserted', v_top10_value_rows,
        'top10RowsDeleted', v_top10_deleted,
        'top10RowsInserted', v_top10_rows
    );
END;
$function$;