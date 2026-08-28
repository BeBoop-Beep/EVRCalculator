-- Canonical exact-printing Chase Efficiency publication surface.
BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_card_chase_efficiency_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market_date DATE NOT NULL,
    built_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    publication_status TEXT NOT NULL CHECK (publication_status IN ('candidate','published','failed')),
    contract_version TEXT NOT NULL,
    calculation_methodology_version TEXT NOT NULL,
    pricing_basis_version TEXT NOT NULL,
    eligible_cohort_count INTEGER NOT NULL CHECK (eligible_cohort_count >= 0),
    excluded_cohort_count INTEGER NOT NULL CHECK (excluded_cohort_count >= 0),
    supported_set_count INTEGER NOT NULL CHECK (supported_set_count >= 0),
    cohort_fingerprint TEXT NOT NULL,
    source_run_fingerprint TEXT NOT NULL,
    diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (market_date, contract_version, calculation_methodology_version, pricing_basis_version)
);

CREATE TABLE IF NOT EXISTS public.pokemon_card_chase_efficiency_rows (
    snapshot_id UUID NOT NULL REFERENCES public.pokemon_card_chase_efficiency_snapshots(id) ON DELETE CASCADE,
    card_variant_id UUID NOT NULL REFERENCES public.card_variants(id),
    canonical_card_id UUID NOT NULL REFERENCES public.pokemon_canonical_cards(id),
    set_id UUID NOT NULL REFERENCES public.sets(id),
    era_id UUID REFERENCES public.eras(id),
    source_calculation_run_id UUID NOT NULL REFERENCES public.calculation_runs(id),
    card_name TEXT NOT NULL,
    canonical_rarity TEXT NOT NULL,
    printing_type TEXT,
    special_type TEXT,
    artwork TEXT,
    exact_pull_probability NUMERIC NOT NULL CHECK (exact_pull_probability > 0 AND exact_pull_probability <= 1),
    current_near_mint_market_price NUMERIC NOT NULL CHECK (current_near_mint_market_price > 0),
    card_price_as_of DATE NOT NULL,
    card_price_source TEXT,
    chase_efficiency NUMERIC NOT NULL CHECK (chase_efficiency > 0),
    best_verified_pack_equivalent_cost NUMERIC NOT NULL CHECK (best_verified_pack_equivalent_cost > 0),
    loose_booster_pack_price NUMERIC CHECK (loose_booster_pack_price > 0),
    chosen_sealed_product_id UUID NOT NULL REFERENCES public.sealed_products(id),
    chosen_product_family TEXT NOT NULL,
    chosen_product_name TEXT NOT NULL,
    chosen_product_price NUMERIC NOT NULL CHECK (chosen_product_price > 0),
    chosen_random_pack_count INTEGER NOT NULL CHECK (chosen_random_pack_count > 0),
    chosen_product_price_source TEXT,
    chosen_product_price_as_of DATE NOT NULL,
    milestones_json JSONB NOT NULL,
    verified_routes_json JSONB NOT NULL,
    overall_rank INTEGER NOT NULL CHECK (overall_rank > 0),
    overall_cohort_size INTEGER NOT NULL CHECK (overall_cohort_size > 0),
    era_rank INTEGER NOT NULL CHECK (era_rank > 0),
    era_cohort_size INTEGER NOT NULL CHECK (era_cohort_size > 0),
    set_rank INTEGER NOT NULL CHECK (set_rank > 0),
    set_cohort_size INTEGER NOT NULL CHECK (set_cohort_size > 0),
    rarity_rank INTEGER NOT NULL CHECK (rarity_rank > 0),
    rarity_cohort_size INTEGER NOT NULL CHECK (rarity_cohort_size > 0),
    PRIMARY KEY (snapshot_id, card_variant_id)
);

CREATE INDEX IF NOT EXISTS pokemon_card_chase_efficiency_rows_overall_idx
    ON public.pokemon_card_chase_efficiency_rows(snapshot_id, overall_rank);
