BEGIN;

CREATE SCHEMA IF NOT EXISTS private;
CREATE TABLE private.pokemon_card_chase_efficiency_publication_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), snapshot_json JSONB NOT NULL,
    expected_row_count INTEGER NOT NULL CHECK (expected_row_count > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);
CREATE TABLE private.pokemon_card_chase_efficiency_publication_rows (
    publication_id UUID NOT NULL REFERENCES private.pokemon_card_chase_efficiency_publication_jobs(id) ON DELETE CASCADE,
    card_variant_id UUID NOT NULL, row_json JSONB NOT NULL,
    PRIMARY KEY (publication_id, card_variant_id)
);
REVOKE ALL ON private.pokemon_card_chase_efficiency_publication_jobs FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON private.pokemon_card_chase_efficiency_publication_rows FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.begin_pokemon_card_chase_efficiency_publication(p_snapshot JSONB)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, private AS $$
DECLARE v_id UUID; v_expected INTEGER;
BEGIN
    v_expected := (p_snapshot->>'eligible_cohort_count')::INTEGER;
    IF v_expected IS NULL OR v_expected <= 0 THEN RAISE EXCEPTION 'Chase Efficiency eligible row count invalid'; END IF;
    INSERT INTO private.pokemon_card_chase_efficiency_publication_jobs(snapshot_json,expected_row_count)
    VALUES(p_snapshot,v_expected) RETURNING id INTO v_id;
    RETURN v_id;
END; $$;

CREATE OR REPLACE FUNCTION public.append_pokemon_card_chase_efficiency_publication_rows(p_publication_id UUID,p_rows JSONB)
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, private SET statement_timeout = '1min' AS $$
DECLARE v_count INTEGER;
BEGIN
    IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' OR jsonb_array_length(p_rows)=0 THEN
        RAISE EXCEPTION 'Chase Efficiency staged rows must be a non-empty array';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM private.pokemon_card_chase_efficiency_publication_jobs WHERE id=p_publication_id) THEN
        RAISE EXCEPTION 'Chase Efficiency publication job missing';
    END IF;
    INSERT INTO private.pokemon_card_chase_efficiency_publication_rows(publication_id,card_variant_id,row_json)
    SELECT p_publication_id,(x->>'card_variant_id')::UUID,x FROM jsonb_array_elements(p_rows) x;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END; $$;

CREATE OR REPLACE FUNCTION public.finalize_pokemon_card_chase_efficiency_publication(p_publication_id UUID)
RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, private SET statement_timeout = '5min' AS $$
DECLARE p_snapshot JSONB; v_id UUID; v_count INTEGER; v_expected INTEGER;
BEGIN
    SELECT snapshot_json,expected_row_count INTO p_snapshot,v_expected
    FROM private.pokemon_card_chase_efficiency_publication_jobs WHERE id=p_publication_id FOR UPDATE;
    IF p_snapshot IS NULL THEN RAISE EXCEPTION 'Chase Efficiency publication job missing'; END IF;
    SELECT count(*) INTO v_count FROM private.pokemon_card_chase_efficiency_publication_rows WHERE publication_id=p_publication_id;
    IF v_count <> v_expected THEN RAISE EXCEPTION 'Chase Efficiency eligible row count mismatch'; END IF;
    IF EXISTS (SELECT 1 FROM private.pokemon_card_chase_efficiency_publication_rows WHERE publication_id=p_publication_id AND (
        (row_json->>'overall_rank')::INTEGER > (row_json->>'overall_cohort_size')::INTEGER OR
        (row_json->>'era_rank')::INTEGER > (row_json->>'era_cohort_size')::INTEGER OR
        (row_json->>'set_rank')::INTEGER > (row_json->>'set_cohort_size')::INTEGER OR
        (row_json->>'rarity_rank')::INTEGER > (row_json->>'rarity_cohort_size')::INTEGER))
    THEN RAISE EXCEPTION 'Chase Efficiency rank outside cohort'; END IF;

    INSERT INTO public.pokemon_card_chase_efficiency_snapshots (
        market_date,built_at,published_at,publication_status,contract_version,calculation_methodology_version,
        pricing_basis_version,eligible_cohort_count,excluded_cohort_count,supported_set_count,cohort_fingerprint,
        source_run_fingerprint,diagnostics_json)
    VALUES ((p_snapshot->>'market_date')::DATE,(p_snapshot->>'built_at')::TIMESTAMPTZ,timezone('utc',now()),'published',
        p_snapshot->>'contract_version',p_snapshot->>'calculation_methodology_version',p_snapshot->>'pricing_basis_version',
        v_count,(p_snapshot->>'excluded_cohort_count')::INTEGER,(p_snapshot->>'supported_set_count')::INTEGER,
        p_snapshot->>'cohort_fingerprint',p_snapshot->>'source_run_fingerprint',coalesce(p_snapshot->'diagnostics_json','{}'::jsonb))
    ON CONFLICT (market_date,contract_version,calculation_methodology_version,pricing_basis_version) DO UPDATE SET
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
        (x->>'rarity_rank')::INTEGER,(x->>'rarity_cohort_size')::INTEGER
    FROM (SELECT row_json x FROM private.pokemon_card_chase_efficiency_publication_rows WHERE publication_id=p_publication_id) staged;
    IF (SELECT count(*) FROM public.pokemon_card_chase_efficiency_rows WHERE snapshot_id=v_id) <> v_count THEN
        RAISE EXCEPTION 'persisted Chase Efficiency count mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM public.pokemon_card_chase_efficiency_rows WHERE snapshot_id=v_id GROUP BY set_id
        HAVING min(set_rank)<>1 OR max(set_rank)<>count(*) OR count(DISTINCT set_rank)<>count(*) OR
               min(set_cohort_size)<>count(*) OR max(set_cohort_size)<>count(*))
    THEN RAISE EXCEPTION 'persisted Chase Efficiency set ranks invalid'; END IF;
    INSERT INTO public.pokemon_card_chase_efficiency_latest(contract_version,calculation_methodology_version,pricing_basis_version,snapshot_id,market_date)
    VALUES(p_snapshot->>'contract_version',p_snapshot->>'calculation_methodology_version',p_snapshot->>'pricing_basis_version',v_id,(p_snapshot->>'market_date')::DATE)
    ON CONFLICT(contract_version,calculation_methodology_version,pricing_basis_version) DO UPDATE SET
        snapshot_id=excluded.snapshot_id,market_date=excluded.market_date,updated_at=timezone('utc',now());
    DELETE FROM private.pokemon_card_chase_efficiency_publication_jobs WHERE id=p_publication_id;
    RETURN v_id;
END; $$;

CREATE OR REPLACE FUNCTION public.abort_pokemon_card_chase_efficiency_publication(p_publication_id UUID)
RETURNS VOID LANGUAGE sql SECURITY DEFINER SET search_path = public, private AS $$
    DELETE FROM private.pokemon_card_chase_efficiency_publication_jobs WHERE id=p_publication_id;
$$;

REVOKE ALL ON FUNCTION public.begin_pokemon_card_chase_efficiency_publication(JSONB) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.append_pokemon_card_chase_efficiency_publication_rows(UUID,JSONB) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.finalize_pokemon_card_chase_efficiency_publication(UUID) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.abort_pokemon_card_chase_efficiency_publication(UUID) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.begin_pokemon_card_chase_efficiency_publication(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.append_pokemon_card_chase_efficiency_publication_rows(UUID,JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.finalize_pokemon_card_chase_efficiency_publication(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.abort_pokemon_card_chase_efficiency_publication(UUID) TO service_role;

COMMIT;
