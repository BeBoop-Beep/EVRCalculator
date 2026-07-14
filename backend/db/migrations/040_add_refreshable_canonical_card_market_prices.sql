-- Durable canonical Pokemon card -> selected Near Mint market-price layer.
--
-- This migration intentionally owns the full contract because the original
-- table/functions were created from the Supabase dashboard and never landed
-- in repository migration history.  It is safe to rerun against that schema.

CREATE TABLE IF NOT EXISTS public.pokemon_canonical_card_market_prices_latest (
    canonical_card_id UUID PRIMARY KEY REFERENCES public.pokemon_canonical_cards(id) ON DELETE CASCADE,
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    pokemon_tcg_api_card_id TEXT NOT NULL,
    legacy_card_id UUID NOT NULL REFERENCES public.cards(id) ON DELETE CASCADE,
    card_variant_id UUID NOT NULL REFERENCES public.card_variants(id) ON DELETE CASCADE,
    condition_id UUID NOT NULL REFERENCES public.conditions(id),
    printing_type TEXT,
    market_price NUMERIC NOT NULL,
    captured_at DATE,
    source TEXT,
    price_selection_reason TEXT NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_card_market_prices_latest_set_id
    ON public.pokemon_canonical_card_market_prices_latest(set_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_card_market_prices_latest_api_id
    ON public.pokemon_canonical_card_market_prices_latest(pokemon_tcg_api_card_id);

COMMENT ON TABLE public.pokemon_canonical_card_market_prices_latest IS
'Refreshable canonical latest Near Mint USD market-price layer. One selected variant/condition per canonical checklist card.';

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id UUID)
RETURNS TABLE (
    canonical_card_id UUID,
    set_id UUID,
    pokemon_tcg_api_card_id TEXT,
    legacy_card_id UUID,
    card_variant_id UUID,
    condition_id UUID,
    printing_type TEXT,
    market_price NUMERIC,
    captured_at DATE,
    source TEXT,
    price_selection_reason TEXT
)
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
WITH near_mint_condition AS (
    SELECT id
    FROM public.conditions
    WHERE name = 'Near Mint'
      AND abbreviation = 'NM'
    ORDER BY id
    LIMIT 1
), identity_candidates AS (
    SELECT
        pcc.id AS canonical_card_id,
        pcc.set_id,
        pcc.pokemon_tcg_api_card_id,
        pcc.rarity,
        c.id AS legacy_card_id,
        cv.id AS card_variant_id,
        cv.printing_type,
        cv.special_type,
        CASE
            -- The parent API id covers every legitimate printing variant and
            -- is the stable identity used by the legacy scraper.
            WHEN c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id THEN 0
            WHEN cv.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id THEN 1
            ELSE 2
        END AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
    JOIN public.card_variants cv
      ON cv.card_id = c.id
    WHERE pcc.set_id = target_set_id
      AND (
          c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
          OR cv.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
          OR (
              lower(regexp_replace(trim(c.name), '\s+', ' ', 'g')) =
                  lower(regexp_replace(trim(pcc.name), '\s+', ' ', 'g'))
              AND regexp_replace(split_part(lower(coalesce(c.card_number, '')), '/', 1), '^0+', '') IN (
                  regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
                  regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', '')
              )
          )
      )
), candidates AS (
    SELECT
        ic.canonical_card_id,
        ic.set_id,
        ic.pokemon_tcg_api_card_id,
        ic.legacy_card_id,
        ic.card_variant_id,
        latest.condition_id,
        ic.printing_type,
        latest.market_price,
        latest.captured_at,
        latest.source,
        CASE
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'non-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_non_holo_base_print'
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_holo_fallback'
            WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
            WHEN ic.printing_type = 'holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_holo_base_print'
            WHEN ic.printing_type = 'non-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_non_holo_fallback'
            WHEN ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL
                THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
            ELSE 'latest_nm_special_or_other_fallback'
        END AS price_selection_reason,
        row_number() OVER (
            PARTITION BY ic.canonical_card_id
            ORDER BY
                ic.identity_rank,
                latest.captured_at DESC NULLS LAST,
                CASE WHEN ic.special_type IS NULL THEN 0 ELSE 1 END,
                CASE
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'non-holo' THEN 0
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'holo' THEN 1
                    WHEN ic.rarity IN ('Common', 'Uncommon') AND ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL THEN 2
                    WHEN ic.printing_type = 'holo' THEN 0
                    WHEN ic.printing_type = 'non-holo' THEN 1
                    WHEN ic.printing_type = 'reverse-holo' AND ic.special_type IS NULL THEN 2
                    ELSE 9
                END,
                latest.created_at DESC NULLS LAST,
                ic.card_variant_id
        ) AS selection_rank
    FROM identity_candidates ic
    CROSS JOIN near_mint_condition nmc
    JOIN LATERAL (
        SELECT
            po.condition_id,
            po.market_price,
            po.captured_at,
            po.source,
            po.created_at,
            po.id
        FROM public.card_variant_price_observations po
        WHERE po.card_variant_id = ic.card_variant_id
          AND po.condition_id = nmc.id
          AND po.market_price > 0
          AND trim(both '"' from upper(coalesce(po.currency, ''))) = 'USD'
        ORDER BY po.captured_at DESC NULLS LAST, po.created_at DESC NULLS LAST, po.id DESC
        LIMIT 1
    ) latest ON true
)
SELECT
    candidates.canonical_card_id,
    candidates.set_id,
    candidates.pokemon_tcg_api_card_id,
    candidates.legacy_card_id,
    candidates.card_variant_id,
    candidates.condition_id,
    candidates.printing_type,
    candidates.market_price,
    candidates.captured_at,
    candidates.source,
    candidates.price_selection_reason
FROM candidates
WHERE candidates.selection_rank = 1;
$$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(target_set_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    existing_count INTEGER;
    resolved_count INTEGER;
    inserted_count INTEGER;
BEGIN
    SELECT count(*)::INTEGER
      INTO existing_count
      FROM public.pokemon_canonical_card_market_prices_latest
     WHERE set_id = target_set_id;

    SELECT count(*)::INTEGER
      INTO resolved_count
      FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id);

    -- Preserve a previously healthy set if an upstream identity/source outage
    -- unexpectedly makes the resolver return no rows. New genuinely unpriced
    -- sets still return zero without fabricating data.
    IF existing_count > 0 AND resolved_count = 0 THEN
        RAISE EXCEPTION
            'Refusing to replace % canonical price rows with zero rows for set %',
            existing_count,
            target_set_id;
    END IF;

    DELETE FROM public.pokemon_canonical_card_market_prices_latest
     WHERE set_id = target_set_id;

    INSERT INTO public.pokemon_canonical_card_market_prices_latest (
        canonical_card_id,
        set_id,
        pokemon_tcg_api_card_id,
        legacy_card_id,
        card_variant_id,
        condition_id,
        printing_type,
        market_price,
        captured_at,
        source,
        price_selection_reason,
        refreshed_at
    )
    SELECT
        resolved.canonical_card_id,
        resolved.set_id,
        resolved.pokemon_tcg_api_card_id,
        resolved.legacy_card_id,
        resolved.card_variant_id,
        resolved.condition_id,
        resolved.printing_type,
        resolved.market_price,
        resolved.captured_at,
        resolved.source,
        resolved.price_selection_reason,
        now()
    FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id) resolved;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all()
