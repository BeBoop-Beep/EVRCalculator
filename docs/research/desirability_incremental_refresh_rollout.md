# Desirability Incremental Refresh — Diagnosis and Phase 1 Rollout

**Status:** Phase 1 (data correctness) complete. Refresh architecture NOT yet built.
**Date:** 2026-07-15
**Database:** Supabase project `TheIndex` (`zwxzxuuawalvwioadhmf`) — treated as production.
**Writes performed this phase:** none. All database access was read-only or dry-run.

This document covers the diagnosis phase and the first implementation phase. It
deliberately does **not** claim the scheduled pipeline is ready. Sections marked
DEFERRED are not built.

---

## 1. Existing runtime diagnosis

### 1.1 Exact batch calculation

`build_anchor_batches` (`backend/desirability/google_trends.py`) sends the anchor
plus `batch_size - 1` subjects per request. At the default `batch_size=5`:

| Quantity | Value |
|---|---|
| Pokémon references | 1,025 |
| Subjects per batch (`batch_size - 1`) | 4 |
| Anchor (Pikachu) excluded from subject list | 1,024 remain |
| **Batches per timeframe** | `ceil(1024 / 4)` = **256** |
| Sleeps per timeframe (`index < len(batches)`) | 255 |

`fetch_timeframe_rows` sleeps `delay_seconds` between batches
(`google_trends.py:532`). Actual request time is ~1–2s per batch.

| `--delay-seconds` | Sleep per timeframe | Wall clock per timeframe |
|---|---|---|
| 180 (the manual command) | 255 × 180s = 45,900s | **~12.8 h** |
| 8 (orchestrator default) | 255 × 8s = 2,040s | ~40 min |

**The ~13 hours is ~99% `time.sleep`.** It is not network time, not parsing, not
database time.

### 1.2 The real dilemma

The two known configurations are both unusable, which is the actual problem to solve:

- `--delay-seconds 8` (orchestrator default) → Google rate-limits the run.
- `--delay-seconds 180` (manual escalation) → 12.8 h per timeframe.

The redesign must find the survivable middle via adaptive throttling, and reduce
the *subject count per run* via sharding. Sharding is the larger lever.

### 1.3 Two aggravating defects found

1. **`stage_trends` never passes `--timeframe`**, so it inherits
   `DEFAULT_TIMEFRAMES` — **all four** windows (1-m, 3-m, 12-m, 5-y). That is
   4 × 256 = 1,024 batches sequentially per run.
2. **`today 3-m` has no consumer.** It is in `DEFAULT_TIMEFRAMES` with
   `window_role="validation"`, but `calculate_derived_trend_scores` never reads
   it. 25% of every full run collects data nothing consumes.

---

## 2. Which timeframes the composite actually consumes — RESOLVED

The prior documentation was ambiguous between "1-m + 12-m" and "1-m + 12-m + 5-y".

**The answer is neither. Canonical desirability consumes `today 1-m` and nothing else.**

Confirmed from two independent directions.

**Code:** `backend/desirability/composite.py:174` —
`"V1 requires recent_trend_score derived from today 1-m only."` The composite
selects only `recent_trend_score`.

**Production data:** `pokemon_trend_scores` contains exactly one score type.

| score_name | rows | distinct pokémon | consumed by composite |
|---|---|---|---|
| `recent_trend_score` | 1,048 | 1,025 | **yes** (`today 1-m`) |
| `search_popularity_score` | **0** | 0 | no |
| `trend_momentum_score` | **0** | 0 | no |

`search_popularity_score` (0.75 × 12-m + 0.25 × 5-y) and `trend_momentum_score`
(1-m vs 5-y) are fully implemented in `trends_normalization.py`, produce zero rows
in production, and are read by nothing downstream.

**Decision (owner, 2026-07-15):** scheduled runs collect `today 1-m` only.
12-m and 5-y become explicit manual backfill, available on demand for when
`search_popularity_score` is wired into the composite. `today 3-m` is dropped.

---

## 3. Multi-timeframe database audit — the premise was false

The brief asked why 12-month and 5-year results "did not appear correctly," and
asked to verify uniqueness/upsert keys prevent one timeframe overwriting another.

**There is no overwrite bug and no key collision.** `pokemon_trend_source_rows`
has **no unique constraint at all** — only `PRIMARY KEY (id)`. The table is
append-only; no timeframe can overwrite another. There is no upsert on this path.

The real cause is far more mundane — the runs never completed:

