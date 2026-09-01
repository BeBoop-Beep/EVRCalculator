# Effort 1G Resume — corrected-authority range fast path

Outcome: `INTERVAL_FAST_PATH_ACCEPTED`

## A. Branch / HEAD

- Branch: `fix/public-rankings-entitlement-regression`
- Deployment/test commit: `a3ce1911ab0301ecf5111396666384fe45e1bb3d`
- Unrelated pre-existing dirty files were preserved and excluded.

## B. Candidate preservation / commit status

- Preserved candidate commit `ded547c` was already reachable; it was not cherry-picked or duplicated.
- Existing migration deployed unchanged: `supabase/migrations/20260831021617_add_market_explorer_interval_range_fast_path.sql`.
- Added range-boundary and authority-regression tests in commit `a3ce191`.

## C. Corrected-authority predeployment gate

| Gate | Celebrations | Fossil |
|---|---:|---:|
| interval rows | 3,209 | 15,748 |
| physical variants | 25 | 186 |
| interval integrity | PASS | PASS |
| invalid instrument rows | 0 | 0 |
| source reconciliation | 3,400 / 3,400, zero mismatches | 23,560 / 23,560, zero mismatches |
| canonical parity | PASS, 136 dates | N/A |
| sibling independence | N/A | PASS |

The candidate consumes already-published intervals. It does not reference or derive eligibility from `duplicate_alias`, `abstract_identity`, `set_value_eligible`, or `opening_eligible`; publication remains governed by the corrected physical-instrument authority.

## D. GiST range semantics

- Native expression: `daterange(valid_from, valid_to, '[)')`.
- Exactly equivalent to `valid_from <= market_date AND (valid_to IS NULL OR market_date < valid_to)`.
- Tests cover bounded/open intervals, inclusive `valid_from`, exclusive `valid_to`, and dates before/after.
- No `btree_gist`, `btree_gin`, or `hypopg` extension was installed or required.

## E. Predeployment benchmark results

Exact candidate migration was exercised in a transaction and rolled back before deployment.

| Scope | 1F execution ms | candidate execution ms | candidate planning ms | candidate shared hit/read | candidate temp read/write |
|---|---:|---:|---:|---:|---:|
| Celebrations full | 433.230 | 71.041 | 0.041 | 26,449 / 25 | 0 / 0 |
| Celebrations Top 10 | 225.777 | 49.687 | 0.032 | 26,437 / 0 | 0 / 0 |
| Fossil full | 857.503 | 180.178 | 0.031 | 26,890 / 54 | 0 / 0 |
| Fossil Top 10 | 495.037 | 104.177 | 0.034 | 26,414 / 0 | 0 / 0 |
| combined full | 894.830 | 167.379 | 0.031 | 26,969 / 0 | 226 / 226 |
| combined Top 10 | 563.630 | 113.947 | 0.031 | 26,413 / 0 | 0 / 218 |

All candidate samples were below 250 ms and materially faster than deployed 1F.

## F. General-filter regression

Transaction-local candidate output was compared row-for-row with deployed 1F. Differences were zero for rarity, Pokemon, price premium, release age, Pokemon + rarity, set + price segment, rarity Top 10, historical full, and historical Top 10.

## G. Historical-window metadata

For a window ending `2026-07-15`, both unranked (211 constituents) and Top 10 (10 constituents) ended on `2026-07-15`; every returned constituent carried market date `2026-07-15`. Exact `observation_id` metadata resolution therefore remains point-in-time correct and does not leak global-current metadata.

## H. Migration deployed

- Applied the existing forward-only migration `20260831021617_add_market_explorer_interval_range_fast_path.sql`.
- Recorded migration version `20260831021617` as applied.
- Persistent changes were limited to the native GiST index and optimized RPC replacement/grants/comments.
- No interval business rows were inserted, updated, or deleted.

## I. Security

- Exactly one overload with the existing nine-argument signature: PASS.
- `SECURITY INVOKER`: PASS.
- execute: service role `true`; PUBLIC `false`; anon `false`; authenticated `false`.
- GiST index `idx_pokemon_variant_market_intervals_validity_gist` exists.
- Candidate extension count: zero.

## J. Production interval scope

| Scope | rows | variants |
|---|---:|---:|
| Celebrations | 3,209 | 25 |
| Fossil | 15,748 | 186 |
| total | 18,957 | 211 |

Two sets only; invalid instrument rows remain zero. No third set was populated.

## K–L. Postdeployment correctness

- Celebrations canonical parity: PASS, 136 rows, max absolute delta `1.2789769243681803e-13`.
- Celebrations source reconciliation: PASS, 3,400 / 3,400, zero mismatches.
- Celebrations source-series parity: PASS, max absolute delta `1.8474111129762605e-13`.
- Fossil source reconciliation: PASS, 23,560 / 23,560, zero mismatches.
- Fossil source-series parity: PASS, max absolute delta `5.4569682106375694e-12`.
- Fossil sibling independence and interval integrity: PASS.
- Unit/regression suite: 117 passed; no tolerance was weakened.

