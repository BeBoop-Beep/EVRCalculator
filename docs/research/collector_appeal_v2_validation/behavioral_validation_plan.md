# Behavioral construct-validation plan — collector paired-choice study

**Status:** design only. Nothing here is implemented. Personal Fit is **not**
built, and this plan does not authorize building it.

**Why this document exists.** Every price-based analysis in this programme is
structurally incapable of validating Collector Appeal. Accessibility mechanically
reduces scarcity, and scarcity is priced — the July study measured
`axis_position` vs set value at **−0.690**. So a Collector Appeal formula that
leans accessible *must* look worse against price, for reasons that have nothing
to do with collectors. No further price regression can resolve whether the
revised formula beats CA7 as a measure of **appeal**; it can only tell us which
is the better price proxy, which is the question we are explicitly not asking.

Collector behaviour is the only ground truth that can.

---

## 1. Three questions, three constructs

The study asks three *separately worded* questions about the same product pair.
They are not paraphrases — each targets a different construct, and the whole
design rests on keeping them apart.

### Financial choice
> Which product would you choose if your primary goal were minimizing financial
> downside?

Validates **Financial RIP**.

### General opening choice
> Which product do you believe would be more appealing for the average Pokémon
> collector to open?

Validates **General Collector Appeal**. Note the deliberate third-person
framing: it asks for a population judgement, not a personal preference.

### Personal choice
> Which product would you personally rather open?

Validates **Personal Fit** — specifically, the *residual* after General Collector
Appeal is accounted for.

**The critical measurement is the divergence between questions 2 and 3.** If
they agree almost perfectly, Personal Fit is not a distinct construct and should
not be built. If they diverge systematically with stated preferences (favorite
Pokémon present, accessibility-vs-chase taste), Personal Fit is real and the
divergence itself is its training signal. A design that asked only "which would
you rather open?" could never separate these and would silently validate a blend
of the two.

---

## 2. What is captured per response

| Field | Why |
|---|---|
| Anonymous user id | Cluster responses; enable user-level held-out evaluation |
| Set pair (A, B) | The unit of comparison |
| Displayed prices for A and B | Price is shown, so it must be modelled, not assumed away |
| Decision type | `financial` / `general` / `personal` |
| Selected product | The outcome |
| Response confidence | 1–5; lets low-confidence responses be down-weighted in sensitivity, never dropped from the primary |
| Presentation order | Detect order effects |
| Whether detailed metrics were viewed first | A choice made after reading RIP is partly a test of the explanation, not the product |
| Model versions shown | A response is only interpretable against the scores that produced the display |
| Timestamp | Detect fatigue, session effects, and drift as prices move |

Model versions are non-negotiable: a response collected under
`overall_rip_v6_80_...` cannot be pooled with one collected under a later
formula without recording which was on screen.

---

## 3. Design controls

**Randomized pair ordering.** Left/right position randomized per presentation;
order recorded so a position effect is measurable rather than assumed absent.

**Product-price controls.** Price is the dominant confound: a cheaper pack wins
the financial question almost by construction. Two mitigations, used together:

1. **Financially matched pairs** — a designed subset where the two products'
   pack costs are within ~10%. This is where the appeal questions carry the most
   information, because price is nearly held constant.
2. **Price as a model covariate** in every specification, so unmatched pairs are
   still usable rather than discarded.

**Avoiding repeated-exposure effects.** No user sees the same *pair* twice in any
decision type. A user may see the same *set* in different pairs — unavoidable
with a 22-set cohort — so set-level exposure count is recorded and tested as a
covariate. Pairs are drawn from a balanced incomplete block design rather than
uniformly at random, so no pair is over-sampled and every set appears a similar
number of times.

**Preference capture, once, before the choices.** Favorite Pokémon (free
selection), favorite trainers, preferred artists, preferred eras, stated
preference for attainable cards versus elite chases, risk tolerance, and
collection-completion goals. Captured *before* the paired choices so it cannot be
rationalized after the fact, and used only in the Personal Fit analysis.

**Financial-versus-collector priority.** A single stated-priority item, used to
test whether the financial and general questions load differently for users who
say they care mainly about value.

---

## 4. Analysis

### Primary: Bradley-Terry with user random effects

