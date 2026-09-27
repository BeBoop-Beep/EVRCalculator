# RIP Benchmark V1 publisher dry run

**Validated only. Production publishing remained disabled and no benchmark rows were written.**

- Calibration: `rip_benchmark_v1_fin5_chase10_collector10_overall5`
- Benchmark: `pokemon_equal_weight_eligible_sets_v1`
- Market/model/evidence date: `2026-09-15` / `2026-09-15` / `2026-09-15`
- Entities/rows: `162` / `648`
- Source coherence: `passed`

| Metric | Raw reference | Score range | Clip 0 / 10 | Monotonic violations | Rank inversions | Exact anchor |
|---|---:|---:|---:|---:|---:|---:|
| Financial | 31.943423 | 2.146215–7.034835 | 0 / 0 | 0 | 0 | 5 |
| Chase | 47.660218 | 2.943588–7.608328 | 0 / 0 | 0 | 0 | 5 |
| Collector | 79.723245 | 1.935135–6.937095 | 0 / 0 | 0 | 0 | 5 |
| Overall | 37.350082 | 2.811084–6.771564 | 0 / 0 | 0 | 0 | 5 |

## Independent Opening Economics reference

Snapshot `42c4489b-bedb-4623-b934-9e34a8c17605`; modeled return on spend `0.392046`; cost/pack `17.697026`; EV/pack `6.938047`.

This financial-return reference is separate from every model-score `benchmark_raw_value`.

## Availability

- Inherited product Chase: 138
- Inherited product Collector: 138
- Explicit unavailable Era metric rows: 0
- Product family policy: certified
- Product Financial/Overall calibration: shadow candidates only; not approved
- Production header/row counts: 0 / 0
