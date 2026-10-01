# Rankings Follow-up B1 - Acceptance Matrix

| # | Requirement | Evidence |
|---|---|---|
| 1-6 | Benchmark C at 5.0, neutral boundaries, S/A top tiers, bottom-quartile F, tiny-cohort D, absolute boundaries | `backend/tests/unit/rankings/test_public_relative.py` |
| 7-8 | Main badge not hardcoded purple; border from supplied tier | `RankingsFollowupB1.contract.test.mjs`, `RankingsScorePrimitives.contract.test.mjs` |
| 9-11 | Component primitive uses own tier; no caption; no arrow | `RankingsFollowupB1.contract.test.mjs` |
| 12-17 | Primary, pill, Product family, graph entity, graph window, Cards selectors green + white | `RankingsFollowupB1.contract.test.mjs`, `RankingsBucket2Presentation.contract.test.mjs` |
| 18 | No yellow active styling | `RankingsFollowupB1.contract.test.mjs` |
| 19 | Generic `primary`/`pill` variants unchanged | `RankingsFollowupB1.contract.test.mjs` |
| 20 | B1-B7 access/security contracts | Rankings/Card/Product frontend contract suites and backend access tests (see results in the hand-off) |

## Closure results
| Check | Result |
|---|---|
| Backend: `test_public_relative` (benchmark + absolute boundaries) | 72 passed |
| Backend: chase efficiency contract (absolute 1/10/25/50/75% boundaries incl. 4,852 cohort) + new Explore RIP stats tier test | 29 passed |
| Backend: rankings redesign, era/set strength, release serving, lens projection, rankings dir | 120 passed after updating one stale expectation |
| Backend: paid-boundary, homepage benchmark, plan access, public RIP standardization | 83 passed |
| Backend: `test_explore_rip_statistics_service.py` | 52 passed with the chase file (1 self-inflicted expectation fixed) |
| Frontend Rankings/Card/Product/Financial/UI contract set | 228 pass, 2 fail (Playwright runner file; "panels are lifted off the room"); both reproduce on the d318ee7b baseline |
| `EraAndPackEconomicsTables.contract.test.mjs` | same 9 baseline failures, untouched |
| `npm ci` | exit 0, manifests unchanged |
| Production build | PASS 85/85 |
| Browser selected-state smoke | 12 pass, 1 not rendered (Collector component, anonymous) |
