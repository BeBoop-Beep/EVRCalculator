# Rankings Bucket 0 handoff

## Readiness verdict

`BUCKET_1_PUBLIC_ACCESS_CONTRACT_READY`

The independently scoped public-access contract is ready even though Product Benchmark publication and authenticated browser evidence remain blocked. Missing MSRP and exact-SKU entertainment cost do not block Bucket 1.

## Bucket 1 — public access

- Add a narrow public Benchmark-headline projection for Era/Set using the field matrix in `CONTRACT_DECISIONS.md`.
- Keep the wide scorecards endpoint protected.
- Include Set logo and symbol in the one identity query and adapters.
- Reuse the existing opening-economics base projection for public Set counts/average pack cost.
- Add a direct exact-product catalogue authority with deterministic alphabetical DB order; do not rank then alphabetize and do not expose price/economics.
- Add byte-level negative tests for every protected field and anonymous browser tests.

## Bucket 2 — score presentation/Product authority

- Stop wrapping absolute Product Overall scores in the 5.0 benchmark presenter.
- Preferred closure: publish and read the existing `pokemon_product_family_equal_weight_v1` / `rip_product_benchmark_v1_fin5_overall5_family_mean` authority, preserving family-specific reference identity and rank semantics.
- If publication is deferred, show the absolute 0–100 metric truthfully with model/cohort context and no invented Overall reference.
- Keep Financial semantics distinct; no generic 5.0 unless the calibrated Product Financial row is actually published.

## Bucket 3 — Set Pack Economics

- Flatten Set -> exact Products by joining existing exact Product prepared rows by `sealedProductId`.
- Preserve Set aggregate and internal family weighting, but do not render family rows.
- Populate cost, pack count, EV/pack, modeled return, published recovery semantics, exact Best-Open and independent dates from exact authorities.
- Leave entertainment cost unavailable until an exact-SKU projection/approved derivation exists.

## Bucket 4 — artwork and identity

- Add separate logo/symbol fields to shared Set identity projections, scorecard adapter, Pack Economics, Product secondary identity and Card Set identity.
- Preserve `logo -> symbol -> initials`; add coverage/fallback fixtures.
- No per-row metadata fetches.

## Bucket 5 — Product UI/MSRP/Best-Open

- Move Scores/Economics control into the table header after the Product authority is corrected.
- Keep exact Best-Open and its `source_market_date`; simplify explanation to an info popover.
- Do not show MSRP. Add it only after a provenance-complete manufacturer-backed store exists.

## Bucket 6 — Cards and performance

- Run the authenticated reproducers before query redesign.
- Add explicit loading, empty, error and retry states; an error must not look like zero ranked cards.
- Measure module, cache, proxy, backend, DB, payload and React phases separately on the production build.
- Preserve global component ranks by keeping filters after global ranking.

## Remaining blockers

- No published canonical Product Benchmark header exists live for the defined Product key/calibration.
- Exact-SKU entertainment cost is not prepared.
- Authenticated Product/Card browser timings and login-without-refresh reproduction require an authorized Plus test session.
- The focused frontend suite has one stale regex contract failure; one budget service test command did not complete within the command window.

No Bucket 1–7 implementation was performed.
