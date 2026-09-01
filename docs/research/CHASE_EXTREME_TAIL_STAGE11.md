# Stage XI — Extreme-Tail vs HHI-Contribution Chase Architecture

## Decision

### `CHASE_SIGNIFICANCE_VALIDATED__DISCRETE_TIERS_UNRESOLVED`

Continuous, HHI-derived Chase Significance validates strongly and cross-era. Extreme
value theory is **rejected**. Discrete Core/Extended tiers remain unresolved — but the
architecture no longer needs them.

> Nothing was migrated, published, deployed or made canonical. Migration 074 remains
> unapplied. `CANONICAL_OVERALL_RIP_VERSION` remains Overall RIP V10.

---

## 1. HHI concentration contribution — VALIDATED, with one caveat stated up front

$$HC_i = \frac{s_i^2}{HHI}, \qquad \sum_i HC_i = 1$$

**The ordering caveat.** `HC` is a strictly increasing function of `s_i` on positive
shares, so **ranking cards by HC is identical to ranking them by price.** Verified on all
7 synthetic cases and all 14 real sets. HC adds *no new ordering information*. What it
adds is a normalised, interpretable decomposition — "this card causes 86% of the set's
measured value concentration" — and a scale on which sets are comparable. Any claim that
HC *discovers* chase cards would be false; the honest claim is that it *quantifies* them.

## 2. Hill spectrum (Phase 2)

| set | era | D1 | D2 (=1/HHI) | D4 | N_HC |
|---|---|---|---|---|---|
| Phantasmal Flames | SV | 5.07 | 2.56 | 2.05 | **1.31** |
| Champion's Path | SWSH | 4.50 | 2.75 | 2.46 | **1.97** |
| Base | vintage | 14.03 | 5.40 | 3.39 | **1.34** |
| Paldean Fates | SV | 27.59 | 6.99 | 4.02 | **1.33** |
| Fossil | vintage | 17.97 | 8.84 | 5.18 | **1.78** |
| Prismatic Evolutions | SV | 16.39 | 8.37 | 5.14 | **1.94** |
| Evolving Skies | SWSH | 17.69 | 8.31 | 5.31 | **2.16** |
| Crown Zenith | SWSH | 37.11 | 17.07 | 9.06 | **2.55** |
| Neo Destiny | vintage | 16.16 | 8.11 | 5.95 | **3.21** |
| Ascended Heroes | SV | 20.35 | 10.82 | 7.70 | **3.90** |
| Paradox Rift | SV | 58.80 | 35.53 | 20.93 | **7.26** |
| Cosmic Eclipse | SM | 45.58 | 28.44 | 19.51 | **9.18** |
| Jungle | vintage | 28.46 | 20.89 | 16.02 | **9.43** |
| Shrouded Fable | SV | 30.53 | 23.91 | 19.17 | **12.32** |

D1 tracks total roster breadth and is dominated by the bulk (Crown Zenith 37.11 despite
being a one-card set). D2 is the Stage IX depth measure. **The useful discriminator is
N_HC**, not any single Dq.

## 3. Concentration-contributor count `N_HC` — the central result

$$N_{HC} = \frac{1}{\sum_i HC_i^2}$$

**Algebraic identity, verified to machine precision (max diff 3.6e-15):**

$$N_{HC} = \frac{D_4^{\,3}}{D_2^{\,2}}$$

So `N_HC` is a deterministic function of the Hill spectrum, not independent information.
That is a mathematical fact worth recording, not a defect.

### Synthetic recovery (Phase 8) — 6 / 7

| case | true count | N_HC | EVT tail K |
|---|---|---|---|
| one hero | 1 | **1.01** | 23 |
| two heroes | 2 | **1.98** | 35 |
| five-card tail | 5 | **4.91** | 30 |
| Core + Extended (3 core) | 3 | **3.06** | 37 |
| smooth heavy tail | none | 1.65 | 43 |
| lognormal + 6 Pareto draws | 6 | 3.14 ✗ | 26 |
| flat upper tail | 10 | **9.55** | 37 |

The single miss (lognormal + Pareto) undershoots because the six Pareto draws are highly
unequal among themselves, which is exactly what `N_HC` is designed to report.

### Real-set face validity

`N_HC` and its top-K cards, on real 2026-08-31 prices:

