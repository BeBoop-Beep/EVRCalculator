# Market Explorer Fix Sheet 2 — Bucket 2 acceptance

Date: 2026-09-30 (America/Phoenix)

Starting Bucket 1 SHA: `d97527aa659b8340cd6decc66124a79806ac5422`

Branch: `fix/market-explorer-sheet2-backend-20260930`

Final commit: the commit containing this receipt (reported in the handoff; a commit cannot embed its own SHA).

## Safety and scope

No production migration, application deployment, serving-pointer change, catalogue write, Activity write, or paid-provider collection occurred. Production access was read-only. The Bucket 1 migration remains staged only.

## Isolated migration validation

PostgreSQL 16.15 was initialized locally under `tmp/` and bound to a non-production port. The repository's 407-file migration directory is not a self-contained fresh-database chain: migration 3, `20260618234913_fix_set_value_history_refresh_bounds_scan.sql`, requires the absent remote-baseline type `public.conditions.id%TYPE`. This is a repository baseline prerequisite, not a Bucket 1 SQL failure.

The staged migration `20260930230000_market_explorer_surface_canonical_movement_v1.sql` was then applied to a second fresh local database containing realistic minimal V2 surface authorities. All three functions compiled and executed. Receipt:

- finalizer updated 4 markets;
- Card Quick 30D = 10.0000%; Card Rarity 30D = 20.0000%; both 1Y values remained null;
- global Top order was Card Rarity #1, Sealed Type #2, Card Quick #3, Card Set #4;
- Cards-filtered Top retained global ranks 1, 3, 4;
- Graded returned 0 rows;
- Rarity movement was non-empty and Cards + Sealed participated in the global ranking.

The full-chain prerequisite failure is explicitly outstanding; no claim is made that the repository can reconstruct its remote baseline from migrations alone.

## Performance method and results

Measurements used local Python/application adapters over the production Supabase read endpoint. They include client-library transport and database execution but not a deployed browser/Next hop. Cold means the first measured process call; warm means the immediately repeated call. Local Next production compilation is separately labelled and is not treated as request latency.

| Lane | Cold | Warm | Result |
|---|---:|---:|---|
| V2 directory | 250.8 ms | 73.5 ms | 392 rows |
| prepared comparison | 461.5 ms | 137.9 ms | production serving generation |
| constituents (general sample) | 308.7 ms | 160.7 ms | first-page read |
| catalogue search | 486.0 ms | 147.2 ms | 20 Card results |
| prepared Screen | 74.0 ms | 80.4 ms | 10 rows |
| direct Card | 336.2 ms | 250.3 ms | 92 sparse daily points |
| direct Sealed | 188.7 ms | 125.2 ms | 156 sparse daily points |
| Raw first constituent page | 121.5 ms | n/a | 10 of 20,315 |
| Total Sealed first/load-more | 65.4 ms | 53.1 ms | 10 of 1,377 each |

The measurable repeated-selection cost was redundant generation-stable directory and alias reads. A 30-second process cache now keys both by serving generation. Every request still reads the tiny serving pointer; a new identity immediately evicts retained directory and alias entries. The cold directory lock covers fetch, validation, and cache publication, coalescing same-process cold requests. History/comparison output and user/entitlement-specific data are not cached.

The initial page's deployed auth, SSR, and first-usable-render waterfall could not be honestly measured without deploying this branch. The optimized Next build compiled in 4.2 minutes locally; that compile time is not runtime latency. Initial dependencies remain parallel, the directory has a 4-second server deadline, and no incompatible older generation is substituted.

## Request bounds

| Lane | Bound |
|---|---:|
| catalogue search | 3,000 ms |
| directory / Screen | 4,000 ms |
| Activity stored projection | 6,000 ms |
| prepared comparison | 8,000 ms |
| constituent page | 8,000 ms |
| direct instrument | 8,000 ms |
| explicit custom build only | 45,000 ms |

