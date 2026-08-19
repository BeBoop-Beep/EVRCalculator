# Financial RIP V4 — Model Decision Record

**Decision date:** 2026-08-18
**Status:** Approved. Implemented in code. **Not yet canonical.**
**Supersedes for new scoring:** nothing — V4 is an additional model version, not a
replacement of V3 in place.

---

## 1. The decision

### 1.1 Realistic Upside

Realistic Upside is the **canonical normalized P95 threshold-to-cost ratio, alone**.

```
V3   realistic_upside = 0.40 * p95_threshold_ratio + 0.60 * realistic_tail_mean_ratio
V4   realistic_upside = 1.00 * p95_threshold_ratio
```

The P95–P99 conditional-mean contribution is **removed from the score**. The metric
itself (`realistic_tail_mean_ratio` / `realisticTailMeanValue`) continues to be
computed and disclosed in the component's raw block; it simply carries zero weight,
exactly as `hard_loss_probability` has always been disclosed-but-unweighted inside
Loss Resilience.

### 1.2 Weights

| Component | Weight |
|---|---|
| True Win Frequency | 25% |
| Typical Retention | 20% |
| Loss Resilience | 15% |
| **Realistic Upside** | **25%** |
| Jackpot Upside | 10% |
| Base Economic Efficiency | 5% |

Numerically identical to V3. Realistic Upside **retains its full 25% influence**.

### 1.3 Everything else

Unchanged from Financial RIP V3: the P95 normalization anchors, the P95
interpolation, True Win Frequency, Typical Retention, Loss Resilience, Jackpot
Upside, Base Economic Efficiency and their sub-weights, the empirical rank-exact
tail contract, the minimum simulation count, and the status vocabulary.

Because no anchor or tail rule moved, V4 deliberately stamps the **V3**
`normalizationVersion` and `tailContractVersion`. A different string would assert a
change that did not happen. `scoreVersion` is what separates a V4 row from a V3 row.

### 1.4 Version identity

```
financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5
financial_rip_v4_config_v1
```

---

## 2. Why P95-only, and why 25% was retained over 20%

The audit found the V3 Realistic Upside definition was the primary source of a small
number of questionable matched-capital decisions.

Measured on the 2026-08-17 development authority, the P95-only definition at 25%
influence:

- reduced Layer-1 matched-capital inversions from **15 to 8** across **5,796**
  comparisons at the 5% tolerance (**3** at the 2% tolerance);
- reduced Realistic/Jackpot correlation from approximately **0.790 to 0.530**;
- preserved approximately **101.1%** of measured reachable-upside positive-control
  separation;
- preserved all tested budget-band top strategies (**0** top-strategy changes);
- produced **no Layer-2, Layer-3 or Layer-4 Pareto defects**;
- remained monotonic under tested price changes;
- was at least as stable as the V3 estimator under persisted-vector subsampling;
- preserved pack/set ranking structure closely (Spearman ≈ **0.9898**, maximum rank
  movement **2**, no set moving ≥3 ranks).

### The rejected 20% candidate

A 20% Realistic Upside candidate reduced Layer-1 inversions further, from 8 to 4,
but reduced measured reachable-upside separation to approximately **77.9%**. The
independent behavioral benchmark did not establish a material advantage for 20%
over 25%.

Because meaningful attainable upside is a central part of the utility purchased by a
voluntary Pokémon opener, the additional suppression of Realistic Upside was **not**
considered justified by four additional inversion removals out of 5,796
matched-capital comparisons.

---

## 3. What Financial RIP is

Financial RIP is not an investment-return optimizer and is not an entertainment
score. It measures:

> The quality of the financial gamble attached to money a user has already chosen to
> spend opening Pokémon.

The construct deliberately values expected financial efficiency, ordinary/typical
outcomes, probability of beating cost, downside severity, realistically attainable
meaningful upside, and extreme jackpot upside.

Realistic Upside answers: *if the user gets a genuinely good, approximately top-5%
opening, how meaningful is that result relative to the money committed?* Jackpot
Upside remains a separate measure of the extreme dream outcome.

### Layer separation

Three constructs remain intentionally separate, and none is folded into another:

1. **Entertainment Cost** — value/cost of the opening experience itself.
2. **Financial RIP** — quality of the financial gamble.
3. **Collector Appeal** — desirability of the collectible outcomes.

Collector Appeal and Entertainment Cost are **not** inputs to Financial RIP.

---

## 4. V4 is a new model version

Financial RIP **V3** and Overall RIP **V9** must remain available for historical data
and published-state reproducibility. V4 is a new model version, **not an in-place
mutation of V3**.