| set | N_HC | K | top-K cards by price |
|---|---|---|---|
| Champion's Path | 1.97 | 2 | $268, $229 — **Charizard V + VMAX** |
| Neo Destiny | 3.21 | 3 | $4250, $3999, $3000 — **the three Shinings** |
| Evolving Skies | 2.16 | 2 | $2311, $1249 — **Umbreon + Rayquaza** |
| Ascended Heroes | 3.90 | 4 | $1033, $976, $646, $387 |
| Base | 1.34 | 1 | $869 — **Charizard** |
| Fossil | 1.78 | 2 | $601, $189 |
| Jungle | 9.43 | 9 | flat holo band, $156 → $87 |
| Shrouded Fable | 12.32 | 12 | flattest set, $75 → $43 |

This is the first method across three stages whose output a collector would recognise.

## 4. EVT (Phases 6–8) — REJECTED

Peaks-over-threshold with Hill-plot stability selection and a PWM Generalised Pareto fit.

**Rejected on the synthetic gate, as Phase 8 requires.** For known structures of 1, 2, 5
and 3 chase cards it returned tail K of **23, 35, 30 and 37**. On real sets: Base → 21,
Fossil → 10, Champion's Path → 18, Phantasmal Flames → 29, Ascended Heroes → 68. No
relationship to structure at any point.

**Why (Phase 7 assumption audit).** The Hill plot is smooth and stable across a wide
threshold range — local CV of 0.008–0.015 — which means there is *no distinguishing
threshold to find*. Stability selection then lands wherever the plot is flattest, which is
mid-tail, not chase. Compounding this: sets carry 60–300 observations of which only 2–6
are plausibly chase, far below the 30–50 exceedances a GPD fit needs; card values are not
iid draws (rarity tiers and treatment structure induce dependence); and price floors
truncate the lower range. **EVT is not statistically appropriate here and was not forced.**

## 5. Card-removal influence (Phase 5)

Removal influence on `1/HHI` is monotonically redundant with HC rank in every set tested —
removing the top card moves the effective count far more than any other, and the ordering
of influence follows the ordering of price exactly. Per Phase 5's instruction, **the
simpler measure (HC) is retained** and removal influence is not carried forward.

## 6. Universe robustness (Phase 15) — the strongest single result

| set | n(A) | n(B) | N_HC (A) | N_HC (B) | hcTop1 (A) | hcTop1 (B) |
|---|---|---|---|---|---|---|
| Paradox Rift | 266 | 428 | 7.26 | **7.26** | 0.337 | 0.337 |
| Paldean Fates | 247 | 326 | 1.33 | **1.33** | 0.864 | 0.864 |
| Phantasmal Flames | 132 | 214 | 1.31 | **1.31** | 0.863 | 0.863 |
| Ascended Heroes | 305 | 464 | 3.90 | **3.90** | 0.359 | 0.359 |
| Shrouded Fable | 107 | 162 | 12.32 | 12.34 | 0.176 | 0.176 |
| Prismatic Evolutions | 181 | 448 | 1.94 | 1.96 | 0.708 | 0.704 |

**`N_HC` is essentially universe-invariant**, even where Universe B carries 2.5× the rows
(Prismatic 181 → 448). Compare Stage X, where `1/HHI` moved by up to **+53%** between the
same two universes. Adding hundreds of cheap reverse variants cannot move a statistic
weighted by `s^4`. This resolves the Stage IX/X universe anxiety for this metric
specifically, and is a strong argument for `N_HC` over `1/HHI` as the headline number.

## 7. EV-HHI (Phase 16) — CLOSED, and they measure different things

Universe B, authoritative pull rates, 6 modern sets:

| set | N_eff value | N_eff EV | N_HC value | N_HC EV |
|---|---|---|---|---|
| Paradox Rift | 37.58 | 33.86 | 7.26 | 9.42 |
| Shrouded Fable | 24.84 | **15.47** | 12.32 | **4.50** |
| Ascended Heroes | 11.41 | 9.24 | 3.90 | 3.81 |
| Prismatic Evolutions | 10.81 | 10.58 | 1.94 | 1.98 |
| Paldean Fates | 7.09 | 6.91 | 1.33 | 1.34 |
| Phantasmal Flames | 2.63 | 2.31 | 1.31 | 1.90 |

EV concentration is consistently **higher** (fewer effective cards) than value
concentration, because pull rates concentrate further onto the rare expensive cards.

