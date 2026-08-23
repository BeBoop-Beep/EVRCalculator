BEGIN;

ALTER FUNCTION public.publish_pokemon_public_rip_leaderboard(
    JSONB,
    JSONB,
    JSONB
)
SET statement_timeout = '60s';

COMMIT;
