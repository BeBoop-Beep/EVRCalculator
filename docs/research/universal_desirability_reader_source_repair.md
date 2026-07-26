# Universal Desirability reader — version-exact source repair (Phase 8.2)

**Public score changes: 0 · Public rank changes: 0 · Source rows re-pointed: 170 of 171**
**Migrations: 0 · CA7 writes: 0 · API contract changes: 0 · Frontend changes: 0**

## The defect

`universal_set_desirability_service._load_latest_v2_rows` selected the component
row that powers the **public** Universal Desirability score like this:

```python
.order("built_at", desc=True)          # newest row per set wins
...
elif row.get("scoring_version") == V2_SCORING_VERSION and ...   # one version, checked as a tiebreak
```

`pokemon_set_desirability_component_scores` is keyed on **six** columns —
`(set_id, scoring_version, hit_policy_version, composite_scoring_version,
fan_popularity_snapshot_id, config_fingerprint)`. Agreeing on `scoring_version`
says nothing about the other two version columns, and all three of the observed
production hit policies share the same `scoring_version`:

| scoring_version | hit_policy_version | rows | sets | expected? |
|---|---|---|---|---|
| `..._v2_40_25_20_15` | `..._hit_policy_v1` | 171 | 171 | no |
| `..._v2_40_25_20_15` | `..._hit_policy_v2` | 170 | 170 | no |
| `..._v2_40_25_20_15` | `..._hit_policy_v2_coverage_cleanup` | 171 | 171 | **YES** |

This is the same defect Phase 8.1 repaired for CA7 — an internal candidate that
writes nothing — left live on the reader that serves the public score.

**Measured against production:** for **170 of 171 sets** the newest row by
`built_at` was **not** the exact-version row. The public score was being computed
from `hit_policy_v1` inputs for every set except Chaos Rising, whose exact row
happened to be the newest only because it had just been backfilled.

Note the direction of the trap: **the wrong rows are newer.** Any test whose
fixture makes the correct row the newest would pass under the defect.

## The repair

`_load_current_component_rows` now selects through the shared contract in
`backend/desirability/component_source.py` — the same module CA7 selects
through. The expected version strings are **not** restated in the service; they
are read from the modules that define them, so the two readers cannot drift
apart. A regression test asserts the service source contains none of the three
version literals.

- Version-exact match on all three columns; no near-miss fallback.
- Zero exact rows → the set is **absent** from `payloads` → `public_payload`
  returns `None` → the API renders it unavailable. Never a fabricated `0.0`.
- Multiple exact rows → withheld from `selected` and logged as `INTEGRITY`.
  Duplicates differ in `fan_popularity_snapshot_id` or `config_fingerprint`, so
  picking one would be picking an input set — an operator's decision.
- Selection no longer depends on row order. `built_at` ordering is retained only
  for stable pagination.
- `sourceSelection` diagnostics are added to the **bundle** only. They are
  internal: `public_payload` is unchanged, field for field.

## Impact — measured against production, read-only

| | Before | After |
|---|---|---|
| Sets served | 171 | 171 |
| Ranked (`coverage = full`) | 135 | 135 |
| Coverage `unavailable` | 36 | 36 |
| Rows from `hit_policy_v1` | **170** | **0** |
| Rows from `v2_coverage_cleanup` | 1 | **171** |
| **Public scores changed** | — | **0** |
| **Public ranks changed** | — | **0** |

**170 sets changed which stored row powers their public value. Zero public values
moved.** Per the phase requirement, that equality is proved, not assumed:

- **166 of 170**: `subject_rollups_json` is **byte-identical** between the v1 row
  and the `v2_coverage_cleanup` row. The v3 score is a pure function of those
  rollups, so it cannot differ.
- **4 of 170**: rollups genuinely differ — the four EX Trainer Kits
  (`EX Trainer Kit 2 Minun`, `EX Trainer Kit 2 Plusle`, `EX Trainer Kit Latias`,
  `EX Trainer Kit Latios`). The cleanup policy collapses duplicate subjects
  (14/13 rollups → 7). All four have `hit_eligible_card_count = 0`, so
  `eligible_subject_rollups` yields **0 eligible subjects under both policies**:
  v3 = `0.0` and coverage = `unavailable` either way. They are non-booster
  products, excluded from the ranked cohort, so no public rank exists to move.
- `set_desirability_score` (D) differs on **0 of 170** rows.

Because no ranked set's score moved, the rank vector is unchanged and no
per-set rank delta table is required — there are no rows to list.

### Chaos Rising

| | Before | After |
|---|---|---|
| Source row | `6e4cf65f-6846-4e7a-91dd-346550d31dca` | `6e4cf65f-…` (unchanged) |
| Hit policy | `v2_coverage_cleanup` | `v2_coverage_cleanup` |
| Score / rank | 69.8947 / 124 | 69.8947 / 124 |

Chaos Rising was already correct under the old rule — **by accident**, because its
exact row was the newest. That accident is exactly why the defect survived: the
one set anyone had recently looked at was the one set the broken rule got right.

## RIP

Unchanged. RIP still consumes **Universal Desirability v3** at its existing
**10%** weight (`DEFAULT_RIP_WEIGHTS = {profit: 0.58, safety: 0.20, stability:
0.12, desirability: 0.10}`), now from the correct exact-version source. CA7 is
**not** wired into RIP and no CA7→D fallback exists. RIP coverage remains
**33 of 33** under Universal Desirability; the 21-of-33 figure is CA7's coverage
and is a separate, internal number.

## Stale cached / materialized output

The service caches payloads **in-process** with a 6-hour TTL
(`CACHE_TTL_SECONDS`), so a running API process will serve the previous
selection until its cache expires or the process restarts. Because no public
value differs between the two selections, that window has **no user-visible
effect** — the same numbers are served from a different row.

No stored snapshot table holds this value: v3 is computed at read time from
`pokemon_set_desirability_component_scores`. **No refresh is performed in this
phase**, and none is required for correctness of the served numbers.
