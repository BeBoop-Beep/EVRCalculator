# Opening Profile Bucket 1 Part A — Set Financial Rankings Top 1% Value Share repair

## Summary

The prior Bucket 2 pass (`OPENING_PROFILE_BUCKET2_SITEWIDE_UI.md`, Surface 1
section) concluded `jackpotValueShare` "was never selected into the bulk
cohort query or projected to the client" and deferred the column as a real
backend-scope change. That conclusion was **incorrect** — it looked at the
wrong block. `jackpotValueShare` lives under `distributionDisclosures`, not
`depthAndRobustness`; `depthAndRobustness` is where the decoy `top1EvShare`
lives. `distributionDisclosures` was already being computed into
`target["financialRipV4"]` for every row of the bulk cohort, in memory,
before this pass touched anything. This was a client-projection gap, not a
backend-data gap.

## Field source (confirmed)

`backend/db/services/explore_rip_statistics_service.py`:
- `_build_financial_rip_v3` (line ~784) parses the persisted
  `financial_rip_v3_payload` for the row and returns, among other things,
  `"distributionDisclosures": dict(payload.get("distributionDisclosures") or {})`.
- `_build_financial_rip_v4` (line ~861) calls
  `project_financial_rip_v4_from_v3_payload(payload)`
  (`backend/calculations/evr/financial_rip_v4.py:199`), which re-projects the
  SAME `distributionDisclosures` dict onto the V4 object.
- The main row-build loop sets `target["financialRipV4"] = financial_v4`
  (line ~1248) for every target in the cohort, in the same pass that builds
  every other already-consumed field on that row. No new query, no per-row
  fetch — `distributionDisclosures.jackpotValueShare` was already resident
  alongside `relativeScore`/`rank`/`tier` before this change.

The bulk cohort request itself (`getRipStatisticsTargets`) was and remains
unchanged — per `rankingsClientProjection.mjs`'s own header comment, that
fetch already returns the *complete* canonical target, and only the
RSC-boundary client projection narrows it. This pass widens that client
projection only.

## Changes

1. `frontend/lib/explore/rankingsClientProjection.mjs` — added
   `"distributionDisclosures"` to `BLOCK_LEAVES.financialRipV4`. Never added
   to `depthAndRobustness` (not in `BLOCK_LEAVES` at all — stays excluded).
2. `frontend/components/explore/setMetricRankingSelectors.mjs` —
   `readFinancialSetRanking` now returns `topOneOutcomeValueShare`, read via
   a dedicated `readTopOneOutcomeValueShare(target)` helper that reads
   ONLY `target.financialRipV4.distributionDisclosures.jackpotValueShare`.
3. `frontend/components/explore/SetMetricRankingsTable.jsx` — added a "Top
   1% Value Share" column to the `financial` kind's desktop table, mobile
   card row, and `columns` config array (5th supporting metric).

No backend file was changed for Part A — the data was already fully
computed server-side; this was a client-projection + selector + table wiring
fix.

## Rules honored

- Never `depthAndRobustness.top1EvShare` — verified by test (decoy present
  in fixture alongside the real value; selector proven to read only the
  real one).
- No N+1 / no per-set reads — the same bulk cohort array already carries the
  block; `rankingsClientProjection.mjs` projects it once per already-fetched
  row.
- No rank-order change — `readFinancialSetRanking().rank` is untouched;
  `canonicalMetricRows` sorts on that field only, verified by regression
  test.

## Tests added

`frontend/components/explore/SetMetricRankings.contract.test.mjs`:
- "Top 1% Value Share reads financialRipV4.distributionDisclosures.jackpotValueShare,
  never the depthAndRobustness.top1EvShare decoy" — asserts the correct
  value is read, asserts it differs from a co-located decoy value, and
  asserts a row with ONLY the decoy stays `null` (no silent substitution).
- "Top 1% Value Share is populated for every row whose disclosure exists
  (no silent empties)" — two-row fixture, one with disclosure, one without;
  asserts correct population and correct `null` for the missing case.
- "Adding Top 1% Value Share does not change canonical financial rank order"
  — two-row fixture sorted by `canonicalMetricRows`; asserts unchanged order.
- "Top 1% Value Share is projected from the SAME already-fetched bulk cohort
  object (no per-row read)" — asserts the table source reads
  `metric.topOneOutcomeValueShare` and contains no `fetch(`/N+1 pattern.

`frontend/lib/explore/rankingsClientProjection.test.mjs`:
- "financialRipV4.distributionDisclosures.jackpotValueShare (Top 1% Value
  Share source) survives projection for every row, and the
  depthAndRobustness decoy never crosses the boundary" — 4-row cohort,
  asserts exact per-row survival and asserts `depthAndRobustness` is absent
  from every projected row's `financialRipV4` block.

## Results

```
cd frontend && node --test lib/explore/rankingsClientProjection.test.mjs components/explore/SetMetricRankings.contract.test.mjs
# tests 33
# pass 33
# fail 0
```

Full `components/explore` + `lib/explore` + `sealed-product-detail`
regression: 130 pre-existing failures (confirmed unrelated — none in any
file this pass touched; see the Bucket 2 doc's Surface 1/2/4 validation
section for the cross-check methodology and the specific pre-existing
`publicMetricContract.contract.test.mjs` count of 5, reproduced unchanged).