RETURNS TABLE(set_id UUID, refreshed_price_rows INTEGER)
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    set_record RECORD;
BEGIN
    FOR set_record IN
        SELECT DISTINCT pcc.set_id
        FROM public.pokemon_canonical_cards pcc
        ORDER BY pcc.set_id
    LOOP
        set_id := set_record.set_id;
        refreshed_price_rows :=
            public.refresh_pokemon_canonical_card_market_prices_latest_for_set(set_record.set_id);
        RETURN NEXT;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_variants(
    p_card_variant_ids UUID[]
)
RETURNS TABLE(set_id UUID, refreshed_price_rows INTEGER)
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    set_record RECORD;
BEGIN
    FOR set_record IN
        SELECT DISTINCT c.set_id
        FROM public.card_variants cv
        JOIN public.cards c ON c.id = cv.card_id
        WHERE cv.id = ANY(coalesce(p_card_variant_ids, ARRAY[]::UUID[]))
        ORDER BY c.set_id
    LOOP
        set_id := set_record.set_id;
        refreshed_price_rows :=
            public.refresh_pokemon_canonical_card_market_prices_latest_for_set(set_record.set_id);
        RETURN NEXT;
    END LOOP;
END;
$$;

DROP VIEW IF EXISTS public.pokemon_canonical_card_market_price_set_diagnostics;
DROP VIEW IF EXISTS public.pokemon_canonical_card_market_price_missing_cards;

CREATE OR REPLACE VIEW public.pokemon_canonical_card_market_price_missing_cards
WITH (security_invoker = true)
AS
SELECT
    pcc.set_id,
    s.name AS set_name,
    pcc.id AS canonical_card_id,
    pcc.name,
    pcc.number,
    pcc.printed_number,
    pcc.rarity,
    pcc.pokemon_tcg_api_card_id
FROM public.pokemon_canonical_cards pcc
LEFT JOIN public.sets s ON s.id = pcc.set_id
LEFT JOIN public.pokemon_canonical_card_market_prices_latest price
  ON price.canonical_card_id = pcc.id
WHERE price.canonical_card_id IS NULL;

