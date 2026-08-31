BEGIN;

-- Runtime lifecycle contracts are parsed by test_set_lifecycle_migration_contract.
-- pokemon-runtime-lifecycle-contract: {"canonical_key":"generationsRadiantCollection","catalog_only":false,"ready_for_daily_scrape":true,"has_card_details_url":true,"supports_opening_simulation":false,"parent_opening_set_key":"generations","subset_type":"radiant_collection","counts_toward_parent_set_value":true,"counts_toward_parent_opening":true}
-- pokemon-runtime-lifecycle-contract: {"canonical_key":"legendaryTreasuresRadiantCollection","catalog_only":false,"ready_for_daily_scrape":true,"has_card_details_url":true,"supports_opening_simulation":false,"parent_opening_set_key":"legendaryTreasures","subset_type":"radiant_collection","counts_toward_parent_set_value":true,"counts_toward_parent_opening":true}

ALTER TABLE public.sets
    ADD COLUMN IF NOT EXISTS parent_opening_set_id UUID REFERENCES public.sets(id),
    ADD COLUMN IF NOT EXISTS subset_type TEXT,
    ADD COLUMN IF NOT EXISTS counts_toward_parent_set_value BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS counts_toward_parent_opening BOOLEAN NOT NULL DEFAULT FALSE;

WITH desired(canonical_key, parent_key) AS (
    VALUES
        ('generationsRadiantCollection', 'generations'),
        ('legendaryTreasuresRadiantCollection', 'legendaryTreasures')
)
UPDATE public.sets AS child
SET parent_opening_set_id = parent.id,
    subset_type = 'radiant_collection',
    counts_toward_parent_set_value = TRUE,
    counts_toward_parent_opening = TRUE,
    catalog_only = FALSE,
    ready_for_daily_scrape = TRUE,
    supports_opening_simulation = FALSE
FROM desired
JOIN public.sets AS parent ON parent.canonical_key = desired.parent_key
WHERE child.canonical_key = desired.canonical_key
  AND child.card_details_url IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.sets
        WHERE canonical_key IN (
            'generationsRadiantCollection',
            'legendaryTreasuresRadiantCollection'
        )
          AND (
              parent_opening_set_id IS NULL
              OR subset_type IS DISTINCT FROM 'radiant_collection'
              OR NOT counts_toward_parent_set_value
              OR NOT counts_toward_parent_opening
              OR catalog_only
              OR NOT ready_for_daily_scrape
              OR supports_opening_simulation
              OR card_details_url IS NULL
          )
    ) THEN
        RAISE EXCEPTION 'Radiant Collection lifecycle/subset normalization failed';
    END IF;
END;
$$;

COMMIT;
