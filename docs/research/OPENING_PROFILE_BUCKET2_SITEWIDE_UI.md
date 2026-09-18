# Opening Profile Bucket 2 — Sitewide UI Pass — STATUS: COMPLETE (4 of 4 non-budget surfaces implemented)

## Update (this pass)

Surfaces 1, 2 and 4 — previously deferred/not-attempted — are now
implemented and tested. See
`docs/research/OPENING_PROFILE_BUCKET1_PART_A_SET_RANKINGS_REPAIR.md` for
the Part A backend/data-source correction that unblocked Surface 1: the
prior pass's claim that `jackpotValueShare` was never selected into the bulk
cohort was wrong — it was already computed server-side into every row's
`financialRipV4.distributionDisclosures`, just never projected across the
RSC client boundary. Surface 3 was re-run this pass (unmodified) and its
existing 52 tests plus the file's full-directory 55 all still pass.

Product Rankings' budget-strategy leg remains untouched and
**BLOCKED_ON_PREPARED_BUDGET_DB**, exactly as before.

## Surface 1 — Set Financial Rankings — IMPLEMENTED

Files: `frontend/lib/explore/rankingsClientProjection.mjs`,
`frontend/components/explore/setMetricRankingSelectors.mjs`,
`frontend/components/explore/SetMetricRankingsTable.jsx`.

Added a "Top 1% Value Share" column to the Financial rankings table
(desktop + mobile), sourced via `readFinancialSetRanking(target)` ->
`target.financialRipV4.distributionDisclosures.jackpotValueShare`. Full
detail in the Part A doc. Existing columns (Expected Value, Typical Opening,
Modeled Return, Chance to Beat Cost) and rank order are unchanged.

Tests: `SetMetricRankings.contract.test.mjs` (12 tests, was 8) and
`rankingsClientProjection.test.mjs` (21 tests, was 20) — see Part A doc for
the specific new assertions. Both files: 100% pass.

## Surface 2 — Set RIP Product Comparison — IMPLEMENTED

File: `frontend/components/explore/RipDecisionPage.jsx`
(`ComparisonTableRow`, `ComparisonMobileRow`, and the `compare-products`
desktop `<thead>`), data already present on `rip_decision_service.py`'s
`_product_decision_row()` (`modeledReturnPercent`, `topOneOutcomeValueShare`,
`typicalOpening`, `chanceToRecoverCost` — all wired in Bucket 1, confirmed
unchanged this pass).

### Before -> after desktop columns (9 columns, both versions)

Before: Product Rank | Product | RIP Score | Tier | Market Price | $ / Pack |
Typical Back | Entertainment Cost | Recover Cost

After: Product Rank | Product | RIP Score **+ Tier (combined cell)** |
Price **+ $/Pack (combined cell)** | Average Return | Typical Opening |
Covers Cost | Top 1% Value Share | Entertainment Cost

RIP Score + Tier now render together (`RipScoreBadge` stacked above
`RipTierMark`) in one `<td>`; Market Price + $/Pack render together (price,
with per-pack price as a `<small>` sub-line) in one `<td>`. This keeps the
table at exactly 9 `<th>`/`<td>` columns while adding Average Return and Top
1% Value Share, per the task's column budget. "Recover Cost" was relabeled
"Covers Cost" to match the canonical Bucket 2 vocabulary (same field,
`product.chanceToRecoverCost`, unchanged).

Mobile (`ComparisonMobileRow`): unchanged structural pattern (identity card
+ locked-value `dl` rows) with two new rows — "Average Return" and "Top 1%
Value Share" — inserted, and "Recover Cost" relabeled "Covers Cost". Market
Price / $ / Pack remain in their own unlocked `dl` rows exactly as before
(still public, never behind `LockedValue`, matching the pre-existing
entitlement contract).

Entitlement: unchanged. All four newly-added/relabeled analytical cells
(`RIP Score/Tier`, `Average Return`, `Typical Opening`, `Covers Cost`, `Top
1% Value Share`, `Entertainment Cost`) stay wrapped in the same
`LockedValue canView={canView}` used before; `Product`, `Product Rank`
identity link, and `Price` (Market Price + $/Pack) remain public, matching
the pre-existing "mobile keeps public identity and market price while
locking all analytical rows" contract, which still passes unmodified.

