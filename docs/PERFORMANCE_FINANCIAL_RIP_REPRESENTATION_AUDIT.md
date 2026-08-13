# Financial RIP Representation Audit (Rankings targets payload — Phase 2)

Follow-on to `PERFORMANCE_TARGETS_PAYLOAD_SLIMMING.md`. After Phase 1 removed
`publicRipContractV4/V5/V6`, the largest non-V7 family left in each Rankings target was
the pair `financialRipV3` (~295 kB) + `financial_rip_v3_payload` (~298 kB).

The prior audit had recorded "0 / 34 byte-identical pairs" and correctly refused to
treat them as duplicates. **They are not duplicates — they are an output and its
input.** This audit proves that lineage, explains the 34-vs-22 coverage, and removes
only the raw input document from the persisted artifact.

**Result: 1,704,939 → 1,425,391 bytes (−279,548, −16.40%) against the live published
payload. Combined with Phase 1: 2,796,414 → 1,512,930 (−45.9%). Zero consumer
differences across 1,496 field comparisons.**

---

## Representation lineage

```
calculation_runs.financial_rip_v3_payload        RAW simulation document (JSONB)
  │   carried onto the target row verbatim at
  │   explore_rip_statistics_service.py:1764
  ▼
_build_financial_rip_v3(target)                  reads target["financial_rip_v3_payload"]
  │   (explore_rip_statistics_service.py:679)
  ▼
target["financialRipV3"]                         score / status / components / versions
  │   (assigned at :954)
  ▼
_rank_financial_rip_v3                           adds rank / tier / relativeScore /
  │   (:632, :1140)                              cohortSize across the ranked cohort
  ▼
publicRipContractV7.financialRip                 public packaging (absoluteScore,
                                                 cohortFingerprint, rankedSetCount,
                                                 normalizationMode, version)
```

| | `financial_rip_v3_payload` | `financialRipV3` | `publicRipContractV7.financialRip` |
| --- | --- | --- | --- |
| Kind | raw calculation-run document | computed verdict | public contract packaging |
| Produced by | simulation persistence | `_build_financial_rip_v3` | `build_public_rip_contract_v7` |
| Relative to cohort | **pre**-normalization | pre-rank, then ranked in place | post-rank |
| Absolute values | yes | yes | yes (`absoluteScore`) |
| Relative values | **no** | yes (`relativeScore`) | yes |
| Rank / tier | **no** | yes | yes |
| Raw diagnostics | yes (`estimationDiagnostics`) | no | no |
| Version identity | `configVersion`, `tailContractVersion`, `scoreVersion`, `normalizationVersion` | `scoreVersion`, `normalizationVersion` | `version`, `normalizationVersion`, `cohortFingerprint` |
| Run identity | `packCost` | `sourceRun` | `sourceRun` |
| Coverage | 22 / 34 | 34 / 34 | 34 / 34 |

Structural key sets:

- **snake (15):** audit, components, configVersion, depthAndRobustness,
  distributionDisclosures, estimationDiagnostics, normalizationVersion, packCost,
  rankable, score, scoreVersion, sessionOpeningProfile, status, statusReason,
  tailContractVersion
- **camel (18):** audit, cohortSize, components, depthAndRobustness,
  distributionDisclosures, normalizationVersion, rank, rankable, relativeScore, score,
  scoreVersion, sessionOpeningProfile, sourceRun, status, statusDetail, statusReason,
  tier, validationProblems
- **V7 (17):** absoluteScore, cohortFingerprint, components, depthAndRobustness,
  distributionDisclosures, normalizationMode, normalizationVersion, rank, rankable,
  rankedSetCount, relativeScore, score, sessionOpeningProfile, sourceRun, status, tier,
  version

---

## 34 vs 22 coverage explanation

Proven from the live payload, and it partitions perfectly with no residue:

| snake type | camel `status` | camel `statusReason` | n | has score | has rank | has V7 financialRip |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `object` | `ready` | — | **22** | 22 | 22 | 22 |
| `null` | `unavailable` | `no_financial_rip_v3_payload_on_latest_run` | **12** | 0 | 0 | 12 |

