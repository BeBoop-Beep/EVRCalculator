-- PROPOSAL ONLY -- DO NOT APPLY BEFORE THE APPLICATION-SIDE ZERO-WRITE
-- FINALIZED-DAY PROTECTION IS DEPLOYED AND VERIFIED.
--
-- Purpose:
--   Preserve FINAL > CANDIDATE provenance for canonical Pokemon Market
--   Standard/Top-10 daily history. Candidate preparation must never downgrade
--   an already-finalized row for the same set/date/scope.
--
-- This proposal deliberately does NOT:
--   * change Market root membership;
--   * alter Market Date Quality;
--   * force-publish any date;
--   * enable Price Storage V2 serving gates;
--   * rewrite historical rows;
--   * change existing behavior for noncanonical writers;
--   * repair Sep-15 data by itself.

BEGIN;

CREATE OR REPLACE FUNCTION public.guard_canonical_rollout_root_set_value_history_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_old_is_final boolean := false;
    v_new_is_candidate boolean := false;
BEGIN
    IF new.value_scope NOT IN ('standard','top10') THEN
        RETURN new;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        v_old_is_final := coalesce(old.source,'') IN (
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

        -- The only new behavior in this proposal: FINAL is one-way with
        -- respect to pre-gate candidate preparation. Returning NULL suppresses
        -- the attempted UPDATE and leaves the finalized row byte-for-byte intact.
        IF v_old_is_final AND v_new_is_candidate THEN
            RETURN NULL;
        END IF;
    END IF;

    -- Preserve the currently deployed allow-list behavior exactly for every
    -- other canonical source transition.
    IF coalesce(new.source,'') IN (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_set_public_rollout_candidate_v1',
        'canonical_root_top10_public_rollout_candidate_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1',
        'price_storage_v2_transition_anchor_v1',
        'price_storage_v2_serving_compatibility_v1'
    ) THEN
        RETURN new;
    END IF;

    -- Preserve the deployed composite-root guard unchanged for noncanonical
    -- writers.
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
'Preserves the existing canonical rollout guard while preventing FINAL Standard/Top-10 rows from being downgraded to candidate provenance.';

COMMIT;
