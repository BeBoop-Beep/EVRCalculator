# Set RIP Consensus Research

READ-ONLY RESEARCH. No Set RIP score is published.

# CURRENT COVERAGE

| Family | Rankable SKUs | Represented sets |
|---|---:|---:|
| Booster Box | 2 | 2 |
| Booster Bundle | 3 | 3 |
| Elite Trainer Box | 3 | 3 |
| Enhanced Booster Box | 0 | 0 |
| Half Booster Box | 0 | 0 |
| Pokémon Center Elite Trainer Box | 3 | 3 |
| Sleeved Booster Pack | 2 | 2 |

# SET × FAMILY MATRIX

The JSON artifact contains 238 explicit cells. Missing cells are classified as catalogued-but-unscored or no-catalogued-product and never receive zero.

# MULTI-SKU REPRESENTATIVE RESULTS

Pre-registered R1 best, R2 median, and R3 mean policies are evaluated. BEST matches a user choosing the best available SKU; median/mean describe typical SKU quality.

# FAMILY CORRELATION MATRIX

| Family A | Family B | Overlap N | Spearman |
|---|---|---:|---:|
| booster_box | booster_bundle | 2 | 1.0 |
| booster_box | elite_trainer_box | 2 | 1.0 |
| booster_box | enhanced_booster_box | 0 | None |
| booster_box | half_booster_box | 0 | None |
| booster_box | pokemon_center_elite_trainer_box | 2 | 1.0 |
| booster_box | sleeved_booster_pack | 2 | 1.0 |
| booster_bundle | elite_trainer_box | 3 | 1.0 |
| booster_bundle | enhanced_booster_box | 0 | None |
| booster_bundle | half_booster_box | 0 | None |
| booster_bundle | pokemon_center_elite_trainer_box | 3 | 0.5 |
| booster_bundle | sleeved_booster_pack | 2 | 1.0 |
| elite_trainer_box | enhanced_booster_box | 0 | None |
| elite_trainer_box | half_booster_box | 0 | None |
| elite_trainer_box | pokemon_center_elite_trainer_box | 3 | 0.5 |
| elite_trainer_box | sleeved_booster_pack | 2 | 1.0 |
| enhanced_booster_box | half_booster_box | 0 | None |
| enhanced_booster_box | pokemon_center_elite_trainer_box | 0 | None |
| enhanced_booster_box | sleeved_booster_pack | 0 | None |
| half_booster_box | pokemon_center_elite_trainer_box | 0 | None |
| half_booster_box | sleeved_booster_pack | 0 | None |
| pokemon_center_elite_trainer_box | sleeved_booster_pack | 2 | 1.0 |

# CONSENSUS CANDIDATES

C1 mean, C2 median, C3 neutral-shrunk means (prior strengths 1/2/3), C4 partial-ballot Borda, and a format-group-balanced alternative are all included in the JSON candidate grid.

Recommended research ordering (not a published score):

| Rank | Set | Consensus | Coverage | Families |
|---:|---|---:|---:|---|
| 1 | Ascended Heroes | 0.7 | 3 | booster_bundle, elite_trainer_box, pokemon_center_elite_trainer_box |
| 2 | Perfect Order | 0.6 | 3 | booster_bundle, elite_trainer_box, pokemon_center_elite_trainer_box |
| 3 | Phantasmal Flames | 0.2 | 3 | booster_bundle, elite_trainer_box, pokemon_center_elite_trainer_box |

# MISSINGNESS / COVERAGE RESULTS

Observed-only, neutral shrinkage, and ≥2/≥3 coverage gates are pre-registered. A failed gate is unavailable, never zero.

# FAMILY COHORT SIZE RESULTS

Ungated, ≥3-set, and ≥5-set participating-family thresholds are pre-registered in code and fully enumerated in JSON.

# FORMAT-GROUP COMPARISON

The group-balanced candidate first averages within homogeneous-pack, trainer-box, and enhanced-box groups, then weights represented groups equally. It remains sensitivity-only.

# LEAVE-ONE-FAMILY-OUT STABILITY

| Omitted family | Overlap N | Spearman | Top-5 overlap | Mean abs movement | Max movement |
|---|---:|---:|---:|---:|---:|
| booster_box | 3 | 1.0 | 3 | 0.0 | 0 |
| booster_bundle | 3 | 0.5 | 3 | 0.666667 | 1 |
| elite_trainer_box | 3 | 0.5 | 3 | 0.666667 | 1 |
| enhanced_booster_box | 3 | 1.0 | 3 | 0.0 | 0 |
| half_booster_box | 3 | 1.0 | 3 | 0.0 | 0 |
| pokemon_center_elite_trainer_box | 3 | 1.0 | 3 | 0.0 | 0 |
| sleeved_booster_pack | 3 | 1.0 | 3 | 0.0 | 0 |

# CURRENT PACK-RANKING COMPARISON

Descriptive only; the pack ranking is not ground truth. Overlap N=3, Spearman=1.0, top-5 overlap=2, mean absolute rank movement=8.333333, maximum movement=23.

# HISTORICAL EVIDENCE

HISTORICAL_EVIDENCE_INSUFFICIENT

No stored historical product-family projections with current canonical model versions were found; historical Monte Carlo was not rerun.

# CONSTRUCT RECOMMENDATION

Set RIP should mean the best currently rankable way to rip a set across the product formats for which evidence exists, with uncertainty from sparse format coverage pulled toward neutral.

This is construct A, BEST WAY TO RIP THE SET. It better matches “What set should I choose to rip right now?” than typical-SKU quality because the user can choose the SKU they buy.

# METHODOLOGY RECOMMENDATION

Retain as the leading candidate: BEST-SKU family representation, equal-family mean standing, neutral 0.50 shrinkage with prior strength 2, a minimum two-family coverage gate, and a minimum three-set participating family cohort. This matches the choice-oriented question, preserves separate consumer formats, and limits one-observation extremes without treating missing products as bad. Current coverage is too thin to select it for promotion.

The choice is methodological and was pre-registered; it does not depend on which set ranks first.

# KNOWN LIMITATIONS

- Half Booster Box and Enhanced Booster Box currently have no or insufficient canonical coverage.
- Verified deferred products are missing evidence, not poor performance.
- Only three sets currently clear the leading candidate's gate, so stability statistics are weak and cannot support promotion.
- Related pack formats may count correlated evidence more than once; group-balanced results are retained as a sensitivity architecture.

# PROMOTION STATUS

RESEARCH_NOT_READY_FOR_PROMOTION

# TESTS

See the committed research unit tests and product-family ranking regression suite.

# FILES CHANGED

- `backend/scripts/research_set_rip_consensus.py`
- `backend/tests/unit/scripts/test_research_set_rip_consensus.py`
- `logs/set_rip_consensus_research.json`
- `logs/set_rip_consensus_research.md`