The 12 are sets whose latest accepted simulation **predates the Financial RIP V3
engine**, so no V3 document exists to compute from. `_build_financial_rip_v3` returns an
explicit unavailable verdict rather than borrowing a V2 number — which is exactly why
the camel object exists on 34/34 while the raw document exists on 22/34.

**The coverage difference is not a reason both forms must be persisted.** It is a
consequence of one being derived from the other.

---

## Semantic field map (22 populated targets)

| Field | Classification | Evidence |
| --- | --- | --- |
| `audit` | IDENTICAL_SEMANTICS_IDENTICAL_VALUE | byte-identical **22/22**, 184,080 B on each side |
| `distributionDisclosures` | IDENTICAL_SEMANTICS_IDENTICAL_VALUE | identical 22/22 across snake, camel **and** V7 |
| `depthAndRobustness` | IDENTICAL_SEMANTICS_IDENTICAL_VALUE | identical 22/22 across all three |
| `score` / `status` / `rankable` / `sessionOpeningProfile` / `normalizationVersion` | IDENTICAL_SEMANTICS_IDENTICAL_VALUE | identical 22/22 across all three |
| `scoreVersion` / `statusReason` | IDENTICAL_SEMANTICS_IDENTICAL_VALUE (camel↔snake) | identical 22/22; absent from V7 |
| `components` | IDENTICAL_SEMANTICS_DIFFERENT_FORMAT | 0/22 equal; 68,932 B snake vs 55,748 B camel vs 54,277 B V7 — the raw block carries pre-normalization member values |
| `rank`, `tier`, `relativeScore` | ONLY_IN_CAMEL (DERIVED, cohort-dependent) | equal to V7 22/22; cannot exist pre-ranking |
| `cohortSize` | ONLY_IN_CAMEL | V7 spells the same idea `rankedSetCount` |
| `sourceRun` | ONLY_IN_CAMEL | equal to V7 22/22 |
| `statusDetail`, `validationProblems` | ONLY_IN_CAMEL | verdict prose/diagnostics |
| `estimationDiagnostics` (4,782 B) | ONLY_IN_SNAKE | raw estimator internals |
| `configVersion` (616 B), `tailContractVersion` (660 B), `packCost` (97 B) | ONLY_IN_SNAKE | raw run provenance |
| `absoluteScore`, `cohortFingerprint`, `normalizationMode`, `version` | ONLY_IN_V7 | public packaging |

### Why 0/34 pairs were byte-identical

Not because the content is independent. Two mechanical reasons:

1. **Different key sets.** Seven keys exist only in camel, four only in snake. A
   top-level equality test can never pass regardless of shared content.
2. **`components` shape differs** — the raw block carries pre-normalization member
   values; the camel block carries the scored components.

Everything else they share is byte-identical. The earlier "0/34" figure was a true
observation that did **not** support the inference that both were needed.

---

## Byte overlap

Over the 22 populated targets:

| Field family | V7 bytes | camel bytes | snake bytes | Semantically duplicated? |
| --- | ---: | ---: | ---: | --- |
| `audit` | 0 | 184,080 | 184,080 | **YES — identical, 62% of the pair** |
| `components` | 54,277 | 55,748 | 68,932 | overlapping, different shape |
| `distributionDisclosures` | 16,898 | 16,898 | 16,898 | **YES — triplicated** |
| `depthAndRobustness` | 12,605 | 12,605 | 12,605 | **YES — triplicated** |
| `sourceRun` | 6,476 | 6,476 | 0 | camel == V7 |
| `estimationDiagnostics` | 0 | 0 | 4,782 | snake-only |
| version/provenance scalars | ~3,146 | ~2,134 | ~2,398 | partly |
| scores/rank/tier scalars | ~742 | ~732 | ~394 | camel == V7 |

**The real redundancy was never camel-vs-snake naming — it is `audit`, carried twice
at 184,080 B per copy.** Removing the raw document eliminates one full copy.

