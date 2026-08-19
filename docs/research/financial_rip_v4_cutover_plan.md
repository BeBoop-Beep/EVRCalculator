# Financial RIP V4 / Overall RIP V10 cutover plan

Status at the time of writing: **code complete, migration ready, pre-promotion
tested — NOT promoted.** Canonical constants still resolve Financial RIP V3 and
Overall RIP V9, no migration has been applied, and nothing has been published.

## What is already true on the feature branch

- Financial RIP V4 and Overall RIP V10 are computed for every authoritative
  target, and are now **ranked on the same cohort, in the same pass, from the
  same authoritative `calculation_run_id`** as V3/V9.
- Each V4/V10 block carries `score`, `rank`, `tier`, `cohortSize`,
  `relativeScore`, `status`, `rankable` and its version identity.
- `publicRipContractV10` is attached beside `publicRipContractV9`, additively.
- Two migrations are authored and unapplied:
  - `072_update_public_rip_rpc_to_v10.sql`
  - `073_add_sealed_product_financial_rip_v4_and_overall_rip_v10.sql`
- Sealed-product `_to_row` persists V4/V10 into their own fields, leaving every
  V3/V9 field byte-identical.

## Order of operations for the eventual cutover

The migrations must be applied **before** the constants flip. The RPC asserts
the model identity, so flipping constants first would make every publication
fail closed; applying migrations first is harmless, because nothing writes V10
until the constants move.

1. Apply `073` (additive columns — no rewrite, no reader depends on it yet).
2. Apply `072` (RPC repointed to V10/V4; nothing builds a V10 payload yet, so
   this makes publication *impossible* until step 3 — that is intended and is
   the reason the two steps are ordered this way, not the reverse).
3. Flip the canonical constants (below) in ONE coordinated change.
4. Run a publication and confirm the V10 snapshot INSERTs as a new lineage
   beside the existing same-date V9 row.

## The exact constants that change in step 3

| File | Constant / function | From | To |
| --- | --- | --- | --- |
| `backend/desirability/scoring_config.py` | `CANONICAL_OVERALL_RIP_VERSION` | `OVERALL_RIP_V9_VERSION` | `OVERALL_RIP_V10_VERSION` |
| `backend/desirability/scoring_config.py` | `CANONICAL_FINANCIAL_RIP_VERSION` (`_CANONICAL_FINANCIAL_RIP_VERSION`) | V3 identity | `FINANCIAL_RIP_V4_VERSION` |
| `backend/desirability/scoring_config.py` | `canonical_public_rip_contract_version()` | imports `PUBLIC_RIP_CONTRACT_V9_VERSION` | imports `PUBLIC_RIP_CONTRACT_V10_VERSION` |
| `backend/calculations/evr/financial_rip_v3_config.py` | `CANONICAL_FINANCIAL_RIP_VERSION` | `FINANCIAL_RIP_V3_VERSION` | `FINANCIAL_RIP_V4_VERSION` |

`canonical_overall_rip_is_v9()` / `canonical_overall_rip_is_v10()` already exist
and will invert automatically; they are not edited.

Frontend: `frontend/components/explore/canonicalRipV7.mjs` reads
`publicRipContractV9`. Because the backend now emits **both** contracts, the
frontend can be repointed independently, before or after the backend flip,
without a coordinated deploy.

## What deliberately does NOT change

- The 90/10 split.
- Collector Appeal V5, in any respect. It is the same score object V9 consumes;
  in `explore_rip_statistics_service` one variable (`collector_appeal_score`)
  feeds both `compute_overall_rip_v9` and `compute_overall_rip_v10`, so the
  appeal input cannot silently diverge between the two models.
- V3/V9 history. Both migrations are forward-only; historical rows keep their
  identity strings and stay readable.
- The sealed-product unique key `(calculation_run_id, sealed_product_id)`.

## Rollback

- Constants: revert the coordinated change.
- `072`: re-apply `067`.
- `073`: `DROP COLUMN` the nine added columns (nothing reads them pre-cutover).
