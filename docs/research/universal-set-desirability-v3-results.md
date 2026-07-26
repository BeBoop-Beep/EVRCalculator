# Universal Set Desirability v3 + Weighted RIP — Results

**Status: implemented, uncommitted, working tree only.** Nothing was committed,
pushed, staged for commit, amended, tagged, or written to any remote. No
database writes: every study here is a read-only query against production.

- Run date: 2026-07-15. Database: Supabase `TheIndex` (`zwxzxuuawalvwioadhmf`).
- Reproduce: `backend/scripts/build_universal_set_desirability_v3.py` (v3 +
  stress tests + pillar diagnostics) and
  `backend/scripts/build_card_market_amplification_study.py` (card-level
  construct validation). Raw output:
  `docs/research/universal_set_desirability_v3_report.json`,
  `docs/research/card_market_amplification_study.json`.

> **Every fixed weight and threshold in this document is a reasoned default, not
> an empirically-optimized truth.** They are configuration parameters
> (`backend/desirability/scoring_config.py`), not literals scattered through
> the code, so per-user re-weighting is a config change rather than a refactor.

---

## 0. Headline

| Question | Answer |
|---|---|
| Sets with Universal Set Desirability | **135 of 171** ranked (`full` coverage); 36 `unavailable`, 0 `partial` |
| Sets with full simulation | **33** (financial pillars + RIP v3) |
| Does missing simulation block desirability? | **No.** 102 sets are ranked for desirability with no simulation at all |
| Set-value association (v3 vs set value) | Spearman **0.308** (n=135) — **descriptive diagnostic, NOT a gate** |
| Is desirability in RIP? | **Yes, at its 10% reasoned-default weight**, never auto-zeroed |
| Construct validation (card level) | **PASSED** — appeal adds real out-of-sample lift beyond controls *and* actual pull scarcity (−4.9% MAE, +0.040 Spearman, leave-whole-set-out, both eras) |
| Does scarcity amplify appeal? | **Yes** — appeal's price slope is ~4.4× steeper on 1-in-472 cards than 1-in-12 (t = +8.4, bootstrap CI excludes 0) |

### The most important correction in this pass

An earlier version of this work gated desirability's entry into RIP on the v3
score tracking total set value at Spearman ≥ 0.50. **That gate was removed, and
it was right to remove it.** Universal Set Desirability deliberately excludes
scarcity, Treatment, price, and simulation data, while market price is *jointly*
produced by demand, scarcity, prestige, supply, and age. Requiring a
price-independent construct to reproduce a price correlation would have selected
the score back toward price contamination — punishing it precisely for being
clean. Had that gate shipped, it would have failed (0.308 < 0.50) and forced
desirability to weight 0 for the wrong reason.

The real validation is the **card-level market amplification study** (§2), and
it passes decisively.

---

## 1. Set-value association — reported, not enforced

Across the 135 `desirabilityCoverage=full` sets that carry a set value:

| Measure | Value |
|---|---|
| Spearman (v3 vs set value) | **0.308** |
| Pearson (v3 vs set value) | 0.273 |
| n | 135 |
| Prior *shipped* V2 score vs set value, same cohort | **0.143** |

Two honest observations:

1. **v3 is more associated with set value than the score it replaces** (0.308 vs
   0.143 on an identical cohort), despite v3 having *stripped* the Treatment
   (rarity) component. The "~0.70 prior benchmark" that motivated the original
   gate is **not reproducible on this cohort** — the shipped V2 score correlates
   at 0.143 here, not 0.70. The 0.70 figure appears to have come from a
   different cohort/metric and should not be cited as a benchmark.
2. A modest association is the *expected* behaviour of a pure subject-appeal
   measure, not a defect.

**Product framing (implemented):** labeled **Market Association** —
"Higher set desirability is positively associated with set value in the current
sample. This is descriptive context, not a price forecast, causal proof, or an
input to the score."

---