---

## Targets consumer map

| Consumer | reads `financialRipV3` | reads `financial_rip_v3_payload` |
| --- | --- | --- |
| Rankings / Explore table | **YES** — `constants/exploreRankingConfig.mjs` reads `financialRipV3.relativeScore`, `.rank`, `.cohortSize`, `.tier` | no |
| Explore RIP Statistics | YES (same config) | no |
| Market | no | no |
| Landing hero | `financial_rip_v3_simulation_count` (a *scalar sibling column*, not this object) | no |
| Set route / metadata / set picker | no | no |
| Sitemap | no | no |
| Publication / history tooling | `financialRipV3.rank` (movement) | no |

**The frontend contains ZERO references to `financial_rip_v3_payload`** — verified by
repo-wide search across `.js/.jsx/.mjs`.

`financialRipV3` is therefore **REQUIRED**, and V7 cannot substitute for it: the
Rankings table reads `cohortSize`, which V7 does not have (it spells it
`rankedSetCount`). Renaming public metrics is out of scope.

---

## Other-endpoint consumers of the raw document

| Consumer | Source | Classification |
| --- | --- | --- |
| `calculation_runs_repository` / `calculation_run_persistence_service` | `calculation_runs` table column | SIMULATION_PUBLICATION |
| `_build_financial_rip_v3` | the in-memory target row, from the calc-run row | PUBLIC_SNAPSHOT_BUILDER (live builder) |
| `audit_financial_rip_v3_inputs.py`, `compare_financial_rip_v2_v3.py` | **`explore_rip_statistics_latest` (a VIEW)** — not this table | RESEARCH/AUDIT |
| `validate_financial_rip_v3_payload`, `compute_financial_rip_v3` | function parameters | OTHER |

None reads it from `pokemon_explore_rankings_snapshot_latest`. Confirmed zero
references in the publisher, the publication contract,
`attach_daily_rip_rank_movements`, and the snapshot reader. The set-page lift list in
`_merge_canonical_rip_contract_into_set_payload` includes `financialRipV3` but **not**
the raw document.

---

## Canonical / fallback chain

Public Financial RIP precedence (`canonicalRipV7.mjs`):

1. `publicRipContractV7.financialRip` — preferred.
2. `overallRipV7` + `financialRipV3` — same model, top-level shape.
3. *(nothing)* — "deliberately no third step."

`financial_rip_v3_payload` **appears nowhere in this chain**. No
`financialRipV3 || financial_rip_v3_payload` compatibility expression exists anywhere in
the frontend. The Rankings table separately reads `financialRipV3.*` via
`exploreRankingConfig.mjs`.

Publication validation (`_score_contract_problems`) requires `publicRipContractV7` only.

---

## External contract status

**Internal transport.** No API documentation files exist; the only `.md` mentions of
`financial_rip_v3_payload` are this repo's own performance audits. Every
`getRipStatisticsTargets` caller is an in-repo Next.js server component. No external
guarantee is broken.

---

## Classification

| Representation | Classification |
| --- | --- |
| `financialRipV3` | **REQUIRED** — Rankings reads `relativeScore`/`rank`/`cohortSize`/`tier`; movement reads `rank`; carries the unavailable verdict for the 12 unranked sets |
| `financial_rip_v3_payload` | **OTHER-ENDPOINT-ONLY / build input** — required by the live builder and the calculation-run store, never read from this artifact |
| `publicRipContractV7.financialRip` | **REQUIRED** — canonical public source, and what publication validation enforces |

---

## Production implementation

`RAW_CALCULATION_DOCUMENT_KEYS_NOT_PERSISTED_IN_LATEST = ("financial_rip_v3_payload",)`,
merged with the Phase-1 tuple into `TARGET_KEYS_NOT_PERSISTED_IN_LATEST` and applied by
the existing `project_latest_rankings_payload` — same boundary, after all validation and
movement, `p_latest` only. History and `p_snapshot` untouched. The live builder still
produces and consumes the raw document.

---

## Candidate payload size