**Shrouded Fable is the decisive case:** value-flat (`N_HC` 12.32) but EV-concentrated
(`N_HC_EV` 4.50). Its expensive cards are also its rarest, so opening EV is dominated by
far fewer cards than collectible value is.

**Verdict:** Value-HHI answers *"how concentrated is collectible market value"* and is the
correct basis for Chase Identity/Significance. EV-HHI answers *"how concentrated is
opening EV"* and belongs in opening economics, not chase identity. They are not
substitutes. Vintage sets lack pull rates; that is a coverage limitation, not an obstacle
to the semantic distinction.

## 8. Stability (Phase 14)

| test | result |
|---|---|
| uniform scaling 0.5× / 2× / 10× / 100× | **HC values bit-identical, 14/14 sets** |
| ±2% independent card noise | Spearman 0.9984–0.9999 |
| ±5% | Spearman 0.9969–0.9996, top-10 overlap 0.96–1.00, max HC move 0.007–0.017 |
| ±10% | Spearman 0.9919–0.9991 |

Continuous significance is extremely stable. This is a categorical improvement over Stage
X's rosters (bootstrap Jaccard 0.18–0.30).

## 9. Discrete tiers (Phase 12) — STILL UNRESOLVED

Tested `K = round(N_HC)` as a descriptive overlay:

| set | K | price-noise Jaccard (±5%) | **bootstrap Jaccard** |
|---|---|---|---|
| Champion's Path | 2 | 1.000 | **0.650** |
| Ascended Heroes | 4 | 1.000 | **0.644** |
| Neo Destiny | 3 | 1.000 | **0.636** |
| Base | 1 | 1.000 | **0.575** |
| Evolving Skies | 2 | 1.000 | **0.456** |
| Prismatic Evolutions | 2 | 1.000 | **0.452** |
| Paradox Rift | 7 | 0.971 | **0.455** |

Face validity is excellent and price-noise stability is near-perfect, but **bootstrap
Jaccard of 0.45–0.65 means K flips between adjacent integers under resampling.** Better
than Stage X's 0.18–0.30, still not defensible as a published membership boundary.

*Methodological caveat, recorded without using it to upgrade the verdict:* bootstrap
resampling drops ~37% of distinct cards per draw, so for a K=1 or K=2 roster a single
resample that omits the top card scores Jaccard 0. Bootstrap may be an unfairly harsh test
for extreme-tail membership. It is nonetheless the test that was pre-registered, and it
was not passed.

**No universal HC threshold was validated.** Per Phase 12, tiers are not forced.

## 10. Human packet (Phase 13)

Created `docs/research/chase_labeling_v2/chase_identity_blind_packet_v2.csv` — 180 rows,
top 20 by price from each of 9 sets spanning vintage → current. Columns are `set_name`,
`card_name`, `card_number`, `rarity`, `printing_type`, `market_price`,
`rank_in_set_by_price` plus blank label fields. **No HC, HHI, EVT, tier, model output or
sealed-product price is present**, asserted programmatically at write time. The Stage IX
packet (0/448) is preserved untouched.

## 11. Architecture consequence

**Architecture B — continuous Chase Significance — is supported.**

| concept | status |
|---|---|
| Chase Depth — `1/HHI` | validated (Stage IX), universe-sensitive in magnitude |
| **Chase Significance — `HC_i = s_i²/HHI`** | **validated**: interpretable, sums to 1, exactly scale-invariant, universe-invariant, Spearman > 0.99 under ±10% noise |
| **Concentration-driver count — `N_HC = D4³/D2²`** | **validated** as a continuous descriptor; recovers known counts in 6/7 synthetics and is face-valid across 27 years |
| Discrete Core/Extended roster | unresolved, and **no longer required** |
| EVT tail roster | rejected |

**Product Chase Opportunity is no longer blocked on a discrete roster.** Its input
contract can become a fixed set-level significance weight per card plus product-specific
pull/composition probabilities, rather than a binary Core/Extended list. That removes the
exact instability that defeated Stages IX, X and Phase 12 here.

Not built in this stage, as instructed.

## 12. Next research step

**One step only:** define and validate the Product Chase Opportunity input contract against
continuous significance — specifically, whether

$$Opportunity_{product} = f\big(P_i,\ HC_i\big)$$

aggregated over a product's pull distribution is stable across products of the same set
and monotone in the things it should be monotone in (more packs, better pull rates, more
concentrated sets). No coefficient calibration, and no Overall RIP work, until that
contract holds.