For a pair (i, j), model `P(i chosen over j) = logit^-1(θ_i − θ_j + βX_ij)`, where
θ is a latent per-set desirability estimated separately for each decision type.
User-level random effects (or clustered standard errors) are mandatory: repeated
choices by one user are not independent observations, and ignoring that would
shrink standard errors toward zero and manufacture significance.

### Equivalent specification: conditional logistic regression

Conditional logit with the pair as the stratum, which is algebraically the
Bradley-Terry model with covariates. Reported alongside so the covariate
coefficients (price, exposure, order) are directly readable.

### The comparison that matters

Three models, evaluated identically:

1. **Financial-only** — Financial RIP V3 as the sole predictor
2. **Appeal-only** — Collector Appeal as the sole predictor
3. **Combined** — both, with the weight *estimated* rather than assumed

The combined model's estimated weight on Collector Appeal is the empirical
counterpart of the 80/20 decision. **If the estimated appeal weight's confidence
interval excludes 0.20, that is direct evidence about the shipped weight** — in
either direction. This is the single most valuable number the study produces.

### Held-out evaluation, two ways

* **By user** — train on some users, predict others. Answers "does this
  generalize to a new collector?"
* **By product pair** — train on some pairs, predict unseen pairs. Answers "does
  this generalize to a new matchup?"

Both are required. Held-out-by-user alone would reward a model that has memorized
this particular 22-set cohort.

### Reported metrics

Predictive **log loss** and **calibration** (reliability curve plus calibration
slope), not accuracy alone. Accuracy on near-tied pairs is uninformative — a
model that calls every close pair a coin flip is *correct* to do so, and accuracy
would penalize it. Log loss rewards honest uncertainty, which is exactly the
behaviour this programme wants from a score.

### Personal Fit specification

Personal Fit is estimated as the **residual** of the personal choice after
conditioning on the general-choice model:

```text
logit P(personal choice of i over j)
    = γ · (GeneralAppeal_i − GeneralAppeal_j)
    + δ · (PersonalMatch_i − PersonalMatch_j)
    + βX_ij
```

`PersonalMatch` is built from the captured preferences (favorite-subject coverage
in the set, accessibility-vs-chase alignment). **If δ is not distinguishable from
zero, Personal Fit does not exist as a separate construct** and must not be
shipped as one. That is a real possible outcome of this study and the design must
be able to return it.

---

## 5. Power analysis

**No single required sample size is asserted here.** The answer depends on the
effect size, the within-user correlation, and the number of choices per user —
all unknown until piloted. What is provided instead is a simulation-based power
script that makes those assumptions explicit and lets them be varied:

```text
backend/scripts/simulate_collector_choice_power.py
```

Parameterized by:

| Parameter | Meaning |
|---|---|
| `--odds-ratio` | Effect size per 1-SD difference in the predictor |
| `--users` | Number of participants |
| `--choices-per-user` | Choices each participant makes, per decision type |
| `--pairs` | Number of distinct product pairs in the design |
| `--within-user-correlation` | Intra-class correlation of a user's choices |
| `--power` | Desired power (default 0.80) |
| `--alpha` | Significance level (default 0.05) |
| `--simulations` | Monte Carlo replications |

It simulates choices under a Bradley-Terry data-generating process with a
user-level random intercept, fits the clustered model, and reports achieved power
across a grid — so the sample size is *derived from stated assumptions* rather
than quoted as a number whose provenance nobody can check.

**Why within-user correlation dominates.** 50 users × 20 choices is not 1,000
independent observations. At an ICC of 0.3 the effective sample size is closer to
150. A power calculation that ignores clustering will understate the required
sample by roughly a factor of three, which is the most common way studies like
this end up underpowered.

---

## 6. Honest limitations, stated in advance

1. **Stated preference is not revealed preference.** Nobody spends money here.
   The general-opening question is partly a guess about *other* collectors, which
   is what makes it the right question for a population-level metric and also
   makes it a judgement rather than a behaviour.
2. **Self-selected respondents.** Users reachable through this product skew
   toward value-focused collectors, which is precisely the population most likely
   to answer the appeal questions financially.
3. **22 sets.** The set-level latent parameters rest on the same small cohort as
   every other result in this programme.
4. **Prices move.** A pair shown in January and April is not the same pair. The
   timestamp and displayed prices exist so this is measurable.
5. **This validates the metric, not the weight — except through the combined
   model.** The 80/20 split is a product decision about what Overall RIP should
   *mean*, and evidence constrains it without determining it.
