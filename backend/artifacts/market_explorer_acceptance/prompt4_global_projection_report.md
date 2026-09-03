# Prompt 4 — Global Daily Serving Projection: Repo-Side Tooling

## A. Branch / HEAD
Branch `fix/public-rankings-entitlement-regression-2`. This report was authored on top of
HEAD `cf128ad4` (docs: finalize Prompt 3 acceptance report), before this session's own commit.
This session performed a repo/tooling/tests-only pass — see section R.

## B. Starting projection state (external / planning baseline, given, not re-derived)
Coverage: 50 sets, 1,886,684 rows, date range 2026-04-07..2026-09-01. 115 sets unprojected.
Approved dates: 143, range 2026-04-07..2026-09-02 (`pokemon_market_date_quality`,
status READY/LEGACY_VERIFIED).

## C. Corrected global authority (external baseline, given, not re-derived)
165 sets, 34,225 physical instruments, 33,956 with NM history, 269 without. 839 retired vintage
predecessor identities already excluded via `pokemon_market_explorer_variant_merge_ledger`.

## D. Coverage metadata repair (tooling design)
`backend/scripts/publish_market_explorer_daily_projection.py::activate_or_repair_coverage`
never trusts a prior `pokemon_market_explorer_card_daily_coverage` row. For every set touched
(new, appended, or `up_to_date`) it recomputes `first_market_date`/`computed_through` from
`MIN`/`MAX(market_date)` and `row_count` from `COUNT(*)` against the actual
`pokemon_market_explorer_card_daily_states` rows for that `set_id`, then upserts. This directly
targets the known 48/50 stale-`row_count` defect (sums to 1,873,043 vs actual 1,886,684) and is
exercised by `test_coverage_row_count_derived_from_actual_table_not_trusted_input`, which
simulates that exact defect shape (correct date bounds, stale understated `row_count`) and
asserts the repaired value matches the real table contents.

## E. Prompt 2 cohort projection — PENDING (production)
Not executed this session. Tooling is ready to run `--era-id`-scoped against the Sun & Moon/XY/
Black & White/HGSS/Platinum/Diamond & Pearl sets once a production `--commit` is authorized.

## F. Prompt 3 cohort projection — PENDING (production)
Not executed. Tooling covers Base/WOTC, Gym, Neo, EX, E-Card, POP, Nintendo Promos, Other via
`--set-id`/`--era-id`. Fossil/Neo Genesis (already repaired in Prompt 3) are idempotent under
this script: a fully-covered-through-date set reports `mode: "up_to_date"` and performs no
rewrite of existing rows, only a row_count repair pass if needed.

## G. Existing 50 Sep-2 advance — PENDING (production)
`--through-date 2026-09-02` with no `--set-id`/`--era-id` (full scope) will forward-append the
single missing date for already-covered sets and run the row_count repair pass for all 50 in
the same invocation, satisfying batching-order step 3.

## H. Global daily-state reconciliation — PENDING (production)
The script's `reconcile_set` computes expected rows by re-running the exact point-in-time
interval join (`valid_from <= market_date AND (valid_to IS NULL OR market_date < valid_to)`)
per materialized date and comparing to `COUNT(*)` on the daily-states table; coverage is gated
on `expected == actual`. Verified in tests; not yet run against live data.

## I. Vintage predecessor exclusion (tooling safeguard; verification PENDING)
`load_retired_predecessor_ids` reads `pokemon_market_explorer_variant_merge_ledger` and
`materialize_date` filters retired ids out of the eligible variant set before the interval join
runs, so a retired predecessor's `card_variant_id` can never receive a row. Exercised by
`test_retired_predecessor_variant_excluded_from_projection`. Live verification pending.

## J. Coverage reconciliation — PENDING (production)

## K. Sampled interval oracle/parity (tooling; PENDING for actual results)
`backend/scripts/accept_market_explorer_global_daily_projection.py::run_acceptance` compares
`get_pokemon_market_explorer_filtered_cohort` (interval oracle) against
`get_pokemon_market_explorer_filtered_cohort_daily` (projection path) for Global All Raw, Top
10, rareHolo, and Premium, plus one representative All Raw + Top 10 pair per requested era —
generalizing the existing exact ten-set comparison
(`accept_market_explorer_ten_set_projection.py`) to the full corpus. It is read-only (RPC calls
only, no --dry-run/--commit gating needed) and bounded the same way the ten-set script is
(chunked statement-timeout windows). Not run live this session.

