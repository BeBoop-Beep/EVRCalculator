# Financial RIP V5 - exact-artifact finalization, contract V12 and backend publication transport (Prompt 5B)

## Status

`FINANCIAL_RIP_V5_BACKEND_PUBLICATION_TRANSPORT_COMPLETE`

Global cutover status is unchanged: **not READY**. Nothing was applied to production: no migration, no V5 row, no V14 publication row, no pointer or selector change. Canonical stays Financial V4 / Overall V12 / `public_rip_contract_v11`. The model, formula and weights were not touched.

## What was built

| Area | Module | State |
|---|---|---|
| Exact-artifact Financial V5 finalizer | `db/services/sealed_product_financial_v5_finalization_service.py` | implemented, unit-proven; not yet run on production artifacts (needs the V5 schema) |
| Overall V14 per-row finalization | same module (`overall_rip_v14_for`) | implemented, unit-proven |
| Inactive V14 candidate in the generic ledger | `db/services/overall_v14_candidate_publication.py` | implemented (rankings generation); set-page generation is a seam, not built |
| Public Contract V12 | `desirability/public_rip_contract_v12.py` | implemented, registered, **not canonical** |
| Identity transport | `public_rip_publication_contract.py`, `pokemon_explore_rankings_publisher.py` | V14 / contract-V12 registered in both maps; runtime still resolves V12 / V11 |
| Candidate readiness (separate from canonical) | `db/services/v5_v14_candidate_readiness.py` + delegate in `rankings_publication_lifecycle.py` | implemented |
| Semantic staleness for a candidate | `evaluate_leaderboard_staleness(expected_identity=...)` | optional parameter, default unchanged |
| Generic active-reader adapter | `overall_versioned_publication_service.active_overall_public_index` | implemented; reader-level parity proven |
| Explicit Ranking V2 orchestration | `db/services/budget_ranking_v2_orchestration.py` | module API, non-default |
| Explicit Best-Open V3 orchestration | `db/services/budget_best_open_v3_orchestration.py` | module API, non-default |
| Future sequence as validated data | `db/services/v5_publication_sequence.py` | implemented; the daily orchestrator does not import it |

## Exact-artifact finalization

Chain per row: opening-simulation gate -> exact current `calculation_run_id` -> exact artifact (**loaded once per run**) -> product distribution (**built once per run for the run's whole pack-count set**) -> deterministic guaranteed offset -> lineage gates -> `build_financial_rip_v5` -> V5-only write through the dedicated repository path. No V4 projection, no summary reconstruction, no substitute run.

**A finding that shaped the design.** The bootstrap draws one index block backing every requested pack count, so a count's vector depends on the WHOLE set of counts requested together. The finalizer therefore requests exactly what Stage 1 requested (the counts of ALL the run's persisted rows, including rows it later refuses), mirroring `opening_economics_v3`. My first test fixtures got this wrong and the lineage gate caught it as a distribution mismatch, which is the gate working as intended.

**Lineage gates (each fails closed to a row-level `unavailable`, never a fabricated score):** artifact loads and its run matches; outcome count equals `simulation_count`; the regenerated vector reproduces persisted EV / median / P05 / P95 / P99; when a stored Financial V4 exists, recomputing V4 on the same vector and cost reproduces it (proves seed identity); the V5 payload validates and reconstructs its own Shortfall Resilience.

**Row-level vs cohort-level.** One unavailable row leaves only that row unavailable and never touches its V4/V12 columns. `cohortComplete` is true only if every row of every current run is ready, and `assert_v5_cohort_complete` is the gate a V14 publication must pass, so a partial cohort cannot masquerade as complete.

## Overall V14

Computed per row by `overall_rip_v14_for` with the V12 finalizer's authority discipline: requires the row's own ready Financial V5 (never V4), a Chase Accessibility row from the **same calculation run** (a stale-run row is refused, not "latest available"), exact Chase and Collector Appeal V5 identities, no renormalization, no fallback. It is materialized only in the generic ledger, not on sealed rows. The candidate writer only ever reaches `staged`/`validated`, never writes `pokemon_overall_rip_current_publication`, never calls the promote RPC (asserted by a recording fake). A partial V14 cohort cannot validate. A run is not promotable until a set-page generation exists.

