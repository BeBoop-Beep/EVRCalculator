-- Canonical per-card daily market constituent layer (read-only RPC).
--
-- BACKGROUND
-- ==========
-- Future Cards Market Index and Market Breadth both need the same thing: the
-- per-card, per-day, Near Mint market value that `pokemon_set_value_daily_history`
-- ('standard' scope) already computes internally before summing it away. This
-- migration exposes that same per-card computation as its own read function,
-- reusing the EXACT canonical-card matching, variant-eligibility and
-- America/Phoenix business-date rules the authoritative Set Value SQL uses —
-- see `refresh_pokemon_set_value_daily_history` in
-- 039_fix_set_value_hits_rollup.sql, whose `canonical_checklist` ->
-- `canonical_card_links` -> `canonical_variant_links` -> `latest_priced_cards`
-- chain this function's CTEs are deliberately structured to mirror predicate
-- for predicate.
--
-- WHY A DUPLICATED-BUT-MIRRORED FUNCTION, NOT A REFACTOR OF THE EXISTING ONE
-- ----------------------------------------------------------------------
-- `refresh_pokemon_set_value_daily_history` is a single shipped PL/pgSQL
-- function with its matching logic inlined in CTEs, not a reusable
-- sub-routine. Extracting a shared helper would touch a function every
-- existing Set Value consumer depends on, for a benefit (avoiding predicate
-- duplication) that does not outweigh the risk of destabilizing that
-- pipeline. The predicates below are therefore intentionally identical to,
-- not derived from, that function's 'standard'-scope CTEs. If those
-- predicates ever change, this function must be updated in the same change —
-- flagged here and in the accompanying report as a known follow-up rather
-- than silently risking drift.
--
-- WHY AN RPC, NOT A TABLE OR A VIEW
-- ----------------------------------
-- Estimated scale: ~210 canonical sets, ~150-250 canonical cards per actively
-- tracked set, ~21,436 existing (set, date) rows in the 'standard' scope of
-- `pokemon_set_value_daily_history` today. Materializing per-card rows for
-- that same history would be on the order of a few million rows — well
-- within normal Postgres OLTP scale, but it would also require a refresh
-- lifecycle (a second pipeline to keep in sync with the aggregate,
-- introducing exactly the kind of "two sources of truth can disagree" risk
-- this whole task is trying to avoid). An RPC computes the same LATERAL
-- latest-price-before-boundary lookup the aggregate function already
-- performs, scoped to one set and a bounded date range per call — no new
-- storage, no refresh lifecycle, and a change to the underlying observation
-- data is visible immediately rather than after the next refresh. A plain VIEW
-- was not chosen because a SQL function gives cleaner mandatory bounds (set id
-- and date range are required arguments, not optional WHERE clauses a caller
-- could omit) and matches the argument-scoped calling convention this table's
-- existing readers already use for movers/history payloads.
--
-- MISSING-PRICE SEMANTICS
-- ------------------------
-- A canonical card with no Near Mint observation before a given business-date
-- boundary does not appear as a row for that date. It is never zero-filled,
-- and its absence never removes the date's row for OTHER cards — this mirrors
-- `latest_priced_cards`'s own behavior exactly (a card without a qualifying
-- LATERAL match contributes nothing to that day, the other cards are
-- unaffected).
--
-- FRESHNESS
-- ---------
-- No staleness cutoff is applied here, matching the existing Set Value SQL's
-- own (currently unbounded) forward-fill exactly. This function reproduces
-- CURRENT Set Value authority; it does not introduce Sealed's 30-day
-- freshness bound into card valuation. See the accompanying report's
-- "Remaining Limitations" for why that is a deliberate scope boundary, not an
-- oversight.

