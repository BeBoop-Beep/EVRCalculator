# Rankings Follow-up B2 - Unified Score Table Contract

One sortable benchmark score table per entity type, implemented once in `frontend/components/explore/BenchmarkEntityScoreTable.jsx` with pure logic in `unifiedScoreTableModel.mjs`.

## Columns
- **Eras:** Rank | Era | RIP Score | Financial | Collector Appeal | Chase | Modeled Sets
- **Sets:** Rank | Set | RIP Score | Financial | Collector Appeal | Chase

Pack Economics is a separate view (Era sub-nav "Pack Economics"; Set sub-nav "Pack Economics") and is not part of this component. The Set sub-nav is now exactly **RIP Score | Pack Economics**.

## Public vs paid data
| Viewer | Source | Result |
|---|---|---|
| Anonymous / Base | `GET /tcgs/pokemon/rankings/headlines` (one request, Overall only) | identity, artwork, Overall score/rank/tier. Financial / Collector Appeal / Chase render a locked cell. |
| Plus / Premium | the same public headlines first, then **one** `GET /tcgs/pokemon/rankings/scorecards?entity_type=era\|set` (Plus-gated, unchanged) | the paid wide rows are merged in; all four metrics carry canonical rank, cohort and tier. |

- The public render is never delayed by the paid request.
- Merge: same `marketDate` -> paid rows win per entity, public identity (artwork) is kept; different `marketDate` -> the paid cohort replaces the public one wholesale, so ranks of two publications are never mixed.
- Defence in depth: for non-entitled viewers the model strips `financial`/`collector`/`chase` from every row before rendering, so a leaky payload still cannot reach the DOM, aria-labels or data attributes.
- Paid data is loaded by `usePaidScorecards(entityType, { sessionCache, entitled })`. The session cache is keyed `${requestKey}:${publication}` (user/access identity + publication) and the response is cached per entity type. Visibility is decided by the pure `resolvePaidScorecards`: not entitled, or loaded under a different identity -> nothing is exposed. A response that resolves after downgrade/identity change is dropped (`live` flag + identity check).

## Sorting and rank
- Sort keys: RIP Score (`overall`), Financial, Collector Appeal, Chase. Identity and Modeled Sets are not sortable.
- Default: RIP Score, rank ascending.
- First click on a metric: best-to-worst canonical rank (ascending). Click the active metric: reverse. `aria-sort` marks the active column (`ascending` = best first).
- **The visible Rank column always shows the canonical rank of the metric the table is sorted by** (`financial.rank` when sorted by Financial, etc.), with `of cohortSize` for assistive tech. Rank is never computed in the browser.
- Ties/unranked: rows are ordered by canonical rank, rows without a rank last (in both directions), then by name, then by entity id (deterministic).
- Anonymous/Base: protected column headers are disabled (lock icon, `disabled`), and no paid request is made to support sorting. On mobile the same four sort buttons exist; protected ones are disabled.
- Sorting and search are client-local over the already loaded cohort (2 Eras / 22 Sets); neither issues a request.

## Search and Era filter
Search (and the Era -> Sets filter) only removes rows. Rank, cohort size and tier on remaining rows are the unchanged canonical values (a Set that is global Financial #1 still shows `#1` when it is the only search hit). Tiers are not recomputed.

## Reference row
"Pokémon Overall Average 5.0" is one pinned row at the top of the table body (not repeated per metric, not part of sorting). It has no rank and no tier. Entitled viewers see 5.0 under all four score columns; Base/anonymous see 5.0 under RIP Score and the standard locked cell under the protected columns. Modeled Sets is blank for the reference. On mobile it is a single pinned strip above the rows.

## Tier cells
- **RIP Score:** the octagonal `/10` badge; its stroke is the tier of `overall`.
- **Financial / Collector Appeal / Chase:** compact number with a thin border in that **metric's own** tier (`RankingsBenchmarkComponentScore`), no internal caption, no arrow. Accessible name carries the metric label.
- Tiers come from the backend `benchmark_presentation` (B1 `benchmark_relative_tier`); React never derives a tier. Rows are not coloured as a whole.
- Palette (`getBenchmarkTierTone`, the explicit interpretation palette): S purple `rgba(192,132,252)`, A teal `rgba(45,212,191)`, B green `rgba(134,239,172)`, C sky `rgba(125,211,252)`, D orange `rgba(251,146,60)`, F red `rgba(248,113,113)`. `RANK_CONFIG` (used elsewhere) paints C yellow and A emerald; Rankings benchmark cells deliberately do not use it. Other site surfaces are unchanged.

## Live Sep-30 examples (backend tests)
Mega Evolution Era: Overall 4.602 / Financial 4.604 / Collector 4.989 / Chase 4.306, ranks 2/2, tiers D / D / C / D. Scarlet & Violet Era: 5.149 / 5.148 / 5.004 / 5.260, tiers C / C / C / S. A below-average Era is never purple.

## Removed
`SetMetricRankingsTable.jsx`, `RankingsScoreTable.jsx`, `rankingsScoreTableModel.mjs` (+test), `setMetricRankingSelectors.mjs` (legacy V4-shape readers, only referenced by their own test), and the Set `financial` / `collectorAppeal` / `chaseAccessibility` views and their per-view paywall.
