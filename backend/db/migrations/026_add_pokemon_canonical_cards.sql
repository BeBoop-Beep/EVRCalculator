-- Migration 026: add canonical Pokemon checklist cards.
--
-- This table is an additive checklist layer sourced from the Pokemon TCG API.
-- It does not replace or repurpose public.cards, public.card_variants, or any
-- pricing observation tables.

CREATE TABLE IF NOT EXISTS public.pokemon_canonical_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id UUID NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    pokemon_tcg_api_card_id TEXT NOT NULL,
    name TEXT NOT NULL,
    supertype TEXT,
    subtypes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    rarity TEXT,
    number TEXT,
    printed_number TEXT,
    artist TEXT,
    pokemon_tcg_api_set_id TEXT,
    national_pokedex_numbers INTEGER[] NOT NULL DEFAULT ARRAY[]::INTEGER[],
    image_small_url TEXT,
    image_large_url TEXT,
    source TEXT NOT NULL DEFAULT 'pokemon_tcg_api',
    source_payload JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_canonical_cards_api_card_id_key UNIQUE (pokemon_tcg_api_card_id),
    CONSTRAINT pokemon_canonical_cards_set_number_name_key UNIQUE (set_id, number, name)
);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_cards_set_id
    ON public.pokemon_canonical_cards (set_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_cards_name
    ON public.pokemon_canonical_cards (name);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_cards_rarity
    ON public.pokemon_canonical_cards (rarity);

CREATE INDEX IF NOT EXISTS idx_pokemon_canonical_cards_pokedex_numbers
    ON public.pokemon_canonical_cards USING GIN (national_pokedex_numbers);

ALTER TABLE public.pokemon_canonical_cards ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_canonical_cards'
          AND policyname = 'pokemon_canonical_cards_read_policy'
    ) THEN
        CREATE POLICY pokemon_canonical_cards_read_policy
            ON public.pokemon_canonical_cards
            FOR SELECT
            USING (true);
    END IF;
END $$;
