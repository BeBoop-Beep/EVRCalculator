# PkmnPrices sold-history shape and persistence — 2026-09-29

## Provider history is cursor-bounded, not day-window bounded

The PkmnPrices card eBay sold endpoint has no 1D / 30D / 90D / lifetime parameter. It exposes cursor-paginated retained sold comps. A historical collector can keep requesting older cursor pages until the provider returns `has_more=false`.

The API documentation calls these "recent eBay sold comps" but does not publish a guaranteed universal retention horizon. Therefore the correct interpretation is:

- **not one day**
- **not capped at 30 days by our integration**
- **not contractually guaranteed lifetime history**
- **all provider-retained rows are reachable by cursor pagination**
- the oldest available `sold_at` can vary materially by card/source page

The `since` parameter is an incremental-ingestion checkpoint, not a sale-date lookback. It filters on `ingested_at`. A transaction collected today may have a `sold_at` weeks or months earlier.

## What our completed 12-card vintage backfill proves

All 12 current vintage-gap provider identities have exhausted their historical cursor and are marked `backfill_complete=true`.

Current persisted archive:

- 2,702 distinct provider transactions
- 12 canonical cards
- oldest `sold_at`: **2024-05-31**
- newest `sold_at`: **2026-09-28**
- first provider ingestion represented in the archive: 2026-07-26
- newest provider ingestion represented: 2026-09-29

Examples show how uneven the provider-retained shape is:

| Card identity | Stored transactions | Provider-retained sold span |
| --- | ---: | --- |
| Shining Noctowl target | 103 | 2024-05-31 → 2026-09-22 |
| Shining Gyarados target | 140 | 2026-04-15 → 2026-09-28 |
| Base Gyarados target | 326 | 2026-07-19 → 2026-09-28 |
| Base Blastoise target | 308 | 2026-07-20 → 2026-09-28 |
| Base Hitmonchan target | 290 | 2026-07-20 → 2026-09-28 |

That variation is provider/data-source history, not an application-level lookback restriction.

PkmnPrices public catalog pages also expose examples with eBay sold rows dating into 2022 and 2023, so multi-year retention exists for at least some cards. It should not be treated as a guaranteed minimum for every card.

## What we persist

`public.pkmnprices_ebay_sold_evidence_v1` is append-only transaction evidence. Each stored row preserves:

- provider listing ID
- provider card ID
- canonical card ID
- internal card variant ID when resolvable
- title
- sold price
- currency
- graded / grader / grade
- provider printing variant
- attribution state
- `sold_at`
- `ingested_at`
- source listing URL
- internal identity classification
- Fair Value eligibility flag
- hard-false Set Value / NM eligibility
- condition state = UNKNOWN
- exclusion reason
- collection timestamp
- full provider payload

Uniqueness is enforced by `(provider_listing_id, provider_card_id)`. Re-runs do not duplicate economic transactions. Provider-side enrichment drift is detected but the first-seen raw evidence row is not silently rewritten.

`public.pkmnprices_sold_sync_state_v1` separately records collection state and watermarks.

This means our own archive can become longer-lived than the provider's future retention window. Once a sold transaction is captured, it remains available to internal research even if an old comp later disappears from the provider feed.

## Broad Fair Value cohort persistence

The first 207-card sold-signal pilot fetched at most 20 sold rows per sampled card and wrote only aggregate research files. Those raw provider rows were not retained.

The next broad pilot now uses the exact same provider calls to additionally persist the returned raw transactions into the existing shadow evidence tables via `--persist-evidence`. Persistence itself consumes no additional provider credits.

The broad research rows remain:

- condition unknown
- research-only
- not Set Value authority
- not Near Mint authority
- not production Fair Value authority

The broad workflow still performs the V2 leakage-free analysis after collection.

## Research interpretation

For Fair Value V2, transaction history should initially be used for:

1. liquidity / transaction depth
2. recency
3. price dispersion
4. market-clearing disagreement with the existing baseline
5. trend / direction
6. confidence or uncertainty

Raw sold dollars should not be converted into an NM price target until condition normalization is separately validated.

## Next history expansion

The 20-row broad pilot is intentionally a bounded first capture, not a complete historical backfill. A follow-up historical backfill should use the saved provider identities and cursor pagination in bounded credit-controlled passes until each research target is exhausted.

After that point, daily incremental polling should checkpoint on `ingested_at`, preserving late-arriving sales whose `sold_at` is older than the current day.
