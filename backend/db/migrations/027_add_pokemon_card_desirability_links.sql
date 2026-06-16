-- Migration 027: add transparent canonical-card to Pokemon desirability links.
--
-- This table maps canonical Pokemon checklist cards to pokemon_reference rows.
-- It intentionally stores link metadata only, not the final desirability score.
-- Scores remain sourced from pokemon_desirability_scores and
-- pokemon_desirability_composite_scores.

CREATE TABLE IF NOT EXISTS public.pokemon_card_desirability_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pokemon_canonical_card_id UUID NOT NULL REFERENCES public.pokemon_canonical_cards(id) ON DELETE CASCADE,
    pokemon_reference_id BIGINT NOT NULL REFERENCES public.pokemon_reference(id) ON DELETE RESTRICT,
    pokedex_number INTEGER NOT NULL,
    link_position INTEGER NOT NULL,
    link_count INTEGER NOT NULL,
    contribution_weight NUMERIC NOT NULL,
    match_method TEXT NOT NULL,
    match_confidence NUMERIC NOT NULL,
    is_hit_eligible BOOLEAN NOT NULL DEFAULT false,
    hit_policy_version TEXT NOT NULL,
    excluded_reason TEXT,
    source TEXT NOT NULL DEFAULT 'pokemon_canonical_cards.national_pokedex_numbers',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT pokemon_card_desirability_links_card_reference_key UNIQUE (
        pokemon_canonical_card_id,
        pokemon_reference_id
    ),
    CONSTRAINT pokemon_card_desirability_links_card_position_key UNIQUE (
        pokemon_canonical_card_id,
        link_position
    ),
    CONSTRAINT pokemon_card_desirability_links_position_check CHECK (link_position >= 1),
    CONSTRAINT pokemon_card_desirability_links_count_check CHECK (link_count >= 1),
    CONSTRAINT pokemon_card_desirability_links_weight_check CHECK (
        contribution_weight >= 0
        AND contribution_weight <= 1
    ),
    CONSTRAINT pokemon_card_desirability_links_confidence_check CHECK (
        match_confidence >= 0
        AND match_confidence <= 1
    )
);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_card
    ON public.pokemon_card_desirability_links (pokemon_canonical_card_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_reference
    ON public.pokemon_card_desirability_links (pokemon_reference_id);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_pokedex
    ON public.pokemon_card_desirability_links (pokedex_number);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_hit_eligible
    ON public.pokemon_card_desirability_links (is_hit_eligible);

CREATE INDEX IF NOT EXISTS idx_pokemon_card_desirability_links_policy_hit
    ON public.pokemon_card_desirability_links (hit_policy_version, is_hit_eligible);

ALTER TABLE public.pokemon_card_desirability_links ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'pokemon_card_desirability_links'
          AND policyname = 'pokemon_card_desirability_links_read_policy'
    ) THEN
        CREATE POLICY pokemon_card_desirability_links_read_policy
            ON public.pokemon_card_desirability_links
            FOR SELECT
            USING (true);
    END IF;
END $$;