| Measurement | Before | After | Saved | % |
| --- | ---: | ---: | ---: | ---: |
| Phase 2 vs live published payload | 1,704,939 | 1,425,391 | 279,548 | **16.40%** |
| Publisher dry-run, combined Phase 1+2 | 2,796,414 | 1,512,930 | 1,283,484 | **45.9%** |

Keys per target: 174 (original) → 171 (Phase 1) → **170** (Phase 2).

---

## Consumer parity

Live published payload vs Phase-2 candidate, real consumer modules, models compared:

- Targets: **34** (including all **12** with `financial_rip_v3_payload = null`)
- Fields per target: **44** → **1,496 comparisons**
- Scenarios: target count, ordering, sitemap URLs, landing hero, `default_target`, `meta`
- **Differences: 0**
- Canonical resolution shape remains `publicRipContractV7` for all 34
- 22/34 available Overall RIP blocks, ranks 1..22, identical both sides

API shape parity: exactly `financial_rip_v3_payload` removed, 0 keys added, 0 values
changed, `meta` and `default_target` identical.

---

## Publication dry-run

```
INFO [rankings-publish] _latest payload projection: 2796414 -> 1512930 bytes
     (-1283484, -45.9%) removed=publicRipContractV4,publicRipContractV5,
     publicRipContractV6,financial_rip_v3_payload
INFO [dry-run] validated complete RIP publication market_date=2026-08-12 rows=22
explore rankings snapshot: publication gate decision (dry-run) [allowed_complete]
     allowed=True: batch 2026-08-12 is complete; promotion allowed
```

PASS — canonical identity correct, 22 ranked cohort, Set Value capability satisfied,
movement attached, projection applied, Financial RIP contract satisfied.

---

## Tests

| Suite | Result |
| --- | --- |
| `test_rankings_latest_payload_projection.py` (12 tests, +4 this phase) | 12 passed |
| Publisher guard, snapshot builder, publication contract, publication gate, public snapshot service, explore targets, public-read retry, onboarding verification, financial RIP V3 public contract, `tests/unit/api` | 287 passed, **1 pre-existing failure** |
| `-k financial_rip_v3` (repo-wide) | **84 passed** |
| Frontend: exploreRankingConfig, FinancialRipV3Breakdown, publicMetricContract, canonicalRipV7, cache identity, publicRelativeRipScores | 106 passed |
| `npx next build` (isolated) | exit 0 |

Pre-existing failure: `test_canonical_top_chase_history_forward_fills…` — test file and
source both unmodified at HEAD, unrelated to this change.

---

## User publication commands

```bash
cd /d/EVRCalculator
# dry-run first
./backend/.venv/Scripts/python.exe -m backend.scripts.build_pokemon_explore_rankings_snapshot --all --dry-run
# then publish
./backend/.venv/Scripts/python.exe -m backend.scripts.build_pokemon_explore_rankings_snapshot --all --commit
```

Expect `-45.9%` and `removed=…,financial_rip_v3_payload`.

## Post-publication verification

```bash
./backend/.venv/Scripts/python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8010 --log-level warning
./backend/.venv/Scripts/python.exe backend/scripts/verify_rankings_payload_slimming.py http://127.0.0.1:8010 25
```

**Projection, not a measurement:** Phase 1 took PostgREST 713.9 → 425.0 ms on a
−39% payload. Phase 2 removes a further 16.4%; on the same transfer-bound model
PostgREST would land near **~370 ms** and HTTP near **~455 ms**. Treat as unvalidated
until the harness runs against the published snapshot.

---

## Carry-forward reliability threads

**Top Chase 503 — UNRESOLVED.** 6/40 (15%) under 40-way concurrency before the
client-side duplicate fix, 0/40 after; the fix was client-side and cannot have repaired
a backend read failure. Not claimed fixed.

**Pull Rates request lifecycle — FOLLOW-UP.** A duplicate genuinely reproduced on 151 in
the pre-Phase-2A build; current traces are clean but no dedicated lifecycle contract test
pins single-request semantics.

Neither was touched here.
