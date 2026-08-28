BEGIN;

-- This recurring service-role-only administrative RPC may legitimately exceed
-- the normal REST statement timeout while atomically validating and inserting
-- the complete Chase Efficiency cohort. Keep the exemption finite and local to
-- this function; its body, signature, grants, and publication semantics remain
-- unchanged.
ALTER FUNCTION public.publish_pokemon_card_chase_efficiency_snapshot(JSONB, JSONB)
    SET statement_timeout = '5min';

COMMIT;
