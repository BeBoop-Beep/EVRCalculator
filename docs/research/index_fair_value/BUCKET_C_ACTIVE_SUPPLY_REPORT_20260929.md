# Bucket C — fixed-panel active supply launch report

## Launch result

Core Panel V1 remains frozen at 207 exact physical variants with fingerprint
`9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f`.

The required preflight used 10 targets, 19 offers/card and a 300-credit hard cap.
It made zero provider requests, spent zero credits and wrote zero database rows.
Its conservative ceiling was 200 credits.

The bounded live smoke then completed on 2026-09-29:

- run `13d1cbfc-d2ed-4310-93ba-7ab16e66d232`;
- 10/10 targets observed, zero target failures;
- 190 captured listings and 225 captured units;
- 20 successful requests and 200 provider credits;
- 20.0 actual credits/card;
- all 10 pages reported `has_more=true` and retained a next-cursor signal.

Those quantities are captured bounded depth only. They are not total market
inventory. No arrival, disappearance or turnover fact was derived.

## Privacy and evidence contract

Seller identities are persisted only as a versioned keyed HMAC. A post-smoke
audit found 190/190 hashes conforming to the contract and zero raw seller-ID,
seller-name or username keys in listing payloads. Item price, shipping, landed
price, quantity, listing update time, provider snapshot time and non-identifying
seller reputation/count fields are retained. Until the additive Bucket C
migration is applied, the new fields are preserved in the existing Bucket A
JSONB evidence boundary; after migration they populate typed columns.

Every attempted target receives either `OBSERVED` or `TARGET_FAILED`. The health
checker distinguishes no run from observed zero supply and can explicitly write
one `RUN_MISSING` row per expected target. Missing collection is never treated as
a listing disappearance. `continuity_eligible` remains false at launch.

## Cost and storage projection

At the measured 20.0 credits/card, a 207-card run projects to 4,140 credits/day.
That is 20.7% of the 20,000-credit Pro allowance before Bucket B use and reserve;
the combined plan still requires review before scheduling.

At the current 19-listing bound, a full day is at most 4,141 rows (one run, 207
summaries and 3,933 listing observations), or 1,511,465 rows/year. Serialized
smoke payload size was 134,645 bytes, averaging 13,464.5 bytes/card. Linear
projection is about 2.658 MiB/day or 0.947 GiB/year before PostgreSQL indexes,
tuple overhead, TOAST behavior, and backups; capacity planning should budget
above that wire-format estimate.

## Scheduling gate

No recurring workflow is included. The 207-card daily panel must remain disabled
until this smoke/cost report is reviewed, Bucket B's measured PkmnPrices budget is
combined with this 4,140-credit projection, and an operational reserve is chosen.
The daily plan after approval is: collect once per UTC observation date, then run
the coverage checker; if collection did not occur, explicitly record the missing
run. Arrival/disappearance remains blocked until adjacent expected dates were
both successfully observed and the broader 30-day maturity gate is met.
