# Stage XIV — Chase Accessibility Publication Contract

## Decision

### `CHASE_ACCESSIBILITY_PUBLICATION_CONTRACT_VALIDATED`

Universe, price and probability authority, missing-data gate, presentation, interpretation,
lineage and stability are all defensible. The metric is ready to be specified as a
set-level surface.

> Nothing was deployed, published, migrated or made canonical. Migration 074 remains
> unapplied. `CANONICAL_OVERALL_RIP_VERSION` remains Overall RIP V10, unchanged, and
> Collector Appeal remains at 10% — the 11% validation happened inside an architecture
> containing a 6% Chase pillar and does not transfer.

---

## 1. Formula

$$O_{pack} = \sum_i HC_i\,p_i, \qquad HC_i = \frac{V_i^2}{\sum_j V_j^2}$$

Equivalently, and computed both ways as a parity check:

$$O_{pack} = \frac{\sum_i V_i^2\,p_i}{\sum_j V_j^2}$$

**Worst parity delta across 22 sets: 8.674 × 10⁻¹⁹.**

## 2. Public meaning

**Technical.** The Chase-Significance-weighted mean of per-card modeled per-pack
probabilities, where Chase Significance is a card's share of its set's value concentration.

**Plain English.** *How much of this set's most meaningful collectible value is actually
reachable from a random pack.*

**Tooltip.** *Chase Accessibility weights every card by how much of the set's value
concentration it carries, then asks how likely one pack is to contain it. Higher means the
cards that matter most in this set are easier to reach.*

**Methodology disclosure.** *Chase Accessibility combines two things: how concentrated a
set's collectible value is (Chase Depth) and how likely the concentrated cards are to
appear in a pack. It uses modeled pull probabilities from the opening simulation and
current market values for every drawable card variant. It contains no sealed-product price
and does not change when product prices move.*

### What it must never be called

It is **not** "the probability of pulling a chase card" and **not** "percent chance to hit
the chase." There is no chase roster — Stages IX, X and XI each failed to produce a
defensible discrete Core/Extended tier, and the architecture no longer needs one. Every
card carries continuous significance, so the binary "hit a chase" event does not exist to
have a probability. Any wording implying `O_pack = 0.4%` means "a 0.4% chance of a chase"
is false and must be rejected in review.

## 3. Authority

**Universe (Phase 1).** Drawable `card_variant` rows in
`simulation_card_variant_pull_rates` with `pull_count > 0`, for the 22 simulation-supported
modern sets. `V_i` and `p_i` are read from the **same rows** — 1:1, no canonical-card
fan-out, no cross-table join, no product input.

**Price (Phase 2).** `price_used` on the latest recorded run per set, carrying
`calculation_run_id`, `set_id`, `card_variant_id` and capture lineage. One coherent
snapshot; card prices are never mixed across runs.

**Probability (Phase 3).** `modeled_probability`. Verified across **all 7,615 cohort rows**:

| check | result |
|---|---|
| null `modeled_probability` | **0** |
| mismatch vs `pack_presence_count / simulation_count` | **0** |
| mismatch vs `1 / effective_pull_rate` | **0** |
| rows where `pull_count ≠ pack_presence_count` | **2,398** |

Two traps are now permanently guarded by regression tests:

* **`effective_pull_rate` is 1-in-N odds, not a probability.** Reading it as one inverts
  the weighting and produces a plausible but wrong answer — Stage XI shipped exactly this
  bug and Stage XII caught it. `test_odds_are_never_a_probability_regression` asserts the
  inverted form is >1000× the correct one.
* **`pull_count / simulation_count` is expected copies, not P(N≥1).** It differs on 2,398
  of 7,615 rows. This also corrects Stage XII's §2 table, which called the two identical —
  true only for rare cards.

## 4. Missing-data rule (Phase 5) — now ratified against data

$$\text{mappedHCmass} = \sum_{i\,:\,\text{valid } V_i,\ p_i} HC_i$$

measured against the **full drawable universe**, so a missing card lowers the mass rather
than vanishing. Below the gate the result is `None` with `unavailable_insufficient_hc_coverage`.
**Unmapped mass is never renormalised** — dividing only by the survivors would make a set
look *more* accessible precisely because an important card went missing, which a dedicated
test asserts.

