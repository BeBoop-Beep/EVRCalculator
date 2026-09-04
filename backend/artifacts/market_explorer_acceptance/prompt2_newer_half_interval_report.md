# Prompt 2 — Newer-Half Interval Backfill: Acceptance Report

This report tracks acceptance for the Market Explorer newer-half interval backfill
(`pokemon_card_variant_market_price_intervals`) covering Sun & Moon, XY, Black & White,
HeartGold & SoulSilver, Platinum, and Diamond & Pearl.

Production database writes for this effort were executed by a process external to this
repo/session (reported as completed by the user, attributed to a parallel ChatGPT-driven
session). This report's DB-dependent sections were **not populated from that external
report verbatim** — the aggregate/global invariants below were independently re-queried
against the live database (project `zwxzxuuawalvwioadhmf`) from this session before being
recorded. Per-era breakdowns, the no-NM classification detail, and the smoke-test dollar
figures were **not independently re-derived per row** in this session; they are recorded
as reported and are consistent with the independently-verified aggregate totals, but
should be treated as externally-sourced detail rather than this session's own line-item
verification.

## A. Branch / HEAD

- Branch: `fix/public-rankings-entitlement-regression-2`
- HEAD at time of prior scaffold: `65f16867`
- Report scaffold committed at `ec0a54b9`
- Branch was ahead of `origin/fix/public-rankings-entitlement-regression-2` by 2 commits (pre-existing, unrelated to this task).

## B. Live cohort counts

Independently confirmed against the live database in this session:

- Total rows in `pokemon_card_variant_market_price_intervals`: **3,738,141** (matches externally reported "AFTER PROMPT 2" total exactly).
- Distinct `card_variant_id` values with at least one interval row (whole table, all cohorts): 27,770.

As reported (not independently re-derived per-set in this session):

- 64 authority-bearing newly populated sets
- 13,666 physical authority variants
- 13,610 variants with qualifying positive USD Near Mint history
- 56 variants with no qualifying NM history — all classified `NO_NM_OBSERVATIONS`

## C. Authority counts by era

As reported by the external production-write process (not independently re-derived per era in this session):

| Era | Sets | Authority variants | NM-history variants | No-NM variants |
|---|---|---|---|---|
| Sun & Moon | 17 | 4,384 | 4,381 | 3 |
| XY | 16 | 3,063 | 3,056 | 7 |
| Black & White | 14 | 2,592 | 2,575 | 17 |
| HeartGold & SoulSilver | 6 | 1,005 | 986 | 19 |
| Platinum | 4 | 973 | 968 | 5 |
| Diamond & Pearl | 7 | 1,649 | 1,644 | 5 |
| **Total** | **64** | **13,666** | **13,610** | **56** |

