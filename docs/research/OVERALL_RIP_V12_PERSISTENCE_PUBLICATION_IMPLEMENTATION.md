# Overall RIP V12 — Persistence & Publication (Code-Only, Shadow Lineage)

**Label: `OVERALL_RIP_V12_PERSISTENCE_PUBLICATION_IMPLEMENTED_CODE_ONLY`**

This is a code implementation pass ("Prompt 3") building the persistence,
finalization wiring, read-model, publication-readiness support, snapshot
wiring, and public contract for Overall RIP V12 — the scoring function
Prompt 2 already implemented in `compute_overall_rip_v12`
(`backend/desirability/weighted_rip.py`). **V10 remains canonical. V12 is
implemented as parallel/shadow lineage only. No production migration
applied. No production V12 rows backfilled. No deployment/publication
performed.**

## V12 identity

`overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
— unchanged from Prompt 2, reused verbatim throughout this pass.

## New public-contract identity

`public_rip_contract_v11` (`backend/desirability/public_rip_contract_v11.py`).
Contract numbering is a SEPARATE lineage from Overall RIP model numbering: the
highest existing contract file was `public_rip_contract_v10.py`, so the next
honest, unused contract identity is V11 — NOT "v12" — even though it carries
the V12 Overall RIP model. `canonical_public_rip_contract_version()`
(`backend/desirability/scoring_config.py`) still resolves to
`PUBLIC_RIP_CONTRACT_V10_VERSION`; V11 is a new, additive, non-canonical key
(`publicRipContractV11`).

## Schema/migration decision

**Created, NOT applied.** New file:
`backend/db/migrations/20260902000000_add_sealed_product_overall_rip_v12.sql`.

Discovery: the repository's migration numbering has moved from the old
sequential `073`/`077`-style numbers to timestamp-based filenames (highest
found in the working tree at start of this pass:
`20260829170301_harden_sealed_market_breadth_snapshot.sql`; a concurrent,
untouched migration `20260902031454_push_down_market_explorer_daily_scope_filters.sql`
was also present but is LATER than the number chosen here). `20260902000000`
was picked as a clearly free, correctly-ordered timestamp not colliding with
any existing or concurrent file.

Migration 077 (`pokemon_set_chase_accessibility_snapshot_latest`) was
confirmed still present, confirmed still unapplied (per its own header
comment), and was **not modified** — Chase Accessibility already has its own
canonical set-level persistence there, so V12 does NOT duplicate raw
Accessibility storage. The new migration adds five columns to
`simulation_sealed_product_results` (the same table migration 073 used for
V10), following 073's own pattern exactly: `overall_rip_v12_score NUMERIC`
(CHECK 0–100), `overall_rip_v12_version TEXT`, `overall_rip_v12_rankable
BOOLEAN`, `overall_rip_v12_status TEXT`, `overall_rip_v12_payload JSONB`. All
nullable, no default, no destructive DDL, wrapped in `BEGIN; … COMMIT;`.
`overall_rip_v12_status` exists (unlike V10, which has none) because V12's own
compute function returns distinct `ready` / `unavailable_missing_input`
statuses, and the finalizer adds a third, `unavailable_authority_mismatch` —
collapsing these into "score is null" would lose the distinction between
"never computed" and "computed and explicitly refused."

## Finalization wiring

**File:** `backend/db/services/sealed_product_rip_finalization_service.py` —
the REAL, production batch finalization path (confirmed by trace: it is
called from the daily opening-publication cohort finalization, joins
Financial RIP V3/V4 + Collector Appeal V5, and is the same place V9/V10 are
computed today).

- `_overall_rip_v12_for(row, appeal_score, accessibility_row, *,
  expected_run_id)` — new function. Resolves Chase Accessibility from a
  pre-batched lookup, enforces authority coherence and version alignment
  (see below), then calls `compute_overall_rip_v12`. Never reimplements the
  `100*A/(A+.002)` transform.
- `_enrichment_for(row, appeal, *, accessibility_row=None,
  expected_run_id=None)` — extended (additively; both new kwargs default to
  `None` so the existing call signature/behavior for V9/V10 is preserved
  byte-for-byte, confirmed by the pre-existing
  `test_sealed_product_rip_finalization_service_v10.py` still passing
  unmodified) to also compute and return the five `overall_rip_v12_*`
  enrichment fields.
- `finalize_sealed_product_rip(...)` — extended with an
  `accessibility_reader_fn` injection point (default: a real batch reader over
  `chase_accessibility_service.read_chase_accessibility_snapshots_for_sets`),
  called **exactly once per finalization run**, before the row loop, for the
  whole cohort's `set_id`s. No V12 code path executes inside the per-row loop
  that issues a new query.
- **File:** `backend/db/services/explore_rip_statistics_service.py` — the
  Explore/set-statistics cohort service that also computes `overallRipV10`
  in-memory per target. Extended additively: one batch
  `read_chase_accessibility_snapshots_for_sets` call before the per-target
  loop, then `target["overallRipV12"] = compute_overall_rip_v12(...)` and
  `target["chaseAccessibility"] = project_chase_accessibility(...)` inside the
  loop, using the SAME authority rule as the finalizer (target's own
  `calculation_run_id`). A `_rank_overall_rip_v12` explicit accessor was added
  alongside `_rank_overall_rip_v10` for read-model parity — not registered in
  any active ranking list.

## Authority-coherence rule (Phase 4 hard gate — satisfied, not bypassed)

Chase Accessibility is set-level, one row per `set_id`
(`pokemon_set_chase_accessibility_snapshot_latest`, migration 077), carrying
its own `calculation_run_id`. The rule implemented: **an Accessibility row is
only accepted for V12 if its own `calculation_run_id` exactly equals the SAME
`expected_run_id` the caller already resolved as the coherent cohort run for
that same product row/target** — in the finalizer this is literally the same
`run_id_by_set_id[set_id]` value already used to decide whether the PRODUCT
ROW itself belongs to the current cohort (the existing
`row_outside_current_cohort` skip logic); in the Explore service it is the
target's own `calculation_run_id`. A row from ANY other run — including a
fully `ready`, numerically valid row from a stale or unrelated run — is
rejected with an explicit `unavailable_authority_mismatch` status, never
silently accepted as "the latest available." This is exercised directly by
`test_authority_mismatch_rejected_even_though_row_is_ready_and_valid`, which
constructs exactly that adversarial case (a valid, `ready`, wrong-run row) and
asserts rejection. No new "run authority" abstraction was invented — this
reuses the exact same `calculation_run_id` map the opening-simulation gate
already produces and the product-row cohort check already consumes.

## Version-alignment checks (Phase 13)

`_overall_rip_v12_for` refuses (returns `unavailable_missing_input`, never a
coerced read) when: `row["financial_rip_v4_version"] !=
OVERALL_RIP_V12_REQUIRED_FINANCIAL_VERSION` (i.e. not exactly Financial RIP
V4); the Accessibility row's `version` field is not exactly
`CHASE_ACCESSIBILITY_VERSION` (`chase_accessibility_v1_hc_value_squared_modeled_probability`).
Collector Appeal alignment is enforced upstream and reused, not reimplemented:
`interpret_collector_appeal_payload` (existing, unmodified) already returns
`score=None` for any non-canonical Collector Appeal version, and V12 shares
that SAME `appeal_score` variable with V9/V10 — a wrong Collector version
therefore already yields V12 "missing input" through the existing gate.
Covered by `test_wrong_financial_version_is_rejected_even_with_valid_score`
and `test_wrong_accessibility_version_is_rejected_even_with_valid_value`.

## Persistence fields

On `public.simulation_sealed_product_results` (additive, migration created
but not applied):

| Column | Type | Notes |
|---|---|---|
| `overall_rip_v12_score` | `NUMERIC` | CHECK 0–100, nullable |
| `overall_rip_v12_version` | `TEXT` | nullable |
| `overall_rip_v12_rankable` | `BOOLEAN` | nullable |
| `overall_rip_v12_status` | `TEXT` | `ready` / `unavailable_missing_input` / `unavailable_authority_mismatch` |
| `overall_rip_v12_payload` | `JSONB` | full `compute_overall_rip_v12` result |

`backend/db/repositories/sealed_product_results_repository.py`:
`_SELECT_FIELDS` and `ENRICHMENT_FIELDS` both extended additively with the
five columns above. `update_sealed_product_enrichment` still refuses any
column not in `ENRICHMENT_FIELDS` (unchanged refusal behavior, now with a
larger allow-list). V10's own six columns are byte-for-byte untouched.

## Read-model wiring

- `backend/db/services/chase_accessibility_service.py` —
  `read_chase_accessibility_snapshots_for_sets(*, set_ids, client)`: new
  batch reader, ONE paged query for an arbitrary-size cohort (keyed by
  `set_id`), the read-model counterpart to the existing single-set
  `read_chase_accessibility_snapshot`.
- `explore_rip_statistics_service.py`: `target["overallRipV12"]`,
  `target["chaseAccessibility"]`, `_rank_overall_rip_v12(row)` — explicit,
  version-suffixed accessors, exactly the convention `overallRipV10` /
  `_rank_overall_rip_v10` already use. No generic/canonical accessor was
  changed to resolve V12.

## Publication readiness

`DEFERRED_CHASE_ACCESSIBILITY_INTEGRITY` and `publication_integrity_failures`
(`backend/db/services/chase_accessibility_service.py`, consumed by
`rankings_publication_lifecycle.py`) were read and reused conceptually
(the SAME `calculation_run_id`-coherence discipline they already enforce for
the Accessibility publication gate is the discipline V12's finalizer-level
authority check applies) but were **not modified** — no second validator was
built. V10 publication readiness is completely unaffected: V12's absence,
mismatch, or unavailability is computed and stored on the SAME product row
alongside V9/V10 without altering the `require_verified_cohort` /
`resolve_finalization_cohort` control flow that gates whether ANY enrichment
(V9, V10, or V12) runs at all. A genuinely broader "V12 shadow readiness"
condition (Financial V4 + Collector V5 + Accessibility V1 all correct version,
mapped HC mass ≥ 0.99, coherent authority, V12 rankable) is expressible today
by combining the existing `publication_integrity_failures` output with the
per-row `overall_rip_v12_status`/`overall_rip_v12_rankable` fields this pass
adds — it was intentionally NOT wired into an active gate, since flipping any
publication switch toward V12 is explicitly out of scope.

## Snapshot/API behavior

`publicRipContractV11` (additive key) carries: `overallRipV12` (score /
status / statusReason / rankable / version / components / missingInputs /
`canonical: false`), `chaseAccessibility` (PUBLIC RAW value/percent/status/
version, plus Chase Depth and mapped HC mass as diagnostics only, plus the
locked public copy strings), and `overallRipV12Composition` (the three named
inputs and their validated weights). It embeds
`publicRipContractV10` verbatim under its own key so a V11 consumer never has
to fetch V10 separately. `overallRipV10`, `publicRipContractV10`, and every
prior contract key are unchanged. Scale separation between the PUBLIC RAW
Chase Accessibility (`A_raw`, e.g. `0.002`) and the Overall-scoring `A_score`
(e.g. `50.0`) is preserved and tested (`test_raw_accessibility_distinct_from_a_score`).

**Payload size:** measured a representative additive payload (`overallRipV12`
+ `chaseAccessibility` + a minimal `publicRipContractV11` marker) at ≈1.16 KB
per target; for the Explore service's `MAX_TARGETS_LIMIT` (200 targets) that
is ≈227 KB added to a cohort-wide response. No per-target DB read was added —
both new batch readers (`read_chase_accessibility_snapshots_for_sets` in the
finalizer and in the Explore service) run exactly once per invocation,
confirmed by `test_finalize_sealed_product_rip_batches_accessibility_reads_once`
(asserts `calls["count"] == 1` for 3 product rows across 1 set) and by static
structural review of `explore_rip_statistics_service.py` (the batch call sits
above the `for target in targets:` loop, not inside it).

## Unsupported-set semantics

A set with no pull model, or whose Accessibility row is missing/not-`ready`,
never receives a synthesized zero: `accessibility_row is None` or
`status != "ready"` routes to `compute_overall_rip_v12(financial, None,
appeal)`, which the underlying transform (`chase_accessibility_overall_score`)
already refuses for a `None`/missing `A_raw`, producing `score: None,
rankable: False, status: "unavailable_missing_input"`. Verified by
`test_v12_never_synthesizes_zero_for_missing_accessibility` and by Prompt 2's
own `chase_accessibility_overall_score` tests (never coerces to 0.0).

## Canonical selector status

**Unchanged.** `CANONICAL_OVERALL_RIP_VERSION` in
`backend/desirability/scoring_config.py` still resolves to
`OVERALL_RIP_V10_VERSION`. Not edited by this pass. V10's own regression
suite (`test_overall_rip_v10_and_financial_v4_integration.py`,
`test_sealed_product_rip_finalization_service_v10.py`) was re-run fresh in
this session and passes unmodified.

## V11 (historical, Core-K-based) status

**Untouched.** `overall_rip_v11_83_financial_v4_11_collector_appeal_v5_06_chase_opportunity_v1`
and `test_overall_rip_v11.py` were re-run fresh and pass unmodified; no file
implementing that lineage was edited by this pass.

## Tests added and run (this session)

- `backend/tests/unit/db/test_sealed_product_rip_finalization_service_v12.py`
  — 12 tests (finalization exactness, missing-input, authority coherence
  including the deliberate "stale-but-valid-row exploit" attempt, version
  alignment for Financial/Accessibility, no-N+1 batch-read assertion,
  V9/V10-unchanged regression).
- `backend/tests/unit/db/services/test_chase_accessibility_service.py` — 4
  new tests appended for `read_chase_accessibility_snapshots_for_sets`
  (batch shape, single-query-per-batch, empty input, 1000-row paging); full
  file now 21 tests, all passing.
- `backend/tests/unit/desirability/test_public_rip_contract_v11.py` — 10
  tests (non-canonical, V10 embedding, raw-vs-A_score scale separation, exact
  composition weights/inputs, shadow-marked, Chase Depth diagnostic-only, no
  ECE in source, no "chance of a chase" in output, locked copy strings,
  null-not-zero on unavailable).
- `backend/tests/unit/db/test_overall_rip_v12_migration_contract.py` — 9
  tests (file existence/uniqueness, exact 5 new columns, nullable/no-default,
  CHECK constraint text, table-scope-only, V10/V11 columns untouched,
  transaction wrapping, "not applied" self-declaration, migration 073
  untouched).

**Run results:**
- The four new test files together: **35 passed, 0 failed.**
- Combined with the pre-existing V10/V11/V12-scoring regression suites
  (`test_overall_rip_v12_chase_accessibility.py`,
  `test_overall_rip_v10_and_financial_v4_integration.py`,
  `test_overall_rip_v11.py`,
  `test_sealed_product_rip_finalization_service_v10.py`): **144 passed, 0
  failed.**
- Full `backend/tests/unit/desirability/` suite: **1926 passed, 73 failed** —
  all 73 failures confined to the pre-existing, untouched
  `test_treatment_market_prestige_v3_round20.py` through `round24.py` (an
  unrelated research track; `git status` confirms zero diff on these files;
  Prompt 2's own record already documented this same file set failing at 51
  cases before this pass — the count grew due to unrelated concurrent branch
  activity, not this change).
- `backend/tests/unit/db/` (excluding pre-existing, unrelated
  environment-broken files: `test_billing_service*.py`,
  `test_frontend_proxy_service_auth.py`,
  `test_frontend_proxy_service_profile_concurrency.py`,
  `test_public_profile_collection_regression.py`,
  `test_supabase_auth_exchange.py` — all fail on `ModuleNotFoundError: No
  module named 'jwt'` / an unrelated `TypeError`, confirmed present before
  and independent of this change): 177 failures, confirmed by inspection to
  be entirely pre-existing/concurrent-branch state (`test_pokemon_public_snapshot_service.py`
  fails on a missing `public_read_client` module attribute in a file this
  pass never touched; `test_billing_migration_order.py` and
  `test_public_rip_rpc_v8_migration_sql.py` fail against migrations later
  than and unrelated to `20260902000000_add_sealed_product_overall_rip_v12.sql`,
  confirmed by grep that the new migration defines neither a billing
  migration nor `publish_pokemon_public_rip_leaderboard`).

## Performance / no-N+1 audit

Both new batch paths (`sealed_product_rip_finalization_service.py`'s
`accessibility_reader_fn` call and `explore_rip_statistics_service.py`'s
`read_chase_accessibility_snapshots_for_sets` call) execute exactly once per
run, positioned above their respective per-row/per-target loops. Verified
structurally by code placement and directly by
`test_finalize_sealed_product_rip_batches_accessibility_reads_once`
(3 product rows across 1 set → `calls["count"] == 1`).

## Regression search (Phase 16)

Grepped `backend/desirability`, `backend/db/services`,
`backend/db/repositories` for `overall_rip_v12` / `OVERALL_RIP_V12` (all
hits classified as this pass's own additive code — no other file references
it) and for `chase_depth` / `effective_pull_rate` / `product_market_cost` /
`Core K` / `chase_opportunity` / `economic_chase_efficiency` /
`product_chase_efficiency` inside the four files this pass edited/added
(`sealed_product_rip_finalization_service.py`, `public_rip_contract_v11.py`,
`explore_rip_statistics_service.py`) — zero hits outside comments. The V12
path takes no Core K, no Chase Opportunity, no ECE, no Product Chase
Efficiency, no Chase Depth as a scoring input (Chase Depth appears only in
`chaseAccessibility.chaseDepth`, explicitly diagnostic, tested by
`test_chase_depth_present_only_as_diagnostic_never_in_composition_inputs`),
no direct `effective_pull_rate` used as a probability, and no
`product_market_cost` dependency.

## Migration/deployment/publication/backfill status

**None applied, none performed.** The migration file exists on disk only.
No `ALTER TABLE` was executed against any database. No canonical selector was
flipped. No ranking order changed. No snapshot, leaderboard, or publication
contract was cut over. No V12 row was backfilled anywhere.

## Files changed

- `backend/db/migrations/20260902000000_add_sealed_product_overall_rip_v12.sql` (new)
- `backend/db/repositories/sealed_product_results_repository.py` (additive)
- `backend/db/services/chase_accessibility_service.py` (additive: batch reader)
- `backend/db/services/sealed_product_rip_finalization_service.py` (additive: V12 wiring)
- `backend/db/services/explore_rip_statistics_service.py` (additive: V12 + contract wiring)
- `backend/desirability/public_rip_contract_v11.py` (new)
- `backend/tests/unit/db/test_sealed_product_rip_finalization_service_v12.py` (new)
- `backend/tests/unit/db/services/test_chase_accessibility_service.py` (additive tests + `in_` fake-client method)
- `backend/tests/unit/db/test_overall_rip_v12_migration_contract.py` (new)
- `backend/tests/unit/desirability/test_public_rip_contract_v11.py` (new)
- `docs/research/OVERALL_RIP_V12_PERSISTENCE_PUBLICATION_IMPLEMENTATION.md` (this file)

## Production canonical status

**V10 remains canonical. V12 is implemented as parallel/shadow lineage only.
No production migration applied. No production V12 rows backfilled. No
deployment/publication performed.**
