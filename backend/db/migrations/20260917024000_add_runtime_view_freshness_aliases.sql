-- Align runtime freshness metadata exposed by the simulation views with the
-- fields already consumed by publication/read services.
--
-- Production evidence on 2026-09-16 showed hundreds of handled 42703 errors
-- because callers probe updated_at/created_at before falling back to run_at,
-- while the two views expose run_at only.  The aliases below preserve run_at as
-- the authority; they do not invent a second clock or mutate underlying data.
--
-- The current view definitions are wrapped in place so every existing column
-- remains byte-for-contract in the same order and the compatibility aliases are
-- appended at the end.  This also keeps the migration resilient to additive
-- columns already present in an environment.

BEGIN;

DO $$
DECLARE
    v_definition text;
    v_additions text := '';
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'explore_rip_statistics_latest'
          AND column_name = 'updated_at'
    ) THEN
        v_additions := v_additions || ', source_view.run_at AS updated_at';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'explore_rip_statistics_latest'
          AND column_name = 'created_at'
    ) THEN
        v_additions := v_additions || ', source_view.run_at AS created_at';
    END IF;

    IF v_additions <> '' THEN
        SELECT regexp_replace(
            pg_get_viewdef('public.explore_rip_statistics_latest'::regclass, true),
            ';[[:space:]]*$',
            ''
        )
        INTO v_definition;

        EXECUTE format(
            'CREATE OR REPLACE VIEW public.explore_rip_statistics_latest '
            'WITH (security_invoker = true) AS '
            'SELECT source_view.*%s FROM (%s) AS source_view',
            v_additions,
            v_definition
        );
    END IF;
END
$$;

DO $$
DECLARE
    v_definition text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'simulation_latest_by_target'
          AND column_name = 'updated_at'
    ) THEN
        SELECT regexp_replace(
            pg_get_viewdef('public.simulation_latest_by_target'::regclass, true),
            ';[[:space:]]*$',
            ''
        )
        INTO v_definition;

        EXECUTE format(
            'CREATE OR REPLACE VIEW public.simulation_latest_by_target '
            'WITH (security_invoker = true) AS '
            'SELECT source_view.*, source_view.run_at AS updated_at '
            'FROM (%s) AS source_view',
            v_definition
        );
    END IF;
END
$$;

COMMIT;
