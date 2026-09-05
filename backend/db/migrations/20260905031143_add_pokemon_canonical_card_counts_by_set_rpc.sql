-- Prompt 3: replace request-time full-corpus paging of pokemon_canonical_cards
-- (used only to compute per-set card counts for /TCGs/Pokemon/Sets) with a
-- single server-side aggregate. Read-only, additive, no destructive changes.
--
-- pokemon_canonical_cards already has idx_pokemon_canonical_cards_set_id
-- (migration 026), so this aggregate is a single index-backed GROUP BY scan
-- of only the rows for the requested sets, returning one row per set instead
-- of paging the entire canonical card corpus into the application.

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_counts_by_set(p_set_ids uuid[])
RETURNS TABLE (set_id uuid, card_count bigint)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT pcc.set_id, count(*)::bigint AS card_count
    FROM public.pokemon_canonical_cards pcc
    WHERE pcc.set_id = ANY(p_set_ids)
    GROUP BY pcc.set_id;
$$;

COMMENT ON FUNCTION public.get_pokemon_canonical_card_counts_by_set(uuid[]) IS
    'Returns one (set_id, card_count) row per requested set id, aggregated in SQL. '
    'Used by the Pokemon Sets catalog endpoint so per-set card counts scale with the '
    'number of sets requested, not with the size of the pokemon_canonical_cards corpus. '
    'Sets with zero canonical cards simply do not appear in the result and must be '
    'defaulted to 0 by the caller.';

REVOKE ALL ON FUNCTION public.get_pokemon_canonical_card_counts_by_set(uuid[]) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.get_pokemon_canonical_card_counts_by_set(uuid[]) TO service_role;
