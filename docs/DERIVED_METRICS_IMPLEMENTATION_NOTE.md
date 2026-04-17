# Derived Metrics Layer — Implementation Note

## What derived metrics are

Derived metrics are product-facing interpretations of Monte Carlo simulation
output.  They answer questions like:

- What is the probability I profit by opening this product?
- How bad is the downside when I lose?
- How dependent is this set on a tiny number of chase cards?
- What is the risk profile at the pack and box level?
- How many packs does it typically take to hit a target card?
- How should all of this be summarised into a single, explainable score?

They are **not** simulation outputs in their own right.  They are computed from
the distribution of values that the simulation engine already produces.

---

## Why they belong in a separate layer

The codebase already has a clean separation:

```
config truth           (constants/, set configs)
        ↓
calculation layer      (packCalcsRefractored/, evrEtb.py)
        ↓
simulation engine      (monteCarloSimV2.py, evrSimulator.py)
        ↓
derived metrics layer  (calculations/evr/derived_metrics.py)  ← this layer
        ↓
persistence / UI       (db/, frontend/)
```

Burying product metrics inside the simulation engine or validation modules
would:

- make the simulation engine harder to evolve independently
- conflate empirical verification (validation) with product interpretation
- make the scoring logic impossible to audit or A/B test

Keeping derived metrics in their own module means:

- the simulation engine can be improved without touching the product layer
- score logic and metric definitions are in one auditable place
- persistence and UI layers always receive the same stable interface

---

## Metric definitions

### `prob_profit`

```
prob_profit = count(value >= pack_cost) / n_runs
```

Fraction of simulated packs whose total value meets or exceeds the pack cost.
Direct count, no smoothing.

### `prob_big_hit_fixed`

```
prob_big_hit_fixed = count(value >= big_hit_threshold_fixed) / n_runs
```

Fraction of packs exceeding an absolute dollar threshold.

### `prob_big_hit_dynamic`

Same count formula but with a threshold derived at call time.  Two modes:

| mode | threshold |
|---|---|
| `cost_multiple` | `param × pack_cost` (e.g. 5× for "5× your money back") |
| `percentile` | the `param`-th percentile of the value distribution |

Both the threshold used and the resulting probability are always returned.

---

### `expected_loss_given_loss`

```
expected_loss_given_loss = mean(pack_cost − value)   for runs where value < pack_cost
```

Average magnitude of loss **when a loss occurs**.  Answers: "when I lose, how
much do I typically lose?"

### `median_loss_given_loss`

Median of `(pack_cost − value)` over losing runs.

### `expected_loss_unconditional`

```
expected_loss_unconditional = mean(max(pack_cost − value, 0))   over all runs
```

The average downside burden **across all runs**, including runs where there was
no loss (contributing 0).  Always ≤ expected_loss_given_loss × (1 − prob_profit).

These two are distinct and must **not** be conflated.

---

### `coefficient_of_variation` (CV)

```
CV = std_dev / mean_value   (None if mean_value ≤ 0)
```

Normalised volatility.  Allows comparison across sets with different absolute
price levels.  A higher CV means the outcome is more unpredictable relative
to the average return.

---

### Chase dependency shares

Given a mapping `card_ev_contributions: {card_id → ev_contribution}`:

```
top1_ev_share = top1_contribution / total_ev
top3_ev_share = sum(top 3 contributions) / total_ev
top5_ev_share = sum(top 5 contributions) / total_ev
```

These measure how concentrated the value is in a small number of cards.
A `top1_ev_share` of 0.8 means 80 % of the average pack EV is driven by one
card — which is a strong signal of binary risk for that set.

If `total_ev ≤ 0`, all shares are returned as `None` (not `0`) to make the
distinction between "zero EV" and "not computed" explicit.

---

### Box / session profit probability

```
session_cost  = pack_cost × n_packs
prob_box_profit = count(session_total_value >= session_cost) / n_runs
```

The session total is the **sum of n_packs independently simulated packs**.
See section below for why sessions are simulated directly.

---

