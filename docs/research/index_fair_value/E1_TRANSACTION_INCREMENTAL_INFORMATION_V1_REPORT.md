# E1 Transaction Incremental Information V1

Date: 2026-09-30

Decision scope: cross-sectional research only. No composite liquidity score, no Fair
Value refit, and no canonical-price mutation.

Preregistration commit: `c642e5bc992f924c6bd6c7af88f011d59917a6e7`

## Coverage

Core Panel V1:
- 207 / 207 cards joined to current Collector Appeal.
- 207 / 207 cards joined to current canonical market price.
- All current prices are captured on 2026-09-30.
- 206 / 207 cards have modeled pull probability.
- 22 sets; all 22 are distinct root groups, so set-grouped and root-set-grouped
  sensitivity are identical for this panel.
- Current Collector Appeal authority:
  `pokemon_collector_appeal_v7_expanded_price_blind_v1`,
  run `e282f26e-2136-4105-b0a3-f0974c4d9d70`, as-of 2026-09-11.

The primary estimator uses within-set demeaning plus partial correlation controlling
Collector Appeal and modeled pull probability. The secondary estimator controls
Collector Appeal but omits pull probability.

## Primary results

| Primitive | Primary partial r | Partial r² | LOO range | LOO sign | Decision |
|---|---:|---:|---:|---:|---|
| Graded share / 180d | +0.7473 | 55.85% | +0.7226 to +0.7665 | 100% | SUPPORTED |
| Relative IQR / 180d | -0.4878 | 23.79% | -0.5394 to -0.4486 | 100% | SUPPORTED |
| Relative MAD / 180d | -0.4660 | 21.72% | -0.5327 to -0.4199 | 100% | DIAGNOSTIC_ONLY |
| log raw sales / 30d | +0.4042 | 16.34% | +0.3712 to +0.4311 | 100% | SUPPORTED |
| log raw sales / 90d | +0.3879 | 15.05% | +0.3403 to +0.4228 | 100% | DIAGNOSTIC_ONLY |
| log raw sales / 180d | +0.3615 | 13.07% | +0.3145 to +0.3947 | 100% | DIAGNOSTIC_ONLY |
| Transaction-day frequency / 180d | +0.2890 | 8.35% | +0.2537 to +0.3472 | 100% | DIAGNOSTIC_ONLY |
| log median gap between sale days | -0.2523 | 6.37% | -0.2866 to -0.1937 | 100% | DIAGNOSTIC_ONLY |
| Exact-attribution share / 180d | +0.0688 | 0.47% | +0.0375 to +0.1034 | 100% | NOT_SUPPORTED |
| log recency days | +0.0124 | 0.02% | -0.0158 to +0.0578 | 81.82% | NOT_SUPPORTED |

The secondary specification is directionally consistent for the supported
primitives:
- graded share: +0.7956
- relative IQR: -0.6891
- raw sales / 30d: +0.6383

## Interpretation

### 1. True completed-sale turnover is not just Collector Appeal

The 30-day raw completed-sale count remains positively associated with current
price *within the same set* after controlling Collector Appeal and modeled pull
probability. The primary partial correlation is +0.4042 and every leave-one-set-out
estimate stays positive.

This supports a real Market Turnover primitive. It does not prove that turnover
causes price or predicts a later return.

The 90d and 180d windows tell essentially the same story and are highly redundant:
- 90d vs 180d within-set correlation: +0.9731
- 30d vs 90d: +0.8651
- 30d vs 180d: +0.8589

Therefore 30d is retained as the primary count-based turnover primitive; 90d and
180d remain useful diagnostics/history-depth fields rather than separate signals.

### 2. Relative transaction dispersion is independently informative

Relative IQR has a strong negative controlled relationship with price
(`r=-0.4878`). Relative MAD gives almost the same result
(`r=-0.4660`) and the two are highly redundant (`r=+0.8292`).

The parsimonious research primitive is therefore relative IQR. Relative MAD stays
as a robustness diagnostic.

