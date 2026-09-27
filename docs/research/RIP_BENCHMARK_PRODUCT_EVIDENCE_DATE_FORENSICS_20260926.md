# RIP Benchmark V1 product evidence-date forensics

## Conclusion

The September 15 model / September 14 product-price offset is **case B: stale
publication sequencing**, not a certified prior-close pricing convention.
Historical product financial evidence therefore remains unavailable. The
deployed benchmark constraint must not be weakened, and no database migration
is required to explain or repair this historical generation.

## Production evidence

- All 22 authoritative calculation runs have `market_date = 2026-09-15` and
  were created on September 15 beginning at 17:02 UTC.
- All 138 exact product result rows were written on September 15 but carry
  `price_as_of = 2026-09-14`, source `TCGPLAYER`.
- The price-observation table contains September 15 observations for all 138
  products. Those observations were persisted between 08:06 and 08:47 UTC,
  more than eight hours before the calculation runs began.
- Therefore the newer observations existed before model execution. The product
  scorer consumed a stale sealed-market snapshot rather than an intentionally
  unavailable same-day market close.

## Code path

`evr_runner.py` passes the calculation run's market date to
`run_stage1_sealed_product_rip`. That service calls `read_snapshot(...,
market_date=...)`. `clip_snapshot_as_of` truthfully selects the most recent
observation at or before the requested date; it does not certify that the
selected observation is from the requested date. The result writer then stores
the selected snapshot's `priceAsOf` verbatim as `price_as_of`.

This behavior is useful for historical reconstruction, but it is not sufficient
for a same-day benchmark evidence contract. The benchmark DB correctly requires
`financial_evidence_market_date = publication.market_date`; treating an older
price as same-day evidence would destroy the distinction the schema enforces.

## Required pipeline fix

Before future benchmark publication can require product evidence:

1. Rebuild every canonical sealed-market snapshot after the day's sealed-price
   observations are complete and before simulation starts.
2. Add a simulation/publication readiness gate requiring the snapshot authority
   date and every selected product `priceAsOf` to equal the calculation-run
   market date for products intended to carry same-day benchmark evidence.
3. Fail the product-evidence slice closed when the gate fails; do not fall back
   to an older observation and relabel it.
4. Preserve `model_market_date`, `price_as_of`, source, snapshot fingerprint,
   calculation run, and result ID in diagnostics so future audits can distinguish
   a same-day result from an at-or-before historical reconstruction.

The model scores remain canonical results of their exact runs. Only the
financial-evidence availability is affected.

## Database follow-up decision

No additive database extension is required for this finding because the offset
was not an approved prior-close semantic. If product leadership later adopts an
explicit prior-close policy, that would require a separate reviewed migration
with distinct `model_market_date`, `financial_evidence_market_date`, and
`product_price_as_of` fields plus an allowed-lag policy. That policy must not be
retroactively inferred from this stale September 15 generation.
