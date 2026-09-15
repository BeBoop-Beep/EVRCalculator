# Opening Profile Bucket 2 — Sitewide UI Pass — STATUS: PARTIAL (1 of 4 surfaces implemented)

## Honest summary

Of the four surfaces in scope, **only Surface 3 (Product Detail — Opening Outcome
Profile) was implemented and tested this pass.** Surfaces 1, 2, and 4 were
investigated but not implemented, for the specific data-availability and
scope-risk reasons documented below. This is a deliberate "ship what's
correct" call, not an oversight — see the per-surface notes.

## Surface 3 — IMPLEMENTED: Product Detail — Opening Outcome Profile

File: `frontend/components/pokemon/sealed-product-detail/ProductRipSection.jsx`

Added `ProductOpeningProfileSummary({ rip })`, a new four-metric `<dl
data-four-metric-summary>` block rendered inside `ProductOpeningProfile`,
directly above the existing `OutcomeRangeRail` (P05/Typical/EV/Price/P95/P99
milestone rail is untouched and stays primary; Entertainment Cost /
Chance-to-Recover-Cost `SUPPORTING_OUTCOMES` tiles are untouched;
`ProductComposition` and the `<details>` "Additional outcome details" block
are untouched). Best-Open Price lives in a fully separate component
(`BestOpenPriceCard.jsx`) and was not touched.

### Exact field-source mapping (confirmed against `pokemon_sealed_product_detail_service.py`)

| Canonical label | Field read in `ProductRipSection.jsx` | Backend source (`_rip_contract`, `pokemon_sealed_product_detail_service.py`) |
|---|---|---|
| Average Return (primary %) | `rip.totalValueToCostRatio` via `percent()` | `detail.get("total_value_to_cost_ratio")` — this is the SAME `expected_value / product_market_cost` ratio Bucket 1 calls `modeledReturnRatio`/`modeledReturnPercent` in `product_family_rankings_service.py`; the Product Detail service has always emitted the identical ratio under this pre-existing name, so no new backend field/substitution was needed. |
| Average Return (secondary $) | `rip.expectedValue` via `money()`, rendered as "`$X average value`" | `detail.get("expected_value")` |
| Typical Opening | `rip.medianValue` via `money()` | `detail.get("median_value")` |
| Covers Cost | `rip.chanceToRecoverCost` via `percent()` | `detail.get("chance_to_recover_cost")` |
| Top 1% Value Share | `rip.topOneOutcomeValueShare` via `percent()` | `(detail.get("financial_rip_v3_payload") or {}).get("distributionDisclosures", {}).get("jackpotValueShare")` — Bucket 1 wiring, never `top1EvShare` |

No `modelBreakEven` field exists anywhere in this response (that name belongs
to the SET-level rankings selectors, not this service), so the "never present
modelBreakEven as the Average Return dollar field" rule was not at risk here.
`rip.expectedValue` is the correct, already-existing dollar field.

No green/red color semantics were applied to Top 1% Value Share — it uses the
same neutral tile styling (`border-[var(--border-subtle)] bg-white/[.025]`)
as the other three tiles.

### Tooltips

All four tiles carry an `InfoPopover` with source-aware, "modeled" wording
(no observed/historical claims), consistent with the existing tooltip pattern
on `SUPPORTING_OUTCOMES`.

### Tests

- `frontend/components/pokemon/sealed-product-detail/SealedProductDetail.contract.test.mjs`
  — added one new test, `"Opening Outcome Profile four-metric summary uses
  canonical Bucket 2 field sources and labels"`, asserting: the block exists
  and renders before `OutcomeRangeRail`; all four canonical labels are
  present; each metric reads its exact canonical source expression
  (`percent(rip.totalValueToCostRatio)`, `money(rip.expectedValue)`,
  `money(rip.medianValue)`, `percent(rip.chanceToRecoverCost)`,
  `percent(rip.topOneOutcomeValueShare)`); `rip.top1EvShare` and
  `modelBreakEven` never appear in the file; and no red/green color class sits
  near the Top 1% Value Share tile.

