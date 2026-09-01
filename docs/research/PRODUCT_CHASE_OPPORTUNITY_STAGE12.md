# Stage XII — Continuous Product Chase Opportunity Input Contract

## Decision

### `CONTINUOUS_PRODUCT_CHASE_OPPORTUNITY_INPUT_CONTRACT_VALIDATED`

Candidate B passes every contract gate: exact boundedness, clean interpretation, all
required monotonicity, product-price invariance, stable joins, hero and deep-set sanity,
and — decisively — **near-zero redundancy with Financial/EV**.

Suitability as an *Overall RIP pillar* is a separate question and is **not** answered here.
Pack-count dominance (Spearman 0.85) means further study is warranted before that decision.

> Nothing was migrated, published, deployed or made canonical. Migration 074 remains
> unapplied. `CANONICAL_OVERALL_RIP_VERSION` remains Overall RIP V10. No version identity
> was minted, no transform chosen, no coefficient calibrated.

---

## 0. Correction carried into Stage XI

Stage XII's Phase 1 field audit found that **Stage XI's Phase 16 EV-HHI table was wrong.**
It used `effective_pull_rate`, which is 1-in-N **odds** (range 20–1430), as if it were a
probability. Recomputed with `modeled_probability`, the conclusion reverses: EV
concentration is *lower* (spread over more effective cards) than value concentration in
every set, because expensive cards are also the rarest so multiplying by probability
flattens rather than sharpens. `CHASE_EXTREME_TAIL_STAGE11.md` §7 has been corrected in
place with an explicit correction notice; the semantic verdict (value-HHI is the Chase
Significance basis, EV-HHI belongs to opening economics) is unchanged and strengthened.

## 1. Selected formula

$$O_p = \sum_i HC_i \cdot P(N_{ip} \ge 1), \qquad HC_i = \frac{s_i^2}{HHI} = \frac{V_i^2}{\sum_j V_j^2}$$

**Plain English:** the probability-weighted fraction of a set's collectible chase
significance that one whole sealed product gives you access to at least once.

## 2. Probability authority (Phase 1)

| field | meaning |
|---|---|
| `modeled_probability` | **per-pack P(N ≥ 1)** — the authority used |
| `pack_presence_count / simulation_count` | identical to the above, 10⁶ simulations |
| `pull_count / simulation_count` | expected **copies** per pack — *not* a probability |
| `effective_pull_rate` | 1-in-N **odds**, i.e. `1 / modeled_probability` — never a probability |
| `pull_count` vs `pack_presence_count` | equal for rare cards (never two in a pack); diverge for commons |

Verified directly: for the Ascended Heroes run, `modeled_probability = 0.000801`,
`1/effective_pull_rate = 0.000801`, `pull_count/sim = 0.000801` all agree.

## 3. The IID lift, and what does *not* need it (Phases 2–3)

$$A_{ip} = 1 - (1 - p_i)^n$$

is the **only** place independence is assumed, and it is inherited from the production
simulator's own `pack_independence_assumption` — restated at product scale exactly as
Stage V-C's `aggregate_to_product` does. It is **not independently validated**: there is no
non-IID product simulation in this system to check it against.

**The aggregation itself needs no cross-card independence.** `O_p` is the expectation of
`Σ HC_i · 1{N_ip ≥ 1}`, so by linearity of expectation `E[O_p] = Σ HC_i · P(N_ip ≥ 1)`
holds whether card hits are independent, correlated, or mutually exclusive. This matters
because hits inside one pack *are* dependent — a slot holds one card — and a formulation
requiring joint independence would be unusable.

Closed-form properties pinned: `n=0 → 0`; `n=1 → p`; strictly increasing in `n`;
`p=0 → 0`; `p=1 → 1`; `n→∞, p>0 → 1`.

## 4. Candidate comparison (Phase 6)

Synthetic hero set, `HC = [0.90, 0.10]`, hero `p = 0.30`:

| n | **B** — at-least-once | **A** — expected copies |
|---|---|---|
| 1 | 0.27500 | 0.27500 |
| 3 | 0.60556 | 0.82500 |
| 9 | 0.90066 | 2.47500 |
| 36 | 0.98422 | 9.90000 |
| 100 | 0.99941 | 27.50000 |

