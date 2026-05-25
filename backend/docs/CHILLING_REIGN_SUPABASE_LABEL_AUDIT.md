# Chilling Reign Supabase Label Audit (Project 5.5.2)

## Scope
Read-only audit of Supabase/local card data for Chilling Reign (`swsh6`) to determine how rare-slot outcomes are represented in persisted card and variant rows.

Constraints preserved:
- No `RARE_SLOT_PROBABILITY` was added.
- `SLOT_SCHEMA_RUNTIME_ENABLED` remains `False`.
- No simulator routing/refactor behavior was changed.

## Authoritative Set Resolution
- Target set id: `swsh6`
- Target set name: `Chilling Reign`
- Resolved Supabase set row id: `1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890`

## Tables / Views Audited
- `cards`
- `card_variants`
- `card_variant_price_observations`
- `card_market_usd_latest_by_condition`
- `simulation_input_cards`
- `simulation_input_cards_with_near_mint_price`

Schema metadata source: Supabase PostgREST OpenAPI document (`/rest/v1/`, `Accept: application/openapi+json`).

## Row Coverage (swsh6)
- Cards: `233`
- Card variants: `369`
- Latest market rows for set variants: `1361`
- Price observation rows fetched for set variants (sampled by chunk): `2000`

## Card-Level Values (Exact Observed)
### Rarity counts
- `Common`: 43
- `Uncommon`: 46
- `Rare`: 23
- `Holo Rare`: 24
- `Ultra Rare`: 62
- `Secret Rare`: 35

### Other card-level findings
- `supertype` is not present on `cards` rows for this set.
- `subtypes` is not present on `cards` rows for this set.
- `set_name` is not present on `cards` rows for this set.
- All cards have `card_number` populated.

Observed `cards` row fields:
- `card_number`, `created_at`, `id`, `image_large_url`, `image_last_synced_at`, `image_small_url`, `name`, `pokemon_tcg_api_id`, `rarity`, `set_id`

## Variant-Level Values (Exact Observed)
### Variant shape
- `printing_type` counts:
  - `non-holo`: 112
  - `reverse-holo`: 136
  - `holo`: 121
- `special_type`: always `NULL` for this set (`369` rows)
- `edition`: always `NULL` for this set (`369` rows)

Observed `card_variants` row fields:
- `card_id`, `created_at`, `edition`, `id`, `image_large_url`, `image_last_synced_at`, `image_small_url`, `pokemon_tcg_api_id`, `printing_type`, `special_type`

### Reverse representation
- Reverse variants are represented via `printing_type = reverse-holo`.
- Reverse count: `136`.

### Condition / source / currency representation (latest view)
From `card_market_usd_latest_by_condition` rows linked to Chilling Reign variants:
- Conditions observed:
  - `Near Mint`: 369
  - `Lightly Played`: 369
  - `Moderately Played`: 342
  - `Heavily Played`: 131
  - `Damaged`: 150
- Currency observed: `USD`
- Source observed: `TCGPlayer`

## Rare-Slot Family Candidate Labels Found
Derived from persisted rarity/name/printing data:
- `regular rare`: 46
- `holo rare`: 48
- `regular vmax`: 8
- `full art v`: 31
- `alternate art v`: 10
- `alternate art vmax`: 3
- `gold/secret rare`: 35

Not observed as explicit structured labels in DB fields:
- `full art trainer`
- `rainbow trainer`
- `rainbow vmax`

## Config Bucket Comparison
Configured normalized buckets:
- `full art v`
- `full art trainer`
- `alternate art v`
- `alternate art vmax`
- `rainbow trainer`
- `rainbow vmax`
- `gold secret rare`

Matching status against current DB/card-pool labels:
- Matched: `full art v`, `alternate art v`, `alternate art vmax`, `gold secret rare`
- Unmatched: `full art trainer`, `rainbow trainer`, `rainbow vmax`

Conclusion:
- `requires_outcome_pool_mapping = true`
- A config-controlled outcome-to-pool mapping is required before introducing `RARE_SLOT_PROBABILITY` for Chilling Reign.

## Extractor Audit (Current Pipeline)
`PackEVRSimulator` still uses `extract_scarletandviolet_card_groups(...)`.

Current behavior notes:
- Despite SV-oriented naming, extraction logic is generic over normalized rarity keys and reverse eligibility.
- For Chilling Reign data, grouping can separate base rarity and reverse pools.
- It cannot reliably distinguish trainer/rainbow/alt families when DB rows lack structured variant fields (`special_type`/`subtypes` are null), so explicit mapping is required for rare-slot outcomes.

## Artifacts
- Script: `backend/scripts/audit_chilling_reign_supabase_labels.py`
- Full JSON output (ignored path): `logs/audits/chilling_reign_supabase_label_audit_swsh6.json`
- Compact in-config summary: `SetChillingReignConfig.CHILLING_REIGN_DB_LABEL_AUDIT`
