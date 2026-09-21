# Financial RIP V5 - serving architecture closure (Prompt 5D)

## Status

`FINANCIAL_RIP_V5_SERVING_ARCHITECTURE_BLOCKED`

Most of the architecture is closed and tested: one serving-release authority, pointer-driven selection in all five named services, a real V14 Set-page generation, the frontend transport, entitlement allowlists, the four CLI commands, and two static audits. One structural gap remains that I found while auditing constant usage: **the Rankings snapshot builder/publisher is not release-driven** (details under Blocker 1). It is small in code but is a builder rewrite, it was not in the five services named for this bucket, and closing it without a live rehearsal would be guesswork. Nothing was applied to production: no migration, V5 row, V14 publication, Ranking V2 / Best-Open V3 publication or pointer move, and no live Best-Open V3 search was run.

## 1. One serving-release authority

`backend/db/services/rip_release.py` maps the active model version to a frozen `RipReleaseBundle`:

| Release | Financial | Overall | Public contract | Ranking | Best-Open | Target keys |
|---|---|---|---|---|---|---|
| V12 | Financial V4 | Overall V12 | `public_rip_contract_v11` | Ranking V1 | V2 preferred, V1 fallback | `overallRipV12` / `financialRipV4` |
| V14 | Financial V5 | Overall V14 | `public_rip_contract_v12` | `budget_product_ranking_v2` | V3 only | `overallRipV14` / `financialRipV5` |

- The model version comes from the generic ledger's current pointer, then the run it points to (must be `published`). Two reads, once per request/build.
- An unknown model version **fails closed** (`UnknownRipRelease`). An unreadable pointer degrades to a bundle explicitly marked `static_fallback` (V12 identity), never silently.
- Pointer-only flip and rollback are tested: V12 -> V14 -> V12 changes service output, the SELECT shape and the ledger use with no code change and no deletion.

### Transitional contract (the stale-ledger risk from 5C)

The V12 release keeps reading **live V12/V4 storage**. The generic ledger's V12 run (dated 2026-09-10) is *not* the V12 score authority, so 5C blocker 7 no longer gates V12 parity. The V14 release reads the generic ledger plus V5 / Ranking V2 / Best-Open V3. The V12 SELECT never names an unlanded V5 column, so deploying this code ahead of the schema is safe (tested).

## 2. Services

| Service | Change | V12 parity | V14 behaviour |
|---|---|---|---|
| `product_family_rankings_service` | release-aware fields, tie-break, gate, projection; ledger overlay for V14 | 25 existing tests unchanged | V5 tie-break, missing/wrong V5 -> noncanonical, missing ledger product -> unrankable, no V4 fallback |
| `set_rip_service` | target keys from the release | 16 existing tests unchanged | selects `overallRipV14` / contract V12 keys |
| `public_overall_product_rankings_service` | ranking method + Best-Open versions from the release; ranking snapshot method verified | 23 existing tests unchanged | Ranking V2 + Best-Open V3 only; no V1/V2 fallback; V1 snapshot -> `ranking_method_mismatch`; absent -> truthful unavailable |
| `pokemon_sealed_product_detail_service` | Best-Open versions from the release; `releaseModelVersion` on the RIP block; V11 shadow block withheld under V14 (it is built from `overallRipV12` storage) | 35 tests pass (one table allowlist gained the pointer/run read) | V3 only |
| `pokemon_public_snapshot_service` | currentness judged against the active release's identity (`candidate_publication_identity()` under V14) | V12 keeps the historical one-argument check | a V12-built snapshot is stale under V14 and vice versa after rollback |

## 3. V14 Set-page generation

`build_v14_set_page_projections` builds one projection per set only from the already-ranked candidate rows (no second ranking) with the full authority evidence. `validate_v14_set_page_projections` checks duplicates, entity set, model / financial / chase / collector versions, fingerprints, market date, contract V12 readiness, mixed publication-run authority and exact product coverage. `write_v14_candidate` stamps each projection with the run id and marks the generation `validated` only if validation passes, so the run can reach `validated` and still never activates (no pointer write, no promote RPC; tested).