**Candidate B selected.** A is unbounded and rewards duplicate hero pulls indefinitely — a
second Charizard does not give you *more access to* Charizard. B saturates each card's
contribution at its own `HC` weight, which is the correct semantics for an access metric.

Candidate C (any-significance-hit probability) was **rejected without testing**: every
priced card has `HC > 0`, so it degenerates to "probability of pulling any card" unless an
arbitrary significance threshold is introduced — which would recreate the Core/Extended
cutoff three stages of work just retired.

**Important practical caveat.** On *real* data the two candidates nearly coincide: across
22 sets, `O(36) / (36 × O(1))` ranges 0.906–0.985, mean **0.957**. Because chase-card
per-pack probabilities are ~10⁻³, `1-(1-p)^n ≈ np` at realistic pack counts. B's
diminishing-returns advantage is mathematically real but only ~4% active at n=36. B is
still the right choice on semantics, not on empirical separation.

## 5. Boundary behaviour (Phase 7)

| case | result |
|---|---|
| zero-pack product | `O = 0.00000` |
| every `A = 1` | `O = 1.0000000000` exactly |
| guaranteed hero (legitimate pack-universe card) | `O = 0.93698`, hero `A` forced to 1 |
| two heroes, equal HC, different rates | rarer hero contributes `A = 0.035` vs `0.517` — correct |
| deep accessible (10 cards) vs concentrated rare hero | `O = 0.517` vs `0.147` at n=36 |

That last row is the designed non-monotonicity in HHI: a **deep, accessible** set
legitimately out-scores a **concentrated, rare-hero** set. Opportunity measures access to
significance, not concentration of it.

## 6. Guaranteed components (Phase 5)

Rule implemented: `A_ip = 1` for a guaranteed card **only if** that card is genuinely part
of the set's random-pack Chase Significance universe. A promotional or fixed card that is
not drawable from packs must never be injected into the universe merely because a product
contains it — doing so would dilute every other card's `HC` and inflate that one product.

**Not exercised against real Stage 2 compositions.** This run used canonical family pack
counts (ETB 9, PC ETB 11, Enhanced BB 36, bundle 6, pack 1) rather than per-SKU
composition records. Validating real guaranteed-component membership is outstanding.

## 7. Real-set results (Phase 8), 22 simulated sets

Per-pack Opportunity ranges **0.00074** (Mega Evolution) to **0.00562** (Obsidian Flames);
whole-box (n=36) ranges **0.0263** to **0.1833**, a **7.0×** spread at fixed pack count.

Absolute values are small by construction: a booster box buys access to 2.6–18% of a set's
chase significance. That is the honest answer — chase cards are rare — but it means any
future public transform must handle a compressed low range.

**Product price independence holds by construction:** no sealed-product price is read
anywhere in the module or the build script.

## 8. Pack-count dominance (Phase 9)

Across all 176 (set × family) products: **Spearman(O, pack_count) = 0.8529**.

High, but not degenerate. Within a set the ordering *is* pack count (O is ~96% linear in
n). Across sets, structure contributes a genuine 7.0× spread at fixed n. So Opportunity is
not merely pack count renamed — but it is substantially driven by it, exactly as an
absolute whole-unit access metric should be.

`O_pack = Σ HC_i p_i` is reported alongside as the product-free control: identical for all
products of a set sharing a random-pack distribution, and the right quantity for comparing
*sets* rather than products.

## 9. Hero vs deep behaviour (Phases 13–14)

Share of `O(36)` contributed by the single top-HC card:

| set | N_HC | hcTop1 | O-share top-1 | O-share top-3 |
|---|---|---|---|---|
| Phantasmal Flames | 1.31 | 0.863 | **0.944** | 0.992 |
| Paldean Fates | 1.33 | 0.864 | **0.864** | 0.971 |
| Prismatic Evolutions | 1.96 | 0.704 | 0.704 | 0.842 |
| Paradox Rift | 7.26 | 0.337 | 0.360 | 0.492 |
| SV Base Set | 8.58 | 0.246 | 0.247 | 0.505 |
| Shrouded Fable | 12.34 | 0.176 | **0.217** | 0.386 |
| Temporal Forces | 13.41 | 0.187 | **0.241** | 0.316 |

**In concentrated sets, Opportunity is essentially the probability of obtaining the single
most expensive card** (Phantasmal Flames 94%). That is semantically defensible — that set's
chase *is* one card — but it must be stated rather than discovered later.