| timeframe | source rows | distinct pokémon | snapshots | snapshot status |
|---|---|---|---|---|
| `today 1-m` | 1,048 | 1,025 | 2 | `captured_relative_search_interest` |
| `today 12-m` | **5** | **5** | 1 | `rate_limited_gracefully` |
| `today 5-y` | **0** | — | 0 | never ran |
| `today 3-m` | **0** | — | 0 | never ran |

The 12-m run captured exactly **one batch** (anchor + 4 subjects) and stopped.
`--stop-after-consecutive-429s 1` did exactly what it was told. 5-y never
executed because `ingest_pokemon_trends.py:413` `break`s out of the remaining
timeframe loop on a graceful rate-limit stop.

**Nothing is corrupted. The data was simply never collected.**

Related key observations:

- `pokemon_trend_scores` unique key is
  `(pokemon_reference_id, source_name, score_name, primary_snapshot_id, scoring_version)`.
  Timeframe is distinguished only *indirectly*, via `primary_snapshot_id`. This
  is adequate today because each snapshot is one timeframe, but it does **not**
  carry `anchor_scheme`. Wiring tiered-v1 will need that dimension before
  tiered and single-Pikachu values can coexist. (No migration applied.)
- **532 of 1,048 (51%) of 1-m rows are zeros** — the Pikachu-anchor compression,
  confirmed at production scale.

---

## 4. Set rebuild fingerprint — FIXED

### The defect

`_config_trace` hashed **only static per-set Python config**: `module`,
`qualname`, `SET_NAME`, `SET_ID`, `GOD_PACK_CONFIG`, `DEMI_GOD_PACK_CONFIG`,
`CHASE_METRICS_EXCLUDED_RARITIES`. It contained no source-data identity.

Production evidence: **171 distinct `config_fingerprint` values across 171 sets** —
exactly one per set, invariant across every rebuild since June.

A second, subtler defect: the builder's skip predicate keyed on
`(set_id, config_fingerprint)`, while the database unique key is
`(set_id, scoring_version, hit_policy_version, composite_scoring_version, fan_popularity_snapshot_id, config_fingerprint)`.
**The builder's key was narrower than the database's**, so it skipped rows
Postgres would have accepted.

Neither key included trend snapshot identity → Trends changes could never
invalidate a set row. Combined with `stage_sets` never passing `--force`, set
rows were frozen against source changes.

### The fix

Staleness now keys on `set_id + config_fingerprint + current_trend_snapshot_ids`.

`current_trend_snapshot_ids` is an existing `jsonb` column already written by the
builder — **no migration required**. Because the fingerprint itself is unchanged,
a stale row is UPDATED in place by the existing upsert rather than accumulating a
new row per refresh. Current-state semantics are preserved.

`_normalized_snapshot_ids` renders both storage shapes identically (Supabase
returns `jsonb`; freshly built rows hold a plain `list`), so unchanged sets do
not falsely read as stale.

**Not yet in the staleness key (DEFERRED):** fan-popularity snapshot version,
subject-link version, rarity-eligibility config, pull-rate version, and the
Collector/Chase/Dual-Path formula versions. The fan snapshot is already part of
the *database* unique key, so it is partially covered. The rest require version
identifiers that do not exist yet.

### Modes

| Flag | Behaviour |
|---|---|
| `--rebuild-changed` | **Default.** Rebuild only sets whose inputs changed. |
| `--rebuild-all` | Rebuild every selected set. Manual use only. |
| `--force` | Deprecated alias for `--rebuild-all`. |

`stage_sets` no longer hardcodes `force=False`. It passes `--rebuild-changed` by
default and exposes `--rebuild-all` on the orchestrator for manual override.

**Known reporting gap:** `list_existing_component_scores` is only called when
`not dry_run`, so a dry run cannot yet report which sets *would* be skipped.
Pre-existing behaviour; not addressed this phase.

---

## 5. Missing data must not become zero — FIXED

### The defect

A set whose cards cannot be classified scored 0.0 on every component —
indistinguishable from a genuinely unappealing set, and ranked as the worst
product in the catalogue. Production: **120 of 511 rows (23.5%)** had all
components at exactly 0.0.

### The fix

`build_metric_status` classifies every set from the existing
`build_set_coverage_audit` counts. Emitted into `diagnostics_json` (the score
columns are `NOT NULL numeric`; a real `metric_status` column needs a migration,
which was **not** applied).

| State | Trigger |
|---|---|
| `valid` | Rarity and subject-link coverage ≥ 50% |
| `partial` | Either coverage below 50%; still rankable |
| `unavailable_missing_rarity` | No card classifies into a hit rarity bucket |
| `unavailable_missing_subject_links` | Hit-eligible cards exist, none resolve to a subject |
| `unsupported_product_type` | No canonical cards mapped |