This should be interpreted as transaction-price concentration / signal quality,
not as "low dispersion is always good." Future longitudinal work must establish
whether dispersion predicts subsequent stability.

### 3. Graded-vs-raw market mix is the strongest cross-sectional primitive

The graded share of completed sales has a very strong controlled association with
current raw-card price (`r=+0.7473`), with a narrow leave-one-set-out range.

This is a supported **market-mix** primitive, not a liquidity primitive and not a
causal value signal. High-value cards may attract more grading; the direction of
causality is not established here.

### 4. Sale cadence adds less than sale count

Transaction-day frequency and median gap both pass the overall materiality gate,
but they are strongly redundant with sale counts:
- 180d count vs transaction-day frequency: +0.8133
- 90d count vs transaction-day frequency: +0.7771
- median gap vs 90d count: -0.8537

Their price-band diagnostics are also more heterogeneous. They remain useful
cadence diagnostics but do not earn separate primary-signal status.

### 5. Exact-attribution share and simple recency do not explain current price

Exact-attribution share has only `r=+0.0688` in the primary controlled model and
changes direction in the secondary model. It is important evidence-quality
metadata, but not supported here as an incremental price-level primitive.

Recency is essentially zero in the primary model (`r=+0.0124`). Keep it as a
freshness/quality field. Any claim about recency predicting stale prices or future
moves requires longitudinal testing.

## Price-band diagnostics

The three retained primary primitives are not equally homogeneous by price band.

Raw sales / 30d:
- LT10: +0.5669
- 10_50: +0.3773
- 50_250: +0.1059
- GE250: +0.5112

Relative IQR:
- LT10: -0.2509
- 10_50: -0.2440
- 50_250: -0.2026
- GE250: -0.2529

Graded share:
- LT10: +0.5451
- 10_50: +0.4298
- 50_250: +0.5213
- GE250: +0.0943

Relative IQR is the most directionally uniform across price bands. Graded share is
much weaker in the GE250 band, which is consistent with a possible saturation
effect in expensive cards and should be investigated rather than hidden.

## Post-selection combined diagnostic

This was run only after the preregistered per-primitive decisions and is not used
to choose the primitives.

Using the three retained primary variables together after removing the same
set/Collector-Appeal/pull-probability controls:

- residual target R² explained: **62.49%**
- unique ΔR² when dropping raw sales / 30d: **3.09%**
- unique ΔR² when dropping relative IQR: **3.44%**
- unique ΔR² when dropping graded share: **27.43%**

Within-set pair correlations:
- sales30 vs graded share: +0.5646
- sales30 vs relative IQR: -0.4867
- graded share vs relative IQR: -0.6190

All three retain some unique information in this diagnostic, with graded/raw mix
the dominant unique contributor.

## Decisions

Primary retained primitives:
- **Market Turnover:** log raw completed sales / 30d — SUPPORTED
- **Transaction Quality:** relative IQR / 180d — SUPPORTED
- **Market Mix:** graded share / 180d — SUPPORTED

Diagnostics retained but not promoted as separate signals:
- raw sales / 90d
- raw sales / 180d
- transaction-day frequency / 180d
- median gap between sale days
- relative MAD / 180d

Not supported as incremental current-price primitives:
- exact-attribution share
- simple sale recency

## What this does not answer

This study does not establish:
- future-return prediction;
- turnover persistence;
- inventory absorption;
- replenishment;
- listing disappearance;
- active-supply scarcity;
- causal effects;
- a composite Market State score.

Those questions require the Bucket C daily active-supply panel and future
point-in-time observations.

## Next research step

Continue collecting Bucket C. Once enough consecutive panel dates exist, combine:
- supported true completed-sale turnover,
- active offered-supply depth,
- seller depth/concentration,
- replenishment/disappearance under proven observation continuity.

Then test absorption and availability separately before considering any higher
level Market Scarcity/Market State construct.

Current status:
`E1_TRANSACTION_INCREMENTAL_INFORMATION_SUPPORTED_WITH_REDUCED_PRIMITIVE_SET`
