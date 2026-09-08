BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_price_intervals_v2_shadow (
    card_variant_id uuid NOT NULL,
    set_id uuid NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    market_price numeric NOT NULL,
    PRIMARY KEY (card_variant_id, valid_from),
    CHECK (market_price > 0),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX IF NOT EXISTS pokemon_market_price_intervals_v2_set_from_idx
    ON public.pokemon_market_price_intervals_v2_shadow (set_id, valid_from, card_variant_id)
    INCLUDE (valid_to, market_price);

CREATE INDEX IF NOT EXISTS pokemon_market_price_intervals_v2_open_idx
    ON public.pokemon_market_price_intervals_v2_shadow (set_id, card_variant_id)
    INCLUDE (market_price, valid_from)
    WHERE valid_to IS NULL;

ALTER TABLE public.pokemon_market_price_intervals_v2_shadow ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_price_intervals_v2_shadow FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pokemon_market_price_intervals_v2_shadow TO service_role;

CREATE TABLE IF NOT EXISTS public.price_storage_v2_interval_backfill_sets (
    set_id uuid PRIMARY KEY,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    eligible_variant_count integer,
    interval_rows bigint,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS price_storage_v2_interval_backfill_sets_status_idx
    ON public.price_storage_v2_interval_backfill_sets (status, eligible_variant_count, set_id)
    WHERE status IN ('pending','failed');

ALTER TABLE public.price_storage_v2_interval_backfill_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.price_storage_v2_interval_backfill_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.price_storage_v2_interval_backfill_sets TO service_role;

INSERT INTO public.price_storage_v2_interval_backfill_sets (
    set_id, status, eligible_variant_count, updated_at
)
SELECT
    metadata.set_id,
    'pending',
    count(*)::integer,
    now()
FROM public.pokemon_market_explorer_card_current_metadata metadata
GROUP BY metadata.set_id
ON CONFLICT (set_id)
DO UPDATE SET
    eligible_variant_count = EXCLUDED.eligible_variant_count,
    updated_at = now();

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(
    p_set_ids uuid[]
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_inserted bigint := 0;
BEGIN
    IF p_set_ids IS NULL OR cardinality(p_set_ids) = 0 THEN
        RETURN jsonb_build_object('set_count',0,'interval_rows',0);
    END IF;

    DELETE FROM public.pokemon_market_price_intervals_v2_shadow interval_row
    WHERE interval_row.set_id = ANY(p_set_ids);

    WITH scoped_metadata AS MATERIALIZED (
        SELECT metadata.card_variant_id, metadata.set_id
        FROM public.pokemon_market_explorer_card_current_metadata metadata
        WHERE metadata.set_id = ANY(p_set_ids)
    ), ordered AS MATERIALIZED (
        SELECT
            event_row.card_variant_id,
            metadata.set_id,
            event_row.effective_date,
            event_row.market_price,
            lag(event_row.market_price) OVER (
                PARTITION BY event_row.card_variant_id
                ORDER BY event_row.effective_date, event_row.id
            ) AS previous_market_price,
            row_number() OVER (
                PARTITION BY event_row.card_variant_id
                ORDER BY event_row.effective_date, event_row.id
            ) AS sequence_number
        FROM public.card_variant_price_events_v2 event_row
        JOIN scoped_metadata metadata
          ON metadata.card_variant_id = event_row.card_variant_id
        WHERE event_row.condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
          AND event_row.source = 'TCGPlayer'
          AND event_row.currency = 'USD'
          AND event_row.market_price > 0
    ), changes AS MATERIALIZED (
        SELECT card_variant_id, set_id, effective_date, market_price
        FROM ordered
        WHERE sequence_number = 1
           OR market_price IS DISTINCT FROM previous_market_price
    ), intervals AS (
        SELECT
            card_variant_id,
            set_id,
            effective_date AS valid_from,
            lead(effective_date) OVER (
                PARTITION BY card_variant_id
                ORDER BY effective_date
            ) AS valid_to,
            market_price
        FROM changes
    )
    INSERT INTO public.pokemon_market_price_intervals_v2_shadow (
        card_variant_id, set_id, valid_from, valid_to, market_price
    )
    SELECT card_variant_id, set_id, valid_from, valid_to, market_price
    FROM intervals;

    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    RETURN jsonb_build_object(
        'set_count', cardinality(p_set_ids),
        'interval_rows', v_inserted
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_interval_backfill_sets(
    p_limit integer DEFAULT 5
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_job record;
    v_result jsonb;
    v_processed integer := 0;
    v_completed integer := 0;
    v_failed integer := 0;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 10 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 10';
    END IF;

    FOR v_job IN
        SELECT q.set_id
        FROM public.price_storage_v2_interval_backfill_sets q
        WHERE q.status IN ('pending','failed')
          AND q.attempts < 5
        ORDER BY q.eligible_variant_count ASC NULLS LAST, q.set_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed := v_processed + 1;

        UPDATE public.price_storage_v2_interval_backfill_sets
        SET status='processing', attempts=attempts+1, started_at=now(),
            completed_at=NULL, last_error=NULL, updated_at=now()
        WHERE set_id=v_job.set_id;

        BEGIN
            v_result := public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(ARRAY[v_job.set_id]);

            UPDATE public.price_storage_v2_interval_backfill_sets
            SET status='complete',
                interval_rows=COALESCE((v_result->>'interval_rows')::bigint,0),
                completed_at=now(), last_error=NULL, updated_at=now()
            WHERE set_id=v_job.set_id;
            v_completed := v_completed + 1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_interval_backfill_sets
            SET status='failed', completed_at=now(),
                last_error=left(SQLERRM,2000), updated_at=now()
            WHERE set_id=v_job.set_id;
            v_failed := v_failed + 1;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'processed',v_processed,
        'completed',v_completed,
        'failed',v_failed
    );
END;
$$;

REVOKE ALL ON FUNCTION public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(uuid[]) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.process_price_storage_v2_interval_backfill_sets(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_market_price_intervals_v2_shadow_for_sets(uuid[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_interval_backfill_sets(integer) TO service_role;

COMMENT ON TABLE public.pokemon_market_price_intervals_v2_shadow IS
'Backend-only compact Market Explorer interval candidate derived from Price Storage V2. Contains no duplicated card metadata and is not a production authority.';

COMMIT;