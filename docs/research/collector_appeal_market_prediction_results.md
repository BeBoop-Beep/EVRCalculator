# Collector Appeal, Market Relationships, and Predictive Valuation — Results

**Status: research only. Nothing committed to RIP, no frontend change, no
database writes, no production table touched.** Canonical RIP is unchanged.

- Run date: 2026-07-15. Database: Supabase `TheIndex` (`zwxzxuuawalvwioadhmf`).
- Constructs: `backend/desirability/collector_appeal.py`.
  Tests: `backend/tests/unit/desirability/test_collector_appeal.py` (38 tests).
- Studies: `backend/scripts/build_collector_appeal_market_study.py`,
  `backend/scripts/build_card_fair_value_study.py`.
- Raw output: `docs/research/collector_appeal_market_prediction_study.json`,
  `docs/research/card_fair_value_study.json`.
  CSVs: `docs/research/collector_appeal_tables/`.
- Seeds: bootstrap `20260716`, uncertainty `20260717`, card models `20260718`.
  500 bootstrap draws, 200 uncertainty draws per scenario.
- Cohort: **21 sets** (S&V 16, Mega Evolution 5), **1,322 priced hit cards**,
  615 distinct subjects. Cohort-limited; not externally validated on other eras.

> Price is used **only** as an external validation outcome and as the card-model
> target. It never entered the construction, normalization, internal weighting,
> or selection of any factor or candidate. Every candidate and weight is
> pre-registered as a module constant; a unit test walks the AST to assert no
> optimizer, no search loop, and no price identifier reaches any construct.

---

# EXECUTIVE RECOMMENDATION

## 1. Collector Appeal is **promising but still provisional**. Do not make it the second-largest RIP pillar. Keep the weight at 10% (15% is defensible; 25–30% is not).

## 2. Chase Appeal (`D × M`) **is ready as its own visible metric** — it survives the set-size correction. It is not a Collector Appeal formula and must not be relabelled as one.

## 3. Current-price estimation is **feasible but coarse**. Forecasting, recovery, and lead-lag are **hard-blocked** — not by method, but because appeal history does not exist.

Three findings drive all of this, and two were not anticipated by the brief.

**(a) `A` and `M` are one axis, not two — so there is nothing to "balance".**
`access_transform(p) = 1 − scarcity_transform(p)` at shared anchors. With one
printing per subject, `M2 ≡ 1 − broad_access` **exactly** (proved by unit test).
The cohort sits near that line: mean `A* + M1* − 1 = +0.040`. Under
complementarity every candidate collapses to a function of the single variable
`A`, and the *curvature* each formula applies is an authorial choice, not
evidence: `sqrt(A·M)` rewards the middle **by construction** and is **not
injective** (A=0.2 and A=0.8 score identically — a highly accessible set and an
extreme-chase set are declared equally appealing). `0.50A + 0.50M` **cancels
entirely** and becomes a rescaled `D`. Position along this axis is a **taste**
axis, not a quality axis: more `A` at the cost of `M` is better only for
collectors who prefer reachable hits. Collapsing it into one scalar requires
choosing whose taste to encode — which is exactly the missing preference data.

**(b) The current desirability pillar is rank-fragile, and is 98.9% a static
third-party scrape.** `D` correlates **0.9887** with `fan_popularity_score`; the
only time-varying input (Google Trends) is **0.0 for 49.7% of subjects** and
averages 2.29/100. And 16 of 21 sets sit in a 0.15-wide band (median adjacent
gap **0.005**, i.e. half a point on the 0–100 scale), so a 5% error in `D`
already drops rank correlation to **0.78**, and a 10% error to **0.56**. `D` is
the *least* robust construct in the study — less stable than Chase Intensity
(0.94 at the same error). **Raising the weight of a pillar this fragile amplifies
a nearly-static popularity scrape whose middle ordering is close to arbitrary.**

**(c) Card Chase Appeal fails.** `Subject Desirability × Card Scarcity` scores
out-of-fold R² **0.137** — far *worse* than scarcity alone (0.475, **−0.34**) and
worse than a plain rarity median (0.678, **−0.54**). Multiplying the two into one
score destroys information that keeping them separate retains.

**Recommended action**

- Keep `RIP = 0.58 Profit + 0.20 Safety + 0.12 Stability + 0.10 UniversalRosterAppeal`.
- If a Collector Appeal move is wanted now, `CA6 = D × (0.5 + 0.5·P)` at **15%**
  is the only defensible step, and it is a small one.
- Ship **Chase Appeal** (`D × M`) as a separate visible metric under that name.
- Expose `A` and `M` as a two-coordinate **profile**, not a blended score.
- Apply migration `046_PROPOSED` and start the capture job — but **fix the trend
  pipeline first** (see §16), because snapshotting a constant yields a constant.

---

## 3. Reproduction of prior findings

The prior factorized study reproduced **exactly**: max |Δρ| = **0.0000** across
every predictor on the primary outcome, and every held-out R² identical.

| Predictor | Prior ρ | Reproduced ρ | Δ |
|---|---|---|---|
| `D1` / roster appeal | 0.5506 | 0.5506 | 0.0 |
| `A*` | −0.4519 | −0.4519 | 0.0 |
| `M1*` | 0.8107 | 0.8107 | 0.0 |
| `D1 × M1*` (F4) | 0.8649 | 0.8649 | 0.0 |
| `F1` balanced | 0.2935 | 0.2935 | 0.0 |
| `F5` accessible | −0.2610 | −0.2610 | 0.0 |

