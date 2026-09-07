BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_explorer_card_daily_states_v2_shadow (
    market_date date NOT NULL,
    card_variant_id uuid NOT NULL,
    set_id uuid NOT NULL,
    market_price numeric NOT NULL CHECK (market_price > 0),
    PRIMARY KEY (market_date, card_variant_id)
);

CREATE INDEX IF NOT EXISTS pokemon_market_explorer_daily_v2_set_date_idx
    ON public.pokemon_market_explorer_card_daily_states_v2_shadow(set_id, market_date, card_variant_id)
    INCLUDE (market_price);

CREATE TABLE IF NOT EXISTS public.pokemon_market_explorer_card_daily_coverage_v2_shadow (
    set_id uuid PRIMARY KEY,
    retained_from date NOT NULL,
    computed_through date NOT NULL,
    row_count bigint NOT NULL DEFAULT 0,
    retention_days integer NOT NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    CHECK (computed_through >= retained_from),
    CHECK (retention_days >= 1)
);

CREATE TABLE IF NOT EXISTS public.price_storage_v2_daily_backfill_sets (
    set_id uuid PRIMARY KEY,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    row_count bigint,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS price_storage_v2_daily_backfill_sets_status_idx
    ON public.price_storage_v2_daily_backfill_sets(status, set_id)
    WHERE status IN ('pending','failed');

ALTER TABLE public.pokemon_market_explorer_card_daily_states_v2_shadow ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_market_explorer_card_daily_coverage_v2_shadow ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_storage_v2_daily_backfill_sets ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.pokemon_market_explorer_card_daily_states_v2_shadow FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.pokemon_market_explorer_card_daily_coverage_v2_shadow FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.price_storage_v2_daily_backfill_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_market_explorer_card_daily_states_v2_shadow TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_market_explorer_card_daily_coverage_v2_shadow TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.price_storage_v2_daily_backfill_sets TO service_role;

INSERT INTO public.price_storage_v2_daily_backfill_sets(set_id,status,updated_at)
SELECT DISTINCT set_id,'pending',now()
FROM public.pokemon_market_explorer_card_current_metadata
ON CONFLICT (set_id) DO UPDATE SET updated_at=now();

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(
    p_set_id uuid,
    p_through_date date,
    p_retention_days integer DEFAULT 100
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_from date;
    v_rows bigint := 0;
BEGIN
    IF p_set_id IS NULL OR p_through_date IS NULL THEN
        RAISE EXCEPTION 'set_id and through_date are required';
    END IF;
    IF p_retention_days IS NULL OR p_retention_days < 1 OR p_retention_days > 400 THEN
        RAISE EXCEPTION 'p_retention_days must be between 1 and 400';
    END IF;

    v_from := p_through_date - (p_retention_days - 1);

    DELETE FROM public.pokemon_market_explorer_card_daily_states_v2_shadow
    WHERE set_id=p_set_id;

    WITH approved_dates AS MATERIALIZED (
        SELECT DISTINCT quality.market_date
        FROM public.pokemon_market_date_quality quality
        WHERE quality.market_date BETWEEN v_from AND p_through_date
          AND quality.status IN ('READY','LEGACY_VERIFIED')
    )
    INSERT INTO public.pokemon_market_explorer_card_daily_states_v2_shadow(
        market_date,card_variant_id,set_id,market_price
    )
    SELECT d.market_date,i.card_variant_id,i.set_id,i.market_price
    FROM approved_dates d
    JOIN public.pokemon_market_price_intervals_v2_shadow i
      ON i.set_id=p_set_id
     AND i.valid_from<=d.market_date
     AND (i.valid_to IS NULL OR d.market_date<i.valid_to);

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    INSERT INTO public.pokemon_market_explorer_card_daily_coverage_v2_shadow(
        set_id,retained_from,computed_through,row_count,retention_days,refreshed_at
    )
    VALUES(p_set_id,v_from,p_through_date,v_rows,p_retention_days,now())
    ON CONFLICT (set_id)
    DO UPDATE SET retained_from=EXCLUDED.retained_from,
                  computed_through=EXCLUDED.computed_through,
                  row_count=EXCLUDED.row_count,
                  retention_days=EXCLUDED.retention_days,
                  refreshed_at=now();

    RETURN jsonb_build_object(
        'set_id',p_set_id,
        'retained_from',v_from,
        'computed_through',p_through_date,
        'retention_days',p_retention_days,
        'row_count',v_rows
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_daily_backfill_sets(
    p_limit integer DEFAULT 5,
    p_retention_days integer DEFAULT 100
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_job record;
    v_through date;
    v_result jsonb;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>10 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 10';
    END IF;
    IF p_retention_days IS NULL OR p_retention_days<1 OR p_retention_days>400 THEN
        RAISE EXCEPTION 'p_retention_days must be between 1 and 400';
    END IF;

    SELECT max(market_date) INTO v_through
    FROM public.pokemon_market_date_quality
    WHERE status IN ('READY','LEGACY_VERIFIED');

    IF v_through IS NULL THEN
        RAISE EXCEPTION 'No approved market date exists';
    END IF;

    FOR v_job IN
        SELECT q.set_id
        FROM public.price_storage_v2_daily_backfill_sets q
        WHERE q.status IN ('pending','failed') AND q.attempts<5
        ORDER BY q.set_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed:=v_processed+1;
        UPDATE public.price_storage_v2_daily_backfill_sets
        SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
        WHERE set_id=v_job.set_id;
        BEGIN
            v_result:=public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(v_job.set_id,v_through,p_retention_days);
            UPDATE public.price_storage_v2_daily_backfill_sets
            SET status='complete',row_count=COALESCE((v_result->>'row_count')::bigint,0),
                completed_at=now(),last_error=NULL,updated_at=now()
            WHERE set_id=v_job.set_id;
            v_completed:=v_completed+1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_daily_backfill_sets
            SET status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now()
            WHERE set_id=v_job.set_id;
            v_failed:=v_failed+1;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'through_date',v_through,
        'retention_days',p_retention_days,
        'processed',v_processed,
        'completed',v_completed,
        'failed',v_failed
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.pokemon_market_explorer_daily_v2_shadow_covers(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path TO ''
AS $$
    SELECT
      p_set_ids IS NOT NULL
      AND cardinality(p_set_ids)>0
      AND p_start_date IS NOT NULL
      AND p_end_date IS NOT NULL
      AND p_end_date>=p_start_date
      AND NOT EXISTS (
        SELECT 1
        FROM unnest(p_set_ids) requested(set_id)
        LEFT JOIN public.pokemon_market_explorer_card_daily_coverage_v2_shadow coverage
          ON coverage.set_id=requested.set_id
        WHERE coverage.set_id IS NULL
           OR p_start_date<coverage.retained_from
           OR p_end_date>coverage.computed_through
      );
$$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(uuid,date,integer) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.process_price_storage_v2_daily_backfill_sets(integer,integer) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.pokemon_market_explorer_daily_v2_shadow_covers(uuid[],date,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(uuid,date,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_daily_backfill_sets(integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.pokemon_market_explorer_daily_v2_shadow_covers(uuid[],date,date) TO service_role;

COMMENT ON TABLE public.pokemon_market_explorer_card_daily_states_v2_shadow IS
'Backend-only bounded hot daily cache derived from compact V2 intervals. Default retention is 100 calendar days; older queries must fall back to compact intervals.';
COMMENT ON TABLE public.pokemon_market_explorer_card_daily_coverage_v2_shadow IS
'Retention-aware V2 daily cache coverage. Coverage is valid only when the requested start is on/after retained_from and requested end is on/before computed_through.';

COMMIT;