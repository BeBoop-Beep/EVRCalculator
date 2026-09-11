-- inDex Sentinel optional AI budget ledger.
--
-- FUTURE PROPOSAL ONLY. P8 DOES NOT APPLY THIS SQL, DOES NOT CREATE A
-- MIGRATION, AND DOES NOT INSTALL OR CALL A PAID AI PROVIDER.
--
-- The deterministic Sentinel works with AI disabled.  This proposal exists so
-- a future reviewed provider cannot be enabled without an atomic, persisted
-- worst-case cost reservation.  The absolute ceiling is $10/month (1000 cents)
-- and cannot be raised by environment configuration.
--
-- Reservation semantics are intentionally conservative: reserve the provider's
-- WORST-CASE cost before a request and never refund the reservation.  This may
-- under-use the monthly budget, but it cannot overspend the configured envelope
-- when every provider request is gated by this function.

BEGIN;

CREATE TABLE public.sentinel_ai_budget (
    budget_month date PRIMARY KEY,
    configured_budget_cents integer NOT NULL DEFAULT 0
        CHECK (configured_budget_cents >= 0 AND configured_budget_cents <= 1000),
    reserved_cents integer NOT NULL DEFAULT 0
        CHECK (reserved_cents >= 0 AND reserved_cents <= configured_budget_cents),
    request_count integer NOT NULL DEFAULT 0
        CHECK (request_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (budget_month = date_trunc('month', budget_month)::date)
);

ALTER TABLE public.sentinel_ai_budget ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sentinel_ai_budget
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sentinel_ai_budget
    TO service_role;

CREATE OR REPLACE FUNCTION public.reserve_sentinel_ai_budget(
    p_budget_month date,
    p_reservation_cents integer,
    p_expected_budget_cents integer
)
RETURNS TABLE (
    allowed boolean,
    reason_code text,
    budget_month date,
    reserved_cents integer,
    configured_budget_cents integer,
    remaining_cents integer,
    request_count integer
)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
    v_row public.sentinel_ai_budget%ROWTYPE;
BEGIN
    IF p_budget_month IS NULL
       OR p_budget_month <> date_trunc('month', p_budget_month)::date THEN
        RETURN QUERY SELECT
            false, 'invalid_budget_month'::text, p_budget_month,
            NULL::integer, NULL::integer, NULL::integer, NULL::integer;
        RETURN;
    END IF;

    IF p_reservation_cents IS NULL OR p_reservation_cents <= 0 THEN
        RETURN QUERY SELECT
            false, 'invalid_reservation'::text, p_budget_month,
            NULL::integer, NULL::integer, NULL::integer, NULL::integer;
        RETURN;
    END IF;

    IF p_expected_budget_cents IS NULL
       OR p_expected_budget_cents <= 0
       OR p_expected_budget_cents > 1000 THEN
        RETURN QUERY SELECT
            false, 'invalid_configured_budget'::text, p_budget_month,
            NULL::integer, NULL::integer, NULL::integer, NULL::integer;
        RETURN;
    END IF;

    -- One atomic UPDATE performs the reservation and cap check under the row
    -- lock acquired by PostgreSQL.  Concurrent callers cannot both spend the
    -- same remaining envelope.
    UPDATE public.sentinel_ai_budget AS b
    SET
        reserved_cents = b.reserved_cents + p_reservation_cents,
        request_count = b.request_count + 1,
        updated_at = now()
    WHERE b.budget_month = p_budget_month
      AND b.configured_budget_cents = p_expected_budget_cents
      AND b.configured_budget_cents <= 1000
      AND b.reserved_cents + p_reservation_cents <= b.configured_budget_cents
    RETURNING b.* INTO v_row;

    IF FOUND THEN
        RETURN QUERY SELECT
            true,
            'reserved'::text,
            v_row.budget_month,
            v_row.reserved_cents,
            v_row.configured_budget_cents,
            v_row.configured_budget_cents - v_row.reserved_cents,
            v_row.request_count;
        RETURN;
    END IF;

    SELECT * INTO v_row
    FROM public.sentinel_ai_budget b
    WHERE b.budget_month = p_budget_month;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            false, 'budget_row_missing'::text, p_budget_month,
            NULL::integer, NULL::integer, NULL::integer, NULL::integer;
    ELSIF v_row.configured_budget_cents <> p_expected_budget_cents THEN
        RETURN QUERY SELECT
            false, 'budget_configuration_mismatch'::text,
            v_row.budget_month, v_row.reserved_cents,
            v_row.configured_budget_cents,
            v_row.configured_budget_cents - v_row.reserved_cents,
            v_row.request_count;
    ELSE
        RETURN QUERY SELECT
            false, 'monthly_budget_exhausted'::text,
            v_row.budget_month, v_row.reserved_cents,
            v_row.configured_budget_cents,
            v_row.configured_budget_cents - v_row.reserved_cents,
            v_row.request_count;
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_sentinel_ai_budget(date, integer, integer)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.reserve_sentinel_ai_budget(date, integer, integer)
    TO service_role;

COMMENT ON TABLE public.sentinel_ai_budget IS
    'Future optional Sentinel AI worst-case reservation envelope; service-role only; hard cap $10/month.';
COMMENT ON FUNCTION public.reserve_sentinel_ai_budget(date, integer, integer) IS
    'Future optional atomic AI budget reservation. SECURITY INVOKER, service-role only, no provider call.';

COMMIT;