Command + result:
```
cd frontend && node --test components/pokemon/sealed-product-detail/SealedProductDetail.contract.test.mjs
# tests 12
# pass 12
# fail 0
```

Full directory regression (all existing + new tests in the surface's own
test directory):
```
cd frontend && node --test components/pokemon/sealed-product-detail/*.test.mjs
# tests 52
# pass 52
# fail 0
```

Cross-check against the site's strictest cross-surface contract
(`publicMetricContract.contract.test.mjs`) — 5 pre-existing failures on this
file exist on unmodified `develop` (confirmed via `git stash` + rerun,
identical 5 failures, identical assertions, all about the `/Explore` RIP
Score display scale — unrelated to Product Detail or this change) and remain
exactly the same 5 failures after this change; no new failures, no
previously-passing assertion regressed.

### Validation performed

- Desktop/mobile: `ProductOpeningProfileSummary` uses the same responsive
  `grid gap-2 sm:grid-cols-2 lg:grid-cols-4` pattern already used by
  `SUPPORTING_OUTCOMES` immediately below it in the same component (1 column
  on narrow phones, 2 at `sm`, 4 at `lg`) — no new breakpoint logic invented.
- Entitlement: the whole `ProductOpeningProfile` component (and therefore the
  new block) is already gated behind `detail.rip && entitled` in
  `SealedProductDetailClient.jsx` (Index Plus only); this pass did not touch
  that gate and the existing "Basic entitlement keeps Product RIP ... behind
  the lock" contract test still passes unmodified.
- Missing data: every one of the four cells uses the existing `percent()` /
  `money()` helpers, both of which already return the literal string
  `"Unavailable"` for `null`/non-finite input — no new null-handling code was
  written, so a product with a missing `topOneOutcomeValueShare` (e.g. one
  whose `financial_rip_v3_payload` predates Bucket 1) renders "Unavailable",
  not a crash or a zero.
- No layout regression: the new block is an additional sibling `<dl>`, not a
  modification of any existing table/rail; column counts of the milestone
  rail (6) and supporting tiles (2) are unchanged.
- Browser sanity check: NOT performed. This sandbox does not have the `run`
  skill's dev-server prerequisites exercised in this pass (no live Next.js
  dev server was started); stated explicitly rather than assumed passing.

## Surfaces NOT implemented this pass, and why

### Surface 1 — Set Financial Rankings (`SetMetricRankingsTable.jsx` /
`setMetricRankingSelectors.mjs`) — DEFERRED, genuine data-availability gap

Traced the real data path: `SetMetricRankingsTable` (kind="financial") reads
via `setMetricRankingSelectors.mjs::readFinancialSetRanking`, which sources
`typicalOpening`/`modelBreakEven`/`modeledReturnPercent`/`chanceToBeatCost`
from `rankingsSort.mjs` off the bulk cohort array assembled by
`explore_rip_statistics_service.py` (backend) and narrowed to the client by
`frontend/lib/explore/rankingsClientProjection.mjs`. Three of the four
canonical metrics map cleanly onto fields already in that bulk payload
(Average Return -> `readModeledReturnPercent`/`readModelBreakEven`, Typical
Opening -> `readTypicalOpening`, Covers Cost -> `chanceToBeatCost`/
`prob_profit`).

**Top 1% Value Share does not exist anywhere in this bulk payload.**
`jackpotValueShare` lives only inside `financialRipV3.depthAndRobustness`,
which is fetched and rendered ONLY on the single-set detail page (via
`FinancialRipV3Breakdown.jsx` / `financialRipV3Selector.mjs`, consuming a
per-set `canonical.financialRipV3` object). Grepping
`explore_rip_statistics_service.py` and `rankingsClientProjection.mjs`
(`BLOCK_LEAVES.financialRipV3 = ["relativeScore","rank","cohortSize","tier"]`
— no `depthAndRobustness`) confirms `depthAndRobustness`/`jackpotValueShare`
was never selected into the bulk cohort query or projected to the client.
Bucket 1 explicitly wired `topOneOutcomeValueShare` only into the three
PRODUCT-level services (`product_family_rankings_service.py`,
`pokemon_sealed_product_detail_service.py`, `rip_decision_service.py`) — it
was never prepared at the SET level for this table's data source.