## 2. Card-level market amplification study — the construct validation

The decisive test, per the amended protocol. Pull scarcity is real: card-level
pull probability is derived from each set's modeled pull-rate assumptions
(`specific_card_odds_denominator`, i.e. `p = 1/denominator`), which is the same
pack model the simulator uses.

- **Sample:** 3,705 priced Pokémon cards, 22 sets, 934 distinct species.
- **Outcome:** `log(card market price)`.
- **Inference:** set fixed effects, cluster-robust SEs by set, plus a 400-draw
  cluster bootstrap resampling **whole sets**.
- **Validation:** **leave-whole-set-out** grouped CV (never random card splits;
  a held-out set has no set intercept, so era + structural controls replace set
  dummies out of sample).
- Weights were **not** chosen by hand before testing.

### Nested model results (pooled)

| Model | OOS MAE | OOS Spearman | OOS R² | within-R² |
|---|---|---|---|---|
| M0 controls only | 0.6736 | 0.705 | 0.817 | 0.822 |
| M1 + appeal | 0.6570 | 0.777 | 0.835 | 0.840 |
| M2 + pull_scarcity | 0.5899 | 0.775 | 0.861 | 0.873 |
| M3 + appeal + scarcity | 0.5611 | 0.815 | 0.880 | 0.891 |
| M4 + appeal×scarcity | 0.5529 | 0.807 | 0.884 | 0.897 |
| M5 + treatment_prestige | **0.5109** | **0.826** | **0.900** | 0.908 |

### Answers to the five primary questions

**1. Does appeal add incremental value beyond scarcity and controls? — YES.**
M3 vs M2: **−4.89% OOS log-price MAE**, **+0.040 held-out Spearman**. This clears
the pre-registered practical gates (≥2% MAE reduction *or* ≥0.02 Spearman gain)
on **both** criteria, out of sample, under leave-whole-set-out CV, and it is
**consistent across both eras** (S&V −4.29% / +0.039; Mega Evolution −8.35% /
+0.034). The coefficient is tight and stable: pooled `appeal` = **+0.0234**
(t = +14.1; bootstrap 95% CI **[+0.0201, +0.0267]**, positive in **100%** of
draws).

**This is the evidence that Pokémon Appeal is a real, non-circular
price-relevant signal** — something the set-level correlation in §1 could never
establish. It is also the reason the removed gate would have been a mistake: the
construct is validated at the card level while "failing" the set-level number.

**2. Does pull scarcity add value beyond appeal? — YES pooled, but NOT in every era.**
Pooled M3 vs M1: **−14.60% MAE**, +0.038 Spearman. But the eras disagree:

| Era | M3 vs M1 (scarcity added to appeal) |
|---|---|
| Scarlet & Violet | **−14.27% MAE**, +0.041 Spearman ✅ |
| Mega Evolution | **+4.56% MAE (worse)**, −0.002 Spearman ❌ |

In Mega Evolution, adding scarcity *hurts* out-of-sample prediction, and M2
(scarcity alone) is worse than M0 (controls alone) by 11.63% — even though its
within-sample coefficient is strongly positive (+2.94, t = 8.8). With only 5
sets, the rarity→odds mapping evidently does not transfer to a held-out set in
that era. **Reported as a genuine contradictory finding, not averaged away.**

**3. Does scarcity amplify appeal (interaction positive)? — YES, robustly, in both eras.**
Pooled `appeal × scarcity` = **+0.0214** (t = **+8.37**; bootstrap 95% CI
**[+0.0163, +0.0264]**, positive in **100%** of draws; S&V +0.0197 t=7.4, ME
+0.0271 t=6.1, both CIs excluding zero). The fitted appeal slope steepens
monotonically with scarcity:

| Pull scarcity | Odds | d log(price) / d appeal |
|---|---|---|
| p10 | ~1-in-12 | +0.0100 |
| p50 | ~1-in-22 | +0.0161 |
| p90 | ~1-in-472 | **+0.0445** |

