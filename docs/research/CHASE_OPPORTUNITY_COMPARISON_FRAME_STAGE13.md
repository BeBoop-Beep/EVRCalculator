# Stage XIII — Chase Opportunity Comparison Frame & Overall-Pillar Suitability

## Decision

### `CHASE_ACCESSIBILITY_VALIDATED_AT_SET_LEVEL__PRODUCT_OPPORTUNITY_DESCRIPTIVE`

Per-pack Chase Opportunity is a genuinely useful, orthogonal **set-level** metric.
Whole-product Chase Opportunity is useful **product-page information** but decomposes
almost exactly into `set accessibility × pack count`, carrying no third component. It
should **not** become an Overall RIP pillar.

**Consequence: Overall RIP Chase-weight research should not resume, and the 83/11/6
Overall RIP V11 candidate is superseded before production cutover.**

> Nothing was migrated, published, deployed or made canonical. Migration 074 remains
> unapplied. `CANONICAL_OVERALL_RIP_VERSION` remains V10. No coefficient chosen, no
> transform selected, no version minted, and the unshipped V11 implementation was not
> modified.

---

## 1. What whole-product Opportunity actually measures

$$O_p = \sum_i HC_i\left[1-(1-p_i)^n\right]$$

**Phase 2 — within-set decomposition, regressed through the origin on pack count alone:**

| set | R²(O ~ n) | Spearman | max residual |
|---|---|---|---|
| Prismatic Evolutions | 0.999958 | **1.0000** | 1.20% |
| Ascended Heroes | 0.999955 | **1.0000** | 1.20% |
| Paldean Fates | 0.999715 | **1.0000** | 3.07% |
| Paradox Rift | 0.999716 | **1.0000** | 3.07% |
| Phantasmal Flames | 0.999623 | **1.0000** | 3.49% |
| Shrouded Fable | 0.998263 | **1.0000** | 7.31% |

`O_p` is `n × O_pack` to within 1.2–7.3%, and the residual is **entirely** saturation —
there is no other term. Spearman is exactly 1.0000 in every set.

**Whole-product Opportunity contains exactly two pieces of information: a set-level
accessibility rate, and how many packs are in the box.**

## 2. What per-pack Opportunity measures

$$O_{pack} = \sum_i HC_i p_i$$

The probability-weighted share of a set's chase significance reachable in one random pack.
Range across 22 sets: **0.00074** (Mega Evolution) to **0.00562** (Obsidian Flames), a
**7.6×** spread. Product-invariant by construction.

## 3. No product-specific information exists beyond pack count (Phases 7–9)

This was the decisive empirical question, and both possible sources are empty.

**Guaranteed components — 0 of 81 qualify.**

| component role | components | in random-pack universe | has market price |
|---|---|---|---|
| `standard_etb_promo` | 27 | **0** | 1 |
| `pokemon_center_standard_promo` | 26 | **0** | 0 |
| `pokemon_center_stamped_promo` | 26 | **0** | 0 |
| `enhanced_booster_box_stamped_topper` | 2 | **0** | 0 |

Every guaranteed component in the system is a promotional or stamped card that is **not
drawable from random packs**. Under the Stage XII rule none of them may receive `A = 1`,
and none may enter the significance universe. Stage XII left this untested; it is now
tested, and the answer is that guaranteed components contribute **zero** legitimate
product differentiation.

**Composition differences — none exist.**

```
pack components ............................ 55
compositions ............................... 55
packs drawn from a different set ............  0
multi-pack-source compositions ..............  0
distinct pack counts ....................... 9, 11, 36
```

Every product is *n* packs of its own set's single random-pack distribution.

**Phase 9 therefore resolves trivially:** ordering products of a set by `O_p` is *exactly*
ordering them by pack count, and there are **no exceptions** — because no mechanism capable
of producing one exists in the data.

## 4. Financial redundancy (Phases 3–4) — not redundant, but that does not rescue it

Synthetic proportional-price products: pack cost fixed at `EV/0.55`, product cost `= n ×
pack cost`, so per-pack economics are identical at every size. 60k simulations per point.

| set | n=1 | n=3 | n=6 | n=9 | n=11 | n=18 | n=36 |
|---|---|---|---|---|---|---|---|
| Ascended Heroes | 26.93 | 36.32 | 36.19 | 40.16 | 41.58 | 42.00 | **45.24** |
| Prismatic Evolutions | 26.28 | 32.60 | 36.83 | 40.39 | 42.40 | 42.51 | 41.51 |
| Phantasmal Flames | 27.57 | 31.03 | 28.56 | 27.43 | 27.47 | 39.39 | **45.17** |
| Paldean Fates | 31.16 | 34.54 | 34.24 | 38.52 | 39.63 | 39.74 | 44.67 |
| Paradox Rift | 42.21 | 44.14 | 42.88 | 43.11 | 42.99 | 41.50 | **36.85** |
| Shrouded Fable | 42.84 | 45.17 | 44.63 | 43.96 | 42.67 | 39.03 | **34.12** |

**Financial RIP V4 does respond to pack count under proportional pricing, and the direction
is set-dependent and non-monotone.** High-variance concentrated sets *gain* from more packs
(more shots at the jackpot); flat sets like Paradox Rift and Shrouded Fable *lose* as
upside compresses toward the mean.

`O_p` meanwhile rises monotonically with `n` in every set. So the two are genuinely
non-redundant — confirming Stage XII's Spearman of 0.025 and refuting the hypothesis that
Financial already expresses the same quantity effect.

