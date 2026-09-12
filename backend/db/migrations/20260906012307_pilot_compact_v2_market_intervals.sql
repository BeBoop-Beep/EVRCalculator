BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_market_price_intervals_v2_shadow_pilot (
    card_variant_id uuid NOT NULL,
    set_id uuid NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    market_price numeric NOT NULL,
    PRIMARY KEY (card_variant_id, valid_from),
    CHECK (market_price > 0),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX IF NOT EXISTS pokemon_market_price_intervals_v2_pilot_set_from_idx
    ON public.pokemon_market_price_intervals_v2_shadow_pilot (set_id, valid_from, card_variant_id)
    INCLUDE (valid_to, market_price);

ALTER TABLE public.pokemon_market_price_intervals_v2_shadow_pilot ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_market_price_intervals_v2_shadow_pilot FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pokemon_market_price_intervals_v2_shadow_pilot TO service_role;

TRUNCATE TABLE public.pokemon_market_price_intervals_v2_shadow_pilot;

WITH pilot_sets(set_id) AS (
    VALUES
      ('0010d2ec-894e-4c17-855d-5de6ff6fd204'::uuid), -- Base
      ('7ceb2e94-7968-4394-95cb-742b01804974'::uuid), -- Expedition Base Set
      ('75cc9ef9-1099-4e47-8d09-17f416606865'::uuid), -- Evolutions
      ('dfcf6c98-1bf3-43a8-83a2-7e56b3c65d03'::uuid), -- Cosmic Eclipse
      ('93212749-ce0e-498e-975e-7d947a3448ce'::uuid), -- Evolving Skies
      ('d001d563-988b-4f8e-904f-acb926748e22'::uuid), -- Scarlet and Violet 151
      ('7a3dd188-4375-41af-94de-c5247fe0b1a6'::uuid), -- Prismatic Evolutions
      ('75cd439d-aaa2-41cb-86f3-2fefa5b26e29'::uuid), -- Ascended Heroes
      ('5e99f658-39f0-4845-9228-db8db3965f32'::uuid), -- Perfect Order
      ('472f851c-2e41-4c80-b6fc-8478d1d92730'::uuid)  -- Pitch Black
), ordered AS MATERIALIZED (
    SELECT
        e.card_variant_id,
        c.set_id,
        e.effective_date,
        e.market_price,
        lag(e.market_price) OVER (
            PARTITION BY e.card_variant_id
            ORDER BY e.effective_date, e.id
        ) AS previous_market_price,
        row_number() OVER (
            PARTITION BY e.card_variant_id
            ORDER BY e.effective_date, e.id
        ) AS sequence_number
    FROM public.card_variant_price_events_v2 e
    JOIN public.card_variants v ON v.id = e.card_variant_id
    JOIN public.cards c ON c.id = v.card_id
    JOIN pilot_sets p ON p.set_id = c.set_id
    WHERE e.condition_id = '4f8d1181-670e-4aea-937c-4d98d2e531a6'::uuid
      AND e.source = 'TCGPlayer'
      AND e.currency = 'USD'
      AND e.market_price > 0
), changes AS MATERIALIZED (
    SELECT
        card_variant_id,
        set_id,
        effective_date,
        market_price
    FROM ordered
    WHERE sequence_number = 1
       OR market_price IS DISTINCT FROM previous_market_price
), intervals AS (
    SELECT
        card_variant_id,
        set_id,
        effective_date AS valid_from,
        lead(effective_date) OVER (
            PARTITION BY card_variant_id
            ORDER BY effective_date
        ) AS valid_to,
        market_price
    FROM changes
)
INSERT INTO public.pokemon_market_price_intervals_v2_shadow_pilot (
    card_variant_id, set_id, valid_from, valid_to, market_price
)
SELECT card_variant_id, set_id, valid_from, valid_to, market_price
FROM intervals;

COMMENT ON TABLE public.pokemon_market_price_intervals_v2_shadow_pilot IS
'Backend-only representative pilot of compact Market Explorer intervals derived from Price Storage V2 market-price changes. Never used by production readers.';

COMMIT;