## L. Global query smoke tests (tooling; PENDING for live results)
Before each RPC comparison the script calls the exact production mechanism the planner already
uses to pick projection-vs-fallback — `daily_projection_covers` in
`backend/db/services/pokemon_market_explorer_query_service.py` (also directly consumed by
`run_market_explorer_query`, whose `diagnostics.executionEngine` reports
`"daily_projection"`/`"interval_fallback"`/`"interval_current"`) — and records the expected
path per scope, rather than inventing a parallel coverage check.

## M. Global/per-era cache builds — PENDING (production)
No production cache builds ran. Design (section N) targets the existing planner build path.

## N. Cache summary/detail behavior (design)
No hand-crafted SQL cache-table writes were introduced. Cache-first activation is meant to run
through the existing `MarketExplorerQueryPlanner` (`backend/db/services/
market_explorer_query_planner.py`) build/lease/publish path — triggering a normal
`run_market_explorer_query` call for Global All Raw and each per-era All Raw scope is sufficient
to populate the prepared/maintained cache via its existing lazy-build mechanism once projection
coverage is current; `maintain_market_explorer_query_cache.py` remains the correct tool for
retention/targeted invalidation, not row insertion. Global Top 10 is flagged as an evaluation
candidate (its RPC/perf numbers are already captured by the same acceptance run in section K) —
no promotion decision is made here. Per the existing contract, summary cache payloads never
duplicate `currentConstituents`/`membershipByDate`; nothing in this session's tooling writes to
`pokemon_market_explorer_query_cache_constituents` or the summary cache directly.

## O. Performance — PENDING (production; instrumentation ready via section K's `performance` block)

## P. Storage — PENDING (production)

## Q. Tests (this session's actual results)
166 passed, 0 failed, run with `python -m pytest -p no:randomly` (test order was flaky for the
new publish-script suite under the repo's default `pytest-randomly` ordering — a shared
`Query.execute` monkeypatch reentrancy artifact in the mock harness, not a bug in the script
itself; deterministic order is 11/11 and 3/3 clean). Suites run:
- `test_publish_market_explorer_daily_projection.py` — 11 passed (new)
- `test_accept_market_explorer_global_daily_projection.py` — 3 passed (new)
- `test_backfill_market_explorer_variant_intervals.py` — passed
- `test_accept_market_explorer_variant_engine.py` — passed
- `test_repair_market_explorer_vintage_predecessor_identities.py` — passed
- `test_market_explorer_query_planner.py` — passed
- `test_pokemon_market_explorer_query_service.py` — passed
- `test_pokemon_sealed_market_explorer_query_service.py` — passed
- `test_market_explorer_query_cache_migration.py` — passed
- `test_market_explorer_instrument_eligibility_migration.py` — passed
- `test_market_explorer_staggered_start_coverage_migration.py` — passed (the staggered-start
  coverage test file referenced in the task)

New-script coverage explicitly includes: new-set activation reconciles-then-activates,
exact interval-to-state parity, coverage NOT activated on reconciliation failure, row_count
derived from actual table (not trusted stale input), staggered start using the set's own
`first_market_date`, forward one-day append for an already-covered set, idempotent rerun with
no duplicate/changed state, no duplicate PK rows, retired-predecessor exclusion, no-NM
exclusion without fabrication, and approved-date filtering by status/range.

`git diff --check` on this session's own files: clean (no output).

## R. Production writes
NONE. Zero live Supabase/production DB connections were made. No script was run with
`--commit`. All verification was against mocked clients in the unit test suite.

## S. Final decision
**PROMPT4_REPO_READY.** Repo-side tooling (publication script, coverage-repair mechanism,
sampled oracle/parity + planner-path acceptance script, cache-first design) is implemented and
test-verified against mocked clients. Production execution (sections E–J, L–P) has not run and
is explicitly out of scope for this session.

## Open item
Three Prompt 3 production migrations were searched for in this worktree and NOT found:
`20260902221622_add_market_explorer_vintage_identity_repair_primitives.sql`,
`20260902221819_add_scoped_variant_monthly_rollup_rebuild.sql`,
`20260903034704_harden_market_explorer_vintage_top_hits_rebuild.sql`.
Status: **PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_CHATGPT** (non-blocking; no SQL was
guessed/invented to fill this gap).