**In deep sets it is genuinely diversified** (Shrouded Fable 22%, Temporal Forces 24%),
which is the specific advantage continuous significance was expected to deliver over a
discrete roster. Confirmed.

## 10. Redundancy audit (Phase 12) — the strongest result

| relationship | Spearman |
|---|---|
| `O(36)` vs EV per pack | **0.0254** |
| `O_pack` vs EV per pack | **0.0254** |
| `O(36)` vs `N_HC` | 0.1361 |
| `O(36)` vs `hcTop1` | −0.0130 |

**Opportunity is not EV in disguise.** The mechanism is the squaring: EV weights cards by
`V_i`, Opportunity weights them by `V_i²/ΣV_j²`. Squaring concentrates weight onto the top
cards so hard that the resulting access metric decorrelates almost completely from expected
value, which is dominated by the many mid-value cards. It is also near-orthogonal to the
set-structure measures, so it carries information neither Financial nor Chase Depth holds.

## 11. Missing-data contract (Phase 17)

$$\text{mappedHcMass} = \sum_{i\ :\ \text{valid } p_i} HC_i$$

Rule implemented: **complete-case, coverage-gated.** If `mappedHcMass < threshold`,
Opportunity is `None` with `status = unavailable_insufficient_hc_coverage` and
`rankable = False`. Unmapped mass is **never renormalised away** — because the metric is
dominated by a handful of cards, a small unmapped *mass* can be a large unmapped *meaning*:
losing one 86%-HC card is not a 14% error, it is the whole metric.

The default threshold is set at 0.99 and is **reported, not ratified**. It was not
empirically calibrated in this stage, and should be before production use.

## 12. Universe and identity mapping (Phase 18)

**Variant-level throughout.** Both `HC` (from `price_used`) and `p_i` (from
`modeled_probability`) are read from the *same rows* of
`simulation_card_variant_pull_rates`, keyed by `card_variant_id`. The join is 1:1 by
construction — there is no canonical→variant fan-out and therefore no double-counting.

This follows Stage X's finding that the drawable-variant universe is authoritative where it
exists, and Stage XI's that `N_HC` is universe-invariant. It also confines this contract to
the 22 simulated modern sets; vintage sets have no pull authority and cannot receive an
Opportunity score at all.

## 13. Stability (Phases 15–16)

| test | result |
|---|---|
| uniform price scaling 0.5× / 2× / 10× / 100× | `HC` **and** `O` bit-identical, **22/22 sets** |
| independent card-price shock ±10% | relative sd of `O` **0.0004 – 0.029** |
| pull-rate shocks ±2 / 5 / 10% | **monotone in every set at every level**, no inverse movement |

## 14. Suitability for Overall RIP — further study warranted, not settled

Arguments for: near-zero Financial/EV redundancy (0.025) means it would contribute genuine
new information; stability is excellent; hero/deep behaviour is interpretable.

Arguments for caution: Spearman 0.85 with pack count means much of what it says about
*products within a set* is "this box has more packs"; and the raw range (0.026–0.183) is
compressed and would need a transform whose choice is itself a research decision.

**No coefficient calibrated, no transform chosen, as instructed.**

## 15. Next research step

**One step only:** decide the comparison frame. Determine whether Overall RIP should
consume whole-unit `O_p` (absolute access, pack-count-driven) or per-pack `O_pack`
(set access rate, product-invariant within a set) — or whether Opportunity belongs on
product pages as a descriptive metric while a different Chase construct enters Overall RIP.

That framing question must be settled before any transform, any coefficient, or any
resumption of Overall RIP V11.

---

## Forward reference

Stage XIII (`CHASE_OPPORTUNITY_COMPARISON_FRAME_STAGE13.md`) settled §15's framing question and
returned `CHASE_ACCESSIBILITY_VALIDATED_AT_SET_LEVEL__PRODUCT_OPPORTUNITY_DESCRIPTIVE`.

It closed the two items left open here: guaranteed components were exercised against real
compositions (**0 of 81 are in the random-pack universe** - all are promos), and composition
differences were enumerated (**none exist**; every product is n packs of its own set's single
distribution). Consequently `O_p = n * O_pack` to within 1.2-7.3% with Spearman exactly 1.0000,
and whole-product Opportunity is **not** supported as an Overall RIP pillar. `O_pack` is validated
as a set-level metric.
