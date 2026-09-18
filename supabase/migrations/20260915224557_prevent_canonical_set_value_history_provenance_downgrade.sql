BEGIN;

DO $guard$
BEGIN
  IF md5(pg_get_functiondef('public.guard_canonical_rollout_root_set_value_history_v1()'::regprocedure)) <> '829f38642188902b1a4f0a124ae1ae85' THEN
    RAISE EXCEPTION 'Concurrent change detected: canonical Set Value history guard changed; revalidate before migration';
  END IF;
END;
$guard$;

CREATE OR REPLACE FUNCTION public.guard_canonical_rollout_root_set_value_history_v1()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_new_is_canonical boolean;
    v_old_is_canonical boolean;
BEGIN
    IF new.value_scope NOT IN ('standard','top10') THEN
        RETURN new;
    END IF;

    v_new_is_canonical := coalesce(new.source,'') IN (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_set_public_rollout_candidate_v1',
        'canonical_root_top10_public_rollout_candidate_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1',
        'price_storage_v2_transition_anchor_v1',
        'price_storage_v2_serving_compatibility_v1'
    );

    v_old_is_canonical := TG_OP = 'UPDATE' AND coalesce(old.source,'') IN (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_set_public_rollout_candidate_v1',
        'canonical_root_top10_public_rollout_candidate_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1',
        'price_storage_v2_transition_anchor_v1',
        'price_storage_v2_serving_compatibility_v1'
    );

    -- Once an accepted canonical provenance owns a row, a generic/legacy writer
    -- cannot silently downgrade it. Canonical-to-canonical repairs and normal
    -- first inserts remain allowed.
    IF v_old_is_canonical AND NOT v_new_is_canonical THEN
        RETURN NULL;
    END IF;

    IF v_new_is_canonical THEN
        RETURN new;
    END IF;

    -- Retain the historical composite-root guard for noncanonical writes that
    -- predates the Sep-10 root-authority cutover.
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

COMMIT;
