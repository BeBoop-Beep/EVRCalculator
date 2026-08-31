# Overall RIP V11 — 83/11/6 Implementation Record

**Status: PARTIAL — scoring core implemented and research-verified; canonical cutover NOT performed.**

> This task implements the model in code and schema. It does **not** publish or
> deploy anything to production. No migration was applied, no snapshot was
> published, no canonical constant was flipped, and no commit was created.

---

## 1. Research lineage

| Stage | Artifact | Contribution |
|---|---|---|
| V-A | `PRODUCT_CHASE_ECONOMICS_STAGE5A.md` | 3x Core multiple; percentile guardrail measured inert in **0 of 21 sets** and **removed** |
| V-B | `PRODUCT_CHASE_ECONOMICS_STAGE5B.md` | the cost denominator: the product's own market cost / its own random pack count |
| V-C | `PRODUCT_CHASE_ECONOMICS_STAGE5C.md`, `product_chase_stage5c.json` | the coupled tier contract; 131 products, 21 sets, 0 unsupported |
| VI | `CHASE_PILLAR_STAGE6.md`, `chase_pillar_stage6_dataset.json` | Core K selected as the Chase construct |
| VI-A | `CHASE_WEIGHT_STAGE6A.md` | weight neighbourhood (its C1–C5 verdicts later shown to describe Candidate B) |
| VI-B | `CHASE_WEIGHT_STAGE6B.md` | `CHASE_WEIGHT_84_10_06_VALIDATED`; transform fixed at the **100** scale |
| VII | `COLLECTOR_WEIGHT_STAGE7.md` | `COLLECTOR_WEIGHT_11_VALIDATED__PRODUCT_LEVEL_SIGNAL_STRUCTURALLY_ABSENT` |

### Correction to the implementation brief

The brief stated the Core floor was built around `max(5C, V95)`. **It is not, and
never was.** Traced to source (`backend/research/product_chase_economics/contract.py`
and Stage V-A §"Percentile guardrail"):

* the Core floor is **`3 × C_product`**, with `C_product = product_market_cost / random_pack_count`;
* **5x was explicitly rejected** — it empties the Core on 9 of 131 real products and reduces 35 to a single card;
* **there is no percentile term**. Stage IV's cap was measured binding in 0/21 sets at every defensible width and deliberately removed.

The brief's own instruction — *"DO NOT TRUST THIS PROMPT OVER THE SOURCE"* — was
followed. The implementation uses 3x, no percentile.

---

## 2. Locked formula

```
Overall RIP V11 = 0.83 · F_V4 + 0.11 · C_V5 + 0.06 · Q
Q               = 100 · K / (K + 10)          NO CLAMP
K               = Stage V-C Core chase count  (Extended K is NOT part of Overall RIP)
```

## 3. Version identities

| Pillar | Identity |
|---|---|
| Overall V11 | `overall_rip_v11_83_financial_v4_11_collector_appeal_v5_06_chase_opportunity_v1` |
| Chase Opportunity | `chase_opportunity_v1_core_k_saturating_100_k10` |
| Core K | `chase_core_k_v1_stage5c_3x_pack_equivalent_cost` |
| Financial (unchanged) | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` |
| Collector (unchanged) | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2` |

A repo-wide search confirmed **no pre-existing `OVERALL_RIP_V11_VERSION`** before this work.

## 4. V10 preservation

`OVERALL_RIP_V10_VERSION`, `OVERALL_RIP_V10_WEIGHTS`, `OVERALL_RIP_V10_EFFECTIVE_WEIGHTS`
and `compute_overall_rip_v10` are **untouched**. V11 was added as new constants and a
new function alongside them. `CANONICAL_OVERALL_RIP_VERSION` **still resolves to V10.**
Asserted by four dedicated tests.

## 5. Production Chase authority

Promoted out of `backend/research/` into production modules that import nothing from research:

* `backend/desirability/chase_core_k.py` — the Stage V-C contract, 3x floor, cost basis, missing-is-not-zero
* `backend/desirability/chase_opportunity.py` — the `100K/(K+10)` transform and payload
* `backend/desirability/weighted_rip.py::compute_overall_rip_v11`
* `backend/desirability/scoring_config.py` — V11 weights, tolerance assertion, required input identities

## 6. Research parity (Phases 4 + 22)

`python -m backend.scripts.validate_overall_rip_v11_parity`

```
cohort                     : 131 products, 21 sets
pack-equivalent cost mism. : 0   worst 0.000e+00
Core K mismatches          : 0
Chase Opportunity mismatch : 0   worst 0.000e+00
Overall V11 mismatches     : 0   worst 4.971e-05   (4-dp public rounding)
Spearman (prod vs research): 1.000000
pairwise disagreements     : 0
PARITY: PASS
```

## 7. Guardrail reproduction (Phase 23)

`python -m backend.scripts.validate_overall_rip_v11_guardrails` — production weights and
production transform, measured with the unchanged Stage VI-A instrument.

| gate | observed | verdict |
|---|---|---|
| C1 clear overrides == 0, max gap < 10 (base + 4 × ±10% shocks) | 0 / **7.34** | PASS |
| C2 close-pair override rate ≥ 0.10 | 0.13375 | PASS |
| C3 Financial > 0.80, Chase < 0.20 | 0.9230 / **0.0754** | PASS |
| C4 Spearman ≥ 0.98, Top-5 turnover ≤ 1 | 0.9918 / 1 | PASS |
| C5 same-set reversals > 0 | **6** | PASS |
| same-set winner changes | **0** | as published |

