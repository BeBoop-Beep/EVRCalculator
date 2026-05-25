# SWSH Production Runtime Smoke

Generated: 2026-05-23T23:27:02.246940+00:00

Read-only production-runtime smoke report for swsh6 and swsh7.

Runtime approval input status: strict_db_input_passed

## Chilling Reign (swsh6)

- Input source: db_evr_input_preparation_service
- Input rows: 233
- Usable price rows: 233
- Simulation engine: slot_schema
- Runtime enabled: True
- Production probability sum: 1.000000
- Residual rare probability: 0.422847
- Estimated pack price used: $10.950000
- Estimated pack price source: EVRInputPreparationService.prepare_for_set.pack_price
- Estimated pack price resolution status: resolved
- Average pack value: $3.407006
- Median pack value: 1.610000
- ROI at estimated pack price: -68.885786%
- ROI formula: (average_pack_value - estimated_pack_price) / estimated_pack_price
- ROI consistency check: passed (abs_delta=0.000000000000)
- Chance to beat pack cost: 3.016000%
- P05/P95/P99: 1.300000 / 6.150000 / 31.550000

### Largest Bucket Deltas

| bucket | expected | observed | delta | abs_delta |
| --- | ---: | ---: | ---: | ---: |
| rare | 0.422847 | 0.421390 | -0.001457 | 0.001457 |
| holo rare | 0.333333 | 0.334650 | 0.001317 | 0.001317 |
| regular v | 0.133333 | 0.134060 | 0.000727 | 0.000727 |
| rainbow vmax | 0.005291 | 0.004890 | -0.000401 | 0.000401 |
| regular vmax | 0.041667 | 0.041350 | -0.000317 | 0.000317 |
| full art trainer | 0.013514 | 0.013800 | 0.000286 | 0.000286 |
| gold secret rare | 0.010417 | 0.010620 | 0.000203 | 0.000203 |
| full art v | 0.021277 | 0.021120 | -0.000157 | 0.000157 |
| alternate art v | 0.009174 | 0.009080 | -0.000094 | 0.000094 |
| alternate art vmax | 0.002525 | 0.002460 | -0.000065 | 0.000065 |

### Top EV-Contributing Cards

| card | ev_contribution | share_of_hit_ev |
| --- | ---: | ---: |
| Blaziken VMAX (Alternate Art Secret) | 0.303342 | 14.402453% |
| Galarian Moltres V (Alternate Full Art) | 0.194119 | 9.216646% |
| Snorlax (Secret) | 0.112639 | 5.348015% |
| Zeraora V (Alternate Full Art) | 0.080294 | 3.812283% |
| Galarian Slowking V (Alternate Full Art) | 0.079431 | 3.771337% |
| Galarian Rapidash V (Alternate Full Art) | 0.074486 | 3.536554% |
| Galarian Articuno V (Alternate Full Art) | 0.060706 | 2.882298% |
| Shadow Rider Calyrex VMAX (Alternate Art Secret) | 0.058283 | 2.767228% |
| Gengar | 0.053472 | 2.538823% |
| Galarian Zapdos V (Alternate Full Art) | 0.052706 | 2.502464% |

### Reverse Slot Sanity

- expected regular reverse count: 100000 | observed: 100000 | delta: 0
- reverse-holo leakage present: False

### Warning Flags

- No warning flags triggered.

## Evolving Skies (swsh7)

- Input source: db_evr_input_preparation_service
- Input rows: 237
- Usable price rows: 237
- Simulation engine: slot_schema
- Runtime enabled: True
- Production probability sum: 1.000000
- Residual rare probability: 0.458309
- Estimated pack price used: $45.860000
- Estimated pack price source: EVRInputPreparationService.prepare_for_set.pack_price
- Estimated pack price resolution status: resolved
- Average pack value: $7.306826
- Median pack value: 1.200000
- ROI at estimated pack price: -84.067105%
- ROI formula: (average_pack_value - estimated_pack_price) / estimated_pack_price
- ROI consistency check: passed (abs_delta=0.000000000000)
- Chance to beat pack cost: 1.452000%
- P05/P95/P99: 0.850000 / 12.570000 / 144.390200

### Largest Bucket Deltas

| bucket | expected | observed | delta | abs_delta |
| --- | ---: | ---: | ---: | ---: |
| rare | 0.458309 | 0.455980 | -0.002329 | 0.002329 |
| alternate art v | 0.012195 | 0.013280 | 0.001085 | 0.001085 |
| regular vmax | 0.054054 | 0.054640 | 0.000586 | 0.000586 |
| holo rare | 0.333333 | 0.333850 | 0.000517 | 0.000517 |
| gold secret rare | 0.004329 | 0.004820 | 0.000491 | 0.000491 |
| regular v | 0.116279 | 0.116000 | -0.000279 | 0.000279 |
| full art trainer | 0.002258 | 0.002420 | 0.000162 | 0.000162 |
| alternate art vmax | 0.003534 | 0.003430 | -0.000104 | 0.000104 |
| rainbow vmax | 0.003968 | 0.003890 | -0.000078 | 0.000078 |
| rainbow trainer | 0.001804 | 0.001740 | -0.000064 | 0.000064 |

### Top EV-Contributing Cards

| card | ev_contribution | share_of_hit_ev |
| --- | ---: | ---: |
| Umbreon VMAX (Alternate Art Secret) | 1.278563 | 21.285822% |
| Rayquaza VMAX (Alternate Art Secret) | 0.556749 | 9.268892% |
| Dragonite V (Alternate Full Art) | 0.522106 | 8.692152% |
| Rayquaza V (Alternate Full Art) | 0.428027 | 7.125889% |
| Umbreon V (Alternate Full Art) | 0.395477 | 6.583991% |
| Espeon V (Alternate Full Art) | 0.253725 | 4.224075% |
| Sylveon VMAX (Alternate Art Secret) | 0.221384 | 3.685653% |
| Leafeon VMAX (Alternate Art Secret) | 0.218009 | 3.629473% |
| Sylveon V (Alternate Full Art) | 0.174102 | 2.898491% |
| Glaceon VMAX (Alternate Art Secret) | 0.167079 | 2.781570% |

### Reverse Slot Sanity

- expected regular reverse count: 100000 | observed: 100000 | delta: 0
- reverse-holo leakage present: False

### Warning Flags

- No warning flags triggered.

## SV/Mega Guardrail

- Changed: False
- All expected v2: True
