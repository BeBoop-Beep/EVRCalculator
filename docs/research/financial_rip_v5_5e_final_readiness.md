# Financial RIP V5 - Prompt 5E: final production readiness (stopped at Phase A)

## Status

`FINANCIAL_RIP_V5_FINAL_CUTOVER_BLOCKED`

Classification: **Rankings writer** (smallest blocker). Per the prompt, no later phase was started until the Rankings writer boundary is fixed and tested. Nothing was written to production in this bucket: no migration, no V5/V14 row, no snapshot, no pointer change. Production is still V12.

## Workspace

- Branch `develop`, HEAD == `origin/develop` == `ef5531b0` at start (verified after `git fetch`). Unrelated dirty files (pricing pipeline, eBay artifacts and migration, logs, supporter research) were left untouched.

## Current production authority (read-only, 2026-09-21)

| Item | Value |
|---|---|
| Release pointer (`pokemon_overall_rip_current_publication`, scope pokemon) | run `0f83d958-95aa-40f1-bcfa-ec550ec3a379`, activated 2026-09-12T00:21:46Z; rankings generation `723e7fb8-e671-45b6-9676-89ac3e7d58a2`; set-page generation `42139262-fea1-4168-89b7-2470c048e675` |
| That run | `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`, `published`, market_date 2026-09-10 (a V13 run 5a49238e is `superseded`) |
| Budget Ranking latest | `budget_product_ranking_v1` + `budget_allocation_floor_quantity_v1`, snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, market date 2026-09-14 (updated 2026-09-16) |
| Best-Open latest | `..._full_market_v1`, snapshot `aab485d9-cf94-489e-b05f-fec68c6f1905`, source date 2026-09-08 |
| `financial_rip_v5_*` columns on `simulation_sealed_product_results` | **0** (schema not landed) |
| RIP-statistics rankings snapshot (`scope=rip-statistics`) | updated 2026-09-18T05:02:57Z, meta stamps Overall V12 / Financial `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`; 34 set targets, **22** with `financialRipV4`/`overallRipV12` ready (== the 22 simulation runs), all 34 carry `setRipV1` |
| Migrations | none of the V5 / Ranking V2 / Best-Open V2 / Best-Open V3 migrations appear in production history (latest: `20260921172923 ebay_api_request_budget_v2`) |

Production has advanced since the 5C shadow (cohort 2026-09-15); the simulation/price authority date for a real build must be re-resolved when work resumes, not taken from this table.

## The blocker, precisely

`explore_rip_statistics_service` builds the Rankings snapshot's **set-level** targets itself: per set target it calls `_build_financial_rip_v4(target)` and `compute_overall_rip_v12(...)`, then stamps `ripWeightsConfig` from the static canonical constants (lines ~1247-1282, 1376, 2577-2591); `rankings_publication_lifecycle` selects on `canonical_overall_rip_target_key()` / `canonical_publication_identity()` (lines ~208, 357, 505, 518).

Making the writer release-driven is therefore **not only identity stamping**. A V14 snapshot needs a set-level `financialRipV5` and `overallRipV14` block per set target, and no code produces one:

- The sealed-product V5 finalizer and V14 candidate work per **sealed product**. The Rankings targets are per **set/run** (22 ready of 34).
- It has not been established that a set target's Financial V4 is exactly the V4 of that run's single-pack distribution / loose-pack row, and so it is not established that its V5 is the finalizer's V5 for the same distribution. That equivalence must be **proven against real data** (exact score parity for all 22 sets), not assumed, before the builder is given a V5 source.
- Guessing it would put a V5 number under a set label without proof, which is the mixed-authority failure this cutover exists to prevent.

## Smallest safe repair (next step)

1. Prove set-target Financial V4 == the run's single-pack finalizer path (read-only, 22/22 exact) and record the mapping (which artifact count / product row feeds the set target).
2. Add a release parameter to the builder: V12 path byte-for-byte unchanged (parity test against the current snapshot fixture); V14 path builds `financialRipV5` from the finalizer's exact evidence and `overallRipV14` via the existing V14 blend with Chase V1 (run-matched) and Collector V5; stamp `ripWeightsConfig` from the release bundle, never V14 values under V12-named fields.
3. Release-parameterize `rankings_publication_lifecycle` identity/target-key and add the mixed-authority rejections (V14+V4, V14+Ranking V1, V14+Contract V11, Ranking V2+V12, stale V12 snapshot under V14).
4. Only then proceed: migration chain rehearsal on disposable Postgres, additive schema landing, real V5 finalization, V14 candidate, Contract V12, Ranking V2, live Best-Open V3, serving/readiness/Sentinel and pointer-flip rehearsal.

## Not done in this bucket (by design, gated on the blocker)

Phases B-M: full-surface matrix, migration inventory/chain test, schema landing, real V5/V14/Contract V12/Ranking V2/Best-Open V3 builds, serving/browser rehearsal, readiness/Sentinel mutations, pointer flip/rollback rehearsal, regression counts, CI evidence for new code. No live evidence table can be filled; every gate below is **not evaluated**, not failed.

| Gate | Status |
|---|---|
| Rankings writer release-driven | **BLOCKED** (this report) |
| All other gates in the 5E table | not evaluated |
| V12 still canonical | yes (verified read-only above) |

## CI

Docs-only change; no workflow is path-triggered by it. CI for the last code commit `e7bf0978` remains green (Best-Open Price Guardrails 35631436175, Pattern Overlay 35631436237).