Popularity is worth **~4.4× more** on a hard-to-pull card than on an easy one:
+10 appeal points is worth roughly **+10%** price on a 1-in-12 card but **+56%**
on a 1-in-472 card. **Contradictory nuance, reported rather than buried:** the
interaction is statistically rock-solid yet barely improves prediction (M4 vs M3:
−1.47% MAE and **−0.008 Spearman**, i.e. marginally *worse* rank ordering). It is
real structure, not a predictive win.

**4. Does Treatment/Rarity Prestige add information after actual pull odds? — YES pooled; NULL in Mega Evolution.**
Pooled M5 vs M4: **−7.59% MAE**, +0.018 Spearman; prestige = **+2.38**
(t = +5.46, bootstrap CI [+1.29, +3.23], 100% positive). This **contradicts the
working assumption** that rarity is merely a coarse proxy for pull odds — two
rarities with similar odds can carry very different prestige, and the market
prices that difference. But it is era-dependent:

| Era | prestige coefficient | bootstrap 95% CI | verdict |
|---|---|---|---|
| Scarlet & Violet | +2.96 (t = +7.46) | [+2.16, +3.93] | clearly positive |
| Mega Evolution | **+0.30 (t = +0.24)** | **[−2.54, +2.48]** | **null — spans zero** |

**5. Consistent across eras? — Partly.** Appeal and the interaction are stable and
consistent; scarcity's incremental value and prestige are **not**:

| Era | n cards | n sets | appeal | appeal×scarcity | prestige | scarcity adds OOS? |
|---|---|---|---|---|---|---|
| Scarlet & Violet | 2,904 | 16 | +0.0232 (t=10.9) | +0.0197 (t=7.4) | +2.96 ✅ | yes (−14.3%) |
| Mega Evolution | 693 | 5 | +0.0242 (t=8.1) | +0.0271 (t=6.1) | +0.30 (null) | **no (+4.6%)** |
| Sword & Shield | 108 | 1 | — | — | — | **skipped** |

Era-specific coefficients are **not** needed for appeal/interaction, but a single
pooled claim about scarcity or prestige would over-generalize from Scarlet &
Violet, which is 78% of the sample.

**Sword & Shield is data-blocked**, not modeled: only 1 set (Lost Origin) has
pull-rate coverage, below the ≥4-set / ≥200-card floor required for credible
leave-whole-set-out CV. All pre-Sword-and-Shield eras have **no** pull-rate model
at all and are entirely outside this study.

### Study limitations (stated, not minimized)

- **Pull scarcity is constant within (set, rarity)**, since assumptions are
  rarity-keyed. Appeal varies within that cell, which identifies the appeal and
  interaction terms cleanly, but scarcity's own coefficient is identified only
  across rarities/sets. This is the most likely reason scarcity fails to
  transfer to held-out sets in Mega Evolution.
- **Controls absorbed by set FE:** `log_release_age` is a set-level constant and
  is dropped under set fixed effects (it still operates in the CV
  specification, which has no set dummies). `is_promo` is all-zero across these
  22 main sets. `is_secret` is a strong control (+1.40, t = 5.27).
- **Supertype cannot be a control**: the sample is Pokémon cards with a species
  link by construction, so supertype is constant.
- **Sample exclusions:** 703 cards had no species link, 69 no pull-rate row for
  their rarity, 13 no price (price coverage ≈ 99.6% of linked cards). All are
  structural "field does not exist"; none dropped to strengthen a result.
- **A data-collection bug was caught and fixed mid-study.** The first run
  batched the price read 25 sets at a time and silently returned partial data,
  dropping 1,298 cards as "no price" and biasing the sample; it produced
  materially different (and wrong) numbers — e.g. scarcity appearing to cut MAE
  by 56%. The reads are now retried and chunked, and every figure above comes
  from the corrected run. A separate bug made `is_secret` always 0 (set size was
  derived from the max card *numerator*, which is itself a secret, instead of
  the printed *denominator* in "245/91").