CREATE INDEX IF NOT EXISTS pokemon_card_chase_efficiency_rows_set_idx
    ON public.pokemon_card_chase_efficiency_rows(snapshot_id, set_id, set_rank);
CREATE INDEX IF NOT EXISTS pokemon_card_chase_efficiency_rows_rarity_idx
    ON public.pokemon_card_chase_efficiency_rows(snapshot_id, canonical_rarity, rarity_rank);

CREATE TABLE IF NOT EXISTS public.pokemon_card_chase_efficiency_latest (
    contract_version TEXT NOT NULL,
    calculation_methodology_version TEXT NOT NULL,
    pricing_basis_version TEXT NOT NULL,
    snapshot_id UUID NOT NULL REFERENCES public.pokemon_card_chase_efficiency_snapshots(id),
    market_date DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (contract_version, calculation_methodology_version, pricing_basis_version)
);

ALTER TABLE public.pokemon_card_chase_efficiency_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_card_chase_efficiency_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pokemon_card_chase_efficiency_latest ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_card_chase_efficiency_snapshots FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.pokemon_card_chase_efficiency_rows FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.pokemon_card_chase_efficiency_latest FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_card_chase_efficiency_snapshots TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_card_chase_efficiency_rows TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_card_chase_efficiency_latest TO service_role;