Held-out R²: B0 −0.3085, B1 −0.9398, B2 +0.3890, B3 +0.6407, B4 −0.7037 — all
identical. `A*` remains ρ = **1.000** with the shipping Accessible Appeal.

**Every baseline claim stands.** All prior findings are treated as confirmed.

*Plain English:* re-running last phase's study gave bit-identical numbers, so
everything built on top of it rests on a solid base.

---

## 4. Collector Appeal candidate definitions

All pre-registered in `collector_appeal.py` before any outcome was examined.

```text
CA0 = D                                        (simplicity benchmark)
CA1 = D × A
CA2 = D × M                                    (= Chase Appeal)
CA3 = D × sqrt(A × M)
CA4 = D × (wA·A + wM·M)      over 75/25, 60/40, 50/50, 40/60, 25/75
CA5 = D × (wA·gA(A) + wM·gM(M) + wI·gA(A)·gM(M))
                             over (0.45,0.45,0.10), (0.40,0.40,0.20), (0.35,0.35,0.30)
CA6 = D × U(A, M) = D × (0.50 + 0.50·P)
```

**`gA` and `gM` are deliberately the identity.** `A` and `M` are already
fixed-anchor log-probability transforms (1-in-10 → 1.0, 1-in-1000 → 0.0). Adding
a further curvature would be an arbitrary nonlinearity, and any curvature chosen
after seeing an outcome is indistinguishable from tuning. Identity is documented
as a decision, not an oversight.

**Dual-Path Depth (`P`)** — the new construct, and the only one that escapes the
taste problem:

```text
P = Σ_s q_s · access(p_easiest_card_s) · scarcity(p_rarest_card_s)
```

*Plain English:* "for the Pokémon this set's collectors actually care about, how
often can you both realistically pull one **and** still have something to chase?"
Wanting both is taste-free — no collector is worse off because the Pikachu they
can reach also has a chase variant. `P` is also the structural **reason**
complementarity breaks (multi-printing subjects), so it is the honest second
dimension rather than a residual artifact. A single-printing subject is bounded
at 0.25, so one card can never masquerade as a dual path.

---

## 5. Synthetic-archetype behaviour

38/38 tests pass. Behaviour across the brief's ten archetypes:

| Property | Result |
|---|---|
| Increasing `D` lowers any candidate? | **Never** (all 13) |
| Increasing `A` lowers an A-bearing candidate? | **Never**; CA2/CA6 correctly unmoved |
| Increasing `M` lowers an M-bearing candidate? | **Never**; CA1 correctly unmoved |
| `D = 0` | **All** candidates → 0. Structure without desirability is never appeal |
| Zero component | CA1/CA3 collapse to 0; CA2 survives via the chase path; CA6 falls to its floor, never 0 |
| Rewards balanced middle by construction? | **CA3 and CA5 do** — peak at A=0.5 comes from the formula's shape |
| Unintuitive ties | **CA3 ties A=0.2 with A=0.8**; CA4_50_50 ties *everything* |
| Collapses under complementarity? | CA4_50_50 → `0.5·D` exactly (asserted) |
| Low `D` / extreme `M` | `M`=1.0 but every candidate < 0.10 — scarcity alone earns no appeal |
| Duplicates vs distinct subjects | One Pokémon twice ≠ two Pokémon (mass strictly lower) |
| Missing data | Returns unavailable, never 0 |

**The decisive archetype result:** of the ten, only the multi-printing archetype
opens a complement gap (> 0.20). Every single-printing archetype sits on the
degenerate line at gap ≈ 0 (asserted to 1e-6). This is the empirical
justification for Dual-Path Depth being the second dimension.

---

## 6. Information-retention and redundancy analysis

Flagged at |ρ| > 0.80. Full table: `collector_appeal_candidate_rankings.csv`.

| Candidate | vs D | vs A | vs M | vs size | Classification |
|---|---|---|---|---|---|
| `CA0` | 1.000 | −0.151 | 0.283 | 0.435 | mostly Desirability restated |
| `CA1` | 0.158 | **0.916** | −0.444 | −0.644 | mostly Accessibility restated |
| `CA2` | 0.565 | −0.501 | **0.930** | **0.777** | mostly Chase restated; size-driven |
| `CA3` | 0.520 | 0.392 | 0.328 | **0.016** | retains both; size-neutral |
| `CA4_75_25` | 0.557 | 0.475 | 0.242 | −0.069 | genuinely distinct |
| `CA4_50_50` | 0.681 | **−0.166** | 0.774 | 0.520 | retains almost no A |
| `CA4_25_75` | 0.603 | −0.408 | **0.903** | 0.714 | mostly Chase restated |
| `CA5_35_35_30` | 0.636 | −0.003 | 0.674 | 0.381 | retains almost no A |
| **`CA6`** | 0.765 | **0.262** | **0.248** | **0.129** | **genuinely distinct; size-neutral** |

**The empirical confirmation of the algebra:** `CA4_50_50` — the "balanced"
50/50 blend — retains ρ = **−0.166** with Accessibility while sitting at 0.774
with Chase Intensity. It is a chase metric wearing a balance label. Its near-zero
A content is not noise; it is the cancellation predicted in §4 showing up in the
data.

