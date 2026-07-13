-- Prevent invalid subset Set Value rows from being published by any writer.
-- The deferred trigger validates the final same-transaction state, allowing
-- standard/hits/top10 to be upserted together in any row order.

BEGIN;

CREATE OR REPLACE FUNCTION public.enforce_pokemon_set_value_scope_invariants()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    v_checklist_value NUMERIC;
    v_subset RECORD;
    v_error JSONB;
BEGIN
    IF NEW.set_value IS NULL OR NEW.set_value::text IN ('NaN', 'Infinity', '-Infinity') THEN
        v_error := jsonb_build_object(
            'code', 'POKEMON_SET_VALUE_SCOPE_INVARIANT',
            'setId', NEW.set_id,
            'date', NEW.snapshot_date,
            'scope', NEW.value_scope,
            'subsetValue', NEW.set_value,
            'checklistValue', NULL,
            'reason', 'value_not_finite'
        );
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = v_error::text;
    END IF;

    IF NEW.set_value < 0 THEN
        v_error := jsonb_build_object(
            'code', 'POKEMON_SET_VALUE_SCOPE_INVARIANT',
            'setId', NEW.set_id,
            'date', NEW.snapshot_date,
            'scope', NEW.value_scope,
            'subsetValue', CASE WHEN NEW.value_scope IN ('hits', 'top10') THEN NEW.set_value ELSE NULL END,
            'checklistValue', NULL,
            'reason', 'value_negative'
        );
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = v_error::text;
    END IF;

    SELECT set_value
    INTO v_checklist_value
    FROM public.pokemon_set_value_daily_history
    WHERE set_id = NEW.set_id
      AND snapshot_date = NEW.snapshot_date
      AND value_scope = 'standard';

    IF NEW.value_scope IN ('hits', 'top10')
       AND v_checklist_value IS NOT NULL
       AND NEW.set_value > v_checklist_value + 0.01 THEN
        v_error := jsonb_build_object(
            'code', 'POKEMON_SET_VALUE_SCOPE_INVARIANT',
            'setId', NEW.set_id,
            'date', NEW.snapshot_date,
            'scope', NEW.value_scope,
            'subsetValue', NEW.set_value,
            'checklistValue', v_checklist_value,
            'reason', 'subset_exceeds_checklist'
        );
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = v_error::text;
    END IF;

    IF NEW.value_scope = 'standard' THEN
        FOR v_subset IN
            SELECT value_scope, set_value
            FROM public.pokemon_set_value_daily_history
            WHERE set_id = NEW.set_id
              AND snapshot_date = NEW.snapshot_date
              AND value_scope IN ('hits', 'top10')
        LOOP
            IF v_subset.set_value IS NULL
               OR v_subset.set_value::text IN ('NaN', 'Infinity', '-Infinity')
               OR v_subset.set_value < 0
               OR v_subset.set_value > NEW.set_value + 0.01 THEN
                v_error := jsonb_build_object(
                    'code', 'POKEMON_SET_VALUE_SCOPE_INVARIANT',
                    'setId', NEW.set_id,
                    'date', NEW.snapshot_date,
                    'scope', v_subset.value_scope,
                    'subsetValue', v_subset.set_value,
                    'checklistValue', NEW.set_value,
                    'reason', CASE
                        WHEN v_subset.set_value IS NULL OR v_subset.set_value::text IN ('NaN', 'Infinity', '-Infinity')
                            THEN 'value_not_finite'
                        WHEN v_subset.set_value < 0 THEN 'value_negative'
                        ELSE 'subset_exceeds_checklist'
                    END
                );
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = v_error::text;
            END IF;
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_pokemon_set_value_scope_invariants
    ON public.pokemon_set_value_daily_history;

CREATE CONSTRAINT TRIGGER trg_enforce_pokemon_set_value_scope_invariants
AFTER INSERT OR UPDATE OF set_id, snapshot_date, value_scope, set_value
ON public.pokemon_set_value_daily_history
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.enforce_pokemon_set_value_scope_invariants();

REVOKE ALL ON FUNCTION public.enforce_pokemon_set_value_scope_invariants() FROM PUBLIC;

COMMIT;