### `prob_no_chase_hit_in_box`

Fraction of simulated sessions where the caller-supplied `chase_hit_fn`
returned `False` for every pack in that session.  The definition of "chase
hit" is left to the caller to keep the metric unambiguous.

---

### `expected_packs_to_hit` / `median_packs_to_hit`

Each run opens packs one at a time using the same simulator callable until the
caller-supplied `is_hit_fn` returns `True`.  The recorded value for that run
is the pack count at which the hit landed.

```
expected_packs_to_hit = mean(packs_per_run)
median_packs_to_hit   = median(packs_per_run)
```

If the target is impossible under the current model, the function raises
`ValueError` before running the full simulation (fail-fast verification).

---

### inDex Score v1

A bounded, explainable 0–100 product score.

#### Ingredients

| component | direction | derivation |
|---|---|---|
| `prob_profit_component` | higher = better | `clamp(prob_profit, 0, 1)` |
| `stability_component` | higher = better | `1 − clamp(CV / CV_MAX, 0, 1)` where `CV_MAX = 5.0` |
| `diversification_component` | higher = better | `1 − clamp(top5_ev_share, 0, 1)` |

#### Formula

```
score_raw = w1 × prob_profit_component
          + w2 × stability_component
          + w3 × diversification_component

ind_ex_score_v1 = round(100 × score_raw, 2)
```

Default weights: `w1 = 0.40`, `w2 = 0.30`, `w3 = 0.30`.

#### Fallbacks for missing inputs

| missing input | fallback value | rationale |
|---|---|---|
| CV = None | stability = 0.5 | Neutral; neither rewarded nor penalised |
| top5_ev_share = None | diversification = 0.5 | Neutral |

Fallbacks are surfaced in the returned breakdown dict — they are never hidden.

#### Why CV is clamped

Raw `1/CV` would be unbounded.  Instead, CV is normalised against `CV_MAX = 5.0`
and clamped to [0, 1] before weighting.  This means:

- A pack with CV = 0 gets full stability credit (1.0).
- A pack with CV ≥ 5 gets zero stability credit (0.0).
- The score **cannot blow up** for exotic distributions.

#### Versioning

The score is explicitly versioned (`score_version = "v1"`).  Future formula
changes must use a new version tag.  Old scores computed with v1 remain
comparable to each other.

---

## Why session outcomes are simulated directly (not approximated)

It would be technically possible to estimate box-level metrics from pack-level
summary statistics (e.g. multiply expected pack value by 36 for a booster box).
This is not done for two reasons:

1. **Variance is not additive in the presence of fat tails and special packs.**
   Approximating box variance from pack variance systematically understates
   risk when rare jackpot packs exist.

2. **`prob_box_profit` cannot be computed correctly from a mean/std summary**
   without distributional assumptions.  Those assumptions would be wrong for
   the highly skewed Pokémon pack value distributions modelled here.

Sessions are therefore simulated by calling the pack simulator `n_packs` times
per session run.  The pack simulator callable is passed into `simulate_session`
rather than constructed inside it — the derived metrics layer never instantiates
a pack model directly.

---

## Persistence shape

See `PackSimulationSummary` in `derived_metrics.py` for the typed schema.

The helper `build_pack_simulation_summary` populates it from the output of
`compute_all_derived_metrics`.

Suggested table name: `pack_simulation_summaries`

All optional fields use `NULL` / `None` to distinguish "not computed" from zero.

---

## Output grouping for UI consumption

The `compute_all_derived_metrics` output is structured to cleanly feed three
UI buckets without client-side data wrangling:

| UI bucket | Keys to surface |
|---|---|
| **Should I Open This?** | `prob_profit`, `expected_loss_unconditional`, `prob_box_profit` |
| **What Am I Chasing?** | `top1_ev_share`, `top5_ev_share`, `expected_packs_to_hit` |
| **Risk Profile** | `coefficient_of_variation`, percentile summary (`p05`–`p99`) |

The score (`ind_ex_score_v1`) and its component breakdown surface across all
three buckets as a top-level summary.