## 4. Frontend transport (no frontend scoring)

- `rankingsClientProjection.mjs` keeps `overallRipV14`, `overallRipV14Composition`, `financialRipV5`.
- `exploreRankingConfig.mjs`: `resolveModeFieldPath` makes the current ranking mode read the V14/V5 block when the target carries it, else V12/V4. Selection only.
- `overallRipExplanationHierarchySelector.mjs`: contract V12 -> contract V11 -> fallback, **contract-driven**; ambient top-level keys are still not an opt-in.
- `financialRipV3Selector.mjs`: the resilience card and the detailed metrics follow the component present: V5 -> Shortfall Resilience, V4 -> Loss Resilience, never both.
- Insights normalizers / adapters and the set-rankings lens pass the new blocks through.
- 5 new node tests. The 7 pre-existing contract-test failures in the wider frontend selection are identical at HEAD (verified against a clean archive) and unrelated.
- **Entitlements:** the V14/V5 keys were added to the same backend allowlists as the blocks they succeed; plan entitlements are unchanged (Plus keeps them, Basic gets none; tested). No frontend access file names these fields.

## 5. CLI

`build-v14`, `ranking-v2`, `best-open-v3`, `readiness` are implemented (dry-run default, `--commit` explicit, `--waive-best-open-v3` is diagnostic only, no command activates or moves a pointer). `--commit` paths require **persisted** ready V5 and otherwise return `not_ready` with a reason and a non-zero exit. `best-open-v3` verifies its Ranking V2 precondition and does not run the hour-long search. `run_v14_stage` was added to the shadow runner for the shared V14 candidate + Set-page stage.

## 6. Audits

`test_release_static_constant_audit.py` classifies every reader of `CANONICAL_OVERALL_RIP_VERSION`, `CANONICAL_FINANCIAL_RIP_VERSION`, `canonical_public_rip_contract_version()` and the target-key selectors as scoring / offline-builder / historical / research / serving (static = marked fallback only), and fails on any unclassified newcomer. A second audit proves the only readers of Ranking / Best-Open snapshots are the two release-driven services and the loaders.

## Blockers

1. **Rankings snapshot builder/publisher is not release-driven.** `explore_rip_statistics_service` stamps `ripWeightsConfig` (Financial, Overall, contract versions) from the static canonical constants and `rankings_publication_lifecycle` selects on the static target key. After a V14 pointer flip the release-aware reader will (correctly, fail closed) treat a V12-built snapshot as stale, but the builder **cannot yet produce a V14-stamped Rankings snapshot** to replace it. The audit names exactly these two files as the known gap. Closing it means release-parameterizing the builder, sourcing Overall from the ledger for V14, and rehearsing a rebuild; that is the first item of Prompt 5E.
2. **Fixture-level, not live, proof for V14 serving.** Service V14 behaviour is proven with fixtures and fakes. It has not run against a real V14 publication because none may exist yet. Sealed detail has no V14-shaped RIP block beyond withholding the V11 shadow.
3. **Live Best-Open V3 search still not run** (out of scope by instruction); the readiness gate with V3 required has therefore not passed.
4. Unchanged from 5C: migrations 047-049 style schema for V5 / Ranking V2 / Best-Open V3 are not applied; nothing is activated.

## Verification notes

- 27 CLI/release/set-page tests, 5 public-rankings tests, 3 detail/snapshot tests, 1 access test, 3 audit tests and 5 node tests were added and pass.
- `test_pokemon_public_snapshot_service.py` fails 158 tests on the local Python 3.8 interpreter with `AttributeError: ... has no attribute 'public_read_client'`; HEAD's service also defines no such name, so this is pre-existing and not caused by this change (a CI run on the matching interpreter is the authority). Modules using `X | None` annotations cannot be collected locally on 3.8 (billing); unrelated.