**Observed coverage.** All 22 sets report `mappedHcMass = 1.000000` within the pull model.
Testing the harder question — priced variants the pull model excludes entirely:

| set | priced but outside pull model | most expensive | HC mass at stake |
|---|---|---|---|
| Scarlet and Violet 151 | 1 | $24.59 | **0.0025** |
| Phantasmal Flames | 2 | $3.04 | 0.000017 |
| Ascended Heroes | 19 | $1.71 | 0.000002 |
| 13 other sets | 0 | — | 0 |

**Gate ratified at `MIN_MAPPED_HC_MASS = 0.99`.** Rationale: worst observed real unmapped
mass is 0.25%, so 0.99 leaves 4× headroom over the worst case while still refusing a set
that has genuinely lost a significant card. This is now data-supported rather than the
provisional value Stage XII carried.

## 5. Presentation (Phase 6) — **B, percentage**

Observed range **0.0744% – 0.5618%**.

| option | verdict |
|---|---|
| A raw fraction (`0.0037`) | mathematically clean, unreadable |
| **B percentage (`0.37%`)** | **selected** — absolute, honest, no cohort dependence |
| C per-1,000 units | arbitrary scaling, no natural unit |
| D relative 0–100 index | rejected — changes when the cohort changes, and invites reading as a probability |
| E `1/O_pack` "packs to significance" | **rejected** — HC is continuous significance, not a discrete event, so a packs-to-event reading is mathematically unjustified |

Percentage is kept **absolute**, not normalised to the cohort. The values are small, and
that is the truth: a single pack reaches well under 1% of a set's chase significance. A
0–100 index would make the number feel like a score and invite exactly the false
probability reading §2 forbids.

## 6. Depth × Accessibility (Phase 8) — all four quadrants are real

Keeping the two axes separate is the point; collapsing them would destroy the distinction.

| archetype | set | N_HC | O_pack |
|---|---|---|---|
| **Concentrated + accessible** | Obsidian Flames | 2.42 | **0.562%** |
| | Scarlet and Violet 151 | 2.99 | 0.458% |
| **Concentrated + inaccessible** | Prismatic Evolutions | 1.96 | **0.084%** |
| | Paldean Fates | 1.33 | 0.218% |
| **Deep + accessible** | Shrouded Fable | 12.34 | **0.450%** |
| | Scarlet and Violet Base Set | 8.58 | 0.322% |
| **Deep + inaccessible** | Mega Evolution | 5.35 | **0.074%** |
| | Paradox Rift | 7.26 | 0.209% |

Prismatic Evolutions versus Shrouded Fable is the clearest illustration: Prismatic's value
is far more concentrated (N_HC 1.96 vs 12.34) yet far less reachable (0.084% vs 0.450%).
One score could not express both facts.

## 7. `1/HHI` versus `N_HC` (Phase 9)

`N_HC` should be the **public** depth descriptor and `1/HHI` should stay research-only.
`N_HC` recovered known counts in 6/7 synthetics and is essentially universe-invariant
(Stage XI), whereas `1/HHI` moved up to +53% between universes. Shipping both would be two
numbers answering one question with different sensitivities — the weaker one adds
confusion, not information.

## 8. Redundancy matrix (Phase 10), 22 sets

| against | Spearman |
|---|---|
| EV per pack | **0.0254** |
| `N_HC` | 0.1361 |
| `hcTop1` | −0.0130 |
| card count | −0.2829 |
| median card value | −0.3642 |
| total set value | −0.5878 |

Reproduced exactly from the final publication dataset, matching Stage XII. Accessibility is
near-orthogonal to EV and to every Chase Depth measure. The strongest relationship — total
set value at −0.59 — is moderate and directionally sensible: sets whose value is very high
tend to hold it in rarer cards.

## 9. Stability (Phases 11–13)

| test | result |
|---|---|
| uniform price scaling 0.5× / 2× / 10× / 100× | **exactly invariant, 22/22 sets** |
| independent card-price shock ±10% | relative sd **0.00036 – 0.02847** |
| pull-rate shocks ±2 / 5 / 10% | **weakly monotone, 22/22 sets** |
| two-formulation parity | worst delta **8.674 × 10⁻¹⁹** |

