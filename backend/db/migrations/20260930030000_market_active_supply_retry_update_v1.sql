BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Bucket C2 retries operate within one expected-date run. Failed placeholder
-- snapshots may be upgraded to OBSERVED on the bounded 21:40 retry; already
-- observed rows remain immutable in application code.
GRANT UPDATE ON public.market_active_supply_snapshots_v1 TO service_role;

COMMENT ON TABLE public.market_active_supply_snapshots_v1 IS
  'Research-only fixed-panel active offered-supply evidence; TARGET_FAILED placeholders may be updated within the same run/date by the bounded retry. OBSERVED rows are application-immutable.';

COMMIT;
