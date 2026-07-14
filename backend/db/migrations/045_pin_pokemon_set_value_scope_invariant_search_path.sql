-- Pin the invariant trigger function's namespace resolution for databases
-- where migration 044 was applied before its search_path hardening.

BEGIN;

ALTER FUNCTION public.enforce_pokemon_set_value_scope_invariants()
    SET search_path = '';

COMMIT;