**But non-redundancy is not sufficient.** The information `O_p` adds beyond `O_pack` is
*pack quantity with no cost attached*. Overall RIP compares products; a pillar that ranks
booster box > ETB > bundle > pack purely on size, independent of price, asserts "buying more
is better" — which is precisely the judgment the Financial pillar exists to make *with* cost
included. That is not double-counting; it is worse, it is quantity credited without its
price.

## 5. Set structure survives at fixed pack count (Phase 10)

At constant n = 36, `O_p` spans **0.0263 → 0.1833**, a genuine **7.0×** spread driven purely
by set accessibility. So `O_p` is not *only* pack count — the set term is real and large.
This is exactly why `O_pack` is worth keeping; it is the part that carries this signal
without the quantity confound.

## 6. Saturation is real but operationally minor (Phase 11)

`O(36) / (36 × O(1))` ranges **0.906–0.985**, mean 0.957. Saturation removes only 1.5–9.4%
at the largest real product size. With chase probabilities ~10⁻³, `1-(1-p)^n ≈ np` across
the entire realistic range. The at-least-once form is still correct semantics, but its
diminishing-returns advantage is **future-proofing, not a present-day differentiator**.

## 7. Overall RIP semantic test (Phase 12)

| scenario | verdict |
|---|---|
| **A** — same set, proportional price, 1 vs 36 packs | Chase would raise Overall solely because the box is bigger. Financial already prices size *with cost*, and moves in **both** directions depending on set. Adding an always-increasing quantity term is not desirable. |
| **B** — same n, different sets, same Financial, different `O_pack` | The higher-access set *should* get credit. This is legitimate — and it is a **set-level** distinction, satisfiable by `O_pack`. |
| **C** — same set and n, guaranteed chase card vs none | **Cannot occur.** 0/81 guaranteed components are in the pack universe. |
| **D** — rare-hero set vs deep accessible set | Resolves usefully (synthetic: 0.147 vs 0.517 at n=36), and again this is a **set-level** distinction. |

Every scenario where Chase adds legitimate value (B, D) is set-level. The only
product-level scenario (A) is the one where it should not.

## 8. No residualised metric was invented (Phase 6)

`O_p − n·O_pack` was computed as a diagnostic and is 1.2–7.3% pure saturation. It is **not**
proposed as a production candidate. Stripping quantity from identical packs correctly leaves
nothing, and manufacturing differentiation from that residue would be inventing signal.

## 9. Set-level usefulness of `O_pack` (Phase 14)

| relationship | Spearman |
|---|---|
| `O_pack` vs EV per pack | **0.0254** |
| `O_p(36)` vs `N_HC` | 0.1361 |
| `O_p(36)` vs `hcTop1` | −0.0130 |

`O_pack` is near-orthogonal to EV, to Chase Depth (`N_HC`) and to top-card concentration.
It answers a question none of them answer: *how reachable is this set's chase value?* A set
can be highly concentrated and unreachable (rare hero), or flat and very reachable. This
deserves to exist as a set-level metric on its own merits.

## 10. Product-page usefulness of `O_p` (Phase 15)

Raw percentage is already the honest presentation: *"this product gives you access to about
X% of this set's chase significance."* Values run 2.6–18.3% for a booster box, sub-1% for a
single pack. The number is small but truthful, and the compression is a property of chase
rarity rather than a defect to be transformed away. No 0–100 transform selected.

## 11. Surviving Chase architecture

| layer | metric | status |
|---|---|---|
| Card | Chase Significance `HC_i = V_i²/ΣV_j²` | validated (Stage XI) |
| Set | Chase Depth `1/HHI`, `N_HC` | validated (Stages IX, XI) |
| Set | **Chase Accessibility `O_pack`** | **validated here — set-level metric** |
| Product | Chase Opportunity `O_p` | **descriptive product-page metric only** |
| Product | Chase Efficiency (price-aware) | future, not started |
| Overall RIP | Chase pillar | **not supported by evidence** |

## 12. Consequence for Overall RIP V11

The 83/11/6 candidate — Financial V4 / Collector V5 / Chase Opportunity — rested on a
product-level Chase pillar that this stage does not support. **It should be retired rather
than resumed.** Overall RIP stays `0.90 F_V4 + 0.10 C_V5` (V10) unless a *different*
independently validated product-level Chase construct emerges.

The unshipped V11 code, migration 074 and its documentation were **not modified** and remain
as historical record of a candidate superseded before cutover. Nothing about them was
wasted: the Chase Opportunity module, the parity harnesses and the Core K promotion all
remain valid work, and the V10-preservation discipline is exactly why retiring V11 costs
nothing.

## 13. Next research step

**One step only:** specify Chase Accessibility (`O_pack`) as a set-level published metric —
its exact universe (drawable variants, 22 simulated sets), missing-data contract,
presentation scale, and relationship to the existing Chase Depth surfaces. That is a
self-contained deliverable that does not touch Overall RIP.

The Economic Chase Efficiency layer, which is where sealed-product price legitimately
belongs, remains untouched and is the natural stage after that.

---

## Forward reference

Stage XIV (`CHASE_ACCESSIBILITY_STAGE14.md`) acted on §13's next step and returned
`CHASE_ACCESSIBILITY_PUBLICATION_CONTRACT_VALIDATED`. It ratified the missing-data gate at
0.99 against observed coverage (worst real unmapped HC mass 0.0025), selected absolute
percentage presentation, confirmed all four Depth x Accessibility quadrants have real
representatives, and recorded the formal supersession of Overall RIP V11 and the old Core K.