Each row also carries `rankable`, `availability_reason`, `canonical_card_count`,
`classified_card_count`, `hit_eligible_card_count`, `rarity_coverage_pct`,
`subject_link_coverage_pct`, and `status_version`.

`pull_rate_coverage_pct` is `None` **on purpose**: pull rates are not resolved at
this layer. Reporting a number would be fabrication. `unavailable_missing_pull_rates`
is therefore specified but unreachable — see Risks.

### Measured against production (dry run, no writes)

| metric_status | sets |
|---|---|
| `valid` | 135 |
| `unavailable_missing_rarity` | 36 |

All 36 score exactly 0.0, confirming they are the missing-data sets. They are
overwhelmingly Black Star Promos (`bwBlackStarPromos`, `dpBlackStarPromos`,
`hgssBlackStarPromos`) and EX Trainer Kits (`exTrainerKitLatias`,
`exTrainerKit2Minun`, …) — promo cards genuinely have no standard rarity, and
Trainer Kits are not booster products. These are exactly the sets that must not
be ranked as least appealing.

36 sets × ~3 version rows each reconciles with the 120 all-zero rows.

**Consumers are not yet updated.** Writing the status does not by itself remove
these sets from rankings — see Risks.

---

## 6. Files changed

| File | Change |
|---|---|
| `backend/scripts/build_pokemon_set_desirability_component_scores.py` | Source-aware staleness key; `--rebuild-changed`/`--rebuild-all`; `build_metric_status`; report counters |
| `backend/scripts/run_desirability_refresh.py` | `stage_sets` no longer hardcodes `force=False`; `--rebuild-all` passthrough; richer stage detail |
| `backend/tests/unit/desirability/test_set_rebuild_staleness.py` | New — 15 tests |

## 7. Tests run

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/desirability/ -q
→ 257 passed (242 pre-existing + 15 new)
```

New tests cover spec items 22–26: `--rebuild-changed`, `--rebuild-all`,
source-version-aware fingerprinting, missing rarity → unavailable, and
unsupported sets excluded from rankings. Items 1–21 and 27–35 cover the refresh
architecture and are **not** built.

## 8. Commands used this phase

```bash
# Dry-run set rebuild against production (read-only; takes no write path)
backend/.venv/Scripts/python.exe backend/scripts/build_pokemon_set_desirability_component_scores.py --dry-run --log-level WARNING

# Unit tests
backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/desirability/ -q
```

---

## 9. Remaining risks

1. **Consumers still rank unavailable sets.** `metric_status` is written but no
   reader filters on it. The 36 sets still surface as 0.0 until the snapshot
   builders and frontend honour `rankable`. **This is the highest-value next
   step** — the fix is not user-visible without it.
2. **`metric_status` lives in `diagnostics_json`, not a column.** Score columns
   are `NOT NULL`, so an unavailable set still stores 0.0 rather than NULL. A
   proposed migration should add real `metric_status` / `availability_reason`
   columns. Not drafted.
3. **`unavailable_missing_pull_rates` is unreachable**, and Trainer Kits are
   classified `unavailable_missing_rarity` when `unsupported_product_type` is
   arguably more accurate. Distinguishing "we lack rarity data" from "this
   product has no rarities by nature" needs a product-type signal that does not
   exist yet.
4. **Staleness key is incomplete** (see §4) — several version identifiers do not
   exist to key on.
5. **The 51% zero rate in Trends data is untouched.** The Pikachu-anchor
   compression is the largest known accuracy defect and is unaddressed.
6. **The refresh architecture does not exist.** Rate limiting, sharding, priority
   watchlist, checkpoint/resume, and incremental propagation are all DEFERRED.

## 10. Not built this phase (DEFERRED)

Sections 2–11 and 16 of the brief: tiered cadence, stable sharding, priority
watchlist, adaptive rate limiting, checkpoint/resume, last-known-good source
status, tiered-anchor integration, query semantics, provider abstraction, and
changed-subject → affected-set propagation.

Task Scheduler setup is **not** documented and the task must **not** be created:
the runtime problem is not yet solved, so there is nothing safe to schedule.

## 11. Manual approval required before production scheduling

Nothing in this phase is scheduled and nothing was written. Before any committed
scheduled execution:

1. The refresh architecture (§10) must exist and be measured, not estimated.
2. A measured normal-run wall clock must be demonstrated against live Google
   Trends — not extrapolated from fixture runs.
3. `--rebuild-changed` must be exercised with `--commit` against a known-changed
   subject set and reviewed.
4. Consumers must honour `metric_status` before the 36 unavailable sets are
   presented to users.