**Only `CA3` and `CA6` retain meaningful information from both axes while
remaining size-neutral.** `CA3` is disqualified on construct grounds (not
injective — see §5). That leaves **`CA6`** as the only survivor.

No candidate is redundant with a financial pillar (max |ρ| vs
Profit/Safety/Stability = 0.553).

*Plain English:* most "balanced" formulas quietly turn into chase metrics. Only
the dual-path one keeps a bit of both and doesn't just measure set size.

---

## 7. RIP weight analysis

Primary method: proportional rescaling of the 58:20:12 ratio. Full grid:
`rip_weight_sensitivity.csv`.

### The brief's 25% assumption is wrong — the crossover is 18.18%

Under proportional rescaling Safety **shrinks** as Collector Appeal grows, so
they cross where `w = (20/90)/(1 + 20/90) = 2/11 = 18.18%`. **Collector Appeal is
already the second-largest pillar at a 20% weight**, not only at 25%.

| CA weight | Profit | Safety | Stability | CA 2nd largest? |
|---|---|---|---|---|
| 10% | 0.5800 | 0.2000 | 0.1200 | No |
| 15% | 0.5478 | 0.1889 | 0.1133 | No |
| **18.18%** | 0.5273 | 0.1818 | 0.1091 | **crossover** |
| 20% | 0.5156 | 0.1778 | 0.1067 | **Yes** |
| 30% | 0.4511 | 0.1556 | 0.0933 | **Yes** |

### Influence

| Candidate @ weight | max rank Δ | mean Δ | ρ vs current RIP | ≥3 ranks | ≥5 ranks |
|---|---|---|---|---|---|
| `CA0` @ 10% | 0 | 0.00 | 1.000 | 0% | 0% |
| `CA0` @ 30% | 9 | 2.29 | 0.846 | 28.6% | 9.5% |
| `CA2` @ 10% | 5 | 1.62 | 0.946 | 19.0% | 4.8% |
| **`CA2` @ 30%** | **14** | **5.91** | **0.290** | **66.7%** | **52.4%** |
| `CA3` @ 30% | 5 | 1.52 | 0.930 | 9.5% | 4.8% |
| **`CA6` @ 10%** | 3 | 0.38 | 0.987 | 4.8% | 0% |
| **`CA6` @ 15%** | 2 | 0.38 | 0.992 | 0% | 0% |
| **`CA6` @ 25%** | 5 | 1.24 | 0.948 | 14.3% | 4.8% |
| `CA6` @ 30% | 6 | 1.43 | 0.936 | 19.0% | 4.8% |

**Influence vs robustness, read together:** `CA2` at 30% would rewrite the
rankings (ρ 0.29, two thirds of sets moving ≥3 places) — but `CA2` is a
scarcity-driven price proxy, so that would convert 30% of RIP into a second
financial term. `CA6` is well-behaved but modest: at 15% it moves nothing
(max 2, mean 0.38), and only at 25–30% does it begin to matter.

That is the tension: **`CA6` only becomes influential at exactly the weights its
construct validity cannot yet justify.**

### Robustness under input uncertainty

Median rank ρ vs base under a lognormal shock to `D`:

