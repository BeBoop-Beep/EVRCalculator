# Rankings Follow-up B1 - Implementation

Branch `fix/rankings-followup-tier-controls-b1-20260930`, from `origin/develop` d318ee7b. No migration, DB write, publication, formula or score change.

## Backend
- `public_relative.py`: added `benchmark_relative_tier`, `absolute_rank_percentile_tier`.
- `rankings_redesign_contract_service.benchmark_presentation` now calls `benchmark_relative_tier` with the score.

## Frontend
- `lib/explore/rankingsSelectedState.mjs`: single green/teal + white selected-state tokens.
- `SegmentedControl.jsx`: `rankings` and `rankingsPrimary` variants use the green selected surface (generic `primary` and `pill` unchanged). Aria-checked, focus ring, arrow-key navigation and disabled styles untouched.
- `RankingsScorePrimitives.jsx`: removed forced purple `accentColor`; the main badge border resolves from `metric.tier`. Added `RankingsBenchmarkComponentScore` (thin own-tier border, no caption, no arrow, aria-label names the metric) for B2; existing neutral metric stays for absolute surfaces.
- `explore.module.css`: `.productFamilyTabActive` (covers Rankings pills, Set/Era lenses, Product family buttons) and `.productFamilyTabOverallActive` are green + white.
- `FinancialRipHistoryChart.jsx`: Sets/Eras and 30D..ALL selected states use the shared green surface.
- `CardRankingsHub.jsx`: Collector Appeal / Chase Efficiency selector uses the `rankings` variant. Collector components already used it.

## Not changed
Era/Set unified tables, graph interactions, Product pagination, Cards queries, entitlements, Pack Economics.

## Workspace note
Another agent was active in D:\EVRCalculator, so this work ran in the isolated worktree D:\EVRCalculator-rankings-followup-b1.