Note: Platinum's history-positive count (968) exceeds the original expected baseline (967)
by one — reported reason is a variant (Supreme Victors, Beldum #90, reverse-holo) whose
first qualifying NM observation landed on 2026-09-02, after the Sep-1 snapshot date, so it
correctly has interval history but is absent from the 2026-09-01 market snapshot. This is
a timing artifact, not a reconciliation defect.

## D. No-NM classification summary

All 56 no-NM variants classified as `NO_NM_OBSERVATIONS` (no positive-USD-NM source rows
exist for these variants). No `IDENTITY_RESOLUTION_FAILURE`, `CURRENCY_MISMATCH_ONLY`, or
`INVALID_PRICE_ONLY` cases reported. As reported by the external process; not
independently re-derived per variant in this session.

## E. Sun & Moon result

**SUN_MOON_ERA_INTERVAL_ACCEPTED** (as reported)
17 sets, 4,384 authority variants, 4,381 represented, 3 no-NM.
Source winners: 611,547. Interval rows: 611,547. Multiple-open violations: 0. Overlaps: 0.

## F. XY result

**XY_ERA_INTERVAL_ACCEPTED** (as reported)
16 sets, 3,063 authority variants, 3,056 represented, 7 no-NM.
Source winners: 422,202. Interval rows: 422,202. Multiple-open violations: 0. Overlaps: 0.

## G. Black & White result

**BLACK_WHITE_ERA_INTERVAL_ACCEPTED** (as reported)
14 sets, 2,592 authority variants, 2,575 represented, 17 no-NM.
Source winners: 353,897. Interval rows: 353,897. Multiple-open violations: 0. Overlaps: 0.

## H. HGSS result

**HGSS_ERA_INTERVAL_ACCEPTED** (as reported)
6 sets, 1,005 authority variants, 986 represented, 19 no-NM.
Source winners: 133,447. Interval rows: 133,447. Multiple-open violations: 0. Overlaps: 0.

## I. Platinum result

**PLATINUM_ERA_INTERVAL_ACCEPTED** (as reported)
4 sets, 973 authority variants, 968 history-positive, 5 no-NM.
Source winners: 132,887. Interval rows: 132,887. Multiple-open violations: 0. Overlaps: 0.
Sep-1 full market correctly has 967 constituents (see note in section C re: the 968th variant).

## J. Diamond & Pearl result

**DIAMOND_PEARL_ERA_INTERVAL_ACCEPTED** (as reported)
7 authority-bearing sets, 1,649 authority variants, 1,644 represented, 5 no-NM.
Source winners: 223,595. Interval rows: 223,595. Multiple-open violations: 0. Overlaps: 0.
DP Black Star Promos resolves to zero Market Explorer physical variants; received no interval population (expected).

## K. Per-era interval row totals

| Era | Interval rows |
|---|---|
| Sun & Moon | 611,547 |
| XY | 422,202 |
| Black & White | 353,897 |
| HeartGold & SoulSilver | 133,447 |
| Platinum | 132,887 |
| Diamond & Pearl | 223,595 |
| **Total added** | **1,877,575** |

Cross-check: 3,738,141 (independently confirmed post-Prompt-2 total) − 1,860,566 (reported
pre-Prompt-2 total) = 1,877,575, consistent with the per-era sum above.

## L. Global newer-half reconciliation

64 authority-bearing sets, 13,666 authority variants, 13,610 NM-history variants, 56
no-NM variants. Interval rows added: 1,877,575. Multiple-open violations: 0 (independently
confirmed, see section M). Daily projection coverage rows / daily projection rows created
for new Prompt 2 sets: 0 (independently confirmed, see section M — total
`pokemon_market_explorer_card_daily_states` row count unchanged at 1,908,119). Interval-only
boundary preserved. Cosmic Eclipse and Evolutions were already-covered pilots prior to
Prompt 2 and are correctly excluded from this cohort's counts.

## M. Open-row invariant results

Independently verified against the live database in this session:

- Multiple-open-row check (`valid_to IS NULL` grouped by `card_variant_id` having count > 1)
  across the entire `pokemon_card_variant_market_price_intervals` table: **0 violations**.
- Overlapping validity periods (`lead(valid_from)` per `card_variant_id` falling before the
  prior row's `valid_to`) across the entire table: **0 overlaps**.
- `pokemon_market_explorer_card_daily_states` total row count: **1,908,119**, matching the
  externally reported "projection remains unchanged" figure exactly — confirms no daily
  projection rows were created for the new Prompt 2 eras.

## N. Interval fallback smoke tests

As reported by the external process for 2026-09-01 (not independently re-run in this
session):

| Era | Full count / total | Top 10 total | Rare holo count / total | Premium count / total |
|---|---|---|---|---|
| Sun & Moon | 4,381 / $55,343.74 | $11,560.23 | 418 / $1,443.83 | 112 / $32,059.92 |
| XY | 3,056 / $37,319.63 | $7,902.07 | 260 / $1,246.03 | 82 / $21,982.03 |
| Black & White | 2,575 / $39,724.05 | $7,591.96 | 323 / $3,072.68 | 89 / $25,189.09 |
| HGSS | 986 / $28,384.35 | $6,604.51 | 148 / $8,984.74 | 60 / $16,883.45 |
| Platinum | 967 / $16,849.92 | $3,922.22 | 112 / $2,701.76 | 35 / $7,438.12 |
| Diamond & Pearl | 1,644 / $21,408.62 | $3,140.23 | 216 / $7,258.79 | 37 / $6,977.26 |

All smoke cases reported as succeeding (interval-fallback path, no timeouts).

## O. Storage before/after

Independently confirmed row-count deltas; byte figures as reported (not independently
re-queried via `pg_relation_size` in this session):

| | Before | After | Delta |
|---|---|---|---|
| Interval rows | 1,860,566 | 3,738,141 (independently confirmed) | +1,877,575 |
| Total interval relation bytes | 1,687,977,984 | 3,427,393,536 | +1,739,415,552 (~1.62 GiB) |
| Heap bytes | 526,458,880 | 1,041,580,032 | +515,121,152 |
| Index bytes | 1,161,347,072 | 2,385,494,016 | +1,224,146,944 |

Daily projection table unchanged: 1,908,119 rows, 468,893,696 bytes (independently confirmed row count).

## P. Tests

Repo-side test suite run from `d:\EVRCalculator` with `PYTHONPATH=.`, `pytest -v`, no live
DB connection used:

| Test file | Result |
|---|---|
| `backend/tests/unit/scripts/test_backfill_market_explorer_variant_intervals.py` | PASS (5/5) |
| `backend/tests/unit/scripts/test_accept_market_explorer_variant_engine.py` | PASS (18/18) |
| `backend/tests/unit/db/test_market_explorer_instrument_eligibility_migration.py` | PASS (6/6) |
| `backend/tests/unit/db/services/test_market_explorer_query_planner.py` | PASS (34/34) |
| `backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py` | PASS (32/32) |
| `backend/tests/unit/db/services/test_pokemon_sealed_market_explorer_query_service.py` | PASS (28/28) |

Total: **123 passed, 0 failed** in 1.04s. No genuine tooling/test defects found; no code
changes were required.

Tooling files checked for cleanliness (all clean, no local modifications vs. HEAD):
- `backend/scripts/backfill_market_explorer_variant_intervals.py`
- `backend/scripts/audit_market_explorer_variant_identity.py`
- `backend/scripts/audit_market_explorer_pass3.py`

`git diff --check` was run on the full working tree: it reports pre-existing trailing-
whitespace warnings only in unrelated log files (`logs/run_simulations.log`,
`logs/task_scheduler_debug.log`) that were not touched as part of this task. No conflict
markers or whitespace issues were introduced by this session's changes.

## Q. Commit SHA

Scaffold commit: `ec0a54b9`. This update commit: see `git log` immediately following this
report's write (this session touched only this report file and ran read-only SQL against
the live database via the Supabase MCP connector — no writes were made).

## R. Production writes

Production writes were made by a process external to this session. This session performed
**zero DB writes** — only read-only SQL (`SELECT` aggregate/invariant checks) via the
Supabase MCP connector, used solely to independently confirm the totals in sections B, K,
M, and O above. As reported by the external process, production writes consisted only of
bounded calls to `refresh_pokemon_card_variant_market_price_intervals(...)` for the
intended Prompt 2 variants — no migrations, no new daily projection rows, no new
projection coverage rows, no cache fabrication, no Base/WOTC/Gym/Neo population. The "no
new projection rows/coverage" portion of this claim is independently confirmed (section M).

## S. Final decision

**GLOBAL_NEWER_INTERVAL_COHORT_ACCEPTED**

Basis: the load-bearing global invariants (total interval row count, zero multiple-open
rows, zero overlapping validity periods, unchanged daily-projection row count) were
independently re-queried against the live production database in this session and match
the externally reported figures exactly. Per-era breakdowns and smoke-test detail are
recorded as externally reported and are internally consistent with the verified
aggregates, but were not independently re-derived per row in this session.

## T. Next recommendation

Proceed to **Prompt 3 of 8** (older/special-cohort interval population), which per the
original spec must begin with the vintage predecessor-identity normalization for
Base/WOTC, Gym, and Neo before those eras are globally populated — do not populate those
eras directly.
