# SWSH Project 16.5 Pull Rate Odds Validation

Final decision: `closed_pull_rate_odds_validated_with_rounding_warnings`

## Guardrails
- db_mutation_performed=false
- execute_rerun_performed=false
- simulator_rerun_performed=false

## Sets Checked
- swsh6: target_id=1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890, run_id=0dd7683c-4146-4dcd-a04c-6f686bd91417
- swsh7: target_id=93212749-ce0e-498e-975e-7d947a3448ce, run_id=91e93106-b677-46de-b398-6728aa7842fb

## swsh6

### Meta Sources
- pull_rate_assumptions_card_counts: OK
- pull_rate_assumptions_bucket_classification: OK
- pull_rate_assumptions_bucket_classification_source: READ_TIME_CARD_METADATA_CLASSIFICATION
- pull_rate_assumptions_regular_reverse_count: OK

### Recomputed Card Pool Counts
- pack_structure: common=43, uncommon=46, rare=23, regular reverse=112
- hit_rarity_model:
  - holo rare: count=24, empty=False, sample=Cinderace, Cobalion, Froslass
  - regular v: count=15, empty=False, sample=Sandaconda V, Blissey V, Galarian Slowking V
  - regular vmax: count=8, empty=False, sample=Tornadus VMAX, Blaziken VMAX, Ice Rider Calyrex VMAX
  - full art v: count=16, empty=False, sample=Blissey V (Full Art), Galarian Articuno V (Full Art), Tornadus V (Full Art)
  - full art trainer: count=13, empty=False, sample=Avery (Full Art), Caitlin (Full Art), Honey (Full Art)
  - alternate art v: count=10, empty=False, sample=Galarian Slowking V (Alternate Full Art), Shadow Rider Calyrex V (Alternate Full Art), Galarian Moltres V (Alternate Full Art)
  - alternate art vmax: count=3, empty=False, sample=Shadow Rider Calyrex VMAX (Alternate Art Secret), Blaziken VMAX (Alternate Art Secret), Ice Rider Calyrex VMAX (Alternate Art Secret)
  - rainbow trainer: count=12, empty=False, sample=Doctor (Secret), Brawly (Secret), Karen's Conviction (Secret)
  - rainbow vmax: count=8, empty=False, sample=Galarian Slowking VMAX (Secret), Celebi VMAX (Secret), Blaziken VMAX (Secret)
  - gold secret rare: count=12, empty=False, sample=Bronzong (Secret), Snorlax (Secret), Fan of Waves (Secret)

### Math Validation
| Group | Rarity | Raw P | Raw Denom | Pull Label | Eligible N | Computed Specific | Payload Specific | Delta | Pass |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| pack_structure | common | 5.0 | None | 5 per pack | 43 | 8.6 | 8.6 | 0.0 | PASS |
| pack_structure | uncommon | 3.0 | None | 3 per pack | 46 | 15.333333333333334 | 15.333333333333334 | 0.0 | PASS |
| pack_structure | rare | 0.4228468044426511 | 2 | 1 in 2.4 packs | 23 | 54.39322174922429 | 54.39322174922429 | 0.0 | PASS |
| pack_structure | regular reverse | 1.0 | 1 | 1 per pack | 112 | 112.0 | 112.0 | 0.0 | PASS |
| hit_rarity_model | holo rare | 0.3333333333333333 | 3 | 1 in 3 packs | 24 | 72 | 72 | 0.0 | PASS |
| hit_rarity_model | regular v | 0.13333333333333333 | 8 | 1 in 8 packs | 15 | 120 | 120 | 0.0 | PASS |
| hit_rarity_model | regular vmax | 0.041666666666666664 | 24 | 1 in 24 packs | 8 | 192 | 192 | 0.0 | PASS |
| hit_rarity_model | full art v | 0.02127659574468085 | 47 | 1 in 47 packs | 16 | 752 | 752 | 0.0 | PASS |
| hit_rarity_model | full art trainer | 0.013513513513513514 | 74 | 1 in 74 packs | 13 | 962 | 962 | 0.0 | PASS |
| hit_rarity_model | alternate art v | 0.009174311926605505 | 109 | 1 in 109 packs | 10 | 1090 | 1090 | 0.0 | PASS |
| hit_rarity_model | alternate art vmax | 0.0025252525252525255 | 396 | 1 in 396 packs | 3 | 1188 | 1188 | 0.0 | PASS |
| hit_rarity_model | rainbow trainer | 0.006622516556291391 | 151 | 1 in 151 packs | 12 | 1812 | 1812 | 0.0 | PASS |
| hit_rarity_model | rainbow vmax | 0.005291005291005291 | 189 | 1 in 189 packs | 8 | 1512 | 1512 | 0.0 | PASS |
| hit_rarity_model | gold secret rare | 0.010416666666666666 | 96 | 1 in 96 packs | 12 | 1152 | 1152 | 0.0 | PASS |

