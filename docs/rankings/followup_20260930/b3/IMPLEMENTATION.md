# Rankings Follow-up B3 - Implementation

Branch `fix/rankings-followup-history-focus-performance-b3-20261001`, from B2 `9de00997`. No backend, migration, index, DB write or publication change. B1 (tiers, green selected states) and B2 (unified Era/Set tables) are untouched.

## Files
- **New:** `lib/rankings/financialHistoryCache.mjs` (session-cache history layer, prewarm/prefetch planning), `components/explore/FinancialRipHistoryLegend.jsx` (key = focus + remove, Clear All), `components/explore/FinancialRipHistoryTooltip.jsx` (tooltip body with scroll region, pinned variant).
- **Rewritten:** `FinancialRipHistoryChart.jsx` (cache reads, one-time seeding, Clear All, focus/hover, pinned tooltip, wheel forwarding, identity-keyed state).
- **Extended:** `financialRipHistoryModel.mjs` (candidates, default request plan, anchor fallback, focus helpers, focused tooltip rows).
- **Plumbing:** `RankingsLazyClient.jsx` (prewarm + idle prefetch effect, passes `sessionCache`), `OpeningEconomicsOverall.jsx`, `OpeningEconomicsDistribution.jsx` (pass `sessionCache`; chart keyed by cache identity).
- **Tests:** `financialHistoryCache.test.mjs`, `financialRipHistoryFocus.test.mjs`, `FinancialRipHistoryLegend.render.test.jsx`, `FinancialRipHistoryB3.contract.test.mjs`; updated `FinancialRipHistoryChart.contract.test.mjs` and `ripBenchmarkSurfaces.contract.test.mjs` (assertions moved with the code).

## Decisions
1. **Reused the Rankings session cache**; verified its identity is `${requestKey}:${publicationIdentity}` (access identity + publication), so paid history is never shared across users, downgrade or publication changes. Entries are keyed by type, range and sorted ids.
2. **Superset projection** is a pure row filter of a completed response for the same type/range; Overall values come from the same rows. An entity outside the superset triggers the normal bounded fetch. In-flight supersets are not awaited (the default request always goes first).
3. **Default prewarm is parent-owned** and uses the same plan helper the chart uses (first 3 Sets, 30D, publication end date) so both resolve to the same cache key; the chart consumes the in-flight/completed entry. It ignores save-data (same bytes the chart would request) but the optional 22-Set prefetch honours it.
4. **Defaults seeded once.** The previous "if selection empty, select first 3" effect re-added Sets after Clear All whenever the Era preset changed; replaced by a one-time seed.
5. **Anchor only after seeding.** The first implementation allowed the 1-entity anchor before defaults were seeded and produced an extra request; found in the browser run and fixed (`seededModes`).
6. **Tooltip scrolling:** Recharts' tooltip is non-interactive by design, so wheel is forwarded from the plot to the hover tooltip, and a click/tap pins an interactive panel for touch, keyboard and precise scrolling. The chart's own pointer interaction is unchanged.
7. **Stale safety:** per-effect `active` flag plus per-range/per-entity cache entries (an older range's response lands in its own entry and is never applied to a newer range); no retry loop (a failed read is not cached and the user retries explicitly).

## Test-driver notes (not product defects)
Playwright's single-jump mouse move does not produce Recharts hover-enter (use stepped moves) and CDP `synthesizeScrollGesture` does not drive the pinned panel, while real touch events (`Input.dispatchTouchEvent`) scroll it correctly. The acceptance script uses stepped moves and raw touch events.
