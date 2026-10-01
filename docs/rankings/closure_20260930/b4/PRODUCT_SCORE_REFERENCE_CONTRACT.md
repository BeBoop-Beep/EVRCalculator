# Product score and reference contract

## Current authority

The current paid Product Scores endpoint receives `overallRipScore` from the published Full Market Product ranking authority. Under the current release this is Overall RIP V12: an absolute `0–100` score. Its model identity is carried from `authority.overallRipVersion`.

The response now declares rather than infers:

- `scoreKind: absolute`
- `scoreScale: 0-100`
- `scoreValue`: the unchanged authority value
- `metricVersion`: the published authority version when supplied
- `benchmarkAvailable: false`

An absolute value such as `53.073` stays `53.073`. It is not divided, clamped, normalized, or routed through a 5.0-centered presentation.

## Benchmark authority and availability

The repository defines the Product family-mean Benchmark contract, but B0 found no live published Product benchmark header. B4 did not publish one. Current state is:

`PRODUCT_BENCHMARK_PUBLICATION_PENDING`

The score response therefore carries an unavailable reference with reason `product_benchmark_publication_pending`, null value, and no publication/calibration identity. The persistent Product reference strip says “Benchmark not yet published”; it never calculates a mean from returned or filtered rows.

## Explicit state separation

The optional backend `product_benchmark` input is the only activation path for Benchmark mode. It must declare `status=available` and supply Product rows plus metric, publication, calibration, rank/cohort, and compatible reference metadata. Only then does the projection emit `scoreKind: benchmark`, `scoreScale: 0-10`, and the supplied score/reference/rank. Absolute data cannot silently fill Benchmark fields, and Benchmark data cannot silently replace absolute values.

The live route currently supplies no `product_benchmark`, so the absolute path is deterministic.

## Presentation and reference behavior

The Product column is titled “Product Overall”. Absolute rows render a clean number with accessible `absolute` and `0-100` context and no `/10`, delta, arrow, or invented 5.0. A future explicitly published Benchmark row renders its supplied value with `/10`.

The reference strip is outside `<tbody>`, receives no rank, and is not part of the sorted/filtered array. Search, family filtering, and column sorting cannot change or move it. Public users receive only a locked/non-numeric reference message derived locally; no protected reference or score data enters the public response.