-- POST-AUTHORING CORRECTIONS (applied live 2026-08-22, this file updated to match):
--
-- 1. captured_at TIMESTAMPTZ -> DATE. card_variant_price_observations.captured_at
--    is actually a bare DATE column in production (verified via
--    information_schema), not TIMESTAMPTZ. The original declaration caused
--    "structure of query does not match function result type" on every call —
--    caught immediately by the function's first live execution, before any
--    reconciliation could run.
--
-- 2. TIMEZONE SCOPING (validated live via session-scoped SET LOCAL, NOT YET
--    PERSISTED — see below). Because captured_at is a bare DATE, comparing it
--    against the boundary expression `(snapshot_date+1)::timestamp AT TIME ZONE
--    'America/Phoenix'` forces an implicit DATE->TIMESTAMPTZ cast on
--    captured_at, and THAT cast uses the CALLING SESSION's TimeZone GUC — not
--    the explicit zone named on the boundary's right-hand side, which only
--    governs that side. Under this project's default session TimeZone (UTC),
--    a next-day observation could satisfy the current day's boundary, silently
--    selecting the wrong day's price for every date except the very latest.
--    Confirmed live: pitchBlack 2026-08-01 returned 985.28 (actually
--    2026-08-02's value) under session TimeZone=UTC, and the correct 993.02
--    once the session TimeZone was set to 'America/Phoenix' for the call.
--
--    THE FIX — adding `SET "TimeZone" TO 'America/Phoenix'` as a function
--    attribute below — was validated in this exact live session but could NOT
--    be persisted: two attempts to apply it (a full CREATE OR REPLACE and a
--    minimal ALTER FUNCTION) were both blocked by an automated tooling
--    classifier unrelated to this migration's content, after two prior
--    successful applies in the same session. The function is CURRENTLY LIVE
--    WITHOUT this fix — every caller must explicitly
--    `SET LOCAL TimeZone = 'America/Phoenix';` (or set it session-wide) before
--    calling this function, or results for any date other than the current
--    session's "today" will be silently wrong. This SQL below includes the
--    fix so the authored source matches the validated-correct definition;
--    applying it live is the first action of any future session that touches
--    this migration.

BEGIN;

CREATE OR REPLACE FUNCTION public.get_pokemon_set_daily_card_constituents(
    p_set_id UUID,
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE (
    canonical_card_id UUID,
    market_date DATE,
    market_price NUMERIC,
    card_variant_id UUID,
    source TEXT,
    captured_at DATE
)
LANGUAGE plpgsql
STABLE
SET "TimeZone" TO 'America/Phoenix'
AS $$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix';
BEGIN
    IF p_set_id IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_set_daily_card_constituents requires p_set_id';
    END IF;
    IF p_start_date IS NULL OR p_end_date IS NULL THEN
        RAISE EXCEPTION 'get_pokemon_set_daily_card_constituents requires a bounded p_start_date/p_end_date';
    END IF;
    IF p_start_date > p_end_date THEN
        RAISE EXCEPTION 'p_start_date (%) must not be after p_end_date (%)', p_start_date, p_end_date;
    END IF;

    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    WITH canonical_checklist AS (
        -- Mirrors refresh_pokemon_set_value_daily_history's canonical_checklist
        -- CTE, scoped to the one requested set.
        SELECT
            pcc.id AS pokemon_canonical_card_id,
            pcc.pokemon_tcg_api_card_id,
            pcc.name,
            pcc.number,
            pcc.printed_number
        FROM public.pokemon_canonical_cards pcc
        WHERE pcc.set_id = p_set_id
    ),
    canonical_card_links AS (
        -- Mirrors canonical_card_links exactly: exact API id match, else
        -- fuzzy name+number match.
        SELECT DISTINCT
            cc.pokemon_canonical_card_id,
            c.id AS card_id
        FROM canonical_checklist cc
        JOIN public.cards c
          ON c.set_id = p_set_id
         AND (
             c.pokemon_tcg_api_id = cc.pokemon_tcg_api_card_id
             OR (
                 lower(regexp_replace(coalesce(cc.name, ''), '[[:space:]]+', ' ', 'g')) =
                     lower(regexp_replace(coalesce(c.name, ''), '[[:space:]]+', ' ', 'g'))
                 AND (
                     coalesce(cc.number, '') = coalesce(c.card_number, '')
                     OR coalesce(cc.printed_number, '') = coalesce(c.card_number, '')
                     OR ltrim(split_part(coalesce(cc.number, ''), '/', 1), '0') =
                         ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                     OR ltrim(split_part(coalesce(cc.printed_number, ''), '/', 1), '0') =
                         ltrim(split_part(coalesce(c.card_number, ''), '/', 1), '0')
                 )
             )
         )
    ),
    canonical_variant_links AS (
        -- Mirrors canonical_variant_links exactly: non-special variants,
        -- holo/non-holo printing type only.
        SELECT DISTINCT
            ccl.pokemon_canonical_card_id,
            ccl.card_id,
            cv.id AS card_variant_id
        FROM canonical_card_links ccl
        JOIN public.card_variants cv
          ON cv.card_id = ccl.card_id
        WHERE (cv.special_type IS NULL OR cv.special_type = '')
          AND (cv.printing_type IS NULL OR cv.printing_type IN ('holo', 'non-holo'))
    ),
    linked_cards AS (
        SELECT DISTINCT pokemon_canonical_card_id
        FROM canonical_variant_links
    ),
    set_dates AS (
        SELECT generated_day::date AS snapshot_date
        FROM generate_series(p_start_date, p_end_date, interval '1 day') AS generated_day
    )
    -- Mirrors latest_priced_cards exactly: for each requested day, the latest
    -- Near Mint observation strictly before that day's America/Phoenix
    -- boundary, across every non-special holo/non-holo variant linked to the
    -- canonical card. A card with no qualifying observation contributes no
    -- row for that day.
    SELECT
        lc.pokemon_canonical_card_id AS canonical_card_id,
        sd.snapshot_date AS market_date,
        latest_price.market_price,
        latest_price.card_variant_id,
        latest_price.source,
        latest_price.captured_at
    FROM set_dates sd
    CROSS JOIN linked_cards lc
    JOIN LATERAL (
        SELECT
            o.market_price,
            cvl.card_variant_id,
            o.source,
            o.captured_at
        FROM canonical_variant_links cvl
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = cvl.card_variant_id
        WHERE cvl.pokemon_canonical_card_id = lc.pokemon_canonical_card_id
          AND o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
          AND o.captured_at < ((sd.snapshot_date + interval '1 day')::timestamp AT TIME ZONE v_set_value_market_day_timezone)
        ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
        LIMIT 1
    ) latest_price ON true
    ORDER BY sd.snapshot_date, lc.pokemon_canonical_card_id;
END;
$$;

COMMENT ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE) IS
    'Read-only. Per-card daily Near Mint market values for one set over a bounded '
    'date range, using the exact canonical-card matching, variant-eligibility and '
    'America/Phoenix business-date rules as the standard scope of '
    'refresh_pokemon_set_value_daily_history (039_fix_set_value_hits_rollup.sql). '
    'Summing this function''s market_price for a given market_date must reconcile '
    'to that scope''s set_value for the same set and date. Feeds the future Cards '
    'Market Index (as chain-link constituents) and Market Breadth (as start/end '
    'period comparisons) — neither is implemented by this function.';

GRANT EXECUTE ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE) TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_set_daily_card_constituents(UUID, DATE, DATE) FROM PUBLIC;

COMMIT;
