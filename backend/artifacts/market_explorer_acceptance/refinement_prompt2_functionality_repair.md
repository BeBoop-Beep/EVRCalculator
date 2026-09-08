# Market Explorer Refinement — Prompt 2 Functionality Repair

## A. Branch / starting HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- Required Prompt-1 closure ancestor: `8ca8418fc69f98518ff0b5fb30785d99953a5ace`
- Actual starting HEAD: `52bee8aa4c263b93b9d4d2c00e2878458b20531d` (the required HEAD plus an unrelated committed collector update, preserved).

## B. Prompt-1 migration source normalization

Production `supabase_migrations.schema_migrations.statements` was queried for all three rows. Repository files now use the actual ledger version followed by the ledger name. The proposed-version files were renamed, leaving no second runnable copy. SHA-256 comparison proved each production statement equals the repository bytes plus the migration API's trailing CRLF:

- `20260908052614_20260907200000_add_market_explorer_exact_instrument_foundation.sql`: `23d8c005...04ae4b`
- `20260908053032_20260908054000_fix_market_explorer_v2_exact_variant_predicates.sql`: `abffbb9c...a64a83`
- `20260908053340_20260908060000_add_bounded_sealed_instrument_search_rpc.sql`: `8a9bc6cb...46ae91`

Production schema and migration history were not modified.

## C. Single-item cache reuse

Fingerprint `caa5a82b065b4fe113c0e6a8f145d3720ba074c3ac99c9730abd9ae09afb8186` remains `ready`. The normal persistent summary-read RPC returned its row in 8.295 ms (`EXPLAIN ANALYZE`), proving reuse rather than another approximately four-second build. The earlier slow repeat was test sequencing.

## D. Asset switching

Raw and Sealed disclosures are controlled by the active draft asset. Clicking either header selects and opens it and closes the other in one action. `Edit this asset`, `All Raw Cards`, and `All Sealed` actions were removed from the rendered hierarchy.

## E. Initial-load behavior

Raw Cards is the initial active/open asset. Its panel renders an explicit canonical-filter loading status and fills from the existing shared options request when ready. Empty filter arrays retain All semantics.

## F. Screens behavior

Screens are inside the active asset context. Template clicks immediately apply to the draft and show applied state; there is no second handoff. Ranked screens immediately reveal Global prepared rankings, and result clicks add the selected prepared market. Sealed excludes card-only screens.

## G. Scope semantics

Ordinary templates preserve current Era/Set scope, including multiple selections and Global scope. Only Top 10 in Selected Set validates exactly one set: zero and multiple selections receive distinct inline guidance. Prompt-1 explicit membership and physical instrument IDs survive template refinement.

## H. Composition relocation

Composition now lives within the active asset. Cards use All/Top N chase language; Sealed uses All Products/Top N by Price. Both still feed the shared `mode = all | chase` query contract.

## I. Reference-market relocation

Per-Set Chase is a compact Raw Cards Reference Market control. It remains an independent prepared series and never mutates the draft. Sealed renders no empty equivalent.

## J. Benchmark-jump root cause/fix

The former independent Benchmarks disclosure mounted below changing Screen content and had unrelated local disclosure state, creating rail-height/layout shifts. The reference control now stays in the Raw asset panel; its callback only toggles prepared selection. No anchor, hash, `scrollIntoView`, focus transfer, or programmatic scroll remains in this interaction.

## K. Card constituent movement architecture

The constituent endpoint enriches only its current page (maximum 100 physical `cardVariantId` values). It resolves published dates once, reads all required baseline rows in one V2 query, and performs at most one V1 fallback query for dates outside V2 retention. Current cache payloads are unchanged. Missing observations return null through the existing movement utility. All four windows ship together, so tab changes remain client-only.

## L. Movement live evidence

Production materialized history for exact variant `10ec7d5f-20cc-465a-abf3-5dfc33179767`, current date 2026-09-06:

- 1D: -9.3750% (baseline 2026-09-05)
- 7D: +16.0000% (published baseline 2026-08-28)
- 30D: -17.1429% (baseline 2026-08-07)
- 3M: +3.5714% (baseline 2026-06-08)

The new page enricher unit tests cover all windows, null/unavailable behavior, exact-item identity, one V2 batch, and one optional V1 batch.

## M. Comparison-language changes

Relative copy states the timeframe, both endpoint returns, and explicitly calls the spread a percentage-point difference. Query naming now yields concise labels such as `All Dragonite Cards`; display naming remains outside query keys/fingerprints.

## N. Prompt-1 regression

Explicit 1..25 normalization, physical card/sealed IDs, generic cache identity, instrument search, Premium authorization, and the six pinned v3 filter fingerprints remain covered. No fingerprint semantics changed.

## O. Tests/build/lint

- Backend focused suite: 226 passed.
- Frontend Market Explorer pure logic, API proxy, query builder contract, paging, and constituent components: 76 passed.
- A separate constituent/auth run: 34 relevant tests passed; only the known unrelated `AuthContext.js` JSX-loader failure occurred.
- Affected JSX: esbuild production syntax/bundle check passed.
- Python `py_compile`: passed.
- `git diff --check`: passed.
- Next production build entered optimized compilation but made no progress and was stopped after a bounded wait.
- Direct ESLint 9 cannot run because this repository still has legacy ESLint config and no `eslint.config.*`.

## P. Genuine blockers

No Prompt-2 source blocker. Browser automation was unavailable, and the repository-wide frontend build/lint tooling limitations above remain unrelated infrastructure issues explicitly excluded from this repair.

## Q. Prompt-3 readiness

Prompt 2 is source-complete and verified. Prompt 3 may begin only after this handoff is accepted; it was not started automatically.

## R. Commit SHA

- Functionality commit: `a8c87d6a` (`fix(market-explorer): repair builder and constituent movement`)
- Acceptance-report commit: recorded in the final handoff.
