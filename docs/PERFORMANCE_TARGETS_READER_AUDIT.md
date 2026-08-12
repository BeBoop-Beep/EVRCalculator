# Performance / Trust — Targets Reader Audit

Branch `feature/perf_updates_two`, starting SHA `851bd3d`.
Measured against the live persisted snapshot published `2026-08-12T18:20:57Z`
(publication `ea2a5cae-c826-492b-8860-624b192c224c`, market date `2026-08-12`, 34 targets).

## Current architecture

```
rankings publication (pokemon_explore_rankings_publisher)
    ↓  validates meta.ripWeightsConfig against canonical_publication_identity()
    ↓  atomic RPC publish_pokemon_public_rip_leaderboard
pokemon_explore_rankings_snapshot_latest   (tcg=pokemon, scope=rip-statistics)
    ↓  get_pokemon_explore_rankings_snapshot_payload  (run_public_read_with_retry)
    ↓  publication-identity validation            ← ADDED THIS PASS
    ↓  checklist Set Value compatibility enrichment
    ↓  opening-set filter + limit prefix + request metadata
GET /explore/rip-statistics/targets
    ↓
frontend process Map (~120 s, fetch cache: "no-store")
```

The expensive live builder (`get_rip_statistics_targets_payload`, ~3.8 s warm /
~150 s cold) is **not** the normal request path. It runs only when the snapshot
row is entirely missing, plus publication and tooling.

## Publication identity

`canonical_publication_identity()` in `public_rip_publication_contract.py` is the
single authority. Four identifiers:

| Identifier | Source constant |
|---|---|
| `financialRipVersion` | `CANONICAL_FINANCIAL_RIP_VERSION` |
| `collectorAppealVersion` | `COLLECTOR_APPEAL_V3_VERSION` |
| `overallRipVersion` | `CANONICAL_OVERALL_RIP_VERSION` |
| `publicRipContractVersion` | `canonical_public_rip_contract_version()` |

- **Publisher** reads them from `meta.ripWeightsConfig` and refuses to publish on
  any mismatch (`publication_contract`), and writes them into the leaderboard
  snapshot row columns + `diagnostics_json`.
- **Reader** (before this pass) checked **nothing**. A row published before a
  cutover stayed in `..._snapshot_latest` and continued to be served as the
  current canonical ranking. A scoring cutover moves no timestamp, so neither
  `updated_at` nor market date could detect it.
- **Reader** (after this pass) reads the same `meta.ripWeightsConfig` block and
  compares it against the same `canonical_publication_identity()`. No version
  literal is restated on the read path; a contract test asserts this.

The live production payload carries all four, all canonical.

## Reader state machine

| State | Detection | Behavior |
|---|---|---|
| CURRENT_VALID | row present, all 4 identifiers canonical | served; `meta.snapshot.publicationIdentity = "current"`; cached as last-known-good |
| STALE_BUT_COMPATIBLE | canonical identity, older market date / `updated_at` | **served normally** — deliberately not conflated with incompatible |
| INCOMPATIBLE_PUBLICATION | any identifier differs | last-known-good if held (`fallbackReason: incompatible_publication_identity`), else `503 RIP_STATISTICS_TARGETS_PUBLICATION_SUPERSEDED`, `Retry-After: 60`. Never the live builder. |
| MALFORMED | identity absent/unreadable | fails **closed** → same path as INCOMPATIBLE |
| MISSING | no row | existing live-builder fallback, unchanged |
| TRANSIENT_READ_FAILURE | transient classifier | last-known-good (`transient_data_service_failure`) else `503 ..._TEMPORARILY_UNAVAILABLE`, `Retry-After: 15` — unchanged |
| non-transient read error | classifier | `500 ..._SNAPSHOT_FAILED` — unchanged |

Fail-closed matches `evaluate_leaderboard_staleness`: "we cannot tell which model
built this" is not "it was built under the current model".

An incompatible snapshot deliberately does **not** fall back to the live builder:
that would hand every visitor a 3.8–150 s publication-grade rebuild for as long
as the superseded row stays published. Republishing is the real fix.

## Healthy read latency

12 direct calls, `limit=100`, full 34-target cohort, no frontend cache:

| Metric | ms |
|---|---|
| min | 567.5 |
| p50 | 801.3 |
| p95 | 959.9 |
| max | 1684.5 |

## Latency decomposition

| Component | Median ms | % |
|---|---|---|
| compatibility enrichment | 402.6 | 57.9% |
| snapshot DB read | 268.9 | 38.6% |
| serialization | 21.6 | 3.1% |
| normalization/slicing | 2.8 | 0.4% |
| **sum** | **696.0** | |

The per-request compatibility enrichment is the **largest single component** —
larger than the snapshot read itself.

## Compatibility enrichment audit

`_enrich_rankings_payload_with_checklist_set_values`

- Reads `pokemon_set_market_dashboard_snapshot_latest`, one batched query,
  filtered by the 34 target set IDs and two window keys.
- Can modify: `checklistSetValue`, `checklist_set_value`,
  `currentChecklistSetValue`, `current_checklist_set_value`,
  `checklistSetValueAsOf`, `checklist_set_value_as_of`, plus the mirrored
  `market.*` block.
- **Only writes when the target has no existing value** — it is explicitly a
  compatibility fill, guarded so it can never overwrite a canonical published
  value (an earlier defect where the laggy dashboard snapshot masked a newer
  Explore publication).

Measured against the current published snapshot:

| Fact | Value |
|---|---|
| targets total | 34 |
| targets already carrying `checklistSetValue` | 34 |
| targets missing it | 0 |
| **targets semantically changed by enrichment** | **0** |
| measured cost | ~403 ms median (57.9% of the read) |

**Classification: B — FALLBACK-ONLY.**
Current snapshots already carry the authoritative Set Value fields; the
enrichment changes nothing for them, and matters only for legacy/incomplete
snapshots.

### Why it was NOT removed or gated in this pass

§13 requires all six conditions. Condition 3 fails:

> Publisher tests prove those fields are part of the persisted publication contract.

They do not. `checklistSetValue` is produced by the rankings builder
(`explore_rip_statistics_service`) and consumed by the frontend and the market
publication audit script, but **no publisher-side validation or test asserts its
presence** — `publication_contract` does not require it. So a future builder
change could silently drop it and publication would still succeed. Gating the
enrichment today would convert that into a public data regression.

Conditions 1, 2, 5 are met with evidence above. The correct order is: add the
publisher contract assertion first, then gate.

## Response size

2,794,794 bytes (~2.79 MB) for 34 targets. Untouched this pass — still carries
V4/V5/V6/V7 blocks and snake_case + camelCase duplicates.

## Frontend cache (observed, unchanged)

`frontend/lib/explore/ripStatisticsServer.js` keeps a shared process Map with a
~120 s TTL, fetching with `cache: "no-store"` so no Next data cache stacks on it.

- A newly published backend snapshot **can remain hidden for up to ~120 s.** That
  is pre-existing and deliberate — it is described in-file as the single
  cross-request freshness boundary.
- Publication-identity checking does **not** change this. It narrows *what* the
  backend will serve, not how long the frontend holds it.
- Consequence worth noting: when the backend returns the new
  `503 ..._PUBLICATION_SUPERSEDED`, the frontend takes its existing recoverable
  stale-fallback path, so an incompatible publication degrades rather than
  erroring the page.

## Next optimization recommendation

**A — gate the compatibility enrichment**, preceded by a publisher contract
assertion that the Set Value fields are part of the persisted publication.
It is 57.9% of a ~800 ms response and provably zero-change for current
snapshots; no other single item on this path is close.
