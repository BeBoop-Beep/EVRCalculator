# Performance Phase — Set Value publication guarantee, then enrichment gating

Branch `feature/perf_updates_two`, starting SHA `0201a02`.
Follows [`PERFORMANCE_TARGETS_READER_AUDIT.md`](PERFORMANCE_TARGETS_READER_AUDIT.md),
whose closing recommendation was: *"gate the compatibility enrichment, preceded by
a publisher contract assertion that the Set Value fields are part of the
persisted publication."* That is what this pass does, in that order.

Measured against the live persisted snapshot published `2026-08-12T18:20:57Z`
(publication `ea2a5cae-c826-492b-8860-624b192c224c`, market date `2026-08-12`,
34 targets, 22 of them ranked).

---

## Publication Set Value guarantee

### The canonical contract

| Property | Value |
|---|---|
| Canonical field | `checklistSetValue` |
| Source | `pokemon_set_value_daily_history`, `value_scope = 'standard'`, at the current published snapshot date, loaded by `explore_rip_statistics_service._load_current_checklist_set_value_lookup` |
| Type | strictly positive number. Strings are **not** coerced — a stringified value is a serialization defect, not a value |
| Aliases required to agree | `checklist_set_value`, `currentChecklistSetValue`, `current_checklist_set_value` |
| As-of fields | `checklistSetValueAsOf`, `checklist_set_value_as_of`, both required to equal the publication's own market date |
| Required of | every **ranked** target (Overall RIP V7 rank present) |
| Legitimately absent for | unranked discovery targets |

Those are exactly the fields `_enrich_rankings_payload_with_checklist_set_values`
could write, and nothing else. Requiring less would leave a field the reader
stops filling and the publisher never checks; requiring more would pin aliases
that one builder assignment already derives from the same variable.

The as-of must equal the market date because the builder resolves the value *at*
the current published snapshot date. A value carrying any other date was not
built for this publication.

### The explicitly encoded exception

A hard "every target must have it" rule would be wrong, and production says so.
`pitchBlack` appears in the persisted payload as an unranked discovery target
with **no** set-value history for the whole of 2026-07-01 → 2026-07-31; its daily
history begins 2026-08-01, the same day it joins the ranked cohort. Requiring the
value of every target would have made a routine set onboarding break leaderboard
publication for a month.

So the requirement is scoped to ranked targets — the same cohort whose missing
relative scores already refuse publication — and the unranked case is reported
through a coverage marker instead.

Verified on live data over the last 61 days: set-value coverage of the current
34-target payload is complete every day since 2026-08-01; before that, the single
gap is `pitchBlack`, unranked.

---

## Publication guard

`pokemon_explore_rankings_publisher.publication_contract` now folds
`set_value_contract_problems(target, market_date=…)` into the same `problems`
list that already carries the score-contract failures. A candidate whose ranked
targets lack the canonical value raises `RuntimeError` **before** any RPC:

```
build candidate
  → publication_contract()            ← identity + scores + SET VALUE  (raises)
  → previous-day movement enrichment
  → attach_publication_metadata()     ← writes the capability marker
  → validate_publication_payload()    ← preflight, incl. marker coherence (raises)
  → client.rpc("publish_pokemon_public_rip_leaderboard")
```

Nothing is written on failure, so the previously valid published snapshot stays
active. `test_a_candidate_missing_set_value_never_reaches_the_publish_rpc`
asserts the RPC call list is empty, not merely that a helper raised.

**Live verification.** A real `--dry-run` publication against production data:

```
INFO [dry-run] validated complete RIP publication market_date=2026-08-12 rows=22
```

The 22 ranked targets produce **zero** set-value contract problems.

---

## Reader capability logic

The reader does **not** decide from field presence. Presence is a property of the
row in hand and cannot distinguish a payload published before the guarantee from
one published after it. The publisher writes an explicit marker into the metadata
block it already owns:

```json
meta.snapshot.setValueContract = {
  "version": "public_rip_set_value_contract_v1",
  "coverage": "complete",
  "targetCount": 34,
  "coveredTargetCount": 34,
  "asOf": "2026-08-12"
}
```

Coverage is measured over **every** target in the payload, ranked or not, because
the reader serves them all. `complete` only when every one satisfies the contract.

`payload_guarantees_canonical_set_value()` in
`public_rip_publication_contract.py` is the one authority both sides use; a
contract test asserts the reader module never restates the version string.

| Publication | Marker | Compatibility DB query |
|---|---|---|
| current canonical, complete coverage | `v1` / `complete` | **not issued** |
| current canonical, partial coverage | `v1` / `partial` | issued |
| legacy (published before this pass) | absent | issued |
| unrecognised future version | e.g. `…_v9` | issued (fails closed) |

Served payloads record which path ran, under the key that already existed:
`meta.sources.checklist_set_value_enrichment` is
`SKIPPED_PUBLICATION_GUARANTEES_SET_VALUE` or `legacy_missing_value_fill_only`.

---

## Semantic parity

Old (always enrich) vs new (gated) reader, same process, same live snapshot,
`limit=100`:

| Fact | Value |
|---|---|
| targets compared | 34 / 34, identical IDs |
| target field comparisons | 5,904 |
| **target-level differences** | **0** |
| meta keys differing | 2, both provenance-only |

Compared per target: every key present on either side — including
`checklistSetValue`, `checklist_set_value`, `currentChecklistSetValue`,
`current_checklist_set_value`, `checklistSetValueAsOf`,
`checklist_set_value_as_of`, `checklistSetValueSource`,
`checklistSetValuePricedCardCount`, `checklistSetValueTotalCardCount`,
`previousChecklistSetValue7d`, `setValueComparisonStatus7d`, the `market` block,
Overall RIP, Financial RIP, Collector Appeal, ranks, tiers, prices and movement
fields.

