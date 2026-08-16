-- Migration 066: Stage 2 sealed-product COMPOSITION model.
--
-- WHY A TABLE AND NOT ANOTHER FAMILY MAP
-- --------------------------------------
-- Stage 1 could resolve composition from the classified FAMILY, because every
-- member of a Stage 1 family opens identically: every booster box is 36 packs of
-- the same set and nothing else. Stage 2 families are not like that. Live
-- inventory for a single set contains, for example:
--
--     "Paradox Rift Elite Trainer Box [Iron Valiant]"
--     "Paradox Rift Elite Trainer Box [Roaring Moon]"
--     "Paradox Rift Elite Trainer Box Case"
--     "Paradox Rift Elite Trainer Boxes [Set of 2]"
--     "Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Iron Valiant]"
--
-- Those share a family and a pack count while guaranteeing DIFFERENT promo
-- cards worth different amounts - and two of them are not single retail openings
-- at all. A family-keyed map cannot express that without lying about at least
-- one row, so Stage 2 composition is keyed on `sealed_product_id`. Eligibility
-- is therefore a property of DATA, not of a name: a SKU with no active verified
-- composition row is simply not Stage 2 scorable, and no substring rule can make
-- it one.
--
-- WHAT IS MODELED
-- ---------------
-- Only what a Stage 2 opening produces value from:
--
--   * booster pack components  (how many packs, from which set)
--   * guaranteed card components (which exact printing, how many)
--
-- Deliberately NOT modeled: sleeves, dice, energy, dividers, the storage box,
-- the player's guide, code cards, coins. Stage 2 opening value is CARD VALUE
-- ONLY and every result row records `accessory_value_included = false` so that
-- limitation is disclosed rather than inferred.
--
-- PACK COMPONENTS ARE A CHILD TABLE, NOT A COLUMN
-- -----------------------------------------------
-- Every Stage 2 product has exactly ONE pack-component row (all packs come from
-- the product's own set). A `pack_count` column on the header would model that
-- just as well TODAY and would be smaller. It is a child table anyway because
-- Stage 3 mixed-set products - where one SKU carries packs from two or more sets
-- - are a known, named next stage, and they need N rows per composition. Adding
-- the table now costs one join; adding it later costs a schema migration plus a
-- rewrite of every reader written against the column.
--
-- GUARANTEED CARD IDENTITY: WHY `card_variant_id` IS THE AUTHORITY
-- ----------------------------------------------------------------
-- The obvious modeling choice is `canonical_card_id` with an optional variant.
-- The data does not support it. Every Stage 2 guaranteed promo in the supported
-- cohort belongs to the SV Black Star Promo catalog, and:
--
--   * `pokemon_canonical_cards` holds ZERO rows for that catalog (it has no
--     unique Pokemon TCG API set match, which is why its config sets
--     SET_ID = None), so there is no canonical id to point at; and
--   * `pokemon_canonical_cards` has no way to express a Pokemon Center-stamped
--     printing at all, while the legacy catalog DOES carry it as a distinct
--     product ("Koraidon - 014" vs "Koraidon - 014 (Pokemon Center Exclusive)").
--
-- Since Stage 2 must distinguish the ordinary promo from the stamped promo -
-- they are different cards with different prices, and a PC ETB guarantees BOTH -
-- the identity that can actually express the difference is the one that must be
-- authoritative. `card_variant_id` is NOT NULL. `canonical_card_id` is nullable
-- and purely informational, populated only where a canonical row genuinely
-- exists, so the model stays honest today and needs no migration if the
-- canonical checklist is ever extended to cover promos.
--
-- PROVENANCE IS NOT OPTIONAL
-- --------------------------
-- `source_type`, `source_reference` and `verified_at` are NOT NULL on the header
-- because a composition asserts what is physically inside a sealed box, and an
-- unsourced assertion of that is a guess wearing a schema. `status` gates
-- scoring: only 'verified' compositions are eligible, so a researched-but-
-- unconfirmed row can be recorded without ever being scored.
--
-- ACCESS
-- ------
-- Backend-private, following the pattern established by migration 065: RLS on,
-- no anon/authenticated grants, service_role only. These are internal research
-- records, not a published contract.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process.

BEGIN;

-- ---------------------------------------------------------------------------
-- Header
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.sealed_product_compositions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sealed_product_id UUID NOT NULL REFERENCES public.sealed_products(id) ON DELETE CASCADE,

    -- Bumped when the ASSERTED CONTENTS change, never for a price refresh.
    -- Result rows record the version they scored so a historical score can be
    -- attributed to the composition that produced it.
    composition_version TEXT NOT NULL,

    -- Only 'verified' is scorable. The others exist so research in progress can
    -- be recorded honestly instead of being held outside the database.
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'verified', 'superseded', 'rejected')),

    source_type TEXT NOT NULL
        CHECK (source_type IN (
            'pokemon_com_product_page',
            'pokemon_center_product_page',
            'pokemon_support',
            'product_catalog',
            'archival_reference'
        )),
    source_reference TEXT NOT NULL,
    verified_at DATE NOT NULL,
    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Idempotency key for composition ingestion: re-running the seeder with the
    -- same SKU and version updates the row rather than adding a second truth.
    CONSTRAINT sealed_product_compositions_sku_version_key
        UNIQUE (sealed_product_id, composition_version)
);

COMMENT ON TABLE public.sealed_product_compositions IS
'Stage 2 sealed-product composition headers. Keyed on sealed_product_id because SKUs sharing a family and pack count can guarantee different promos. Only status = verified is scorable.';

