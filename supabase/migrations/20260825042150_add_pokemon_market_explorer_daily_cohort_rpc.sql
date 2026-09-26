CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_daily_cohort(
    p_set_ids UUID[],
    p_start_date DATE,
    p_end_date DATE,
    p_card_ids UUID[] DEFAULT NULL,
    p_top_n INTEGER DEFAULT NULL
)
RETURNS TABLE (
    market_date DATE,
    constituent_count INTEGER,
    eligible_universe_count INTEGER,
    basket_value NUMERIC,
    common_count INTEGER,
    common_current_value NUMERIC,
    common_previous_value NUMERIC
)
LANGUAGE sql
STABLE
AS $$
    WITH base AS (
        SELECT canonical_card_id, market_date, market_price
        FROM public.get_pokemon_cards_daily_constituents(
            p_set_ids, p_start_date, p_end_date, p_card_ids
        )
    ),
    ranked AS (
        SELECT
            b.*,
            row_number() OVER (
                PARTITION BY b.market_date
                ORDER BY b.market_price DESC, b.canonical_card_id
            ) AS price_rank,
            count(*) OVER (PARTITION BY b.market_date) AS universe_count
        FROM base b
    ),
    sel AS (
        SELECT * FROM ranked
        WHERE p_top_n IS NULL OR price_rank <= p_top_n
    ),
    agg AS (
        SELECT
            s.market_date,
            count(*)::int AS constituent_count,
            max(s.universe_count)::int AS eligible_universe_count,
            sum(s.market_price) AS basket_value
        FROM sel s
        GROUP BY s.market_date
    ),
    ordered AS (
        SELECT
            a.market_date,
            lag(a.market_date) OVER (ORDER BY a.market_date) AS previous_date
        FROM agg a
    )
    SELECT
        o.market_date,
        a.constituent_count,
        a.eligible_universe_count,
        round(a.basket_value::numeric, 2) AS basket_value,
        coalesce(c.common_count, 0)::int AS common_count,
        round(coalesce(c.common_current_value, 0)::numeric, 2) AS common_current_value,
        round(coalesce(c.common_previous_value, 0)::numeric, 2) AS common_previous_value
    FROM ordered o
    JOIN agg a ON a.market_date = o.market_date
    LEFT JOIN LATERAL (
        SELECT
            count(*)::int AS common_count,
            sum(current_day.market_price) AS common_current_value,
            sum(previous_day.market_price) AS common_previous_value
        FROM sel current_day
        JOIN sel previous_day
          ON previous_day.canonical_card_id = current_day.canonical_card_id
         AND previous_day.market_date = o.previous_date
        WHERE current_day.market_date = o.market_date
    ) c ON o.previous_date IS NOT NULL
    ORDER BY o.market_date;
$$;

COMMENT ON FUNCTION public.get_pokemon_market_explorer_daily_cohort(UUID[], DATE, DATE, UUID[], INTEGER) IS
    'Read-only. Per-DATE cohort aggregates for one Market Explorer query: the day''s '
    'basket value plus the common-cohort sums needed to chain-link it against the '
    'previous observed day. Built directly on get_pokemon_cards_daily_constituents, '
    'so its card-eligibility and business-date predicates are identical BY '
    'CONSTRUCTION rather than by duplication. p_top_n applies the chase cutoff per '
    'date AFTER all filtering (NULL = all constituents), which is what makes chase '
    'membership dynamic per day. Returns one row per market date rather than one per '
    'card-date: the full-history card-date panel for a global rarity is ~29k-64k rows '
    'and cannot cross the 1000-row response cap in fewer than dozens of round trips, '
    'which is the entire cost of such a query. Index levels are NOT computed here; '
    'the caller chain-links from common_current_value / common_previous_value.';

GRANT EXECUTE ON FUNCTION public.get_pokemon_market_explorer_daily_cohort(UUID[], DATE, DATE, UUID[], INTEGER) TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_market_explorer_daily_cohort(UUID[], DATE, DATE, UUID[], INTEGER) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.get_pokemon_market_explorer_daily_cohort(UUID[], DATE, DATE, UUID[], INTEGER) FROM anon, authenticated;
