# Rankings Follow-up B2 - Acceptance Matrix

| # | Requirement | Evidence |
|---|---|---|
| 1-2 | Entitled Era rows populate all four metrics; Mega Evolution has no dashes | `BenchmarkEntityScoreTable.render.test.jsx` (rendered HTML), backend `test_paid_era_scorecards_carry_all_four_metrics_with_benchmark_tiers`, browser run (desktop/mobile Plus) |
| 3 | Public Era contract exposes only Overall | backend `test_public_era_headlines_stay_overall_only`; `unifiedScoreTableModel.test.mjs` strip test; browser anon DOM scan (no 4.604/4.306/4.989) |
| 4 | Paid wide endpoint still gated | `test_paid_response_boundary.py` (Era + Set: 401 anonymous, 403 Base, 200 Plus, no read before gate) |
| 5-7 | Entitled Set rows populate four metrics; public Set Overall-only; artwork kept | merge tests (identity/artwork kept), `test_public_headlines_are_overall_only_and_keep_set_artwork`, browser run |
| 8-9 | One Era table, one Set table | render test (one `<table>`, one `data-rankings-unified-score-table`), browser "exactly one score table" |
| 10-12 | Separate Set Financial / Collector / Chase tables removed | `SetMetricRankings`, `SetRankingsHub`, `RankingsScoreTables` contract tests; registry is `ripScore`, `packEconomics`; files deleted |
| 13 | Pack Economics remains separate | `RankingsFollowupB2.contract.test.mjs`; browser: Pack Economics view has no unified table |
| 14-17 | Overall / Financial / Collector / Chase sort by own `.rank` | `unifiedScoreTableModel.test.mjs`; browser: Financial -> Temporal Forces #1, Collector -> Paradox Rift #1, Chase -> Scarlet & Violet 151 #1 (Rank column shows that metric's rank) |
| 18 | Reverse sort | model test; browser (second Chase click puts worst rank first) |
| 19 | Search does not recompute rank | model + render tests (`#2`, `of 2` unchanged under search) |
| 20 | Sorting is client-local | `RankingsFollowupB2.contract.test.mjs` (table/model have no fetch); browser: 0 requests while sorting |
| 21-24 | RIP badge / Financial / Collector / Chase borders use their own tier | render test (per-cell `data-tier` and border colours), browser computed-style checks |
| 25 | Mega Evolution Overall 4.60 not purple/S | render test + browser (stroke `251,146,60`, never `192,132,252`) |
| 26 | Reference 5.0 neutral and unranked | render test (one row, four `5.0`, no tier, no rank) |
| 27-28 | Anonymous cells locked; public payload has no component values | render test (leaky payload still stripped), browser DOM scan, no `scorecards` request when anonymous |
| 29-30 | Paid values vanish on access loss; late response ignored | `resolvePaidScorecards` tests + hook contract (`live` flag, identity-scoped cache key). **Not exercised in a live browser** (no mid-session downgrade run). |
| 31 | Era -> Sets filter | `RankingsFollowupB2.contract.test.mjs`; browser (Mega Evolution Era -> chip + only Mega Sets) |
| 32-34 | B1 styling, absolute helper, Product V12 untouched | `RankingsFollowupB2.contract.test.mjs`, `RankingsFollowupB1.contract.test.mjs`, backend `test_public_relative.py`; no Product files modified |
| P | Stale `EraAndPackEconomicsTables` suite reconciled | 9 failures -> 0, 16/16 pass (see IMPLEMENTATION.md) |

## Results
| Check | Result |
|---|---|
| Frontend focused set (398 tests) | 380 pass, 18 fail; **0 new** vs. the B1 baseline. The 18 are the existing Set-detail/Playwright/panel failures; `EraAndPackEconomicsTables` is now fully green |
| New B2 frontend tests | `unifiedScoreTableModel` 8, `BenchmarkEntityScoreTable.render` 8, `RankingsFollowupB2.contract` 8 - all pass |
| Backend (rankings dir, contract service, paid boundary, plan access) | 161 passed |
| Production build (B7 procedure, backend base `http://127.0.0.1:8001`, isolated `node_modules`) | PASS, 85/85 static pages, `/Rankings` 131 B / 115 kB First Load JS, no warnings from B2 files |
| Browser (Playwright, production server, mocked Sep-30-style fixtures) | 70/70 checks pass: desktop 1440 and mobile 390, anonymous and Plus |

Browser caveats: fixtures are controlled mocks (not live Supabase); mid-session downgrade, the Cards/Products tabs, and the Overview tab were not re-run.