The two documented meta differences:

- `meta.sources.checklist_set_value_enrichment` — the provenance key above.
- `meta.snapshot.setValueContract` — the new capability marker.

No public metric changed. This is expected rather than lucky: the gate condition
(`checklistSetValue` present and valid on every target) is strictly stronger than
the enrichment's own no-op condition, so skipping it *cannot* change a value.

---

## DB request behaviour

| | snapshot row read | compatibility read |
|---|---|---|
| Before | 1 | 1 (`pokemon_set_market_dashboard_snapshot_latest`) |
| After — guaranteed publication | 1 | **0** |
| After — legacy / partial publication | 1 | 1 |

`test_guaranteed_publication_never_reads_the_compatibility_source` instruments
the client's `table()` and asserts the compatibility table is never named.

---

## Performance

### Direct backend, over HTTP

12 requests, `GET /explore/rip-statistics/targets?limit=100`, clean uvicorn
process per arm, no frontend cache. Both arms measured in the same session,
minutes apart, against the same production database.

| Metric | Before | After | Improvement |
|---|---|---|---|
| min | 1648.7 ms | 865.4 ms | −47.5% |
| **p50** | **1666.9 ms** | **889.9 ms** | **−46.6%** |
| p95 | 1737.6 ms | 993.1 ms | −42.8% |
| max | 1943.9 ms | 999.7 ms | −48.6% |
| response bytes | 2,625,429 | 2,625,588 | +159 B (the marker) |

> **On the ~801 ms figure in the earlier audit.** Today's session is roughly 2×
> slower end to end against the same data — the snapshot read alone measured
> ~670 ms here against ~269 ms then. The absolute baseline is therefore not
> comparable across sessions, which is why a fresh before-arm was measured in the
> same window rather than compared against the recorded number. The before-arm
> was also re-run after the after-arm (p50 1666.9 ms, first run 1720.9 ms) to
> confirm the gap is the code path and not drift.

### Latency decomposition

In-process, instrumented, 12 iterations per arm after 3 warm-ups:

| Component | Before median | After median | Delta |
|---|---|---|---|
| compatibility enrichment | 861.7 ms | **0.0 ms** | **−861.7 ms** |
| snapshot DB read | 696.1 ms | 669.8 ms | −26.3 ms (noise) |
| normalization / slicing | 73.5 ms | 73.1 ms | −0.4 ms |
| serialization | 17.2 ms | 17.0 ms | −0.2 ms |
| **total** | **1662.1 ms** | **762.6 ms** | **−899.5 ms (−54.1%)** |

The compatibility enrichment goes to zero exactly, and the whole of the total's
improvement is attributable to it. The snapshot DB read is now ~88% of the
remaining response.

### Frontend

Isolated `next start` on the phase build (`.next-perf/set-value-contract`), one
process per arm, each pointed at its own backend.

| Path | Before | After |
|---|---|---|
| cold Rankings (first request, fresh process) | 2012 ms | **1159 ms** |
| warm Rankings (3 runs) | 107 / 98 / 91 ms | 108 / 94 / 90 ms |
| Home → Rankings (warm median of 3) | 63 ms | 54 ms |
| Rankings → Set (warm median of 3) | 438 ms | 437 ms |

Exactly the predicted shape: cold discovery improves by roughly the backend
delta; warm navigation does not move, because
`frontend/lib/explore/ripStatisticsServer.js`'s ~120 s process Map was already
hiding the backend latency from it.

### Response size

2,625,588 bytes (~2.63 MB) for 34 targets — unchanged apart from the 159-byte
marker. Nothing was slimmed this pass; the payload still carries V4/V5/V6/V7 and
the snake_case + camelCase duplicates.

### The 120-second frontend Map

Untouched, as scoped. Worth recording that it is now a proportionally *larger*
share of end-to-end publication freshness: the backend read it fronts got ~2×
cheaper, so the Map is a bigger fraction of the delay between publishing a
snapshot and a visitor seeing it. Not optimized here.

---

## Legacy fallback

An older or incomplete compatible snapshot carries no `setValueContract` marker,
or one reporting `partial`, or an unrecognised version. In every one of those
cases the reader takes the pre-existing path unchanged:
`_enrich_rankings_payload_with_checklist_set_values` runs, reads
`pokemon_set_market_dashboard_snapshot_latest`, fills only values that are
missing, never overwrites a canonical published value, and on failure degrades to
the existing warning + `FAILED_OPTIONAL` source rather than erroring the request.

The helper is retained in full — it still has a supported consumer (legacy and
partial-coverage publications) and the missing-snapshot live-fallback path.

**Production note.** The currently published snapshot predates this change and
therefore carries no marker, so it is served on the legacy path and pays the
enrichment until the next publication writes the marker. The HTTP after-arm above
was measured through a scratchpad rig that injects the marker the publisher
would have written; the payload was otherwise the live one. No production write
was made in this pass.

---

## Files changed

- `backend/db/services/public_rip_publication_contract.py`
- `backend/scripts/pokemon_explore_rankings_publisher.py`
- `backend/db/services/pokemon_public_snapshot_service.py`
- `backend/tests/unit/scripts/test_rip_leaderboard_history_contract.py`
- `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py`
- `docs/PERFORMANCE_SET_VALUE_PUBLICATION_CONTRACT.md` (this file)

## Next optimization

**B — the ~670 ms snapshot DB read.** It is now ~88% of the healthy response and
the only component of any size left on this path. Option A (slimming the 2.63 MB
payload) is the other candidate, but serialization measures 17 ms, so the payload
size is a transfer-and-parse cost rather than a backend one and should be
measured client-side before being attacked.
