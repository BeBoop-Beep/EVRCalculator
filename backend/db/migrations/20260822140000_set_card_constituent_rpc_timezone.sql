-- Persist the canonical America/Phoenix function-level timezone for
-- public.get_pokemon_set_daily_card_constituents.
--
-- WHY THIS IS A SEPARATE, ADDITIVE MIGRATION
-- ==========================================
-- 20260822130000_add_pokemon_set_daily_card_constituents_rpc.sql has already
-- been applied to the live database. That file stays as the historical record
-- of the deployed function shape. This migration is the additive follow-up
-- that lands the one piece its live apply could not persist: the function-level
-- TimeZone configuration.
--
-- WHAT WAS WRONG
-- --------------
-- card_variant_price_observations.captured_at is a bare DATE column. The
-- function's business-date boundary predicate is:
--
--     o.captured_at < ((snapshot_date + interval '1 day')::timestamp
--                      AT TIME ZONE 'America/Phoenix')
--
-- The right-hand side is a TIMESTAMPTZ, so captured_at is implicitly cast
-- DATE -> TIMESTAMPTZ to compare. That implicit cast resolves using the
-- CALLING SESSION's TimeZone GUC -- NOT the zone named on the right-hand
-- side, which only governs its own side of the comparison. Under this
-- project's default session TimeZone of UTC, midnight-UTC captured_at values
-- land 7 hours ahead of the Phoenix boundary, so an observation captured the
-- NEXT day can satisfy the CURRENT day's boundary. The result is a silently
-- wrong price for every market date except the caller's current day.
--
-- Measured live on Surging Sparks under the default UTC session, immediately
-- before this migration was applied (RPC sum vs authoritative set_value):
--
--     2026-08-22   1242.80 vs 1242.80   0.00   (current day: unaffected)
--     2026-08-15   1230.76 vs 1232.06  -1.30
--     2026-07-23   1300.23 vs 1307.77  -7.54
--     2026-04-11   1144.36 vs 1142.13  +2.23
--
-- Canonical card counts were identical (244) on every date, confirming this
-- is price SELECTION drift, not a constituent-cohort difference.
--
-- WHY FUNCTION-LEVEL CONFIG RATHER THAN A CALLER CONTRACT
-- ------------------------------------------------------
-- Requiring every caller to issue `SET LOCAL TimeZone = 'America/Phoenix'`
-- makes the correctness of the canonical market-date definition depend on
-- caller discipline, application process timezone, and connection-pool
-- defaults. The America/Phoenix day boundary IS the market-date definition
-- that pokemon_set_value_daily_history uses; that authority belongs to the
-- function, not to its callers. `SET "TimeZone"` as a function attribute makes
-- Postgres apply the setting for the duration of each call and restore the
-- caller's value on exit, regardless of session, pool, or process timezone.
--
-- SCOPE
-- -----
-- Schema-only, and deliberately minimal. ALTER FUNCTION ... SET is used
-- instead of CREATE OR REPLACE so this migration cannot alter the function
-- body, signature, volatility, security mode, or ACL -- it changes exactly
-- one attribute. No market data is read, written, or refreshed.

BEGIN;

ALTER FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE)
    SET "TimeZone" TO 'America/Phoenix';

COMMIT;