| σ on D | `CA0` (= today's pillar) | `CA6` | `CA2` (chase) |
|---|---|---|---|
| 0.05 | **0.782** | 0.877 | 0.978 |
| 0.10 | **0.559** | 0.706 | 0.936 |
| 0.20 | **0.409** | 0.546 | 0.852 |

**This is the study's most decision-relevant number.** The pillar RIP ships today
is the *least* robust construct measured. A 10% error in desirability — entirely
plausible for a score that is 98.9% a one-off third-party popularity scrape —
reorders the rankings almost beyond recognition (ρ 0.56). `CA6` is meaningfully
more robust than `CA0` at every error level, which is a genuine argument *for*
the dual-path term. But neither is robust enough to justify doubling or tripling
its weight.

Under pull-rate error (±30% independent) all candidates hold up well; the
binding uncertainty is in `D`, not in the pull model.

*Plain English:* today's desirability pillar is packed so tightly that small
errors reshuffle it. Making it a bigger share of RIP makes that noise louder.

---

## 8. Size-bias analysis — the decisive test

> Does Chase Appeal explain market value beyond the number of chances a large set
> has to contain desirable rare cards?

**Yes.** Full table: `set_size_adjusted_analysis.csv`.

| Construct | vs eligible cards | raw top-10 ρ | partial (all size controls) | attenuation |
|---|---|---|---|---|
| `D1` | 0.435 | 0.551 | 0.703 | −0.153 |
| `A*` | −0.772 | −0.452 | 0.303 | −0.755 |
| `M1*` | 0.718 | 0.811 | 0.592 | +0.218 |
| **`D × M`** | **0.777** | **0.865** | **0.784** | **+0.081** |
| `dual_path_depth` | 0.129 | −0.052 | 0.476 | −0.528 |
| `CA6` | 0.129 | 0.420 | 0.741 | −0.322 |

**`D × M` loses only 0.081 to size controls (0.865 → 0.784).** Its size
correlation is real (0.777) but it is *not* the source of its market
relationship.

The independent check — an expected-score model fitted on **size controls only,
with price never a regressor**:

| Size-adjusted variant | top-10 ρ | Bootstrap 95% CI | includes 0? | vs eligible cards |
|---|---|---|---|---|
| **Excess Chase Appeal** | **0.622** | **[0.222, 0.880]** | **No** | 0.123 |
| Excess Chase Intensity | 0.548 | [0.090, 0.823] | No | 0.076 |

After stripping out everything predictable from opportunity count, Chase Appeal
retains ρ = 0.622 with a CI excluding zero, and its size correlation collapses
from 0.777 to 0.123. **The prior study's most serious reservation about `D × M`
is resolved: the effect is not a set-size artifact.**

### A methodological correction to the brief

The brief proposed "fixed top-k average-value outcomes that do not mechanically
reward large sets." **This is vacuous for rank statistics:** `top_10_avg =
top_10_total / 10` is a monotone transform, so Spearman is *identical* for both
(verified — every construct's `raw_top10_avg` equals its `raw_top10`). The
meaningful contrast is top-10 (fixed k) versus *total set value* (size-sensitive),
which is what is reported.

---

## 9. Current market relationships

Full matrix: `set_level_market_relationships.csv`. Value-**level** and
value-**concentration** outcomes are reported separately throughout.

| Predictor | top-10 value | Value HHI | Top-1 share |
|---|---|---|---|
| `D1` | 0.551 | 0.297 | 0.416 |
| `A*` | −0.452 | 0.401 | 0.338 |
| `M1*` | **0.811** | 0.117 | 0.029 |
| **`D × M`** | **0.865** | 0.157 | 0.140 |
| `dual_path_depth` | −0.052 | **0.468** | 0.348 |
| `CA6` | 0.420 | 0.381 | 0.355 |
| `complement_gap` | 0.614 | — | — |
| `axis_position` | **−0.690** | — | — |

**Three readings that matter:**

1. **`D × M` is the metric that best explains set value** (0.865, CI
   [0.660, 0.948], LOSO [0.844, 0.899], 0 sign flips) — and it survives size
   control. This is a real, robust market result.
2. **`axis_position` = −0.690.** The more a set's taste coordinate leans toward
   accessibility, the *lower* its value. This is the taste↔price tradeoff stated
   numerically: accessibility mechanically reduces scarcity, and scarcity is
   priced. **Any Collector Appeal formula that leans accessible will look bad
   against price for reasons that have nothing to do with collectors.**
3. **Dual-Path Depth has no value-level signal (−0.052, CI includes zero) but the
   strongest HHI relationship of any construct (0.468).** It is a *concentration*
   construct: sets with reach-plus-chase structure spread value differently, they
   don't hold more of it. That is a coherent finding, not a failure — and a
   larger concentration relationship is **not** automatically "better".

*Plain English:* chase scarcity explains set value; accessibility works against
price by definition; dual-path structure changes how value is spread, not how
much there is.

---

## 10. Card-level Chase Appeal — a negative result

1,322 cards, 21 sets, grouped-by-set validation (a held-out set's cards never
train its own model). Full ladder: `card_fair_value_study.json`.

| Model | OOF R² | MAE (log) | MdAPE | Spearman |
|---|---|---|---|---|
| B0 rarity median | **0.678** | 0.698 | 48.8% | 0.740 |
| B1 set + rarity controls | 0.556 | 0.834 | 62.2% | 0.708 |
| B2 desirability only | 0.047 | 1.345 | 86.2% | 0.031 |
| B3 scarcity only | 0.475 | 0.943 | 76.7% | 0.689 |
| B4 desirability + scarcity | 0.569 | 0.864 | 67.3% | 0.731 |
| B5 + interaction | 0.580 | 0.853 | 66.9% | 0.734 |
| **B6 Card Chase Appeal** | **0.137** | 1.287 | 83.8% | 0.093 |
| **B7 full permitted** | **0.739** | **0.649** | 49.3% | **0.835** |

**Card Chase Appeal fails its own test.**

| Comparison | Δ R² |
|---|---|
| vs desirability alone | **+0.091** |
| vs scarcity alone | **−0.338** |
| vs rarity alone | **−0.541** |
| vs set + rarity controls | **−0.419** |
| interaction over additive (B5 − B4) | **+0.010** |

It beats desirability alone and loses to everything else. Collapsing desirability
and scarcity into one product **destroys** information that keeping them separate
retains (B4 = 0.569 vs B6 = 0.137), and the interaction term adds +0.010 — noise.

**A plain rarity median (0.678) beats every desirability/scarcity model.** Only
the full model beats it, by +0.061. Most of what these constructs "explain" about
card price is rarity.

*Plain English:* multiplying desirability by scarcity into one card score makes
predictions worse than just knowing the card's rarity. Don't ship it.

---

## 11. Fair-value model results — feasible but coarse

Best model B7: OOF R² **0.739**, Spearman 0.835, MdAPE **49.3%**.

Headline R² is flattering. **Within every price tier, R² is negative:**

| Actual price tier | n | MdAPE | mean bias (log) | R² |
|---|---|---|---|---|
| under $5 | 586 | 48.7% | **−0.426** | **−0.457** |
| $5–25 | 453 | 47.6% | −0.145 | **−1.442** |
| $25–100 | 218 | 48.8% | **+0.446** | **−3.848** |
| over $100 | 65 | 62.1% | **+0.925** | **−2.353** |

The model separates cheap from expensive cards and does nothing more. Within any
tier it is worse than that tier's mean. The bias is classic shrinkage: it
**over-predicts cheap cards** (−0.43) and **under-predicts expensive ones**
(+0.93). Per-set fit ranges from MAE 0.447 (White Flare) to **1.296 (Paldean
Fates)**.

**Prediction intervals are not reported.** With no repeated-observation error
model and residual spread this heteroskedastic, any interval would be
indefensible.

*Plain English:* we can sort cards into roughly the right price band, but the
typical estimate is still off by about half. This is a triage tool, not an
appraisal.

---

## 12. Valuation-gap results — these are model errors, not opportunities

`gap = log(actual) − log(out-of-fold expected)`. All predictions out-of-fold.
Gap sd 0.828. Table: `valuation_gaps.csv`.

**The diagnostics say these gaps are not tradeable signals:**

- **Spearman(gap, actual price) = +0.368.** Genuine mispricings would be roughly
  orthogonal to price level. These are partly the price tier restated — the
  arithmetic shadow of the shrinkage in §11.
- **58% of extreme gaps (69 of 118 with |gap| > 1.5) are in a single set:
  Paldean Fates** — the worst-fitting set, a special shiny-subset product whose
  print run the model cannot see. That is an omitted **set-level** variable, not
  118 card-level opportunities.
- The largest "below model" cards are all cheap Paldean Fates commons the model
  over-predicts (Weavile $3.22 vs $32.58 expected). The largest "above model" are
  chase cards it under-predicts (Zekrom ex $562.64 vs $23.17). **This is the
  model's compression, seen from both ends.**

**Confidence-adjusted valuation gap: BLOCKED.** Every input the brief names for
it — liquidity, sales volume, price-observation sparsity — is **absent from the
schema**. Any "confidence" weight would be fabricated.

**Verdict on Q13:** these gaps are **overwhelmingly missing-variable errors**,
not market opportunities. They must not be shipped as under/overvaluation.

---

## 13. Forecasting feasibility — BLOCKED

Not attempted. Manufacturing a result here would be indefensible, for a reason
that no modelling choice can fix.

| Requirement | Reality |
|---|---|
| Appeal history | **1 snapshot** (2026-06-11). Momentum/persistence are undefined |
| Card price history | 98 days (2026-04-07 → 2026-07-15) |
| 30-day forward returns | ~2 non-overlapping windows — not evaluable |
| 90 / 180-day forward returns | **Impossible** on a 98-day panel |

The one long card panel — `pokemon_set_top_chase_card_daily_history`, **415 days,
1,673 cards** — was deliberately **not** used for forecasting: its membership is
determined by *being a top-priced chase card*, so forward returns computed from it
are selected on the outcome. It is a spurious-result generator, not a validation
set. It is usable for *descriptive* top-chase history only.

---

## 14. Stable-appeal recovery — BLOCKED

`Appeal Persistence` and `Appeal Momentum` both require appeal at ≥2 time points.
Appeal exists at **exactly one**. No drawdown cohort, hazard model, or survival
analysis can be run, regardless of how many price drawdowns the 98-day panel
contains. This remains the most interesting open hypothesis in the programme and
is entirely gated on §16.

---

## 15. Reverse causality — BLOCKED, but with an unexpected reassurance

The lead-lag test cannot run: there is nothing to lag.

The brief's specific worry was that *price rises → creators discuss → search
interest rises → measured desirability rises*, making desirability look
predictive when it is derivative. Two facts bear on this:

- **The risk channel is real but currently near-dormant.** `D` = 0.75·fan
  popularity + 0.25·trend, and the trend component is **0.0 for 49.7% of
  subjects**, averaging 2.29/100. `D` correlates **0.9887** with fan popularity
  alone. So today, almost none of `D` can be price-driven — the contamination
  channel carries almost no weight.
- **But the window is contaminated by design.** The trend component was captured
  on 2026-06-11 over a trailing **1-month** window that sits *inside* the price
  panel. It is contemporaneous with the prices it would "predict".

**Classification: indeterminate due to insufficient data** — with the caveat that
if the trend pipeline is repaired (§16), this risk grows from negligible to
material, and the point-in-time discipline in migration 046 becomes essential
rather than precautionary.

---

## 16. Data inventory and gap register

| Field | Table | Coverage | Point-in-time safe? | Status |
|---|---|---|---|---|
| Card market price | `card_variant_price_observations` | 2026-04-07 → 07-15, **98 days**, 12.6M rows, daily, TCGPlayer | Yes | **Listing-derived, NOT completed sales** |
| Card price (latest) | `pokemon_canonical_card_market_prices_latest` | current only | No (upserted) | OK for current-value work |
| Monthly rollups | `card_variant_price_monthly_rollups` | **2 months** | Yes | Too short |
| Set value | `pokemon_set_value_daily_history` | 100 days, 166 sets | Yes | Short |
| Top-chase card price | `pokemon_set_top_chase_card_daily_history` | **415 days**, 1,673 cards | Yes | **Selected on price rank** — biased for returns |
| Subject desirability | `pokemon_desirability_composite_scores` | **1 snapshot**, upserted | **No** | **BLOCKING** |
| Google Trends | `pokemon_trend_scores` | **1 capture**, `today 1-m`, 1 of 3 snapshots rate-limited | **No** | **BLOCKING + degraded** |
| Sales volume / count | — | — | — | **ABSENT** |
| Listing count / supply velocity | — | — | — | **ABSENT** |
| Liquidity | — | — | — | **ABSENT** |
| Grading population / gem rate | — | — | — | **ABSENT** |
| Reprint events | — | — | — | **ABSENT** |
| Sealed availability | — | — | — | **ABSENT** |
| Card condition mix | `conditions` exists | not in the price layer used | — | Partial |
| Rarity / treatment / set age / printings | derived | full | Yes | Available |

A schema-wide search for `%volume%`, `%sales%`, `%listing%`, `%population%`,
`%gem%`, `%liquid%`, `%reprint%`, `%supply%` returned **nothing**.

### The collection plan — and the trap in it

Proposed and **not applied**:

- `backend/db/migrations/046_PROPOSED_desirability_daily_history.sql` — three
  append-only tables with `observed_on` (what the source describes) separated
  from `captured_at` (when we recorded it) and an explicit `is_backfilled` flag,
  so a backfill can never be mistaken for a contemporaneous observation.
- `backend/scripts/capture_desirability_history.py` — dry by default; verified
  dry-run appends 1,025 desirability + 1,048 trend rows. Refuses to run with
  `--commit` if the migration is absent rather than silently capturing nothing.
  Skips rate-limited snapshots, because recording one as an observation would
  inject a fake trough into every momentum series computed later.

> **Snapshotting alone will not unblock forecasting.** `D` is 98.9% a static fan
> popularity scrape. Capturing it daily produces a **flat line**, and Appeal
> Momentum computed from it would be almost pure noise. **The trend pipeline must
> be repaired first** — it is rate-limited, zero for half the roster, and runs on
> a 1-month window. Fixing the time-varying input is the prerequisite, not the
> snapshot cadence.

**Minimum viable collection:** repair trends → capture weekly (12-month window,
stable anchor term) + desirability daily → **6 months** before a 30-day
walk-forward is credible, **12–18 months** for 90/180-day horizons and drawdown
recovery cohorts. Highest-value external additions, in order: **completed-sale
prices**, **sales volume**, **listing counts**, then grading population.

---

## 17. Recommended next actions

1. **Repair the Google Trends pipeline** (rate limiting, 49.7% zeros, 1-month
   window). Everything longitudinal is gated on this, and no amount of
   snapshotting substitutes for it. *Highest value in the programme.*
2. **Apply migration 046 and schedule the capture job.** The binding constraint
   is calendar time; the value is almost entirely in starting early.
3. **Ship Chase Appeal (`D × M`)** as its own visible metric — it survives size
   correction and is the strongest, most robust market construct measured.
4. **Do not ship Card Chase Appeal.** It is a negative result.
5. **Run the collector-preference study** (financially-matched pairwise "which
   would you rather open?"). This is now the decisive missing evidence — see §19.
6. **Investigate `D`'s clustering.** 16 of 21 sets inside a 0.15 band is a
   product problem regardless of pillar weight: the middle ordering is close to
   arbitrary.
7. Defer the RIP weight increase until 5 and 6 land.

---

## 18. Exact limitations

1. **n = 21 sets.** Every set-level result rests on 21 points.
2. **Cohort-limited** to S&V (16) and Mega Evolution (5). No external holdout;
   Lost Origin is excluded entirely. Not validated on Sword & Shield or earlier.
3. **Modeled, not observed, pull rates**, constant within set × rarity.
4. **`D` carries no measured uncertainty** — the σ scenarios in §7 are
   assumptions, not estimated bounds.
5. **Price is listing-derived**, not completed sales.
6. **Card models omit** volume, liquidity, supply, population, reprints and
   condition mix — §12's gaps are dominated by exactly these.
7. **Contemporaneous only.** Nothing here predicts future prices, and no such
   claim is made.
8. **`CA6`'s floor and gain (0.50 / 0.50) are reasoned defaults**, not validated.
   They are pre-registered, never fitted — but "not fitted" is not "correct".
9. **Blocked:** collector-preference validation; all forecasting, recovery, and
   lead-lag work; confidence-adjusted valuation gaps.

---

## 19. What remains unvalidated without collector-preference data

This is the honest core of the phase. **Every construct that plausibly represents
opening *experience* is unmeasurable against price by construction**, because
accessibility lowers scarcity and scarcity is priced (`axis_position` vs value =
−0.690). Another price regression cannot resolve whether `CA6` beats `CA3` beats
`CA0` as a *Collector Appeal* measure — it can only tell us which is the better
price proxy, which is the question we are explicitly not asking.

Specifically unvalidated:
- Where real collectors sit on the `A ↔ M` taste axis, and whether one point can
  represent them all. **Several distinct collector-preference profiles likely
  exist**, in which case a single scalar Collector Appeal is the wrong object and
  the profile (`axis_position`, `D`, `P`) is the right one.
- Whether Dual-Path Depth is something collectors actually value, or merely a
  mathematically convenient orthogonal axis.
- Whether `CA6`'s 0.50/0.50 floor/gain match any real preference.

A financially-matched pairwise elicitation ("which would you rather open?")
resolves all three and nothing else does.

---

## 20. Exact tests and files changed

| Suite | Result |
|---|---|
| `test_collector_appeal.py` (new) | **38 passed** |
| `test_factorized_opening_appeal.py` | **40 passed** (unchanged) |
| `backend/tests/unit/desirability` (full) | **206 passed, 0 failed** (168 pre-existing, unchanged) |
| Frontend contract tests | **not run — no payload or frontend code was touched** |

| File | Status | Purpose |
|---|---|---|
| `backend/desirability/collector_appeal.py` | **added** | CA0–CA6, Dual-Path Depth, RIP reweighting (research only) |
| `backend/scripts/build_collector_appeal_market_study.py` | **added** | Goals 1 & 2 |
| `backend/scripts/build_card_fair_value_study.py` | **added** | Card Chase Appeal, Models One & Two |
| `backend/scripts/capture_desirability_history.py` | **added, PROPOSED** | History capture; dry by default, never run with `--commit` |
| `backend/db/migrations/046_PROPOSED_desirability_daily_history.sql` | **added, NOT APPLIED** | Point-in-time history tables |
| `backend/tests/unit/desirability/test_collector_appeal.py` | **added** | 38 tests |
| `docs/research/collector_appeal_market_prediction_results.md` | **added** | This document |
| `docs/research/collector_appeal_market_prediction_study.json` | **added** | Raw output |
| `docs/research/card_fair_value_study.json` | **added** | Raw output |
| `docs/research/collector_appeal_tables/*.csv` | **added** | 7 supporting tables |

No production module, payload, frontend file, RIP weight, or database object was
touched. A unit test asserts the new module performs no database access; the
capture script is the only file that *can* write, it is dry by default, and it
has never been run with `--commit`.

---

# DECISION TABLE ONE: Collector Appeal

| Candidate | Math valid | Preserves D | Preserves A | Preserves M | Size-neutral | Distinct from financial | Robust | Affects RIP | Suitable as Collector Appeal | Weight range |
|---|---|---|---|---|---|---|---|---|---|---|
| `CA0 = D` | Yes | — | **No** | **No** | Partial (0.44) | Yes | **Weakest (0.56 @ σ=.10)** | Only ≥25% | Incumbent; taste-free but fragile | 10% |
| `CA1 = D×A` | Yes | Yes | **Restates it (0.92)** | No (−0.44) | No (−0.64) | Yes | Moderate | Yes | No — it is `A` renamed | — |
| `CA2 = D×M` | Yes | Yes | **No (−0.50)** | **Restates it (0.93)** | **No (0.78)** | Yes | **Strongest** | **Overwhelms at ≥20%** | **No — it is a market metric** | 0% (ship separately) |
| `CA3 = D√(AM)` | **No — not injective** | Yes | Yes (0.39) | Yes (0.33) | **Yes (0.02)** | Yes | Moderate | Weak | **No — ties opposite sets** | — |
| `CA4 50/50` | **Degenerate** | Yes | **No (−0.17)** | Yes (0.77) | Partial | Yes | Moderate | Moderate | **No — chase in disguise** | — |
| `CA4 75/25` | Yes | Yes | Yes (0.48) | Weak (0.24) | Yes (−0.07) | Yes | Moderate | Weak | Only under an accessibility taste | — |
| `CA5 (all)` | Hump by construction | Yes | **No (≈0)** | Yes (0.67) | Partial | Yes | Moderate | Moderate | No | — |
| **`CA6 = D×(0.5+0.5P)`** | **Yes** | **Yes (0.77)** | **Yes (0.26)** | **Yes (0.25)** | **Yes (0.13)** | **Yes** | **Better than CA0** | Only ≥25% | **Best available — provisional** | **10–15%** |

# DECISION TABLE TWO: Market Metrics

| Metric | Raw | Size-controlled | LOSO stable | Pull-robust | Card-level | Set-level | Explanatory / predictive | Product label |
|---|---|---|---|---|---|---|---|---|
| `D` | 0.551 | 0.703 | Yes | Yes | **R² 0.047 — no** | Weak | Explanatory only | `universal_roster_appeal` |
| `A` | −0.452 | 0.303 | Yes | Weakest | No | Inverse | Explanatory (negative by construction) | `accessible_appeal` (report as probabilities) |
| `M` | 0.811 | 0.592 | Yes | Yes | R² 0.475 | **Strong** | Explanatory | `chase_intensity` |
| **`D × M`** | **0.865** | **0.784** | **Yes [0.844,0.899]** | **Yes** | n/a | **Strongest** | **Explanatory only** | **`chase_appeal`** |
| Excess Chase Appeal | 0.622 | — (size-free) | — | — | n/a | Strong | Explanatory | research diagnostic |
| `dual_path_depth` | −0.052 | 0.476 | CI incl. 0 | Yes | n/a | **Concentration only** | Explanatory | internal submetric |
| `axis_position` | −0.690 | −0.197 | Yes | Yes | n/a | Strong | **Taste coordinate — not a score** | profile axis |
| Card Chase Appeal | R² **0.137** | — | — | — | **Fails** | n/a | **Neither** | **do not ship** |

# DECISION TABLE THREE: Predictive Readiness

| Goal | Status | Current performance | Missing data | Minimum next step | Leakage risk | Reverse-causality risk | Next validation |
|---|---|---|---|---|---|---|---|
| Current fair-value estimation | **Available (coarse)** | OOF R² 0.739, MdAPE **49.3%**, negative within every tier | volume, liquidity, population, reprints, condition | Add completed-sale prices + volume | Low (grouped by set) | None (contemporaneous) | Per-tier recalibration |
| Model-implied under/overvaluation | **Partially available — not shippable** | gap sd 0.83; ρ(gap, price) = **+0.368**; 58% of extremes in one set | same as above | Set-level print-run/product-type feature | Low | Unknown | Requires forward returns |
| Confidence-adjusted gap | **Blocked** | — | liquidity, volume, observation sparsity — **all absent** | Capture listing + sales counts | — | — | — |
| Future price / return forecasting | **Blocked** | — | ≥6–18 months of appeal + price history | **Repair trends**, then migration 046 | **High if backfilled** | **High** | Walk-forward only |
| Recovery after drawdown | **Blocked** | — | appeal history; 90/180d price windows | Same | High | High | Event study once ≥12 months |
| Appeal→price lead-lag | **Blocked** | — | ≥2 appeal observations (have **1**) | Same | High | **The core risk** | Cross-lag once ≥6 months |

---

# ANSWERS TO THE TWENTY QUESTIONS

1. **What should `M` be called?** **Chase Intensity** — elite scarcity among
   desirable subjects, desirability magnitude excluded.
2. **What should `D × M` be called?** **Chase Appeal**. Not Opening Appeal, not
   Collector Appeal: it carries none of the accessibility axis (−0.50).
3. **Is `D × M` still strong after controlling for set size?** **Yes.** 0.865 →
   0.784 partial (attenuation 0.081); Excess Chase Appeal 0.622, CI [0.222,
   0.880] excludes zero, size correlation collapses 0.777 → 0.123.
4. **Is there a defensible combined Collector Appeal formula today?**
   **Provisionally — `CA6 = D × (0.5 + 0.5·P)`.** It is the only candidate that
   is mathematically sound, size-neutral, retains both axes, and beats the
   incumbent on robustness. Its floor/gain are unvalidated.
5. **Does it retain meaningful information from both `A` and `M`?** Yes — 0.26
   and 0.25. It is the only sound candidate that does (`CA3` also does but is not
   injective; `CA4_50_50` retains **−0.17** of `A`).
6. **What weight gives meaningful influence without overwhelming RIP?** For
   `CA6`, influence only begins at **25%** (max Δ 5, mean 1.24). At 15% it moves
   almost nothing. For `CA2` even 20% overwhelms (ρ 0.67).
7. **Is making Collector Appeal the second-largest pillar defensible now?**
   **No.** It becomes second-largest above **18.18%** (not 25%), and `CA6` only
   matters at 25–30% — precisely the weights its unvalidated taste assumption
   cannot support. Compounding this, the underlying `D` is the least robust
   construct measured (ρ 0.56 at σ=0.10).
8. **Which current metric best explains set value?** **`D × M`** (0.865, CI
   excludes zero, LOSO [0.844, 0.899], survives size control).
9. **Which best explains individual card value?** **Rarity** (median alone: R²
   0.678). Among constructs, modeled scarcity (0.475). Desirability is nearly
   useless at card level (0.047).
10. **Does Card Chase Appeal outperform desirability or scarcity alone?** Beats
    desirability (+0.091). **Loses badly to scarcity (−0.338) and rarity
    (−0.541).** Do not ship it.
11. **How accurately can current prices be estimated out of sample?** R² 0.739,
    Spearman 0.835, **MdAPE 49.3%** — and negative R² within every price tier.
    Band-sorting, not appraisal.
12. **Which cards appear above/below model-implied fair value?** Listed in
    `valuation_gaps.csv` — but see 13.
13. **Are those gaps missing-variable errors or opportunities?** **Overwhelmingly
    missing-variable errors.** ρ(gap, price) = +0.368 and 58% of extreme gaps sit
    in one set (Paldean Fates) whose product type the model cannot see.
14. **Do valuation gaps predict future returns?** **Unknown and untestable** on
    98 days of price history.
15. **Does stable appeal predict faster recovery?** **Untestable.** Appeal exists
    at one point in time.
16. **Do appeal changes lead price changes?** **Indeterminate.** Currently the
    channel is near-dormant (`D` is 98.9% fan popularity, trend is 0 for half the
    roster) — but the trend window is contemporaneous with the price panel, so
    the test is unfalsifiable as constructed.
17. **What can be credibly built now?** Chase Appeal as a visible metric; the
    accessibility probability readings; a coarse fair-value band estimator; the
    `A`/`M` profile.
18. **What requires more data?** All forecasting, recovery, lead-lag,
    confidence-adjusted gaps, and any under/overvaluation claim.
19. **What should inDex snapshot immediately?** **Repair Google Trends first**,
    then desirability daily and trends weekly via migration 046. Snapshotting
    today's near-static `D` captures a flat line.
20. **What is the highest-value next research phase?** **The collector-preference
    study.** It is the only thing that can resolve the taste axis, and no further
    price regression can substitute for it. The trend-pipeline repair is the
    highest-value *engineering* task, since it gates everything longitudinal.
