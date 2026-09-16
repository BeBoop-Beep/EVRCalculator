-- PROPOSAL ONLY -- DO NOT APPLY BEFORE THE APPLICATION-SIDE CANDIDATE
-- RECONCILIATION CHANGE IS DEPLOYED AND VERIFIED.
--
-- Purpose:
--   Preserve FINAL > CANDIDATE provenance for canonical Pokemon Market
--   Standard/Top-10 daily history. Candidate preparation is allowed to create
--   or refresh candidate-owned rows before Market Date Quality, but it must
--   never downgrade an already-finalized row for the same set/date/scope.
--
-- This proposal deliberately does NOT:
--   * change Market root membership;
--   * alter Market Date Quality;
--   * force-publish any date;
--   * enable Price Storage V2 serving gates;
--   * rewrite historical rows;
--   * drop any table/function;
--   * repair Sep-15 data by itself.

BEGIN;

CREATE OR REPLACE FUNCTION public.guard_canonical_rollout_root_set_value_history_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_new_is_final boolean := false;
    v_new_is_candidate boolean := false;
    v_new_is_canonical boolean := false;
    v_old_is_final boolean := false;
    v_old_is_candidate boolean := false;
    v_old_is_canonical boolean := false;
BEGIN
    IF new.value_scope NOT IN ('standard','top10') THEN
        RETURN new;
    END IF;

    v_new_is_final := coalesce(new.source,'') IN (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1',
        'price_storage_v2_transition_anchor_v1',
        'price_storage_v2_serving_compatibility_v1'
    );
    v_new_is_candidate := coalesce(new.source,'') IN (
        'canonical_root_set_public_rollout_candidate_v1',
        'canonical_root_top10_public_rollout_candidate_v1'
    );
    v_new_is_canonical := v_new_is_final OR v_new_is_candidate;

    IF TG_OP = 'UPDATE' THEN
        v_old_is_final := coalesce(old.source,'') IN (
            'canonical_root_set_public_rollout_v1',
            'canonical_root_top10_public_rollout_v1',
            'canonical_root_standard_backfill_v1',
            'canonical_root_top10_backfill_v1',
            'price_storage_v2_transition_anchor_v1',
            'price_storage_v2_serving_compatibility_v1'
        );
        v_old_is_candidate := coalesce(old.source,'') IN (
            'canonical_root_set_public_rollout_candidate_v1',
            'canonical_root_top10_public_rollout_candidate_v1'
        );
        v_old_is_canonical := v_old_is_final OR v_old_is_candidate;

        -- FINAL is one-way with respect to pre-gate candidate preparation.
        -- Returning NULL suppresses the attempted UPDATE and leaves the
        -- finalized row byte-for-byte intact. Candidate -> FINAL remains
        -- allowed, as do explicit FINAL -> FINAL repair/finalization paths.
        IF v_old_is_final AND v_new_is_candidate THEN
            RETURN NULL;
        END IF;

        -- Preserve the existing live protection: once an accepted canonical
        -- source owns a row, a generic/legacy writer cannot silently downgrade
        -- its provenance.
        IF v_old_is_canonical AND NOT v_new_is_canonical THEN
            RETURN NULL;
        END IF;
    END IF;

    IF v_new_is_canonical THEN
        RETURN new;
    END IF;

    -- Preserve the historical composite-root guard for noncanonical writers.
    IF EXISTS (
        SELECT 1
        FROM public.pokemon_market_public_rollout_root_sets_v1 r
        WHERE r.set_id = new.set_id
          AND r.activated_market_date <= new.snapshot_date
          AND (r.release_date IS NULL OR r.release_date <= new.snapshot_date)
          AND EXISTS (
              SELECT 1
              FROM public.sets child
              WHERE child.parent_opening_set_id = new.set_id
                AND child.counts_toward_parent_set_value = true
          )
    ) THEN
        RETURN NULL;
    END IF;

    RETURN new;
END;
$function$;

COMMENT ON FUNCTION public.guard_canonical_rollout_root_set_value_history_v1() IS
'Protects canonical Pokemon Market Standard/Top-10 history with FINAL > CANDIDATE > noncanonical source precedence. Candidate preparation may not downgrade a finalized row; candidate-to-final and explicit final repair paths remain allowed.';

COMMIT;
