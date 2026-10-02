# Market Explorer corrective final acceptance — 2026-10-02

## Verdict

**BLOCKED — do not merge or deploy the application branch.**

The integrated application expects `search_pokemon_market_explorer_catalog_v2`,
but that staged read-only catalog migration is not installed in the serving
database. The live catalog route therefore fails before the six-viewport
behavior matrix can truthfully pass.

No production write, migration application, Activity rebuild, merge, or
application deployment was performed during this acceptance attempt.

## Integrated source baseline

- Branch: `fix/market-explorer-corrective-final-acceptance-20261002`
- Integrated starting SHA: `94ec07a188214cb5866f28cbfe8d526b60dd8a19`
- Sequential ancestry:
  - data/read path: `9172ba17`
  - interactions: `f2ef1b86`
  - search/constituents: `94ec07a1`

## First failing boundary

Story under test:

`Market Explorer UI -> Next catalog proxy -> FastAPI catalog route -> serving Supabase RPC -> grouped search response`

| Boundary | Result | Evidence |
|---|---|---|
| Serving directory | PASS | `GET /market/explorer/prepared-directory` returned HTTP 200 in 478 ms. |
| Prismatic Cards directory authority | PASS | `set:7a3dd188-4375-41af-94de-c5247fe0b1a6`, generation `5caf929a-4962-4334-84a0-c75d3635135b`, `available`, 180 constituents, `index_and_composition`. |
| Prismatic Sealed directory authority | PASS | `sealed-set:7a3dd188-4375-41af-94de-c5247fe0b1a6`, same generation, `available`, 26 constituents, `index_and_composition`. |
| Catalog search data boundary | **FAIL** | `GET /market/explorer/catalog/search?asset=cards&q=prismatic&limit=12` returned HTTP 503 in 246 ms with `CATALOG_SEARCH_UNAVAILABLE`. |
| Independent prepared screen read | PASS | `GET /market/explorer/prepared-screen?screen=top-performers&asset=sealed&limit=10` returned HTTP 200 in 66 ms with exactly 10 rows. |

The FastAPI response code is the service's explicit missing-RPC classification.
The staged migration exists in source as
`20261002090000_market_explorer_catalog_search_v2_paging.sql`; acceptance did
not apply it because this bucket forbids deployment and production writes.

## Failure classification

| Classification | Finding |
|---|---|
| Code defect | No new code defect demonstrated before the stop boundary. The integrated application correctly fails closed when its required RPC is absent. |
| Upstream outage | **No.** Directory and prepared-screen reads were healthy and fast during the same receipt window. |
| Legitimate unavailable data | **No.** Both Prismatic catalog markets are explicitly `available` with current enumerable compositions. |
| Expected dev cold compile | Not implicated. The failure was emitted directly by the already-running FastAPI read path in 246 ms. |
| Release-order/schema mismatch | **Yes — blocking.** Application code requiring catalog V2 is ahead of the serving database contract. |

## Required scenario matrix

Per the acceptance rule, scenarios after the first broken data boundary were
not marked passed using fixture-only evidence.

| # | Scenario | Final status |
|---:|---|---|
| 1 | Raw + Sealed initial markets | UNPROVEN in this final live matrix |
| 2 | Add Prismatic Cards | UNPROVEN |
| 3 | Prismatic loads without timeout under healthy upstream | UNPROVEN |
| 4 | Prismatic chip inspection + focus | UNPROVEN |
| 5 | Activity available for focused supported market | UNPROVEN |
| 6 | Enter/exit Activity without losing Index workspace | UNPROVEN |
| 7 | Raw parent Inspect | UNPROVEN |
| 8 | Sealed parent Inspect | UNPROVEN |
| 9 | Raw/Sealed constituent pagination | UNPROVEN |
| 10 | Movement selector has no gap after LT | UNPROVEN |
| 11 | 1Y graph fills actual available history | UNPROVEN |
| 12 | Prismatic Cards grouped priced search + continuation | **BLOCKED: live 503** |
| 13 | Prismatic Sealed grouped priced search + continuation | **BLOCKED by same missing catalog V2 authority** |
| 14 | Top Sealed: 10 | PASS at backend boundary; browser/viewports unproven |
| 15 | Worst Sealed: 10 | UNPROVEN |
| 16 | Generic market pills have asset suffixes | UNPROVEN |
| 17 | Builder remove controls and secondary-button styling | UNPROVEN |
| 18 | Tooltip authoritative values at/before hover date | UNPROVEN |
| 19 | No unexpected 5xx | **FAIL: catalog search returned 503** |
| 20 | No console errors | UNPROVEN |

## Viewport and screenshot status

The required `1728x1000`, `1440x900`, `1024x768`, `768x1024`, `390x844`, and
`844x390` screenshot matrix was not produced after the blocking live data-path
failure. Producing fixture screenshots and labeling them as live acceptance
would conceal the missing serving contract.

## Exact release recommendation

1. Do not merge or deploy the integrated application commit yet.
2. Review and promote the already-staged catalog V2 migration through the
   approved database release process; do not rebuild or replace Prismatic
   Activity authority.
3. Verify the live catalog endpoint returns HTTP 200 with a market group,
   priced physical rows, and `nextCursor` for both Cards and Sealed.
4. Re-run all 20 scenarios across all six viewports, capturing screenshots,
   console output, and route/status/elapsed-time receipts.
5. Only then issue a final pass verdict.