**Temporal behaviour (Phase 11) was not measured.** Coherent historical snapshots of the
pull model do not exist at sufficient depth — pull rates carry 1–4 runs per set. The two
drivers must be recorded separately in diagnostics when this is revisited: **price movement**
changes `HC`, **pull-model revision** changes `p`. Recommended cadence therefore inherits
the coordinated market/simulation publication pipeline rather than an independent schedule,
but **cadence is not finalised** and should not be until real movement is observed.

## 10. Coverage (Phase 14)

**22 of 22 simulation-supported sets are computable**, all at `mappedHcMass = 1.000000`.

Every set outside that cohort — all vintage and most mid-era sets, roughly 190 of 212
configured sets — has **no authoritative pull model** and must report
`unavailable_pull_model`. Rates are never fabricated and the metric is never extended
across eras it cannot support. This is a real and permanent coverage boundary, not a
temporary gap: Chase Accessibility requires a simulation that vintage sets do not have.

## 11. Product-page relationship (Phase 15)

| surface | metric |
|---|---|
| Set page | Chase Accessibility per pack — `O_pack` |
| Product page | Chase Opportunity per product — `O_p` |

Any product-page presentation must state that `O_p` scales with pack count: Stage XIII
established `O_p = n × O_pack` to within 1.2–7.3%, Spearman exactly 1.0000. Products must
**not** be ranked by it, and no price may be attached.

## 12. Chase Efficiency boundary (Phase 16) — contract only, not implemented

The next layer may consume Chase Significance, pull probabilities, whole-product
Opportunity **and** product cost, to answer: *how economically efficient is this sealed
product as a way to pursue this set's chase significance?* That is where sealed-product
price legitimately enters.

The historical `3 × C_product` work is **evidence, not a formula to reuse.** Its validated
findings — the coupled 3×/1× contract, the pack-equivalent cost denominator, the rejection
of the percentile guardrail — remain useful inputs to that design. Nothing about it is
automatically inherited.

## 13. Supersession records (Phases 17–18)

### `OVERALL_RIP_V11_83_11_06_SUPERSEDED_BEFORE_CUTOVER`

**Reason.** The proposed product-level Chase pillar was invalidated by subsequent Chase
architecture research. Continuous Chase Accessibility validated as *set-level* information;
whole-product Opportunity validated as *descriptive, quantity-dependent* information rather
than an independent Overall RIP pillar.

Code, migration 074 and documentation are **preserved unmodified**. Migration 074 remains
unapplied, canonical remains V10, and no runtime behaviour depends on any V11 constant —
`CANONICAL_OVERALL_RIP_VERSION` still resolves to V10, verified.

### `chase_core_k_v1_stage5c_3x_pack_equivalent_cost`

**Retired for** Chase Identity, chase rosters, Chase Opportunity and any Overall RIP pillar.
**Retained as research evidence for** future Economic Chase Efficiency and product-native
pack-equivalent cost work. It is not the current Chase authority and must not be presented
as one.

### `chase_opportunity_v1_core_k_saturating_100_k10`

**Superseded** as the intended production Chase Opportunity formula. The current descriptive
product metric is `O_p = Σ HC_i[1−(1−p_i)^n]`, which shares no construction with it.

## 14. Tests (Phase 19)

`backend/tests/unit/research/test_chase_accessibility_stage14.py` — **23 passed**, covering
HC sums to 1, two-formulation parity, odds/probability inversion regression, expected-copies
confusion, scale invariance, weak monotonicity in every probability, zero and certain
boundary cases, mapped mass measured against the full universe, fail-closed on a missing
high-significance card, non-renormalisation, tiny-gap tolerance, unavailable pull model,
determinism, version lineage on every payload, and a signature assertion that no product
input can be passed at all.

## 15. Next step

**One step only:** implement Chase Accessibility as a set-level read model and surface —
schema, builder, publication gate keyed on `mappedHcMass` and `unavailable_pull_model`, and
the set-page presentation — behind the existing coordinated market/simulation publication
pipeline. No Overall RIP involvement, no product ranking, no price.
