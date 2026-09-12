# inDex Fair Value — eBay Supply D1

## Decision

`EBAY_SUPPLY_SIGNAL_NOT_READY`. Browse access works, but the pilot does not yet establish an identity authority with measured precision. No Fair Value model was fit.

## Access and API contract

The stored eBay client credentials successfully completed the application-token flow and an `EBAY_US` Browse search returned HTTP 200. The supported endpoint is `GET /buy/browse/v1/item_summary/search`; it exposes listing identity, title, price, condition, buying options, shipping containers, and seller data. Pagination uses `limit`, `offset`, and the returned `next` URI. eBay warns that `total` is an estimate and should not control pagination.

The default Browse allowance is 5,000 calls/day. Production use remains restricted: eBay requires an EPN application, business-model review, Developer Support approval, and applicable contracts. Credential/API success is not evidence that the application has completed production licensing. Storage must be purpose-limited and reviewed against the API License Agreement before production use.

The repository contains a frontend `/api/ebaySearch` proxy, but its referenced backend `/integrations/ebay/search` implementation was not found.

## Frozen pilot

Seventy cards were selected deterministically across all seven Fair Value price bands and the Collector Appeal range before querying. The final pilot capture made 70 calls, returned 6,644 first-page results, encountered no rate-limit events, and averaged 771 ms/call.

The conservative classifier counted 3,961 raw-condition exact matches. Sixty-nine of 70 cards had at least one accepted result (98.57% coverage). Per-card accepted counts are first-page counts, not complete market depth.

Contamination among returned results was 16.16% graded, 5.66% wrong-card, 0.11% detected lot/bundle, and 12.40% likely/ambiguous. Seller identifiers were present for 69 cards, supporting unique-seller and concentration research; listing quantity depth was not available. Price quartiles, IQR, CV, fixed-price count, and auction count were available. Shipping-adjusted price remains null unless a destination-applicable numeric charge is unambiguous.

The five retained exact-match examples were visually consistent with their canonical card, but this convenience sample is too small and not independently randomized. Exact-match precision is therefore **not estimated**. Set abbreviations, title omissions, artwork/parallel ambiguity, card-number collisions, misleading “pack fresh” language, and condition labels that say only “Ungraded” are the major failure modes. `RAW_ELIGIBLE_CONDITION` must not be described as Near Mint.

## Cost and cadence

One page per card costs 4,349 calls per full cohort, fitting beneath the current 5,000-call daily default when run in isolation. Weekly capture is about 18,846 calls/month. Complete pagination could exceed this materially and is not costed from the unreliable `total` estimate. No scheduler should be created until matching precision passes an independent review gate.

## Point-in-time authority design

The proposal contains append-only source runs, listing observations, and card aggregates. Every row stores distinct `observed_at` and `captured_at`; a current listing must never be backfilled as historical. Raw payload storage is minimal and contingent on legal approval. No DDL was applied.

## Research boundary

An active snapshot measures offered supply and asking-price dispersion. It does not measure completed demand, sell-through, velocity, or realized price. Marketplace Insights remains Limited Release and existing completed-sales entitlement is unverified. PSA Population Reports are available manually by grade, while the public API documents single-cert verification only; automated population collection remains unverified and was not attempted.

One current snapshot would be sufficient for a cross-sectional experiment only after match precision is independently measured and variant/condition contamination is brought under an approved threshold. D1 has not crossed that gate.
