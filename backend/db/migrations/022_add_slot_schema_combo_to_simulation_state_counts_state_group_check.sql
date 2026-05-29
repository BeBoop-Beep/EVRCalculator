-- Migration 022: allow slot-schema combo-state persistence in simulation_state_counts.
--
-- Scope:
--   - Preserves the currently used state_group values.
--   - Adds slot_schema_combo for additive reverse+rare combo-state persistence.
--
-- Non-goals:
--   - No table or column renames.
--   - No loosening to arbitrary text values.
--   - No simulation math or probability changes.

DO $$
DECLARE
    existing_definition text;
BEGIN
    IF to_regclass('public.simulation_state_counts') IS NULL THEN
        RAISE EXCEPTION 'Table public.simulation_state_counts does not exist';
    END IF;

    SELECT pg_get_constraintdef(c.oid, true)
    INTO existing_definition
    FROM pg_constraint AS c
    JOIN pg_class AS t
      ON t.oid = c.conrelid
    JOIN pg_namespace AS n
      ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'simulation_state_counts'
      AND c.conname = 'simulation_state_counts_state_group_check';

    IF existing_definition IS NOT NULL
       AND position('slot_schema_combo' in existing_definition) > 0 THEN
        RAISE NOTICE 'simulation_state_counts_state_group_check already allows slot_schema_combo';
        RETURN;
    END IF;

    ALTER TABLE public.simulation_state_counts
        DROP CONSTRAINT IF EXISTS simulation_state_counts_state_group_check;

    ALTER TABLE public.simulation_state_counts
        ADD CONSTRAINT simulation_state_counts_state_group_check
        CHECK (
            state_group IN (
                'pack_path',
                'normal_pack_state',
                'slot_schema_combo'
            )
        );
END $$;