## M. Direct database performance (five samples, milliseconds)

| Scope | first | samples | median | min | max | class |
|---|---:|---|---:|---:|---:|---|
| Celebrations full | 55.695 | 55.695, 46.128, 45.363, 47.058, 45.577 | 46.128 | 45.363 | 55.695 | PASS_TARGET |
| Celebrations Top 10 | 44.620 | 44.620, 45.110, 41.760, 42.607, 42.321 | 42.607 | 41.760 | 45.110 | PASS_TARGET |
| Fossil full | 141.522 | 141.522, 134.760, 132.705, 136.578, 132.891 | 134.760 | 132.705 | 141.522 | PASS_TARGET |
| Fossil Top 10 | 92.414 | 92.414, 95.619, 95.210, 95.190, 95.284 | 95.210 | 92.414 | 95.619 | PASS_TARGET |
| combined full | 154.733 | 154.733, 153.624, 153.858, 153.485, 152.131 | 153.624 | 152.131 | 154.733 | PASS_TARGET |
| combined Top 10 | 105.817 | 105.817, 106.487, 107.072, 106.183, 107.073 | 106.487 | 105.817 | 107.073 | PASS_TARGET |

## N. API/RPC performance (five samples, milliseconds)

| Scope | first | samples | median | min | max |
|---|---:|---|---:|---:|---:|
| Celebrations full | 194.815 | 194.815, 131.632, 110.557, 108.465, 103.781 | 110.557 | 103.781 | 194.815 |
| Celebrations Top 10 | 103.419 | 103.419, 118.541, 96.017, 139.091, 98.488 | 103.419 | 96.017 | 139.091 |
| Fossil full | 223.087 | 223.087, 252.354, 217.986, 218.778, 219.847 | 219.847 | 217.986 | 252.354 |
| Fossil Top 10 | 149.477 | 149.477, 151.855, 153.377, 149.076, 149.983 | 149.983 | 149.076 | 153.377 |
| combined full | 234.522 | 234.522, 228.076, 227.564, 271.682, 234.449 | 234.449 | 227.564 | 271.682 |
| combined Top 10 | 161.295 | 161.295, 165.709, 162.858, 162.918, 172.529 | 162.918 | 161.295 | 172.529 |

These are end-to-end PostgREST timings and are intentionally separate from server execution.

## O. Current-only timing

Five end-to-end read-only RPC samples were collected for the latest date (`2026-08-28`). All medians are below the preferred 100 ms terminal target even including network/runtime overhead, so a persistent current table is unnecessary.

| Scope | query | median ms | min/max ms | count | basket value |
|---|---|---:|---:|---:|---:|
| Celebrations | current aggregate | 61.000 | 59.111 / 127.540 | 25 | 107.76 |
| Celebrations | Top 25 | 60.515 | 56.847 / 63.311 | 25 | 107.76 |
| Fossil | current aggregate | 83.208 | 78.546 / 123.160 | 186 | 7,024.45 |
| Fossil | Top 25 | 59.065 | 54.820 / 63.296 | 25 | 4,644.72 |
| combined | current aggregate | 83.628 | 79.724 / 86.519 | 211 | 7,132.21 |
| combined | Top 25 | 89.273 | 57.148 / 193.440 | 25 | 4,644.72 |

## P. Shared hits / filter rows before and after

- Prior Fossil B-tree validity expansion: about 143.649 ms; inner scan returned about 173 rows/date and removed about 7,413 rows/date.
- Postdeploy native range expansion: 56.218 ms execution, 1.282 ms planning, 26,518 shared hits, 24,304 output rows; the GiST bitmap returned about 199 candidates/date and the set filter removed 25/date (3,500 total across 140 loops).
- Full-function before/after shared-buffer and temp figures are recorded in section E.

## Q–T. Decision and next workstream

- Classification: every common direct-DB median is `PASS_TARGET` (<250 ms).
- Final decision: `INTERVAL_FAST_PATH_ACCEPTED`.
- Stop further interval architecture work; daily facts are not justified.
- Exact next recommendation: **TERMINAL QUERY PLANNER + PREPARED SERIES + PERSISTENT CUSTOM CACHE**.
- Preserve this next-workstream contract: prepared-series exact equivalence; normalized query fingerprint; persistent custom-series cache; one-date incremental cache update; thundering-herd protection; optimized latest/current reads; unchanged API response contract; future prompt bar maps to the same normalized spec.

## U. Evidence paths

- This report: `artifacts/market_explorer_acceptance/20260830_effort1g_resume/effort1g_resume_range_fast_path.md`
- Migration: `supabase/migrations/20260831021617_add_market_explorer_interval_range_fast_path.sql`
- Contract tests: `backend/tests/unit/db/test_market_explorer_cohort_optimization_migration.py`
