# Effort 1H Cards Watermark — historical-horizon acceptance

Outcome: `CARDS_PUBLICATION_WATERMARK_CORRECTED`

## Contract correction

Cards publication freshness now comes from the Market Explorer quality
authority: the latest `pokemon_market_date_quality.market_date` for
`tcg='pokemon'` with status `READY` or `LEGACY_VERIFIED`.

The Set Value coverage rollup remains only a scoped history-existence guard. It
no longer supplies the Cards publication date. Sealed resolution is unchanged.

The dedicated Cards resolver accepts an optional upper horizon for deterministic
historical acceptance. Normal application calls omit it and resolve the latest
usable quality date.

## Deterministic contracts

- Set Value at D3 and quality at D2 resolves D2.
- Cohort maximum date equals the Cards watermark.
- READY D1, DEGRADED D2, READY D3 resolves D3.
- An open/coverage horizon at D3 and quality at D2 resolves D2.
- A scope without history raises instead of inventing a date.
- D1 -> D2 quality publication misses old L1 and incrementally requests
  `[D1,D2]`.
- A ready D2 L2 remains a true hit when Set Value is already at D3.
- Golden fingerprint remains
  `2cb8862bc86ab03be481ae12f163838a5c9a6371ffc5613cbac03d27b139541d`.

Focused Cards/Sealed/planner/fingerprint verification: 130 passed.

## Production read-only acceptance at 2026-08-28

- quality watermark through the explicit horizon: `2026-08-28`
- cohort result `asOf`: `2026-08-28`
- Fossil Cards L2 `computed_through`: `2026-08-28`
- ten fresh-worker sources: `persistent_cache`
- novel calls: zero (the harness raises if claim, publish, or novel is reached)
- twenty same-worker sources: `memory_cache`
- L2 reads during the twenty L1 samples: zero

| Path | Median ms | p95 ms | Min ms | Max ms |
|---|---:|---:|---:|---:|
| Cards persistent L2 | 268.573 | 507.359 | 235.617 | 507.359 |
| Cards L1 | 2.762 | 3.000 | 2.657 | 3.000 |

These are backend-to-production measurements, not network-free dictionary-only
timings. No production writes occurred. The separate 2026-08-29/30 backfill was
not inspected, modified, restarted, awaited, or used as an acceptance dependency.
