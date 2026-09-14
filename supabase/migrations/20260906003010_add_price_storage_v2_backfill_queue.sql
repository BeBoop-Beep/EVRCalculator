BEGIN;

CREATE TABLE IF NOT EXISTS public.price_storage_v2_backfill_sets (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    variant_count integer,
    event_rows bigint,
    current_rows bigint,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS price_storage_v2_backfill_sets_status_idx
    ON public.price_storage_v2_backfill_sets (status, set_id)
    WHERE status IN ('pending','failed');

ALTER TABLE public.price_storage_v2_backfill_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.price_storage_v2_backfill_sets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.price_storage_v2_backfill_sets TO service_role;

INSERT INTO public.price_storage_v2_backfill_sets (
    set_id, status, variant_count, updated_at
)
SELECT
    card.set_id,
    'pending',
    count(variant.id)::integer,
    now()
FROM public.card_variants variant
JOIN public.cards card ON card.id = variant.card_id
GROUP BY card.set_id
ON CONFLICT (set_id)
DO UPDATE SET
    variant_count = EXCLUDED.variant_count,
    updated_at = now();

CREATE OR REPLACE FUNCTION public.process_price_storage_v2_backfill_sets(
    p_limit integer DEFAULT 3
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $$
DECLARE
    v_job record;
    v_variant_ids uuid[];
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
        FROM public.price_storage_v2_backfill_sets q
        WHERE q.status IN ('pending','failed')
        ORDER BY q.variant_count ASC NULLS LAST, q.set_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        v_processed := v_processed + 1;

        UPDATE public.price_storage_v2_backfill_sets
        SET status = 'processing',
            attempts = attempts + 1,
            started_at = now(),
            completed_at = NULL,
            last_error = NULL,
            updated_at = now()
        WHERE set_id = v_job.set_id;

        BEGIN
            SELECT array_agg(variant.id ORDER BY variant.id)
            INTO v_variant_ids
            FROM public.card_variants variant
            JOIN public.cards card ON card.id = variant.card_id
            WHERE card.set_id = v_job.set_id
              AND EXISTS (
                  SELECT 1
                  FROM public.card_variant_price_observations observation
                  WHERE observation.card_variant_id = variant.id
              );

            IF v_variant_ids IS NULL OR cardinality(v_variant_ids) = 0 THEN
                UPDATE public.price_storage_v2_backfill_sets
                SET status = 'complete',
                    event_rows = 0,
                    current_rows = 0,
                    completed_at = now(),
                    updated_at = now()
                WHERE set_id = v_job.set_id;
                v_completed := v_completed + 1;
                CONTINUE;
            END IF;

            v_result := public.rebuild_card_variant_price_events_v2_from_raw_scope(v_variant_ids);

            UPDATE public.price_storage_v2_backfill_sets
            SET status = 'complete',
                event_rows = COALESCE((v_result->>'event_rows')::bigint, 0),
                current_rows = COALESCE((v_result->>'current_rows')::bigint, 0),
                completed_at = now(),
                last_error = NULL,
                updated_at = now()
            WHERE set_id = v_job.set_id;
            v_completed := v_completed + 1;
        EXCEPTION WHEN OTHERS THEN
            UPDATE public.price_storage_v2_backfill_sets
            SET status = 'failed',
                completed_at = now(),
                last_error = left(SQLERRM, 2000),
                updated_at = now()
            WHERE set_id = v_job.set_id;
            v_failed := v_failed + 1;
        END;
    END LOOP;

    RETURN jsonb_build_object(
        'processed', v_processed,
        'completed', v_completed,
        'failed', v_failed
    );
END;
$$;

REVOKE ALL ON FUNCTION public.process_price_storage_v2_backfill_sets(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.process_price_storage_v2_backfill_sets(integer) TO service_role;

COMMENT ON TABLE public.price_storage_v2_backfill_sets IS
'Resumable set-level migration ledger for converting legacy card price observations into Price Storage V2 without changing production readers.';

COMMIT;