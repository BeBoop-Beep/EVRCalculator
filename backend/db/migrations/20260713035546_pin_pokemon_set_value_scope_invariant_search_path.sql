BEGIN;
ALTER FUNCTION public.enforce_pokemon_set_value_scope_invariants()
    SET search_path = '';
COMMIT;