Implementing this column would require either (a) a genuinely new backend
change — adding a column to the shared, payload-size-sensitive bulk cohort
query that `rankingsClientProjection.mjs`'s own header comment says is
already the largest transfer on the site — which is not "wiring an
already-prepared field," it's new backend work outside this bucket's stated
scope, or (b) shipping a column that reads `null`/"Unavailable" for every
single row with no exception, which is a materially different (and worse)
failure mode than the occasional-missing-data case the "no garbage" bar is
meant to allow. Per the task's own stated preference for correctness over
breadth, this surface was deferred rather than either overreaching into new
backend scope or shipping a permanently-empty column.

### Surface 2 — Set RIP Product Comparison — NOT ATTEMPTED

Not reached this pass due to time budget after the Surface 1 investigation
and the Surface 3 implementation/test/validation cycle. `rip_decision_service.py`
does have `topOneOutcomeValueShare` wired (Bucket 1, `_product_decision_row()`),
so the backend data likely supports this surface — but the actual comparison
table component (consolidating "RIP Score + Tier" and "Price + $/Pack" into
combined cells without widening the table, across desktop AND mobile, while
preserving entitlement gating exactly) was not located/read/edited/tested in
this pass. Marking this NOT ATTEMPTED rather than blocked — a future pass
should start from `rip_decision_service.py`'s `sealedProducts.products[]` and
trace forward into `RipDecisionPage.jsx`.

### Surface 4 — Product Detail This Set / Same Format comparisons — NOT ATTEMPTED

Also not reached this pass. `productDetailModel.mjs::comparisonRows()` (read
in this pass) already sources `detail.comparisons.sameFamily` /
`detail.comparisons.sameSet` from the cached detail payload with no
additional fetch — per Bucket 1's own doc, comparison rows already reuse the
cached Product Family Rankings projection, so the "zero new N+1" constraint
looks pre-satisfied structurally. But `ProductComparisonSection.jsx` itself
(31 lines, not read in depth) and its row-rendering markup were not
inspected/edited/tested, so no implementation claim is made here.

## Explicitly out of scope, per the task brief (unchanged from Bucket 1)

Product Rankings' budget-strategy leg remains **BLOCKED_ON_PREPARED_BUDGET_DB**
— `score_budget_strategy()` computes `topOneOutcomeValueShare`/`averageReturn`
but `budget_product_ranking_rows` has no DB columns for them yet, and this
pass did not touch Supabase/migrations/SQL, per both the Bucket 1 doc and this
task's hard constraints. The non-budget Product Rankings table itself was not
attempted in this pass (time budget), so no claim is made about it either way.

## What remains before Bucket 2 can be called complete

1. Surface 2: locate and read the actual RIP Product Comparison table
   component, implement combined cells, add/extend its contract test.
2. Surface 4: read `ProductComparisonSection.jsx` in full, upgrade its rows to
   the four metrics + price while keeping compact RIP/tier/format context,
   verify desktop+mobile+entitlement, add/extend its contract test.
3. Surface 1: either get sign-off to extend the bulk cohort backend query
   with `depthAndRobustness`/`jackpotValueShare` (a real, scoped backend
   change, tracking payload-size impact), or explicitly drop Top 1% Value
   Share from this specific surface's four-metric requirement and ship the
   other three columns.
4. A real browser check via the repo's dev-server convention (not performed
   in this pass) for the one surface that WAS changed.
5. Product Rankings' non-budget leg (Rank, Product/Set, RIP Score+Tier,
   Financial RIP, Chase Accessibility, Collector Appeal, Price/Best-Open,
   plus the four explanatory metrics) — not attempted, no data-availability
   blocker identified yet either way.