**Flags `YYYYY`.** Chase share (0.0754), max gap (7.34), same-set reversals (6), clear
overrides (0) and winner changes (0) match Stage VII §8 to the published digit.

**Two residual deltas, recorded rather than smoothed over:** close-override rate
0.13375 vs the published 0.1293, and Spearman 0.9918 vs 0.9927. Both gates pass with
margin either way, but the difference is unexplained and is likely a CONTROL-definition
difference between the Stage VII sweep and the V10 CONTROL used here. **It should be
reconciled before cutover.**

## 8. Coverage (Phase 6) — the 131 vs 137 discrepancy, resolved

| | count |
|---|---|
| Supported opening sets (`supported_opening_set_keys()`) | **22** |
| Distinct V10-rankable SKUs, all history | **138** |
| Stage V-C/VI/VII research cohort | **131**, 21 sets |
| Difference | **Destined Rivals, 7 SKUs, 1 set** |

Verified against production (read-only SELECTs): 138 = 131 + Destined Rivals (7). The
set has a config, resolves cleanly, and had an equally-fresh V10-rankable run in the
same 2026-08-27 batch as all 21 research sets.

Root cause, confirmed by executing the cohort resolver directly:

```
2026-08-31  current = 20 of 22
  destinedRivals  stale  latest simulation 2026-08-29, behind promoted market date 2026-08-31
  journeyTogether stale  latest simulation 2026-08-28, behind promoted market date 2026-08-31
```

`resolve_research_cohort` admits only sets whose opening simulation is `current`.
Destined Rivals was stale at the 2026-08-28 research date, which is exactly why the
cohort is 21 sets / 131 products.

**This is benign, version-agnostic simulation-freshness filtering, not missing Chase
coverage.** The exclusion is upstream of every pillar and applies identically to V10 and
V11; Destined Rivals will acquire Core K on its next refresh exactly as it acquires
Financial V4 and Collector V5. It is therefore **not** a
`OVERALL_RIP_V11_BLOCKED_CHASE_COVERAGE_REGRESSION`. The 138 figure counts historical
rows across all time, not one coherent cohort.

The per-product coverage table required by Phase 6 has **not** been produced, because it
depends on the persistence and pipeline work listed as outstanding in §11.

## 9. Schema

`backend/db/migrations/074_add_sealed_product_chase_opportunity_and_overall_rip_v11.sql`
— next free number after 073; strictly additive, all columns NULLABLE with no DEFAULT.

Adds to `simulation_sealed_product_results`: `chase_opportunity_score`,
`chase_opportunity_version`, `chase_opportunity_status`, `chase_opportunity_core_k`,
`chase_opportunity_diagnostics`, `overall_rip_v11_score`, `overall_rip_v11_version`,
`overall_rip_v11_rankable`, `overall_rip_v11_payload`,
`overall_rip_v11_collector_appeal_version`, `overall_rip_v11_chase_opportunity_version`.

Two `NOT VALID` CHECK constraints enforce missing-is-not-zero (score and K arrive
together) and that a V11 score cannot exist without its Chase pillar. One partial index
supports the `(version, rankable, score DESC)` ranking predicate.

**Not applied anywhere.** Statically reviewed only — see §11.

## 10. Tests

```
backend/tests/unit/desirability/test_overall_rip_v11.py        31 passed
backend/tests/unit/desirability/ + version alignment        1877 passed, 13 failed
```

The 13 failures are the pre-existing baseline Stage VII recorded — `test_pull_model_live_fallback.py` (6)
and `test_public_rip_cohort_integration.py` (7), same files and same counts. Both were
inspected rather than assumed harmless: they fail on pull-model coverage state and on
sets lacking Collector Appeal, and touch no Overall RIP, V10, V11 or Chase code path.

## 11. What is NOT done

The following brief phases are **outstanding**. No canonical reader has been moved to V11
and nothing behaves differently in production today.

* Phase 12 — Stage 1 / Stage 2 sealed-product scoring pipeline
* Phase 13 — Stage 2 economic parity tests (ETB, PC ETB, Enhanced Booster Box guaranteed components)
* Phase 14 — finalization / persistence / DTO round-trip
* Phases 15–16 — family, budget-normalized, Explore RIP reader cutover
* Phases 17–19 — public contract V11, Chase API payload, publication pipeline
* Phase 20 — frontend canonical version contracts
* Phase 21 — backfill / recompute tooling
* Phase 25 — migration execution against a schema clone (no local Postgres or authorized
  clone was available; the migration is statically reviewed only)
* Phase 6 — the per-product/per-family coverage table (depends on the above)
* §7 — the two unreconciled guardrail statistics

## 12. Deployment status and rollback

Nothing deployed, nothing published, no commit. Rollback of what exists is deleting three
new files (`chase_core_k.py`, `chase_opportunity.py`, the test module), two validation
scripts, the unapplied migration, and reverting the additive blocks in `scoring_config.py`
and `weighted_rip.py`. No stored data and no reader depends on any of it.
