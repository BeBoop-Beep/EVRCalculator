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

## Prompt 5E-A - Set-level Financial authority proof and Rankings writer repair

Status: `FINANCIAL_RIP_V5_SET_RANKINGS_WRITER_READY` for the **writer/builder**, with one live-data precondition that is NOT met yet (below). The historical blocker entry above is left as written; this section is its resolution evidence.

### What the existing set-level Financial V4 is

A Rankings set target's `financialRipV4` is re-projected from the `financial_rip_v3_payload` persisted on the set's calculation run (`simulation_derived_metrics`), built at simulation time as `build_financial_rip_v3(values, pack_cost)` over the run's per-pack outcome vector (`derived_metrics.compute_derived_metrics`). That vector is what `simulation_pack_outcome_artifacts` stores for the run, and the payload records the `packCost` it used. Set authority = `(run's pack-outcome artifact, payload.packCost)`. It is **not** a sealed-product row and not a product family: in several sets the loose-pack sealed product's V4 differs from the set's V4 (Journey Together 31.9723 vs 31.7427, Chaos Rising 32.7262 vs 32.2528, Stellar Crown 28.4835 vs 28.2371, Black Bolt 29.519 vs 29.446), so a "loose booster pack" mapping would have been wrong. Contract named in code: `set_financial_authority_v1` (`backend/db/services/set_financial_authority.py`).

### 22/22 lineage proof (read-only; `backend/scripts/audit_set_financial_authority.py`; data in `financial_rip_v5_set_authority_lineage.json`)

Classification: **A = 22, B = 0, C = 0, D = 0.** For every current set: the artifact belongs to the same run; outcome count, pack cost, mean, median, P05, P95 and P99 match the persisted run statistics (1e-6); the V3 payload recomputed from the vector reproduces the persisted score and all six components (max abs diff 0.0); the V4 control recomputed from the vector equals the persisted-V3 re-projection (diff 0.0). The proof can fail: unit tests show it detects a wrong run, the same set name with a wrong run, a wrong distribution, a changed quantity, a changed opening cost, an altered source statistic and an altered V4 component (`test_set_financial_authority.py`, 6 tests). Five artifact reads first hit a transient statement timeout (classified D by the audit) and were re-read with a bounded retry; they resolved to A.

### Code

- `set_financial_authority.py`: binds a run row to its artifact, verifies every persisted statistic, and scores Financial V5 through the canonical `score_row_v5` (which also asserts the V4 control reproduces the stored V4 before V5 is scored). V5 is recomputed from the exact vector, never derived from a V4 number.
- `set_rankings_v14.py`: per-target `financialRipV5` and `overallRipV14` (canonical `overall_rip_v14_for`: exact V5, run-matched Chase V1, exact Collector V5, no renormalization, no V4/V12 fallback). V14 lives only under its own keys.
- `explore_rip_statistics_service.get_rip_statistics_targets_payload(release=None, ...)`: `None` is the static V12 bundle, so every existing caller is unchanged. V14 adds the V5/V14 blocks, ranks them, attaches `publicRipContractV12`, uses `overallRipV14` for the Overall cohort audit, and stamps `ripWeightsConfig` (financial, overall, weights, public contract) from the release bundle.
- `rankings_publication_lifecycle.py`: `release` on readiness and parity (target key and identity). A snapshot that is not a coherent snapshot of the selected release returns `BLOCKED_RELEASE_AUTHORITY_MISMATCH`.
- `rankings_release_authority.py`: `snapshot_release_problems` and `observed_bundle_problems` reject V14+V4, V14+Ranking V1, V14+Contract V11, Ranking V2+Overall V12, V14+Best-Open V1/V2, V5 under a V4 identity, V14 under a V12 key, wrong-run V5 evidence, a stale other-generation snapshot, a cohort-fingerprint mismatch and an unknown release.
- The static audit now classifies the two builder files as release-driven; the known gap is empty.

### V12 preservation

The release-driven builder on the existing fixture with `release=None` and with the V12 bundle is identical, and it is identical to the pre-change module (the `ef5531b0` version of the file loaded side by side on the same fixture, times stripped): 2 targets, `identical: True`. All 53 pre-existing explore/lifecycle/compact tests pass unchanged. A live old-vs-new V12 comparison could not be run (see the view timeout below).

### Live V14 dry run (read-only) and the precondition that is not met

- **Financial V5: 22/22 ready**, each built from its own run's artifact (`runMatchesAuthority: true`).
- **Overall V14: 1/22 ready.** The other 21 are refused, correctly, by the run-match rule: the current Chase Accessibility rows (updated 2026-09-17, one per set) belong to the previous calculation runs, and production's set runs have advanced (newest run 2026-09-18 18:08Z); only 1 of the 22 Chase rows sits on a current run. Nothing fell back to V4/V12. Ranks over the ready set were contiguous and the assembled snapshot passed `snapshot_release_problems`. Data: `financial_rip_v5_set_targets_v14_dry_run.json`.
- Collector Appeal V5 inputs for this dry run were the values published in the current snapshot (`financial_rip_v5_collector_inputs_snapshot_2026-09-18.json`), because the live bundle build is retry-bound under DB contention; they are keyed by the snapshot's older runs, so this dry run is not a valid Collector check for the new runs either.
- The 22/22 Overall V14 gate is therefore **not demonstrated live**. It needs Chase Accessibility V1 (and Collector Appeal V5) republished for the current simulation runs. Overall V12 has the same run-match requirement, so this is a production freshness prerequisite, not a defect in this code, but it must be closed before the readiness phase.
- **Production read-path finding:** `explore_rip_statistics_latest` currently times out through the API role (about 9 s against the 8 s `authenticator` statement timeout) even for `select set_id`. The Rankings builder's own read of that view fails on production today (4/4 retries), which is consistent with the rankings snapshot last updating 2026-09-18. It is independent of this work but blocks the daily Rankings publisher and a full live builder run.

### Tests and CI

108 focused tests pass locally (release serving, static audit, set authority 6, set rankings V14 5, Rankings writer/release 24, lifecycle, explore service). Pre-existing local failures (public-snapshot `public_read_client` AttributeError, billing on Python 3.8, unrelated eBay/treatment suites) are unchanged baseline. CI on `e753f6f9`: Best-Open Price Guardrails **35661477218 success** (runtime, windows-lock, postgres-integration), Pattern Overlay Guardrails **35661477095 success**. The proof commit is `588a98b6`.

### Remaining 5E work (resume from Phase B; nothing below was started)

1. Republish Chase Accessibility V1 and Collector Appeal V5 for the current runs and resolve the `explore_rip_statistics_latest` timeout, so a full live V14 Rankings build (22/22 Overall V14) and the live V12 old/new parity run can be shown.
2. Phase B release-bundle re-audit, C migration inventory and disposable-Postgres chain test, D additive schema landing, E-M as specified. No migration, V5/V14 row, snapshot or pointer change was made in 5E-A; V12 remains canonical.