V3 is preserved behaviorally, not merely nominally: a SHA-256 digest over eight
complete V3 payloads (four distribution shapes × two pack costs) is pinned by
`backend/tests/unit/calculations/test_financial_rip_v3_behavioural_freeze.py`. Any
change to any published V3 leaf moves that digest and fails the build.

### Overall RIP V10

```
overall_rip_v10_90_financial_v4_10_collector_appeal_v5
= 0.90 * Financial RIP V4 + 0.10 * Collector Appeal V5
```

Collector Appeal V5 is unchanged. The 90/10 composition is unchanged. Only the
declared financial input moves (V3 → V4).

V10 is a new version rather than a repoint of V9 for the same reason V8 and V9 were
new versions: **the identifier names its inputs, not just the ratio.** The V9 string
asserts a Financial-V3-backed composition, and that assertion is true of every row
ever written under it. Repointing V9 at V4 would make the string false for new rows
while leaving old rows unmarked, so one version would mean two different things
depending on write date.

---

## 5. Temporal validation limitation

**The V4 decision does NOT have independent temporal validation.**

The 2026-08-17 published state was the development authority. 2026-08-18 could not
become an independent published validation state because its scrape cohort remained
incomplete.

This limitation is **explicitly accepted**.

Future complete/published market states must be treated as **prospective
out-of-sample validation**.

The absence of temporal validation must not be rewritten historically as though it
occurred. The condition is recorded machine-readably as
`temporalValidationStatus: "none_independent_temporal_validation_at_promotion"` in
the V4 weights disclosure payload, and asserted by test.

---

## 6. Cross-format implication

Financial RIP V4 natural-unit scores are **NOT** automatically cross-format
comparable.

The prior audit established that packs, bundles, ETBs, booster boxes and other sealed
products must be compared using approximately equal committed capital. V4 does not
change this: the pack-count dependence is a property of scoring a product-sized
outcome vector against a product-sized cost, not of the Realistic Upside definition
V4 revises.

Therefore:

```
SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE = False
```

Future cross-format comparison must use the validated equal-spend strategy framework.

**No universal natural-unit #1–#137 Product RIP leaderboard is authorized by this
decision.**

---

## 7. Next construct

After V4 implementation, the next product construct is:

> With approximately $X to spend, which sealed opening strategy provides the
> strongest Financial RIP profile?

The comparison must use whole retail units, actual market prices, actual committed
capital, leftover-budget disclosure, empirical distribution aggregation, canonical
guaranteed-value composition, and matched-capital tolerance.

---

## 8. Implementation and verification references

| Concern | Location |
|---|---|
| V4 configuration | `backend/calculations/evr/financial_rip_v4_config.py` |
| V4 model binding | `backend/calculations/evr/financial_rip_v4.py` |
| Shared engine + V3 binding | `backend/calculations/evr/financial_rip_v3.py` |
| Overall RIP V10 | `backend/desirability/weighted_rip.py` |
| Version registries / cutover switch | `backend/desirability/scoring_config.py` |
| Public contract V10 | `backend/desirability/public_rip_contract_v10.py` |
| Research parity verifier | `backend/scripts/research_financial_rip_v4_parity.py` |
| Frozen research artifact | `research_financial_rip_final_validation_20260818.json` |
| V3 behavioural freeze | `backend/tests/unit/calculations/test_financial_rip_v3_behavioural_freeze.py` |

Research-candidate parity is proven as an **identity**, not a tolerance: the frozen
`P95_ONLY_25` candidate scored the V3 component vector under the V3 weights with
Realistic Upside replaced by `normalize_metric("p95_threshold_ratio", …)`, which is
exactly what production V4 computes. Residual differences are 4-decimal publication
rounding only (derived budget 1e-4).

---

## 9. Canonical status

As of this record, the canonical selection remains:

```
CANONICAL_FINANCIAL_RIP_VERSION  -> financial_rip_v3_outcome_profile_25_20_15_25_10_5
CANONICAL_OVERALL_RIP_VERSION    -> overall_rip_v9_90_financial_v3_10_collector_appeal_v5
CANONICAL_COLLECTOR_APPEAL       -> collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2
```

Promotion to V4/V10 is a **coordinated publication event**, not a constant edit. It
requires, in order: version-aware sealed-product persistence, a V4/V10 ranking path,
a publish-RPC migration repointing the canonical identity assertions, V4/V10
authority rows, and only then the canonical constants advancing together with a
snapshot rebuild. Canonical readers must never point at a model for which
authoritative rows do not exist.
