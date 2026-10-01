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

## Closure (second pass)
- **Shared-workspace cleanup:** NOT performed. `git apply --reverse --check` of the B1 five-file patch failed on `frontend/components/ui/SegmentedControl.jsx` because the shared copy only holds the one-line import (the remaining hunks were made in this worktree). Per the stop rule nothing was changed in `D:\EVRCalculator` (branch `fix/market-explorer-sheet2-backend-20260930`, HEAD 6960bf41). The shared tree still carries my four edited files plus untracked `rankingsSelectedState.mjs`; the other four are byte-identical to the B1 versions, and the SegmentedControl diff is exactly one added import line. The Market Explorer agent's own changes there are committed, so no overlap with another agent's hunks was found.
- **Absolute helper adoption:** Card Chase Efficiency `_public_row` and Explore RIP statistics `_calculate_score_ranks_and_tiers` now use `absolute_rank_percentile_tier`. Scores, ranks, tie-breaks, cohorts and filters are unchanged. `public_rank_tier` marked LEGACY (no production callers).
- **Dependencies:** `npm ci` in the isolated `frontend` (659 packages, exit 0); `package.json` and `package-lock.json` sha256 unchanged.
- **Production build** (B7 procedure, `BACKEND_API_BASE_URL` and `NEXT_PUBLIC_BACKEND_API_BASE_URL` = `http://127.0.0.1:8001`, `PERF_AUDIT_DIST_DIR=.next-build-b1`): compiled 2.8 min, lint/type complete (one existing `react-hooks/exhaustive-deps` warning in a file B1 does not touch), page data complete, 85/85 static pages, `/Rankings` 131 B / 115 kB First Load JS. Static-generation "Dynamic server usage" notices appear for pages that fetch the (not running) backend; the build still succeeds.
- **Browser smoke** (Playwright, production server on :3108, B7 anonymous route fixtures): 12/12 rendered selected controls had green/teal surface and white text with aria selected: top nav Overview/Eras/Sets/Products/Cards, Era and Set pills, Product family, graph Sets and 30D, Cards Collector Appeal. The Collector component row and the Product Scores/Economics toggle did not render under the anonymous fixture, so those are covered by source contracts only.
