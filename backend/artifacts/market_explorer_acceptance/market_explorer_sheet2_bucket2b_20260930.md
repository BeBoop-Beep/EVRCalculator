# Market Explorer Fix Sheet 2 — Bucket 2B closure

Date: 2026-09-30 (America/Phoenix)

Starting SHA: `6960bf41af03829b7e1eef80009bf641f38af571`

Branch: `fix/market-explorer-sheet2-backend-closure-20260930`

Final commit: the commit containing this receipt (reported in the handoff).

## Safety

No production writes, migration, deployment, serving-pointer change, provider collection, or Bucket 1 movement-methodology change occurred. Production access was read-only.

## Activity evidence precision

FMA v1.1 does not contractually require listing-count and listed-quantity points to share every date. The chart adapter therefore builds the sorted union of both date sets. Each side is independent: absent listing count is `null`, absent listed quantity is `null`, and an explicit zero remains numeric zero.

A date-only aggregate remains date-only. The adapter no longer turns `2026-09-23` into a fabricated midnight timestamp. With no aggregate provider-confirmed timestamp, the Prismatic supply DTO is:

```json
{
  "date": "2026-09-23",
  "listingOfferCount": 38,
  "listedQuantity": 40,
  "contributingConstituents": 2,
  "quantityProvenance": "LOWER_BOUND_SUM_OF_CONFIRMED_CONSTITUENT_SNAPSHOTS",
  "observedAt": null,
  "currentUntil": null,
  "state": "HISTORICAL_OBSERVATION"
}
```

No interpolation, zero-fill, OHLC, demand score, turnover inference, earliest/latest-member timestamp, build timestamp, or midnight synthesis is present.

## Direct Card canonical history

The Card reader now combines:

1. the existing backend-only `get_card_variant_price_observed_history_v2` Price Storage V2 RPC, fixed to Near Mint / TCGPlayer / USD and bounded through today; and
2. retained `pokemon_market_explorer_card_daily_states_v2_shadow` rows.

Price Storage V2 reconstructs lossless observed-date history from compressed observation-presence ranges plus price-change events. This is preferable to exposing the ACL-hardened interval table through PostgREST; production confirmed that table is intentionally absent from the Data API schema cache. No migration or broader grant was introduced.

Rows merge by date. Positive, non-future daily evidence deterministically overwrites a same-date Price Storage V2 point. No missing calendar dates are generated and no forward-fill is performed by the application.

Representative production read, Umbreon ex variant `3b62356c-ea20-43cd-a161-24cd6b1ed35e`:

| | Before | After |
|---|---|---|
| first date | 2026-06-22 | 2026-05-28 |
| last date | 2026-09-29 | 2026-09-29 |
| unique sparse points | 92 | 95 |

The complete series normalizes exactly once from the May 28 raw price of 1.00, producing Index 100. It is clipped only after normalization. A production `startDate=2026-07-19` response begins with raw price 500.00 and Index 50,000—not a reset to 100. Dates are strictly ordered and unique; non-positive and future points are excluded.

## Direct Sealed audit

Repository services, sealed snapshots, market movement SQL, and product detail all identify `sealed_product_price_observations` as the canonical Sealed history authority; no separate earlier compressed/interval authority was found. The direct reader remains unchanged: positive USD observations, legacy null/lowercase USD normalization, and latest valid observation per date.

Production sample `404e8168-71f9-4ab2-b814-7ebe157fcbcb` contained 158 valid USD rows across 156 dates. Direct output contained the same 156 dates, 2026-04-07 through 2026-09-30. No gap requiring reconciliation was found.

## Frozen FMA regression

The Bucket 2 envelope correction remains in force: a database `2026-09-30T12:01:00+00:00` constituent-page `validated_at` is emitted as `2026-09-30T12:01:00Z`. The real-shaped page, group, and instrument responses each validate with zero errors against their frozen FMA v1.1 schemas. Schema strictness, `additionalProperties`, date-time format, response validation, and `contractVersion` were not loosened.

## Entitlement and bounds

The direct endpoint still accepts exactly one UUID catalogue identity and has no auth/plan dependency. List-valued IDs and extra arbitrary-basket fields fail request validation. The arbitrary exact-basket query continues through its unchanged Premium feature boundary. Request bounds are unchanged: search 3s; directory/Screen 4s; Activity 6s; prepared/constituents/direct 8s; only custom build 45s.

## Verification

- Backend direct/Activity/capability tests: 18 passed.
- Focused Activity/bounds frontend tests: 7 passed.
- Frozen schemas: page/group/instrument, zero validation errors.
- Python compilation: API and changed backend services passed.
- Optimized Next compilation: passed in 3.9 minutes; the repository-wide lint/type phase remained hung and was interrupted after successful compilation.
- Production reads: Umbreon complete-history and start-date normalization receipts passed; Sealed authority reconciliation passed.
- The new public-direct runtime cases were added to the existing FastAPI route suite. That suite's local import remained hung in the repository's pre-existing full API test environment, so it is not counted above.

No Bucket 3 blocker remains in the Option 1 DTO. Bucket 3 must render `observedAt: null` as date-only evidence and retain the nullable independent supply measures.