- **This is contemporaneous, not predictive.** No forward-return test exists;
  no "predicts future price" claim is made anywhere.
- **No coefficient here was transferred into RIP weights.** These fit price, not
  user utility — doing so would turn RIP into a price predictor and destroy its
  differentiation.

---

## 3. Product consequence — Chase Magnetism (simulation-only)

Because the amplification study succeeded, the amplification structure is exposed
as its **own simulation-only metric**, `chase_magnetism_v1_simulation_only`
(`backend/desirability/simulation_opening_details.py`) — "popular Pokémon on
genuinely hard-to-pull cards":

```
appeal_excess   = max((demand - 50) / 50, 0)                  # 0..1
scarcity_weight = clamp((-log10(p) - 1) / (3 - 1), 0, 1)      # 1-in-10 .. 1-in-1000
contribution    = appeal_excess * scarcity_weight
score           = 100 * (1 - exp(-sum(contribution) / 2))
```

Shape is a **reasoned default chosen structurally** — no price-model coefficient
was imported. Hard rules enforced in code and tests:

- **Pull scarcity is never merged into Universal Set Desirability.** The
  universal score stays pure, price-independent, simulation-independent subject
  appeal, available across all eras — including the ~102 sets with no pull model.
- **Chase Magnetism does not feed RIP in this pass.**

### Chase Magnetism redundancy audit (required precondition, report-only)

Computed across the 21 sets with both a magnetism score and financial pillars:

| Pair | Spearman | Redundancy flag (|ρ| > 0.8) |
|---|---|---|
| Chase Magnetism ↔ Profit | **0.042** | no |
| Chase Magnetism ↔ Safety | −0.170 | no |
| Chase Magnetism ↔ Stability | −0.091 | no |
| Chase Magnetism ↔ Universal Set Desirability | 0.669 | no |

**Finding: Chase Magnetism is NOT redundant with the financial pillars** — it is
essentially uncorrelated with Profit (0.04) and only mildly negatively related to
Safety/Stability. It carries information those pillars do not, and it is
*distinct* from Universal Set Desirability too (0.67, sharing the appeal input
but diverging on scarcity). Highest-magnetism sets are Paldean Fates (95.3),
Ascended Heroes (93.5), and Scarlet & Violet 151 (76.4) — none of which are
Profit leaders (Profit 8.1, 22.7, 22.5).

So the redundancy objection does **not** block it. The remaining blocker is a
**product decision** about what RIP is meant to reward — a chase-excitement axis
is a different claim than "this pack pays back". Per the amendment, it is
reported and **not wired into RIP** in this pass.

---

## 4. Final formulas + default weights

**Universal Set Desirability v3** (`universal_set_desirability_v3`) — identical
for every set; no price, Treatment, scarcity, simulation, special-pack, or era
multiplier:

```
Universal Set Desirability =
    (30/90) · Chase Subject Strength    [33.333%]
  + (25/90) · Chase Subject Depth       [27.778%]
  + (35/90) · Favorite Hit Coverage     [38.889%]
```

- **Chase Subject Strength** = `0.50·top1 + 0.30·top2 + 0.20·top3` over
  **distinct** subjects (one Pokémon cannot occupy multiple slots). Missing slots
  **renormalize** the available weights; zero is never inserted.
- **Chase Subject Depth** = HHI effective subject count over demand above the
  50 baseline: `share_i = c_i/Σc`, `HHI = Σ share_i²`,
  `effective = 1/HHI`, `depth = 100·(min(effective, 8) − 1)/7`.
- **Favorite Hit Coverage** (checklist-based; **not** pull accessibility):
  `raw = Σ sqrt(max((demand − 50)/50, 0))`, normalized by a **fixed saturated
  transform** `100·(1 − e^(−raw/3))`.