## Public Contract V12

Identity `public_rip_contract_v12`. The real V11 contract is embedded **verbatim** under `publicRipContractV11` (built from the untouched target, as V11 embeds V10). Explicit `financialRipV5` and `overallRipV14` blocks fail closed on wrong versions, V4-shaped components, or score/rank inconsistency; composition discloses Financial V5 / Chase V1 / Collector V5 at 86/4/10. **Design decision:** the generic `overallRip` / `financialRip` slots are forwarded by pure re-keying of the explicit blocks, deliberately NOT through the V10 staging chain, because that chain stamps V4 identities into the generic financial slot and would mislabel V5. Public vocabulary is unchanged; the internal component term appears only inside `financialRipV5.components`.

## Backend generic Overall transport (limits stated plainly)

The generic reader was already model-independent. Proven with fixtures: while the active publication is V12 it reproduces the legacy V12 score, rank, tier and version; with a V14 fixture the same code returns V14 with no model-specific field family; mixed authority and score-without-rank are refused; reading never writes. **Not done:** rewiring the concrete services (product-family rankings, public overall product rankings, sealed-product detail, public snapshot, Set RIP) onto `active_overall_public_index`. Parity is proven at the reader, not per service, and rewiring against a live V12 ledger belongs with the 5C dry run.

## Readiness, staleness, monitors

`candidateReady` requires: exact V5 on every row, V14 complete and coherent, Ranking V2 complete, Best-Open V3 bound to the exact Ranking V2 snapshot (id, timestamp, fingerprint) unless explicitly waived, contract V12 blocks ready, identity coherence. `canonicalImpact` is always `"none"`; canonical identity is reported only to make the separation visible, and neither state is derived from the other. Audit of monitoring surfaces: the staleness refresher and Sentinel-style checks read the canonical selectors (`canonical_publication_identity`), so they follow a future flip without edits; only `evaluate_leaderboard_staleness` needed a candidate hook. Candidate absence is not an alert while inactive.

## Ranking V2 / Best-Open V3 orchestration

Ranking V2: requires an explicit `budget_product_ranking_v2` request (a V1 request is never relabelled), requires ready V5 source rows, reports a not-landed V5 schema truthfully (`financial_v5_schema_not_landed`), loads each artifact once, resolves Chase once, builds the payload with the builders validated on real Postgres, and commits only through the versioned RPC. Best-Open V3: requires a live Ranking V2 snapshot ranked under V14, picks each axis benchmark from its own authority, currentness is method-aware (V1/V2 cannot mask or satisfy V3), refuses non-exact axis results. **Not done:** CLI entry points; these are importable module APIs, and the existing builders/publishers/schedulers do not import them (asserted).

## Tests and baseline

- New: 102 tests across finalizer (14), V14 + candidate (13), contract V12 + V11 (28), transport + readiness (23), generic reader parity (6), orchestration (14), sequence (4).
- Baseline comparison: 75 affected suites, pristine `git archive` of HEAD vs the modified tree. After: 212 failed / 1321 passed; baseline 209 failed / 1282 passed / 39 collection errors. The exact failing-name diff shows three names failing only after: two "protected files unmodified" guards in `test_stage1_sealed_product_finalization.py` (they diff `sealed_product_distribution.py`, which another effort committed) and `test_scheduled_publication_contract.py::test_the_canonical_versions_named_in_the_message_are_the_real_ones` (reads `infra/local/run_simulations.sh`; the baseline copy lacked `infra/`, so it errored there). **None of my modified files, and none of the files those tests inspect, overlap.** This is demonstrated by file-set disjointness, not by re-running those three on an untouched tree. The other ~209 failures are the shared repository's existing failures (branch/ancestry guards, unmocked Supabase calls, etc.).

## Remaining before cutover (Prompt 5C and beyond)

Frontend/version transport; controlled schema landing (V5 sealed columns, Ranking V2, Best-Open V2 then V3); running the finalizer against real artifacts and the current-cohort dry run (this is where exact-lineage parity to stored V4 is actually confirmed on production data); building the V14 set-page generation projections; rewiring services onto the generic reader; CLI wrappers for the two orchestrators; the final pre-cutover report and explicit activation.