CREATE OR REPLACE VIEW public.pokemon_canonical_card_market_price_set_diagnostics
WITH (security_invoker = true)
AS
WITH canonical_counts AS (
    SELECT set_id, count(*) AS canonical_card_count
    FROM public.pokemon_canonical_cards
    GROUP BY set_id
), priced_counts AS (
    SELECT set_id, count(*) AS canonical_cards_with_latest_nm_price
    FROM public.pokemon_canonical_card_market_prices_latest
    GROUP BY set_id
), resolvable_counts AS (
    SELECT
        cc.set_id,
        (
            SELECT count(*)
            FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(cc.set_id)
        ) AS canonical_cards_with_resolvable_nm_price
    FROM canonical_counts cc
), missing_cards AS (
    SELECT
        set_id,
        jsonb_agg(
            jsonb_build_object(
                'name', name,
                'number', number,
                'printed_number', printed_number,
                'rarity', rarity,
                'pokemon_tcg_api_card_id', pokemon_tcg_api_card_id
            )
            ORDER BY number, name
        ) AS missing_cards
    FROM public.pokemon_canonical_card_market_price_missing_cards
    GROUP BY set_id
), variant_diagnostics AS (
    SELECT
        c.set_id,
        count(cv.id) AS variant_rows,
        count(cv.id) FILTER (WHERE cv.pokemon_tcg_api_id IS NULL)
            AS variant_rows_with_null_pokemon_tcg_api_id,
        count(cv.id) FILTER (
            WHERE cv.pokemon_tcg_api_id IS NULL
              AND c.pokemon_tcg_api_id IS NOT NULL
        ) AS variant_rows_naively_fixable_from_parent_card_api_id,
        count(cv.id) FILTER (
            WHERE cv.pokemon_tcg_api_id IS NULL
              AND c.pokemon_tcg_api_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.card_variants existing
                  WHERE existing.pokemon_tcg_api_id = c.pokemon_tcg_api_id
              )
        ) AS variant_rows_parent_api_id_not_already_used,
        count(cv.id) FILTER (
            WHERE cv.pokemon_tcg_api_id IS NOT NULL
              AND c.pokemon_tcg_api_id IS NOT NULL
              AND cv.pokemon_tcg_api_id <> c.pokemon_tcg_api_id
        ) AS variant_rows_api_id_differs_from_parent
    FROM public.cards c
    LEFT JOIN public.card_variants cv ON cv.card_id = c.id
    GROUP BY c.set_id
)
SELECT
    cc.set_id,
    s.name AS set_name,
    cc.canonical_card_count,
    coalesce(pc.canonical_cards_with_latest_nm_price, 0) AS canonical_cards_with_latest_nm_price,
    coalesce(rc.canonical_cards_with_resolvable_nm_price, 0) AS canonical_cards_with_resolvable_nm_price,
    cc.canonical_card_count - coalesce(pc.canonical_cards_with_latest_nm_price, 0)
        AS canonical_cards_missing_latest_nm_price,
    coalesce(mc.missing_cards, '[]'::jsonb) AS missing_cards,
    coalesce(vd.variant_rows, 0) AS variant_rows,
    coalesce(vd.variant_rows_with_null_pokemon_tcg_api_id, 0)
        AS variant_rows_with_null_pokemon_tcg_api_id,
    coalesce(vd.variant_rows_naively_fixable_from_parent_card_api_id, 0)
        AS variant_rows_naively_fixable_from_parent_card_api_id,
    coalesce(vd.variant_rows_parent_api_id_not_already_used, 0)
        AS variant_rows_parent_api_id_not_already_used,
    coalesce(vd.variant_rows_api_id_differs_from_parent, 0)
        AS variant_rows_api_id_differs_from_parent,
    coalesce(rc.canonical_cards_with_resolvable_nm_price, 0) -
        coalesce(pc.canonical_cards_with_latest_nm_price, 0)
        AS refreshable_price_row_gap
FROM canonical_counts cc
LEFT JOIN public.sets s ON s.id = cc.set_id
LEFT JOIN priced_counts pc ON pc.set_id = cc.set_id
LEFT JOIN resolvable_counts rc ON rc.set_id = cc.set_id
LEFT JOIN missing_cards mc ON mc.set_id = cc.set_id
LEFT JOIN variant_diagnostics vd ON vd.set_id = cc.set_id;

ALTER TABLE public.pokemon_canonical_card_market_prices_latest ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pokemon_canonical_card_market_prices_latest_public_read
    ON public.pokemon_canonical_card_market_prices_latest;
CREATE POLICY pokemon_canonical_card_market_prices_latest_public_read
    ON public.pokemon_canonical_card_market_prices_latest
    FOR SELECT
    TO anon, authenticated
    USING (true);

REVOKE INSERT, UPDATE, DELETE, TRUNCATE
    ON public.pokemon_canonical_card_market_prices_latest
    FROM anon, authenticated;
GRANT SELECT ON public.pokemon_canonical_card_market_prices_latest TO anon, authenticated;

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_variants(UUID[]) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all() TO service_role;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_variants(UUID[]) TO service_role;