- Eligibility: `universal_desirability_eligibility_v2` — price-independent,
  simulation-independent; rarity is used only to classify eligibility, never as
  a numeric multiplier.

**RIP v3** (`rip_v3_weighted_four_component`) — linear, **no caps, no clamps** on
desirability's influence:

```
RIP = 0.58·Profit + 0.20·Safety + 0.12·Stability + 0.10·Desirability
```

Profit is 0.58 (not the discussed 0.57) so the weights sum to exactly 1.00.
**Renormalization rule (one rule, everywhere):** when a component is absent —
weight 0, or missing data — the remaining weights renormalize proportionally to
1.0. Desirability excluded → 0.644 / 0.222 / 0.133 (`financial_rip_v2`).
`w_desirability = 0` and `w_desirability = 1.0` are both valid, tested states.

---

## 5. Pillar diagnostics (report-only; weights NOT auto-adjusted)

**Redundancy matrix** (Spearman across the 33 simulated sets). No pair exceeds
the |ρ| > 0.8 double-counting flag:

| Pair | Spearman | Flag |
|---|---|---|
| Profit ↔ Safety | 0.566 | no |
| Profit ↔ Stability | 0.431 | no |
| Safety ↔ Stability | 0.440 | no |

**Weight sensitivity** — rank correlation of each alternative's RIP leaderboard
against the shipping default:

| Alternative | Rank Spearman vs default | Largest movers |
|---|---|---|
| 50/25/15/10 | 0.989 | Rebel Clash +5, Ascended Heroes −3 |
| 65/17/8/10 | 0.990 | Rebel Clash −4, Battle Styles +3 |
| desirability at 0 | 0.991 | S&V 151 −4, Shrouded Fable +4 |
| desirability at 15 | 0.995 | Shrouded Fable −4, Chaos Rising −2 |

**Interpretation:** the ranking is highly stable (ρ ≈ 0.99) under every
reasonable re-weighting, so the exact subjective weights are **not load-bearing**
— which is itself the argument for stating plainly that they are defaults rather
than defending them as optimal. Pillars are **never** weighted by correlation to
price or set value (hard prohibition, enforced by test).

---

## 6. Desirability-influence report (10% weight, with vs without)

Transparency only — there is no cap to select. Every large move is explainable
from visible desirability components:

| Set | RIP rank without | with | Δ | score Δ |
|---|---|---|---|---|
| Scarlet and Violet 151 | 10 | 6 | **+4** | +6.97 |
| Shrouded Fable | 9 | 13 | **−4** | +2.64 |
| Ascended Heroes | 13 | 10 | +3 | +7.44 |
| Twilight Masquerade | 6 | 8 | −2 | +5.64 |

Movement is small and bounded *linearly* by the 10% weight — the largest rank
delta across all 33 sets is 4 places. Scarlet & Violet 151 rises because its
subject roster (Charizard/Pikachu-tier, deep) is genuinely strong; Shrouded Fable
falls because its financial profile outruns a thin 99-card subject roster.

---

## 7. Coverage — two independent axes

`desirabilityCoverage` and `simulationCoverage` are **separate states**; neither
implies the other.

| desirabilityCoverage | Sets |
|---|---|
| full | **135** |
| partial | 0 |
| unavailable | 36 |

| simulationCoverage | Sets |
|---|---|
| full | **33** |
| unavailable | 138 |

**102 sets are `desirabilityCoverage=full` + `simulationCoverage=unavailable`** —
exactly the expected older-set case. They show a real desirability score and
all-set rank; Financial/Overall RIP and pull-access are shown as *unavailable*,
never as zero.

All 36 `unavailable` sets fail for one honest reason — `no_eligible_pokemon_subjects`
(share = 0.0): promo/POP/McDonald's/Trainer-Kit-style products with no
hit-eligible Pokémon subjects under the eligibility policy. None is a data bug.

---

## 8. All-set stress tests (135-set desirability cohort)

