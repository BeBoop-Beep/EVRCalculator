# RIP Benchmark V1 publisher dry run

**Validated only. Production publishing remained disabled and no benchmark rows were written.**

- Calibration: `rip_benchmark_v1_fin5_chase10_collector10_overall5`
- Benchmark: `pokemon_equal_weight_eligible_sets_v1`
- Market/model/evidence date: `2026-09-25` / `2026-09-25` / `2026-09-25`
- Entities/rows: `162` / `648`
- Source coherence: `passed`

| Metric | Raw reference | Score range | Clip 0 / 10 | Monotonic violations | Rank inversions | Exact anchor |
|---|---:|---:|---:|---:|---:|---:|
| Financial | 30.223709 | 2.280058–7.825118 | 0 / 0 | 0 | 0 | 5 |
| Chase | 47.691314 | 2.983149–7.596809 | 0 / 0 | 0 | 0 | 5 |
| Collector | 79.478832 | 1.959577–6.961537 | 0 / 0 | 0 | 0 | 5 |
| Overall | 35.847932 | 2.993374–7.338774 | 0 / 0 | 0 | 0 | 5 |

## Independent Opening Economics reference

Snapshot `71ead935-5a0a-43cc-b0e2-7fc7b2de6d3e`; modeled return on spend `0.387119`; cost/pack `17.468877`; EV/pack `6.762527`.

This financial-return reference is separate from every model-score `benchmark_raw_value`.

## Availability

- Inherited product Chase: 138
- Inherited product Collector: 138
- Explicit unavailable Era metric rows: 0
- Product family policy: certified
- Product Financial/Overall calibration: approved `rip_product_benchmark_v1_fin5_overall5_family_mean` (scale 5 / 5)
- Production header/row counts: 3 / 1944