Test: `RipDecisionPage.productComparison.contract.test.mjs`, rewritten to
lock the new 9-column contract and to assert the combined cells and the two
new fields' exact source expressions (`product.modeledReturnPercent`,
`product.topOneOutcomeValueShare`, never `product.top1EvShare`). 6/6 pass.
Also re-ran `RipDecisionPage.contract.test.mjs` + `ripDecisionContract.test.mjs`
(40/40 pass, no regression).

## Surface 3 — Product Detail — Opening Outcome Profile — RE-VERIFIED, unchanged

No code changes this pass (a test proving a defect was the only condition
that would have justified touching it; none was found).

```
cd frontend && node --test components/pokemon/sealed-product-detail/*.test.mjs
# tests 55
# pass 55
# fail 0
```
(52 from the original implementation pass + 3 new from this pass's Surface 4
test file in the same directory.)

## Surface 4 — Product Detail This Set / Same Format comparisons — IMPLEMENTED

Files: `backend/db/services/pokemon_sealed_product_detail_service.py`
(`_comparison_row`), `frontend/components/pokemon/sealed-product-detail/ProductComparisonSection.jsx`.

### Data flow trace (no new fetch, confirmed)

`comparisonRows(detail, mode)` in `productDetailModel.mjs` already reads
`detail.comparisons.sameFamily` / `detail.comparisons.sameSet` off the
single cached detail payload — unchanged, still zero client-side fetches.

On the backend, `_comparison_row()` builds each same-set/same-family row
from `ranking_by_id.get(candidate_id)`, which is itself sourced from
`_published_rankings(client)` -> the ALREADY-FETCHED
`pokemon_explore_rankings_snapshot_latest` row, parsed once per page load
(`publication["payload"]`) via `_ranking_rows()`. That per-product ranking
dict is the exact `product_family_rankings_service.py` row shape, which
already carries `modeledReturnPercent`, `medianValue`, `chanceToRecoverCost`,
and `topOneOutcomeValueShare` (Bucket 1) — `_comparison_row()` simply was
not copying those four fields into its output dict. This pass adds four
lines copying them through, verbatim, with no new table read, no new
`client.table()` call. `test_detail_payload_does_not_issue_extra_query_per_comparison_row`
(pre-existing, asserts the `simulation_sealed_product_results` query fires
exactly once regardless of comparison cohort size) still passes unmodified,
confirming no query-count regression.

### Frontend

`ProductComparisonSection.jsx` renders a new `<dl data-comparison-opening-profile>`
inside the existing `entitled && row.rankable` gated block (same gate RIP
Score/Tier already use) showing Average Return (`percentPoints(row.modeledReturnPercent)`),
Typical Opening (`money(row.typicalOpening)`), Covers Cost
(`percent(row.chanceToRecoverCost)`), Top 1% Value Share
(`percent(row.topOneOutcomeValueShare)`). Price (`money(row.currentPrice)`),
compact RIP Score/Tier badge line, and Format Rank line are all unchanged.
No fetch/await was introduced in this component.

### Tests

Backend: `test_pokemon_sealed_product_detail_service.py` — two new unit
tests directly against the pure `_comparison_row()` function: one proving
population when a ranking row carries the four fields, one proving they
stay `None` (not zero/garbage) when no ranking row exists. 32/32 pass in
the file (30 pre-existing + 2 new).

Frontend: new file `ProductComparisonSection.contract.test.mjs` — asserts
the four canonical field-read expressions are present, asserts the decoy
`row.top1EvShare` never appears, asserts no `fetch(`/`await` was
introduced, asserts the canonical label vocabulary, and asserts the new
block sits inside the existing entitled+rankable gate. 3/3 pass.

## Explicitly out of scope (unchanged)

Product Rankings' budget-strategy leg remains **BLOCKED_ON_PREPARED_BUDGET_DB**
— `score_budget_strategy()` computes `topOneOutcomeValueShare`/`averageReturn`
but `budget_product_ranking_rows` has no DB columns for them yet. This pass
did not touch Supabase/migrations/SQL/Best-Open/production. The non-budget
Product Rankings table itself was not attempted (out of this task's stated
scope), so no claim is made about it either way.

## Original pass narrative (for history)

The section below is preserved from the prior pass for audit trail. It
describes the STATE BEFORE this pass's Surface 1/2/4 work; it is retained
rather than deleted so the "what was deferred and why" reasoning remains
visible, even though the Surface 1 conclusion in particular was later found
to be based on an incorrect field-location read (see Part A doc).

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