**Top 10 / bottom 5 (v3):**

| # | Set | v3 | prior V2 | Top subjects |
|---|---|---|---|---|
| 1 | Ascended Heroes | 95.48 | 90.90 | Charizard, Pikachu, Gengar |
| 2 | Paldean Fates | 95.33 | 73.77 | Charizard, Pikachu, Mew |
| 3 | Cosmic Eclipse | 94.86 | 79.27 | Charizard, Pikachu, Mimikyu |
| 4 | Team Up | 94.64 | 78.85 | Pikachu, Gengar, Eevee |
| 5 | Hidden Fates Shiny Vault | 94.47 | 77.71 | Charizard, Eevee, Sylveon |
| … | … | | | |
| 132 | Gym Heroes | 48.37 | 6.67 | |
| 133 | Celebrations | 48.25 | 8.33 | |
| 134 | Double Crisis | 43.28 | 21.54 | |
| 135 | Emerging Powers | 31.67 | 10.71 | |

1. **Coverage audit** — per-set canonical/eligible/linked/subject counts and
   coverage reason codes are in the JSON report. `full` requires ≥90% of
   hit-eligible cards scored; ≥50% is `partial`; below that `unavailable`.
2. **Fan/trend sensitivity** — rank Spearman vs the shipped 75/25:
   100/0 → **0.812**, 50/50 → **0.737**. The shipped 75/25 is *not* fragile in
   ordering, but the median set's score moves up to ~48 points across configs,
   so trend weighting is **materially load-bearing on levels**. 75/25 retained
   (no defect found); flagged as a real sensitivity, not dismissed.
3. **Single-top-subject removal** — 100 sets `broad`, 35 `moderately concentrated`,
   **0 single-subject dependent**. The model is not carried by one chase per set.
4. **Set-size bias** — Spearman vs checklist size **0.412**, vs hit-eligible count
   **0.542**, vs distinct subjects **0.451**. Favorite Hit Coverage is the most
   size-correlated component (0.495), Strength the least (0.201). Size
   correlation is **real but not dominant**; the sqrt/saturated transforms are
   doing their job. Larger modern sets genuinely do contain more desirable
   subjects, so this is partly signal, not purely bias — but it is the top
   candidate for future work.
5. **Iconic-subject stress** — excluding the top-10 demand species
   (Charizard, Pikachu, Gengar, Eevee, Mew, Mimikyu, Sylveon, Lucario, Greninja,
   Umbreon) the ranking still correlates **0.824** with baseline; excluding the
   top 20, **0.732**. Not a Charizard/Pikachu artifact, though they matter.
6. **Era distribution** — no era-normalization applied (no metadata bias proven).
   Means range 68.7 (Gym, n=2) to 91.6 (E-Card, n=3); the large modern eras sit
   at 85–87 and WOTC/Base at 79.1. Modern sets score higher partly because they
   are larger — see (4).
