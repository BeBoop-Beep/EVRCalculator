-- One canonical card-day constituent authority for Set Value-adjacent analytics.
--
-- The existing batched reader already owns canonical/legacy identity resolution,
-- legitimate standard-variant selection, Near Mint positive-price selection,
-- Phoenix market days, and latest-known-price-as-of-day behavior.  Preserve that
-- implementation under an internal compatibility name, then put the canonical
-- eligibility boundary in exactly one public reader.  The legacy single-set RPC
-- becomes a projection-only wrapper; it contains no constituent-selection SQL.

BEGIN;

ALTER FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    RENAME TO get_pokemon_cards_daily_constituents_resolved_universe;

CREATE FUNCTION public.get_pokemon_cards_daily_constituents(
    p_set_ids uuid[],
    p_start_date date,
    p_end_date date,
    p_card_ids uuid[] DEFAULT NULL::uuid[]
)
RETURNS TABLE(
    canonical_card_id uuid,
    set_id uuid,
    market_date date,
    market_price numeric,
    card_variant_id uuid,
    source text,
    captured_at date
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET "TimeZone" TO 'America/Phoenix'
AS $function$
    SELECT raw.canonical_card_id,
           raw.set_id,
           raw.market_date,
           raw.market_price,
           raw.card_variant_id,
           raw.source,
           raw.captured_at
    FROM public.get_pokemon_cards_daily_constituents_resolved_universe(
        p_set_ids, p_start_date, p_end_date, p_card_ids
    ) AS raw
    JOIN public.pokemon_canonical_cards AS canonical
      ON canonical.id = raw.canonical_card_id
     AND canonical.set_id = raw.set_id
    WHERE canonical.set_value_eligible = TRUE
    ORDER BY raw.market_date, raw.canonical_card_id;
$function$;

COMMENT ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[]) IS
    'Canonical reusable card-day constituent authority. Its eligible universe is '
    'pokemon_canonical_cards.set_value_eligible=true, identical to standard Set Value. '
    'Identity, variant, Near Mint, positive-price, Phoenix-date and as-of-day resolution '
    'are delegated to the preserved resolved-universe implementation.';

CREATE OR REPLACE FUNCTION public.get_pokemon_set_daily_card_constituents(
    p_set_id uuid,
    p_start_date date,
    p_end_date date
)
RETURNS TABLE(
    canonical_card_id uuid,
    market_date date,
    market_price numeric,
    card_variant_id uuid,
    source text,
    captured_at date
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET "TimeZone" TO 'America/Phoenix'
AS $function$
    SELECT canonical_card_id, market_date, market_price,
           card_variant_id, source, captured_at
    FROM public.get_pokemon_cards_daily_constituents(
        ARRAY[p_set_id], p_start_date, p_end_date, NULL::uuid[]
    );
$function$;

COMMENT ON FUNCTION public.get_pokemon_set_daily_card_constituents(uuid, date, date) IS
    'Deprecated single-set compatibility wrapper over get_pokemon_cards_daily_constituents. '
    'Contains no independent constituent-selection rules.';

REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents_resolved_universe(uuid[], date, date, uuid[])
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_pokemon_set_daily_card_constituents(uuid, date, date)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_pokemon_cards_daily_constituents(uuid[], date, date, uuid[])
    TO service_role;
GRANT EXECUTE ON FUNCTION public.get_pokemon_set_daily_card_constituents(uuid, date, date)
    TO service_role;

COMMIT;