## swsh7

### Meta Sources
- pull_rate_assumptions_card_counts: OK
- pull_rate_assumptions_bucket_classification: OK
- pull_rate_assumptions_bucket_classification_source: READ_TIME_CARD_METADATA_CLASSIFICATION
- pull_rate_assumptions_regular_reverse_count: OK

### Recomputed Card Pool Counts
- pack_structure: common=42, uncommon=51, rare=19, regular reverse=112
- hit_rarity_model:
  - holo rare: count=20, empty=False, sample=Victini, Florges, Galarian Moltres
  - regular v: count=18, empty=False, sample=Arctovish V, Dracozolt V, Lycanroc V
  - regular vmax: count=15, empty=False, sample=Gyarados VMAX, Glaceon VMAX, Vaporeon VMAX
  - full art v: count=22, empty=False, sample=Dracozolt V (Full Art), Glaceon V (Full Art), Jolteon V (Full Art)
  - full art trainer: count=5, empty=False, sample=Copycat (Full Art), Gordie (Full Art), Raihan (Full Art)
  - alternate art v: count=11, empty=False, sample=Leafeon V (Alternate Full Art), Sylveon V (Alternate Full Art), Rayquaza V (Alternate Full Art)
  - alternate art vmax: count=6, empty=False, sample=Duraludon VMAX (Alternate Art Secret), Umbreon VMAX (Alternate Art Secret), Rayquaza VMAX (Alternate Art Secret)
  - rainbow trainer: count=5, empty=False, sample=Gordie (Secret), Copycat (Secret), Raihan (Secret)
  - rainbow vmax: count=11, empty=False, sample=Dracozolt VMAX (Secret), Glaceon VMAX (Secret), Garbodor VMAX (Secret)
  - gold secret rare: count=12, empty=False, sample=Froslass (Secret), Full Face Guard (Secret), Lightning Energy (Secret)

### Math Validation
| Group | Rarity | Raw P | Raw Denom | Pull Label | Eligible N | Computed Specific | Payload Specific | Delta | Pass |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| pack_structure | common | 5.0 | None | 5 per pack | 42 | 8.4 | 8.4 | 0.0 | PASS |
| pack_structure | uncommon | 3.0 | None | 3 per pack | 51 | 17.0 | 17.0 | 0.0 | PASS |
| pack_structure | rare | 0.45830871993712796 | 2 | 1 in 2.2 packs | 19 | 41.45677176425199 | 41.45677176425199 | 0.0 | PASS |
| pack_structure | regular reverse | 1.0 | 1 | 1 per pack | 112 | 112.0 | 112.0 | 0.0 | PASS |
| hit_rarity_model | holo rare | 0.3333333333333333 | 3 | 1 in 3 packs | 20 | 60 | 60 | 0.0 | PASS |
| hit_rarity_model | regular v | 0.11627906976744186 | 9 | 1 in 9 packs | 18 | 162 | 162 | 0.0 | PASS |
| hit_rarity_model | regular vmax | 0.05405405405405406 | 18 | 1 in 18 packs | 15 | 270 | 270 | 0.0 | PASS |
| hit_rarity_model | full art v | 0.00993676603432701 | 101 | 1 in 101 packs | 22 | 2222 | 2222 | 0.0 | PASS |
| hit_rarity_model | full art trainer | 0.002258355916892502 | 443 | 1 in 443 packs | 5 | 2215 | 2215 | 0.0 | PASS |
| hit_rarity_model | alternate art v | 0.012195121951219513 | 82 | 1 in 82 packs | 11 | 902 | 902 | 0.0 | PASS |
| hit_rarity_model | alternate art vmax | 0.0035335689045936395 | 283 | 1 in 283 packs | 6 | 1698 | 1698 | 0.0 | PASS |
| hit_rarity_model | rainbow trainer | 0.001803751803751804 | 554 | 1 in 554 packs | 5 | 2770 | 2770 | 0.0 | PASS |
| hit_rarity_model | rainbow vmax | 0.003968253968253969 | 252 | 1 in 252 packs | 11 | 2772 | 2772 | 0.0 | PASS |
| hit_rarity_model | gold secret rare | 0.004329004329004329 | 231 | 1 in 231 packs | 12 | 2772 | 2772 | 0.0 | PASS |

## Rounding Warnings
- swsh6 uncommon specific odds raw=15.333333 displayed_label_denominator=15.0 (UI rounds to whole packs for denominators >=10).
- swsh6 rare specific odds raw=54.393222 displayed_label_denominator=54.0 (UI rounds to whole packs for denominators >=10).
- swsh7 rare specific odds raw=41.456772 displayed_label_denominator=41.0 (UI rounds to whole packs for denominators >=10).

## Blockers
- None

## Next Recommendation
- If desired, increase Pull Rates display precision for specific-card odds labels when denominators are non-integers (e.g., show 1 in 15.3 packs).