-- Partial unique index, not a constraint: exactly ONE verified composition may
-- exist per SKU at a time. Without this, superseding a composition by inserting
-- a new version could leave two verified rows and make "the" composition of a
-- product ambiguous at scoring time - which the resolver would have to break by
-- some arbitrary tiebreak.
CREATE UNIQUE INDEX IF NOT EXISTS sealed_product_compositions_one_verified_per_sku
    ON public.sealed_product_compositions (sealed_product_id)
    WHERE status = 'verified';

-- ---------------------------------------------------------------------------
-- Pack components
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.sealed_product_composition_pack_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_id UUID NOT NULL
        REFERENCES public.sealed_product_compositions(id) ON DELETE CASCADE,

    -- The set the packs are FROM. For every Stage 2 product this equals the
    -- parent product's set; it is stored explicitly rather than implied so a
    -- Stage 3 mixed-set product needs new ROWS, not a new schema.
    set_id UUID NOT NULL REFERENCES public.sets(id),
    pack_count INTEGER NOT NULL CHECK (pack_count > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One row per (composition, set). A product with packs from two sets gets
    -- two rows; a product with "9 packs and also 2 more packs" of one set is a
    -- data-entry error, not a real product.
    CONSTRAINT sealed_product_composition_pack_components_unique
        UNIQUE (composition_id, set_id)
);

COMMENT ON TABLE public.sealed_product_composition_pack_components IS
'Booster packs a composition contains, by source set. A child table rather than a column so Stage 3 mixed-set products need rows, not a migration.';

CREATE INDEX IF NOT EXISTS sealed_product_composition_pack_components_composition_idx
    ON public.sealed_product_composition_pack_components (composition_id);

-- ---------------------------------------------------------------------------
-- Guaranteed card components
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.sealed_product_composition_card_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_id UUID NOT NULL
        REFERENCES public.sealed_product_compositions(id) ON DELETE CASCADE,

    -- THE identity. See the header note: this is the only column in the
    -- database that can distinguish an ordinary promo from its Pokemon Center-
    -- stamped counterpart, and Stage 2 must distinguish them.
    card_variant_id UUID NOT NULL REFERENCES public.card_variants(id),

    -- Informational only, and nullable because the canonical checklist does not
    -- currently cover promo catalogs. Never used to resolve a price.
    canonical_card_id UUID REFERENCES public.pokemon_canonical_cards(id),

    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),

    -- What this card IS in the product, e.g. 'standard_etb_promo',
    -- 'pokemon_center_standard_promo', 'pokemon_center_stamped_promo',
    -- 'enhanced_display_promo'. Free text on purpose: a CHECK list would have to
    -- be migrated every time a new product pattern is researched, and the role
    -- is descriptive - nothing branches on it during scoring.
    component_role TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The same printing cannot be listed twice in one composition; a product
    -- that guarantees two copies uses quantity = 2. This is what makes
    -- "no duplicate promo components" a database property rather than a hope.
    CONSTRAINT sealed_product_composition_card_components_unique
        UNIQUE (composition_id, card_variant_id)
);

COMMENT ON TABLE public.sealed_product_composition_card_components IS
'Guaranteed card components. card_variant_id is authoritative because it is the only identity that distinguishes a Pokemon Center-stamped printing from the ordinary one; canonical_card_id is informational and often absent for promo catalogs.';

CREATE INDEX IF NOT EXISTS sealed_product_composition_card_components_composition_idx
    ON public.sealed_product_composition_card_components (composition_id);

-- ---------------------------------------------------------------------------
-- Result-row additions
-- ---------------------------------------------------------------------------
-- Additive to the EXISTING Stage 1 result table rather than a second results
-- table: a Stage 2 row is still one sealed product's opening scored against one
-- calculation run, and splitting it would duplicate the finalizer, the readers
-- and the cohort logic to store the same shape twice.
--
-- These columns do NOT restate the composition - the composition tables remain
-- authoritative for what is in the box. They record what was SCORED: enough to
-- prove which composition produced this row and to audit the split between
-- random pack value and guaranteed value without re-running anything. Stage 1
-- rows leave them NULL except `accessory_value_included`, which is meaningful
-- for every row.

ALTER TABLE public.simulation_sealed_product_results
    ADD COLUMN IF NOT EXISTS composition_id UUID
        REFERENCES public.sealed_product_compositions(id),
    ADD COLUMN IF NOT EXISTS random_pack_count INTEGER,
    ADD COLUMN IF NOT EXISTS random_pack_expected_value NUMERIC,
    ADD COLUMN IF NOT EXISTS guaranteed_component_count INTEGER,
    ADD COLUMN IF NOT EXISTS guaranteed_component_market_value NUMERIC,
    ADD COLUMN IF NOT EXISTS guaranteed_value_share_of_expected_value NUMERIC,
    ADD COLUMN IF NOT EXISTS accessory_value_included BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.simulation_sealed_product_results.random_pack_expected_value IS
'Mean of the K-pack random component alone, BEFORE guaranteed card value. Kept separate so promo value is never conflated with pack EV.';

COMMENT ON COLUMN public.simulation_sealed_product_results.accessory_value_included IS
'Always false. Stage 2 models collectible card value only; sleeves, dice, energy, dividers, the storage box, the player guide and code cards carry no modeled value.';

-- ---------------------------------------------------------------------------
-- Access: backend-private, per migration 065
-- ---------------------------------------------------------------------------

ALTER TABLE public.sealed_product_compositions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sealed_product_composition_pack_components ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sealed_product_composition_card_components ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sealed_product_compositions FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.sealed_product_composition_pack_components FROM anon, authenticated, PUBLIC;
REVOKE ALL ON public.sealed_product_composition_card_components FROM anon, authenticated, PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.sealed_product_compositions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sealed_product_composition_pack_components TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sealed_product_composition_card_components TO service_role;

COMMIT;
