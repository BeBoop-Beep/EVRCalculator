-- Durable daily Pokemon set market value history.
--
-- This table is sourced from card_variant_price_observations and is independent
-- from simulation_derived_metrics.simulated_set_value. It stores one daily set
-- value per set/scope using the latest known Near Mint card price as of each day.

BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_set_value_daily_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    value_scope TEXT NOT NULL DEFAULT 'standard',
    set_value NUMERIC,
    priced_card_count INTEGER,
    total_card_count INTEGER,
    source TEXT NOT NULL DEFAULT 'card_variant_price_observations_near_mint_latest_as_of_day',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT pokemon_set_value_daily_history_scope_check CHECK (value_scope IN ('standard', 'hits', 'top10'))
);

ALTER TABLE public.pokemon_set_value_daily_history
    ADD COLUMN IF NOT EXISTS value_scope TEXT NOT NULL DEFAULT 'standard';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'pokemon_set_value_daily_history_scope_check'
          AND conrelid = 'public.pokemon_set_value_daily_history'::regclass
    ) THEN
        ALTER TABLE public.pokemon_set_value_daily_history
            ADD CONSTRAINT pokemon_set_value_daily_history_scope_check
            CHECK (value_scope IN ('standard', 'hits', 'top10')) NOT VALID;
    END IF;
END $$;

ALTER TABLE public.pokemon_set_value_daily_history
    VALIDATE CONSTRAINT pokemon_set_value_daily_history_scope_check;

-- Earlier local drafts keyed only set_id + snapshot_date. Drop those objects so
-- scoped rows can coexist for the same set/day.
ALTER TABLE public.pokemon_set_value_daily_history
    DROP CONSTRAINT IF EXISTS pokemon_set_value_daily_history_set_date_key;

DROP INDEX IF EXISTS public.idx_pokemon_set_value_daily_history_set_snapshot_date_unique;

