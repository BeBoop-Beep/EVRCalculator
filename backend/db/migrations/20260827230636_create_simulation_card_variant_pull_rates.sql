-- Additive run-scoped exact variant pull publication.
CREATE TABLE IF NOT EXISTS public.simulation_card_variant_pull_rates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    calculation_run_id uuid NOT NULL REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    card_id uuid NOT NULL REFERENCES public.cards(id) ON DELETE CASCADE,
    card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE CASCADE,
    condition_id uuid NULL REFERENCES public.conditions(id) ON DELETE SET NULL,
    printing_type text NULL,
    special_type text NULL,
    pull_count bigint NOT NULL CHECK (pull_count >= 0),
    pack_presence_count bigint NOT NULL CHECK (pack_presence_count >= 0),
    simulation_count bigint NOT NULL CHECK (simulation_count > 0),
    modeled_probability double precision NULL CHECK (
        modeled_probability IS NULL OR (modeled_probability > 0 AND modeled_probability <= 1)
    ),
    effective_pull_rate double precision NULL CHECK (
        effective_pull_rate IS NULL OR effective_pull_rate >= 1
    ),
    price_used numeric NOT NULL CHECK (price_used >= 0),
    price_source text NULL,
    price_captured_at timestamptz NULL,
    model_source text NOT NULL,
    model_version text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('modeled', 'insufficient_observed_pulls')
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT simulation_card_variant_pull_rates_run_variant_key
        UNIQUE (calculation_run_id, card_variant_id),
    CONSTRAINT simulation_card_variant_pull_rates_presence_lte_copies
        CHECK (pack_presence_count <= pull_count),
    CONSTRAINT simulation_card_variant_pull_rates_presence_lte_simulations
        CHECK (pack_presence_count <= simulation_count),
    CONSTRAINT simulation_card_variant_pull_rates_probability_state
        CHECK (
            (status = 'modeled' AND pull_count > 0 AND pack_presence_count > 0
                AND modeled_probability IS NOT NULL AND effective_pull_rate IS NOT NULL)
            OR
            (status = 'insufficient_observed_pulls' AND pull_count = 0
                AND pack_presence_count = 0 AND modeled_probability IS NULL
                AND effective_pull_rate IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS simulation_card_variant_pull_rates_run_idx
    ON public.simulation_card_variant_pull_rates (calculation_run_id);
CREATE INDEX IF NOT EXISTS simulation_card_variant_pull_rates_variant_run_idx
    ON public.simulation_card_variant_pull_rates (card_variant_id, calculation_run_id);
CREATE INDEX IF NOT EXISTS simulation_card_variant_pull_rates_set_run_idx
    ON public.simulation_card_variant_pull_rates (set_id, calculation_run_id);

ALTER TABLE public.simulation_card_variant_pull_rates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.simulation_card_variant_pull_rates FROM anon, authenticated;
GRANT ALL ON TABLE public.simulation_card_variant_pull_rates TO service_role;

COMMENT ON TABLE public.simulation_card_variant_pull_rates IS
    'Run-scoped exact card-variant pack-presence frequencies observed by the authoritative V2 simulator. Additive to simulation_input_cards; never a historical reconstruction.';


