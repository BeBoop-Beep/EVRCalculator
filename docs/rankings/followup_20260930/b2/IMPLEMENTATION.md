# Rankings Follow-up B2 - Implementation

Branch `fix/rankings-followup-unified-score-tables-b2-20260930`, from B1 `ddff5f02`. No migration, DB write, publication, formula or score change. Pack Economics content, Product V12 scale, history graph and Cards queries untouched.

## Defect fixed: Era components showed dashes
`RankingsLazyClient.loadEra()` only ever loaded the public Overall headlines, while `EraRankings` expected Overall + Financial + Collector + Chase, so entitled users saw dashes. The live Sep-30 data has all four metrics. Entitled Era viewers now also receive the existing Plus-gated wide scorecard (`/tcgs/pokemon/rankings/scorecards?entity_type=era`), merged over the public rows after entitlement resolves.

## Frontend
- `unifiedScoreTableModel.mjs` (new, pure): column registry, public-only stripping, public/paid merge, filter, sort (canonical rank), click/aria-sort rules.
- `BenchmarkEntityScoreTable.jsx` (new): the single Era/Set table - desktop table and mobile list, mobile sort buttons, pinned reference row, locked/pending cells, `RankingsRipScoreBadge` + `RankingsBenchmarkComponentScore`.
- `lib/rankings/usePaidScorecards.js` + `paidScorecardVisibility.mjs` (new): one entitlement-gated wide read per entity type, identity-scoped visibility.
- `EraRankings.jsx`, `SetRipScoreLeaderboard.jsx`: now thin wrappers (shell/search/identity) over the shared table; `SetRankingsHub.jsx` loses the per-metric views and the second paid read; `setRankingViews.mjs` -> RIP Score + Pack Economics; `RankingsLazyClient.jsx` passes `sessionCache` / entitlement and keys `EraRankings` by cache identity.
- `interpretationTone.js`: added `getBenchmarkTierTone` (explicit palette; see contract). `RankingsScorePrimitives.jsx` uses it for the RIP badge stroke and the component score border.
- Removed: see "Removed" in `UNIFIED_SCORE_TABLE_CONTRACT.md`.

## Request budget
Era: 1 public headlines + <=1 paid scorecard (entitled). Set: 1 public headlines + <=1 paid scorecard (entitled). Sorting/search: 0 requests. Verified in the browser run (no duplicate headline/scorecard requests; sorting added none).

## Stale-test reconciliation (`EraAndPackEconomicsTables.contract.test.mjs`, 9 baseline failures -> 0)
Every replaced test carries an in-file `RECONCILED (B2)` comment. Summary (OLD -> WHY OBSOLETE -> NEW):

1. *Explore normalization transports two Era rows into EraRankings* - asserted `page` passed `eraSetStrength` and `<EraRankings contract=...>` in the retired `ProductFamilyRankingsClient` (not routed by any page) -> Era rows now come from public headlines -> normalizer/selector assertions kept; page/lazy-client wiring asserted instead.
2. *EraRankings uses the Rankings table shell* - asserted the retired Era Set Strength table (`canonicalRows`, Tier, Strongest Set, Set Strength Range) -> replaced by the unified table -> asserts shell, unified table, approved columns, fail-closed copy, and that the retired labels are gone.
3. *Pack Economics keeps canonical aggregates...* - one literal `useState({ key: "modeledReturnOnSpend"` -> Basic viewers now start on `setName` (`entitled ? ... : "setName"`) -> literal updated; all other assertions untouched.
4. *all four lenses share the analytics shell* - page/client date plumbing and Era Set Strength header tokens of the retired client -> page passes `rankingsMarketDate` to `RankingsLazyClient`; header tokens updated to the live copy.
5. *Rankings and Pack Economics reuse pill primitives* / *top-level entry resets* - asserted strings in the retired client -> now asserted in `RankingsLazyClient` / `SetRankingsHub`.
6. *Set Pack Economics entitlement* / 7. *Basic cannot sort hidden intelligence* - expected `SetRankingsHub` to `return null` for Basic -> Basic now gets the public pack preview and `SetPackMetrics` locks protected cells (`entitled`) -> asserts the real mechanism. Era-side assertions kept.
8. *Era Pack Economics Plus matrix* / 9. *Era baseline one renderer/colgroup* - single-line source literals that the formatted source no longer matches (multi-line `new Set([...])`, `COLUMNS.map((column) => (<col`) -> whitespace-normalised comparison, behavioural assertions unchanged.
10. *no table-specific color material* - `EraRankings` owned its `<thead>` -> the shared score table does now; same guarantee asserted on it.

Finding (not changed - Pack Economics is out of scope): `SetPackMetrics.changeSort` does not itself block Basic users from selecting a protected column; the Basic payload is the public preview, so there are no protected values to order by.

Other tests updated for the new structure: `SetRankingsHub`, `RankingsScoreTables`, `SetMetricRankings` (legacy selector tests removed with the dead module), `RankingsRepairBucket1`, `ripBenchmarkSurfaces`, `RankingsBucket1PublicAccess`, `RankingsBucket2Presentation`, `RankingsScorePrimitives`, `RankingsFollowupB1`.

## Environment note
Work ran in the isolated worktree `D:\EVRCalculator-rankings-followup-b1`; the shared checkout was not touched.
