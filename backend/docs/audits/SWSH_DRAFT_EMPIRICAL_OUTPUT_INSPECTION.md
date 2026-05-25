# SWSH Draft Empirical Output Inspection

Generated: 2026-05-23T21:55:40.265282+00:00

Runtime approval input status: strict_db_input_passed

Read-only inspection report for swsh6 and swsh7 draft slot-schema runtime subclasses.

## Chilling Reign (swsh6)

- Pack count: 100000
- Input source: db_evr_input_preparation_service
- Input rows: 233
- Strict DB input: True
- Fallback used: False
- Price field detected: Price ($)
- Missing price rows: 0
- Non-positive price rows: 0
- Usable price rows: 233
- Estimated pack price: 10.9500
- Residual rare probability: 0.422847
- Average pack value: 3.428776
- Median pack value: 1.610000
- ROI at estimated pack price: 0.313130
- Chance to beat pack cost: 3.089000%
- Chance at big hit: 0.986000%
- P05/P95/P99: 1.300000 / 6.260000 / 31.520200

### Probability Table Status

- Sum is one: True
- Mapping keys match: True
- Production runtime enabled: True
- Production has RARE_SLOT_PROBABILITY: True

### Largest Bucket Deltas

| bucket | expected | observed | delta | abs_delta |
| --- | ---: | ---: | ---: | ---: |
| rare | 0.422847 | 0.421420 | -0.001427 | 0.001427 |
| full art v | 0.021277 | 0.021920 | 0.000643 | 0.000643 |
| holo rare | 0.333333 | 0.333740 | 0.000407 | 0.000407 |
| rainbow vmax | 0.005291 | 0.005660 | 0.000369 | 0.000369 |
| regular vmax | 0.041667 | 0.041990 | 0.000323 | 0.000323 |
| regular v | 0.133333 | 0.133020 | -0.000313 | 0.000313 |
| rainbow trainer | 0.006623 | 0.006450 | -0.000173 | 0.000173 |
| alternate art vmax | 0.002525 | 0.002670 | 0.000145 | 0.000145 |
| full art trainer | 0.013514 | 0.013620 | 0.000106 | 0.000106 |
| gold secret rare | 0.010417 | 0.010340 | -0.000077 | 0.000077 |

### Reverse Slot Sanity

- expected regular reverse count: 100000 | observed: 100000 | delta: 0
- reverse-holo leakage present: False

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

### Warning Flags

- TRIGGERED [info] reverse_pool_representation_uses_base_rows: Reverse pool contains non-reverse printing_type rows, likely because DB legacy input represents reverse-slot values through Reverse Variant Price ($). This is not rare-slot leakage when rare_slot_reverse_holo_leakage_by_bucket is empty.

## Evolving Skies (swsh7)

- Pack count: 100000
- Input source: db_evr_input_preparation_service
- Input rows: 237
- Strict DB input: True
- Fallback used: False
- Price field detected: Price ($)
- Missing price rows: 0
- Non-positive price rows: 0
- Usable price rows: 237
- Estimated pack price: 45.8600
- Residual rare probability: 0.458309
- Average pack value: 7.474066
- Median pack value: 1.200000
- ROI at estimated pack price: 0.162976
- Chance to beat pack cost: 1.385000%
- Chance at big hit: 1.105000%
- P05/P95/P99: 0.860000 / 12.490000 / 140.180100

### Probability Table Status

- Sum is one: True
- Mapping keys match: True
- Production runtime enabled: True
- Production has RARE_SLOT_PROBABILITY: True

### Largest Bucket Deltas

| bucket | expected | observed | delta | abs_delta |
| --- | ---: | ---: | ---: | ---: |
| holo rare | 0.333333 | 0.331640 | -0.001693 | 0.001693 |
| regular v | 0.116279 | 0.117420 | 0.001141 | 0.001141 |
| regular vmax | 0.054054 | 0.054760 | 0.000706 | 0.000706 |
| rare | 0.458309 | 0.457860 | -0.000449 | 0.000449 |
| alternate art vmax | 0.003534 | 0.003950 | 0.000416 | 0.000416 |
| alternate art v | 0.012195 | 0.011840 | -0.000355 | 0.000355 |
| gold secret rare | 0.004329 | 0.004500 | 0.000171 | 0.000171 |
| rainbow vmax | 0.003968 | 0.004030 | 0.000062 | 0.000062 |
| full art trainer | 0.002258 | 0.002210 | -0.000048 | 0.000048 |
| rainbow trainer | 0.001804 | 0.001840 | 0.000036 | 0.000036 |

### Reverse Slot Sanity

- expected regular reverse count: 100000 | observed: 100000 | delta: 0
- reverse-holo leakage present: False

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

### Warning Flags

- TRIGGERED [info] reverse_pool_representation_uses_base_rows: Reverse pool contains non-reverse printing_type rows, likely because DB legacy input represents reverse-slot values through Reverse Variant Price ($). This is not rare-slot leakage when rare_slot_reverse_holo_leakage_by_bucket is empty.