7. **Normalization stability** — the shipping Favorite Hit Coverage transform is
   **fixed and cohort-independent**, so leave-one-set-out shift is **0 by
   construction** (adding/removing a set cannot move another set's score). The
   cohort-robust variant, tested for comparison, shifts a median 0.01 but up to
   **11.58** points under LOSO — which is exactly why the fixed transform ships.
   Depth cap sensitivity: rank Spearman 0.988 (cap 6), 1.000 (cap 8, default),
   0.976 (cap 10) — the cap choice is not load-bearing.
8. **Existing-rank comparison** — v3 vs shipped V2: rank Spearman **0.645**.
   Largest movers, each explained:

| Set | V2 # | v3 # | Δ | Reason |
|---|---|---|---|---|
| Expedition Base Set | 114 | 11 | **+103** | depth method tier-points→HHI (+100); strength eligibility/renormalization (+85) |
| Celebrations: Classic Collection | 109 | 8 | **+101** | same; V2 scored it 20.0 |
| Legendary Collection | 112 | 22 | +90 | same |
| Crown Zenith | 86 | 6 | +80 | depth (+75), strength (+43) |
| Secret Wonders | 115 | 35 | +80 | depth (+100), strength (+82) |

The movement is dominated by **older sets rising**. V2's depth/accessible
components used tier-point caps that structurally zeroed sets whose subjects sat
below fixed thresholds, and V2's missing-slot policy inserted zeros. v3's HHI
depth and slot renormalization fix both, which is precisely the class of set
(vintage, no special packs) V2 under-served.

---

## 9. Simulation-cohort findings

**Card-level pull rates were not where the pipeline expected them.** The
snapshot `cards_json.pullRate` field is **null for every card in every set** —
so the first v3 run produced *zero* Simulation Opening Details. Card-level pull
probability is instead derived from each set's rarity-keyed
`pull_rate_assumptions` (`specific_card_odds_denominator`), which is what both
studies now use. This is a genuine data-plumbing gap worth fixing at the source.

Simulation Opening Details (`simulation_opening_details_v1`) computes, per
eligible card, subject access probability
`P(≥1 eligible card for subject in one pack)`, using exact slot-exclusive math
where slot groups are known and an explicitly-reported additive capped
approximation otherwise (mutually-exclusive same-slot cards add; independence
applies only across slots). Special Pack Appeal is **null, never zero**, when a
set has no such mechanic. Details compute for **22 of the 33** simulated sets;
the other 11 have no pull-rate assumptions and are reported as
`missing_pull_rates` rather than zero.

**Universal desirability vs pull accessibility — they disagree, and that is the
point.** Favorite Hit Coverage (checklist-based) vs Pull-Accessible Favorite
Exposure across those 22 sets: Spearman **−0.20**. The two are *mildly
negatively* related — large modern checklists carry many desirable subjects but
dilute the odds of actually pulling any one of them. This is strong evidence that
naming the checklist component "Accessible Favorite Hits" (as V2 did) was
misleading, and that the two must stay separate metrics.

| Set | Coverage rank | Pull-access rank | Gap |
|---|---|---|---|
| Shrouded Fable | 22 | 4 | **+18** (small set, easy access) |
| Prismatic Evolutions | 3 | 21 | **−18** (deep roster, hard to hit) |
| Chaos Rising | 21 | 7 | +14 |
| Ascended Heroes | 2 | 16 | −14 |

This is a **user-facing insight, never a reason to alter the universal rank**.

---

## 10. UI changes

- **All full-desirability sets** (with or without simulation) show score,
  all-set rank, percentile, the three components, top subjects, effective subject
  count, and coverage explanation.
- Copy: *"Set Desirability measures the popularity and depth of the Pokémon
  subjects in the set. It does not use card prices or predict future value."*
- **Removed misleading framing:** "Market confirmed" / "Partly confirmed" /
  "Weakly confirmed" verdict labels → **Market Association** bands ("Strong /
  Moderate / Weak market association"). The `Hits Only` and `Chase / High Value`
  card-validation scopes were **deleted** — both select cards *by rarity or
  price*, so any correlation they showed partially selects on the outcome.
- The card-validation chart now **defaults to Pure Pokémon Demand over all
  priced cards** (the price-independent read) instead of the merged Card Appeal,
  and Card Appeal carries an explicit note that its price correlation is
  inherited from Treatment/rarity and is not evidence of collector demand.
- RIP weights are rendered **from the backend config payload**, never hardcoded
  in the frontend, and always labeled *"reasoned default weighting"*.
- No "only Scarlet & Violet / Mega Evolution can be ranked for desirability"
  statement exists — 135 sets across 15 eras are ranked.

---

## 11. API contract

`explore_rip_statistics` targets now carry (additively; legacy fields untouched
during migration, with a `deprecatedFields` note):

- `desirabilityCoverage` / `simulationCoverage` — independent `{status, reasons}`
- `universalSetDesirability` — score/rank/percentile/version/asOf/components/
  componentWeights/topSubjects/effectiveSubjectCount/coverage, plus
  `setValueAssociation` (descriptive; **no** `clearedToInfluenceRip` flag exists)
- `rip` — score/rank, the four component contributions, the **weights object
  sourced from config**, and version
- `meta.ripWeightsConfig`, `meta.setValueAssociation`

No cap fields exist anywhere. No authoritative calculation happens in the
frontend.

---

## 12. Tests

| Suite | Result |
|---|---|
| `backend/tests/unit/desirability` (incl. **30 new**: 22 universal + 8 amplification) | **114 passed, 0 failed** |
| `backend/tests/unit/db/services` explore RIP + rip comparison | **14 passed, 0 failed** |
| `frontend` contract + alignment suites | **196 passed, 0 failed** |

**Full-suite regression check.** `pytest backend/tests/unit` on this working tree:
**42 failed, 1594 passed**. The identical command on a clean worktree at `HEAD`
(`0eb6347`): **42 failed, 1564 passed**. Same 42 failures, +30 passing — i.e.
**this work introduces zero regressions**, and the 42 are pre-existing on this
branch in modules untouched here (`calculations`, `interpretation`,
`logging_integration`, collection/profile services). They are copy/assertion
drift, not anything this pass caused, and are **not** fixed here.

Notable guards: Treatment/price/simulation **cannot** enter the universal score
(injecting them changes nothing); duplicate species cannot occupy multiple
Strength slots; component weights equal 30/90, 25/90, 35/90; renormalization is
exact; **no cap/clamp on desirability influence** (max-desirability moves RIP
exactly 10.0 points vs zero-desirability); `w_desirability` 0 and 1.0 both valid;
pillar diagnostics never mutate shipping weights; and a guard asserting **no gate
machinery survives** anywhere in the scoring code.

---

## 13. Known limitations

1. **v3 is computed at read time** from `pokemon_set_desirability_component_scores`
   subject rollups and cached in-process (6h TTL). A persistence pass into its own
   snapshot table is the natural follow-up; the payload shape is already final.
2. **Trend weighting moves levels materially** (§8.2) even though ordering is
   stable. Worth a deliberate decision.
3. **Set-size correlation** (~0.41–0.54) is real; partly signal, partly bias.
4. **Pull scarcity is rarity-keyed**, not per-card.
5. **Only 2 eras** have credible pull-rate coverage; everything pre-Sword-and-Shield
   is outside the amplification study entirely.
6. **`cards_json.pullRate` is null everywhere** — a data-plumbing gap (§9).
7. **The "~0.70 prior benchmark" is not reproducible** (§1); the shipped V2 score
   correlates at 0.145 on this cohort.
8. **No historical appeal series exists**, so no forward-return/predictive claim
   is possible or made.

## 14. Deferred (captured, not built — not presented as done)

- **Chase Magnetism into RIP** — the redundancy audit *passed* (§3: ρ = 0.04 vs
  Profit), so the remaining blocker is a product decision about what RIP should
  reward, not a statistical one. Not wired in; reported only.
- **Chase Magnetism UI** — the metric is computed and returned by
  `simulation_opening_details_v1`, but no dedicated UI surface was built.
- **Longitudinal price prediction** — requires capturing daily prices + weekly
  raw desirability components + versioned metadata *as of each date* going
  forward. Only after that may any UI say "predict/forecast/leading indicator".
- **Collector-preference validation** (financially-matched "which would you
  rather open, ignoring resale?" → Bradley–Terry latent ranking) — still the most
  important missing construct test, and the one competitors cannot reproduce
  from public prices.
- **Data-informed default weights** — only once behavioural data exists.
- User-facing weight customizer (scaffolded: weights already flow from config).
- Era-relative Treatment Prestige ontology; historical pull rates for older eras;
  trainer/non-Pokémon desirability; artwork/artist desirability.