CREATE OR REPLACE FUNCTION public.publish_pokemon_card_chase_efficiency_snapshot(p_snapshot JSONB, p_rows JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_id UUID; v_count INTEGER; v_distinct INTEGER;
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Chase Efficiency rows must be an array'; END IF;
    v_count := jsonb_array_length(p_rows);
    IF v_count = 0 OR v_count <> (p_snapshot->>'eligible_cohort_count')::INTEGER THEN
        RAISE EXCEPTION 'Chase Efficiency eligible row count mismatch';
    END IF;
    SELECT count(DISTINCT x->>'card_variant_id') INTO v_distinct FROM jsonb_array_elements(p_rows) x;
    IF v_distinct <> v_count THEN RAISE EXCEPTION 'duplicate Chase Efficiency card_variant_id'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rows) x WHERE
        (x->>'overall_rank')::INTEGER > (x->>'overall_cohort_size')::INTEGER OR
        (x->>'era_rank')::INTEGER > (x->>'era_cohort_size')::INTEGER OR
        (x->>'set_rank')::INTEGER > (x->>'set_cohort_size')::INTEGER OR
        (x->>'rarity_rank')::INTEGER > (x->>'rarity_cohort_size')::INTEGER)
    THEN RAISE EXCEPTION 'Chase Efficiency rank outside cohort'; END IF;

    INSERT INTO public.pokemon_card_chase_efficiency_snapshots (
        market_date,built_at,published_at,publication_status,contract_version,
        calculation_methodology_version,pricing_basis_version,eligible_cohort_count,
        excluded_cohort_count,supported_set_count,cohort_fingerprint,source_run_fingerprint,diagnostics_json
    ) VALUES (
        (p_snapshot->>'market_date')::DATE,(p_snapshot->>'built_at')::TIMESTAMPTZ,timezone('utc',now()),'published',
        p_snapshot->>'contract_version',p_snapshot->>'calculation_methodology_version',p_snapshot->>'pricing_basis_version',
        v_count,(p_snapshot->>'excluded_cohort_count')::INTEGER,(p_snapshot->>'supported_set_count')::INTEGER,
        p_snapshot->>'cohort_fingerprint',p_snapshot->>'source_run_fingerprint',coalesce(p_snapshot->'diagnostics_json','{}'::jsonb)
    ) ON CONFLICT (market_date,contract_version,calculation_methodology_version,pricing_basis_version) DO UPDATE SET
        built_at=excluded.built_at,published_at=timezone('utc',now()),publication_status='published',
        eligible_cohort_count=excluded.eligible_cohort_count,excluded_cohort_count=excluded.excluded_cohort_count,
        supported_set_count=excluded.supported_set_count,cohort_fingerprint=excluded.cohort_fingerprint,
        source_run_fingerprint=excluded.source_run_fingerprint,diagnostics_json=excluded.diagnostics_json
    RETURNING id INTO v_id;

    DELETE FROM public.pokemon_card_chase_efficiency_rows WHERE snapshot_id=v_id;
    INSERT INTO public.pokemon_card_chase_efficiency_rows (
        snapshot_id,card_variant_id,canonical_card_id,set_id,era_id,source_calculation_run_id,card_name,canonical_rarity,
        printing_type,special_type,artwork,exact_pull_probability,current_near_mint_market_price,card_price_as_of,card_price_source,
        chase_efficiency,best_verified_pack_equivalent_cost,loose_booster_pack_price,chosen_sealed_product_id,
        chosen_product_family,chosen_product_name,chosen_product_price,chosen_random_pack_count,chosen_product_price_source,
        chosen_product_price_as_of,milestones_json,verified_routes_json,overall_rank,overall_cohort_size,era_rank,era_cohort_size,
        set_rank,set_cohort_size,rarity_rank,rarity_cohort_size)
    SELECT v_id,(x->>'card_variant_id')::UUID,(x->>'canonical_card_id')::UUID,(x->>'set_id')::UUID,
        nullif(x->>'era_id','')::UUID,(x->>'source_calculation_run_id')::UUID,x->>'card_name',x->>'canonical_rarity',
        x->>'printing_type',x->>'special_type',x->>'artwork',(x->>'probability')::NUMERIC,
        (x->>'current_market_price')::NUMERIC,(x->>'card_price_as_of')::DATE,x->>'card_price_source',
        (x->>'chase_efficiency')::NUMERIC,(x->>'best_verified_pack_equivalent_cost')::NUMERIC,
        nullif(x->>'loose_booster_pack_price','')::NUMERIC,(x->>'chosen_sealed_product_id')::UUID,
        x->>'chosen_product_family',x->>'chosen_product_name',(x->>'chosen_product_price')::NUMERIC,
        (x->>'chosen_random_pack_count')::INTEGER,x->>'chosen_product_price_source',(x->>'chosen_product_price_as_of')::DATE,
        x->'milestones',x->'verified_routes',(x->>'overall_rank')::INTEGER,(x->>'overall_cohort_size')::INTEGER,
        (x->>'era_rank')::INTEGER,(x->>'era_cohort_size')::INTEGER,(x->>'set_rank')::INTEGER,(x->>'set_cohort_size')::INTEGER,
        (x->>'rarity_rank')::INTEGER,(x->>'rarity_cohort_size')::INTEGER FROM jsonb_array_elements(p_rows) x;
    IF (SELECT count(*) FROM public.pokemon_card_chase_efficiency_rows WHERE snapshot_id=v_id) <> v_count THEN
        RAISE EXCEPTION 'persisted Chase Efficiency count mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM public.pokemon_card_chase_efficiency_rows WHERE snapshot_id=v_id GROUP BY set_id
        HAVING min(set_rank)<>1 OR max(set_rank)<>count(*) OR count(DISTINCT set_rank)<>count(*) OR min(set_cohort_size)<>count(*) OR max(set_cohort_size)<>count(*))
    THEN RAISE EXCEPTION 'persisted Chase Efficiency set ranks invalid'; END IF;

    INSERT INTO public.pokemon_card_chase_efficiency_latest(contract_version,calculation_methodology_version,pricing_basis_version,snapshot_id,market_date)
    VALUES(p_snapshot->>'contract_version',p_snapshot->>'calculation_methodology_version',p_snapshot->>'pricing_basis_version',v_id,(p_snapshot->>'market_date')::DATE)
    ON CONFLICT(contract_version,calculation_methodology_version,pricing_basis_version) DO UPDATE SET
        snapshot_id=excluded.snapshot_id,market_date=excluded.market_date,updated_at=timezone('utc',now());
    RETURN v_id;
END; $$;
REVOKE ALL ON FUNCTION public.publish_pokemon_card_chase_efficiency_snapshot(JSONB,JSONB) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_pokemon_card_chase_efficiency_snapshot(JSONB,JSONB) TO service_role;
COMMIT;
