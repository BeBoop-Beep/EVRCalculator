-- Canonical simulation business date.
--
-- New unattended runs carry the promoted market date explicitly. Existing rows
-- remain deterministic: the compatibility views retain their original
-- timestamp-derived snapshot_date when market_date is NULL. No historical row
-- is rewritten by this migration.
ALTER TABLE public.calculation_runs
    ADD COLUMN IF NOT EXISTS market_date date;

COMMENT ON COLUMN public.calculation_runs.market_date IS
    'Explicit promoted Pokemon market date for this simulation; NULL on legacy runs, whose historical date remains the pre-migration view result.';

CREATE INDEX IF NOT EXISTS idx_calculation_runs_market_date_target
    ON public.calculation_runs (market_date DESC, target_type, target_id)
    WHERE market_date IS NOT NULL;

DO $migration$
DECLARE
    view_name text;
    legacy_name text;
    projection text;
BEGIN
    FOREACH view_name IN ARRAY ARRAY[
        'calculation_history_daily_latest',
        'calculation_history_trend'
    ]
    LOOP
        legacy_name := view_name || '_legacy_timestamp_date';

        IF to_regclass('public.' || legacy_name) IS NULL THEN
            IF to_regclass('public.' || view_name) IS NULL THEN
                RAISE EXCEPTION 'required view public.% does not exist', view_name;
            END IF;
            EXECUTE format('ALTER VIEW public.%I RENAME TO %I', view_name, legacy_name);
        END IF;

        SELECT string_agg(
            CASE WHEN column_name = 'snapshot_date'
                THEN 'COALESCE(r.market_date, l.snapshot_date) AS snapshot_date'
                ELSE format('l.%I', column_name)
            END,
            ', ' ORDER BY ordinal_position
        )
        INTO projection
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = legacy_name;

        IF projection IS NULL OR position('AS snapshot_date' IN projection) = 0 THEN
            RAISE EXCEPTION 'legacy view public.% lacks snapshot_date', legacy_name;
        END IF;

        EXECUTE format(
            'CREATE VIEW public.%I WITH (security_invoker = true) AS
             SELECT %s
             FROM public.%I l
             LEFT JOIN public.calculation_runs r
               ON r.id = l.calculation_run_id',
            view_name, projection, legacy_name
        );

        -- The legacy objects are implementation details and must not create a
        -- second public analytics contract.
        EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', legacy_name);
        EXECUTE format('GRANT SELECT ON public.%I TO anon, authenticated, service_role', view_name);
    END LOOP;
END
$migration$;

