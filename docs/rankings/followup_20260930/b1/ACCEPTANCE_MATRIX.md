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