DELETE FROM public.pokemon_set_value_daily_history h
USING public.pokemon_set_value_daily_history newer
WHERE h.set_id = newer.set_id
  AND h.snapshot_date = newer.snapshot_date
  AND h.value_scope = newer.value_scope
  AND (
      newer.updated_at > h.updated_at
      OR (newer.updated_at = h.updated_at AND newer.created_at > h.created_at)
      OR (newer.updated_at = h.updated_at AND newer.created_at = h.created_at AND newer.id > h.id)
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_pokemon_set_value_daily_history_set_date_scope_unique
    ON public.pokemon_set_value_daily_history (set_id, snapshot_date, value_scope);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_value_daily_history_set_scope_date
    ON public.pokemon_set_value_daily_history (set_id, value_scope, snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_pokemon_set_value_daily_history_snapshot_date
    ON public.pokemon_set_value_daily_history (snapshot_date DESC);

CREATE INDEX IF NOT EXISTS idx_cards_set_id_for_value_history
    ON public.cards (set_id);

CREATE INDEX IF NOT EXISTS idx_card_variants_card_id_for_value_history
    ON public.card_variants (card_id);

CREATE INDEX IF NOT EXISTS idx_card_variant_price_observations_variant_condition_captured_at_for_set_value
    ON public.card_variant_price_observations (card_variant_id, condition_id, captured_at DESC);

CREATE OR REPLACE FUNCTION public.sync_pokemon_set_value_daily_history_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := timezone('utc', now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_pokemon_set_value_daily_history_updated_at
    ON public.pokemon_set_value_daily_history;

CREATE TRIGGER trg_sync_pokemon_set_value_daily_history_updated_at
BEFORE UPDATE ON public.pokemon_set_value_daily_history
FOR EACH ROW
EXECUTE FUNCTION public.sync_pokemon_set_value_daily_history_updated_at();

CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history(
    p_set_id UUID DEFAULT NULL,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_near_mint_condition_id public.conditions.id%TYPE;
    v_rows_upserted INTEGER := 0;
BEGIN
    SELECT id
    INTO v_near_mint_condition_id
    FROM public.conditions
    WHERE lower(name) = 'near mint'
    ORDER BY id
    LIMIT 1;

    IF v_near_mint_condition_id IS NULL THEN
        RAISE NOTICE 'Near Mint condition not found; pokemon_set_value_daily_history refresh skipped.';
        RETURN 0;
    END IF;

    WITH requested_sets AS (
        SELECT id
        FROM public.sets
        WHERE p_set_id IS NULL OR id = p_set_id
    ),
    simulation_set_ids AS (
        SELECT DISTINCT s.id AS set_id
        FROM requested_sets s
        JOIN public.calculation_runs cr
          ON cr.target_id = s.id::text
         AND cr.target_type = 'set'
         AND cr.valuation_method = 'combined'
        JOIN public.simulation_input_cards sic
          ON sic.calculation_run_id = cr.id
        WHERE sic.card_variant_id IS NOT NULL
    ),
    simulation_tracked_cards AS (
        SELECT DISTINCT
            s.id AS set_id,
            coalesce(sic.card_id, cv.card_id) AS card_id,
            sic.card_variant_id,
            coalesce(c.rarity, sic.rarity_bucket) AS rarity,
            'simulation_input_cards'::text AS universe_source
        FROM requested_sets s
        JOIN public.calculation_runs cr
          ON cr.target_id = s.id::text
         AND cr.target_type = 'set'
         AND cr.valuation_method = 'combined'
        JOIN public.simulation_input_cards sic
          ON sic.calculation_run_id = cr.id
        LEFT JOIN public.card_variants cv
          ON cv.id = sic.card_variant_id
        LEFT JOIN public.cards c
          ON c.id = coalesce(sic.card_id, cv.card_id)
        WHERE sic.card_variant_id IS NOT NULL
          AND coalesce(sic.card_id, cv.card_id) IS NOT NULL
    ),
    fallback_tracked_cards AS (
        SELECT DISTINCT
            c.set_id,
            c.id AS card_id,
            cv.id AS card_variant_id,
            c.rarity,
            'card_variants_by_set'::text AS universe_source
        FROM requested_sets s
        JOIN public.cards c
          ON c.set_id = s.id
        JOIN public.card_variants cv
          ON cv.card_id = c.id
        WHERE NOT EXISTS (
            SELECT 1
            FROM simulation_set_ids sim
            WHERE sim.set_id = s.id
        )
    ),
    tracked_cards AS (
        SELECT * FROM simulation_tracked_cards
        UNION ALL
        SELECT * FROM fallback_tracked_cards
    ),
    observed_bounds AS (
        SELECT
            tc.set_id,
            min(timezone('utc', o.captured_at)::date) AS first_observation_date,
            max(timezone('utc', o.captured_at)::date) AS latest_observation_date
        FROM tracked_cards tc
        JOIN public.card_variant_price_observations o
          ON o.card_variant_id = tc.card_variant_id
        WHERE o.condition_id = v_near_mint_condition_id
          AND o.market_price IS NOT NULL
          AND o.market_price > 0
          AND o.captured_at IS NOT NULL
        GROUP BY tc.set_id
    ),
    set_dates AS (
        SELECT
            b.set_id,
            generated_day::date AS snapshot_date
        FROM observed_bounds b
        CROSS JOIN LATERAL generate_series(
            greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date)),
            least(coalesce(p_end_date, b.latest_observation_date), b.latest_observation_date),
            interval '1 day'
        ) AS generated_day
        WHERE greatest(b.first_observation_date, coalesce(p_start_date, b.first_observation_date))
              <= least(coalesce(p_end_date, b.latest_observation_date), b.latest_observation_date)
    ),
    latest_priced_candidates AS (
        SELECT
            sd.set_id,
            sd.snapshot_date,
            tc.card_id,
            tc.rarity,
            latest_price.market_price,
            tc.universe_source
        FROM set_dates sd
        JOIN tracked_cards tc
          ON tc.set_id = sd.set_id
        JOIN LATERAL (
            SELECT o.market_price
            FROM public.card_variant_price_observations o
            WHERE o.card_variant_id = tc.card_variant_id
              AND o.condition_id = v_near_mint_condition_id
              AND o.market_price IS NOT NULL
              AND o.market_price > 0
              AND o.captured_at IS NOT NULL
              AND o.captured_at < ((sd.snapshot_date + interval '1 day') AT TIME ZONE 'UTC')
            ORDER BY o.captured_at DESC NULLS LAST, o.id DESC
            LIMIT 1
        ) latest_price ON true
    ),
    priced_cards AS (
        SELECT
            set_id,
            snapshot_date,
            card_id,
            max(rarity) AS rarity,
            max(market_price) AS card_price,
            min(universe_source) AS universe_source
        FROM latest_priced_candidates
        GROUP BY set_id, snapshot_date, card_id
    ),
    tracked_counts AS (
        SELECT
            set_id,
            count(DISTINCT card_id)::integer AS total_card_count,
            count(DISTINCT card_id) FILTER (
                WHERE lower(coalesce(rarity, '')) NOT IN ('common', 'uncommon', 'rare', 'rare holo', 'promo')
            )::integer AS hit_card_count
        FROM tracked_cards
        GROUP BY set_id
    ),
    standard_aggregated AS (
        SELECT
            pc.set_id,
            pc.snapshot_date,
            'standard'::text AS value_scope,
            round(sum(pc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            max(tc.total_card_count)::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:standard:' || min(pc.universe_source) AS source
        FROM priced_cards pc
        LEFT JOIN tracked_counts tc
          ON tc.set_id = pc.set_id
        GROUP BY pc.set_id, pc.snapshot_date
    ),
    hits_aggregated AS (
        SELECT
            pc.set_id,
            pc.snapshot_date,
            'hits'::text AS value_scope,
            round(sum(pc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            max(tc.hit_card_count)::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:hits:' || min(pc.universe_source) AS source
        FROM priced_cards pc
        LEFT JOIN tracked_counts tc
          ON tc.set_id = pc.set_id
        WHERE lower(coalesce(pc.rarity, '')) NOT IN ('common', 'uncommon', 'rare', 'rare holo', 'promo')
        GROUP BY pc.set_id, pc.snapshot_date
    ),
    ranked_priced_cards AS (
        SELECT
            pc.*,
            row_number() OVER (
                PARTITION BY pc.set_id, pc.snapshot_date
                ORDER BY pc.card_price DESC, pc.card_id
            ) AS price_rank
        FROM priced_cards pc
    ),
    top10_aggregated AS (
        SELECT
            rpc.set_id,
            rpc.snapshot_date,
            'top10'::text AS value_scope,
            round(sum(rpc.card_price)::numeric, 2) AS set_value,
            count(*)::integer AS priced_card_count,
            10::integer AS total_card_count,
            'card_variant_price_observations_near_mint_latest_as_of_day:top10:' || min(rpc.universe_source) AS source
        FROM ranked_priced_cards rpc
        WHERE rpc.price_rank <= 10
        GROUP BY rpc.set_id, rpc.snapshot_date
    ),
    aggregated AS (
        SELECT * FROM standard_aggregated
        UNION ALL
        SELECT * FROM hits_aggregated
        UNION ALL
        SELECT * FROM top10_aggregated
    ),
    upserted AS (
        INSERT INTO public.pokemon_set_value_daily_history (
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            total_card_count,
            source
        )
        SELECT
            set_id,
            snapshot_date,
            value_scope,
            set_value,
            priced_card_count,
            total_card_count,
            source
        FROM aggregated
        ON CONFLICT (set_id, snapshot_date, value_scope)
        DO UPDATE SET
            set_value = EXCLUDED.set_value,
            priced_card_count = EXCLUDED.priced_card_count,
            total_card_count = EXCLUDED.total_card_count,
            source = EXCLUDED.source,
            updated_at = timezone('utc', now())
        RETURNING 1
    )
    SELECT count(*)
    INTO v_rows_upserted
    FROM upserted;

    RETURN coalesce(v_rows_upserted, 0);
END;
$$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history_for_variants(
    p_card_variant_ids UUID[],
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT timezone('utc', now())::date
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_set_id UUID;
    v_total_rows INTEGER := 0;
BEGIN
    IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 THEN
        RETURN 0;
    END IF;

    FOR v_set_id IN
        SELECT DISTINCT c.set_id
        FROM public.card_variants cv
        JOIN public.cards c
          ON c.id = cv.card_id
        WHERE cv.id = ANY(p_card_variant_ids)
          AND c.set_id IS NOT NULL
    LOOP
        v_total_rows := v_total_rows + public.refresh_pokemon_set_value_daily_history(
            v_set_id,
            p_start_date,
            p_end_date
        );
    END LOOP;

    RETURN v_total_rows;
END;
$$;

CREATE OR REPLACE VIEW public.pokemon_set_value_daily_history_coverage
WITH (security_invoker = true)
AS
SELECT
    s.id AS set_id,
    s.name AS set_name,
    h.value_scope,
    min(h.snapshot_date) AS first_snapshot_date,
    max(h.snapshot_date) AS latest_snapshot_date,
    count(DISTINCT h.snapshot_date)::integer AS distinct_snapshot_days,
    min(h.priced_card_count)::integer AS min_priced_card_count,
    max(h.priced_card_count)::integer AS max_priced_card_count,
    max(h.total_card_count)::integer AS total_card_count,
    (count(h.id) > 0) AS has_history
FROM public.sets s
LEFT JOIN public.pokemon_set_value_daily_history h
  ON h.set_id = s.id
GROUP BY s.id, s.name, h.value_scope;

ALTER TABLE public.pokemon_set_value_daily_history ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_set_value_daily_history TO service_role;
GRANT SELECT ON public.pokemon_set_value_daily_history_coverage TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_set_value_daily_history(UUID, DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_set_value_daily_history_for_variants(UUID[], DATE, DATE) TO service_role;

-- Initial all-set backfill. This can be rerun safely; rows are upserted by
-- (set_id, snapshot_date, value_scope).
SELECT public.refresh_pokemon_set_value_daily_history();

COMMIT;
