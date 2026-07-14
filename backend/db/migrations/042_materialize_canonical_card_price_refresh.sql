-- Evaluate the set-scoped resolver once. The previous safety count plus insert
-- evaluated it twice and pushed a few large sets over PostgREST's timeout.

CREATE OR REPLACE FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(target_set_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    existing_count INTEGER;
    resolved_count INTEGER;
    inserted_count INTEGER;
    resolved_rows JSONB;
BEGIN
    SELECT count(*)::INTEGER
      INTO existing_count
      FROM public.pokemon_canonical_card_market_prices_latest
     WHERE set_id = target_set_id;

    SELECT coalesce(jsonb_agg(to_jsonb(resolved)), '[]'::jsonb)
      INTO resolved_rows
      FROM public.get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id) resolved;

    resolved_count := jsonb_array_length(resolved_rows);

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
        row.canonical_card_id,
        row.set_id,
        row.pokemon_tcg_api_card_id,
        row.legacy_card_id,
        row.card_variant_id,
        row.condition_id,
        row.printing_type,
        row.market_price,
        row.captured_at,
        row.source,
        row.price_selection_reason,
        now()
    FROM jsonb_to_recordset(resolved_rows) AS row(
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
    );

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$;

REVOKE ALL ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(UUID)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_for_set(UUID)
    TO service_role;