Prepared timeout copy says the read timed out; it does not call the operation a build. Abort signals and request-sequence guards prevent older direct-search completions from overwriting newer focus.

## Direct physical-item discovery

`POST /market/explorer/direct-instrument` accepts exactly `{asset, instrumentId, startDate?}`. Asset is Cards or Sealed, the ID must be one UUID, and catalogue membership is independently verified. Cards reuse exact variant metadata and canonical daily card states. Sealed reuses exact product metadata and its USD observations (including the established null/lowercase USD normalization), retaining the latest valid observation per date.

The server returns one stable `direct:<asset>:<uuid>` series, raw prices, first-valid-point index values, as-of/range, image/context, and one complete truthful constituent. Browser code only projects this server result into the existing chart shape. Basic replaces its sole active series; paid plans may append within their existing active-market limit. The Premium `/market/explorer/query` arbitrary exact-basket entitlement and `FEATURE_MARKET_EXPLORER_EXPLICIT_INSTRUMENTS` were not changed.

## Parent transport

Production-read evidence for generation `81400ef7-dcdb-4eda-923d-381c84f5b936`:

- `raw`: `index_and_composition`, 20,315 constituents; page response preserved market key, generation ID, total, cursor (`nextCursor=10`) and 10 exact rows.
- `sealedMarket`: `index_and_composition`, 1,377 constituents; first and second pages retained the same market/generation identity and returned 10 rows each.

No legacy “parent is non-enumerable” inference is needed or introduced.

## Market Activity violation and chart contract

The currently served Prismatic requests were reproduced separately. Group validated. Constituent page failed first at `$.evaluatedAt`: PostgreSQL supplied `2026-09-30T16:31:47+00:00`, while frozen FMA v1.1 requires UTC `YYYY-MM-DDTHH:MM:SSZ`. The immutable stored payload and schema were valid; page service normalization owned the defect. It now canonicalizes database timestamptz values to seconds plus `Z`. After the fix, group, constituent-page, and instrument responses all returned zero schema errors.

Authority was reproduced without writes: roster denominator 174; observed constituents 19; not collected 155; window-proven 0; 180-day observed-sale lower bound 1,583; supply only on Sep 23 from 2 variants; 38 listing offers and 40 listed copies.

The frozen transport remains intact. The chart adapter exposes generation/roster pins, as-of, activity/canonical ranges, coverage, totals, sales source and sparse `{date, observedSoldCount, proofState}`, plus supply source and sparse `{date, listingOfferCount, listedQuantity, quantityProvenance, observedAt, currentUntil, state}`. It never fills a missing date; an explicit proven zero remains zero. A Sep 23 point defaults to `HISTORICAL_OBSERVATION`, never “current listings.” Capability results now explicitly return supported windows `[7,30,90,180]`. Existing asset gating remains Cards-only; Sealed and Graded do not become Activity-capable.

## Verification

- Backend service tests: 15 passed (direct instrument + Activity service/capability).
- V2 surface tests: 35 passed, 1 unrelated repository-wide filesystem-scan test deselected.
- Focused frontend Explorer/Activity tests: 32 passed.
- Python compilation: passed for API and all changed backend services.
- Optimized Next compilation: passed in 4.2 minutes; the subsequent repository-wide lint/type phase was interrupted after compilation.
- Broader frontend run exposed pre-existing/unrelated dirty-worktree contract failures, so it is not represented as a Bucket 2 green suite.

## Remaining Bucket 3 work / blockers

- Build the final three-mode chart and UX from the adapter; this bucket intentionally does not implement it.
- Measure deployed auth/SSR/Next-proxy/first-usable-render spans once application deployment is authorized.
- Supply a reproducible remote-baseline snapshot/bootstrap if a truly fresh execution of all 407 migrations is required.
- Resolve unrelated worktree frontend contract failures separately; they were preserved and not folded into this bucket.
