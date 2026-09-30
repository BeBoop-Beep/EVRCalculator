# E1 Transaction Incremental Information V1 — preregistration

Date: 2026-09-30

## Status and scope

This is a cross-sectional research study on the frozen 207-card Core Panel V1.
It does not define a composite liquidity/market-state score, does not refit Fair
Value, and does not mutate canonical pricing.

Frozen transaction primitive source:
- docs/research/index_fair_value/core_panel_transaction_primitives_v1.json
- observation date: 2026-09-30
- panel fingerprint: 9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f

## Research question

Do transaction-turnover and transaction-quality primitives contain cross-sectional
information beyond card Collector Appeal, acquisition difficulty, and set-level
effects?

This study deliberately separates:
1. contemporaneous cross-sectional association, which can be studied now;
2. future predictive information, which cannot be claimed from one snapshot.

## Authorities / joins

- identity: pokemon_canonical_cards.id
- current canonical price: pokemon_canonical_card_market_prices_latest, captured
  on the observation date
- Collector Appeal: current pokemon_collector_appeal_current pointer joined to
  pokemon_card_collector_appeal_rankings
- acquisition difficulty: modeled_pull_probability where available
- structural grouping: sets.id; era is absorbed by set fixed effects
- transaction primitives: frozen Core Panel JSON artifact only

No condition-normalized sold-price fields are used. D3/V4 is independent.

## Primary cross-sectional target

`log(current canonical market price)`.

Because this target is contemporaneous, any association is descriptive /
incremental-information evidence, not a claim of causal value or future returns.

## Candidate primitives

Turnover:
- log1p(raw_sales_30)
- log1p(raw_sales_90)
- log1p(raw_sales_180)
- raw_transaction_day_frequency_180
- log1p(raw_recency_days)
- log1p(median_gap_days)

Transaction quality / market mix:
- raw_exact_share_180
- graded_share_180
- relative MAD = raw_mad_180 / raw_median_180
- relative IQR = (raw_p75_180 - raw_p25_180) / raw_median_180

The relative dispersion ratios are undefined when the raw median is non-positive;
such rows are excluded for those primitive-specific tests only.

## Controls and estimator

Primary estimator is a within-set partial correlation:

1. demean target, candidate primitive, Collector Appeal and modeled pull
   probability within each set;
2. compute the partial Pearson correlation between target and primitive,
   controlling for Collector Appeal and modeled pull probability.

This absorbs all set-constant factors, including era and set age, without
pretending held-out sets share a fixed-effect coefficient.

A secondary control specification omits modeled pull probability so the one
missing pull-probability row does not determine the result.

## Stability diagnostics

For every candidate primitive:
- leave-one-set-out partial correlation;
- sign-consistency across the 22 leave-one-set-out estimates;
- min/max LOO estimate;
- price-band within-set partial-correlation diagnostics where sample size permits;
- pairwise correlations among transaction primitives to identify redundancy.

No p-value threshold alone determines support.

## Decision rubric

SUPPORTED:
- material primary absolute partial correlation (predeclared |r| >= 0.20);
- same sign in >= 90% of leave-one-set-out estimates;
- no single set changes the conclusion across the |r|=0.20 materiality boundary
  by more than 0.10;
- secondary control specification is directionally consistent.

DIAGNOSTIC_ONLY:
- informative descriptive pattern, but materiality/stability gate is not met; or
- primitive is strongly redundant with another supported primitive and is better
  retained as a diagnostic.

NOT_SUPPORTED:
- primary |r| < 0.10 and LOO estimates remain near zero / unstable without a
  coherent subgroup pattern.

NEEDS_MORE_HISTORY:
- the primitive's intended claim is fundamentally longitudinal (for example
  persistence, absorption, replenishment or future returns), so this snapshot
  cannot establish it even if contemporaneous association exists.

Values with 0.10 <= |r| < 0.20 default to DIAGNOSTIC_ONLY unless a strong,
pre-specified stability pattern justifies retaining them for later longitudinal
testing.

## Interpretation boundary

This study can say that a primitive contains contemporaneous information not
obviously reducible to Collector Appeal, pull probability and set membership.
It cannot say that turnover causes price, predicts future excess returns, or
constitutes a validated liquidity/scarcity score.

Those stronger questions require future point-in-time observations and the
Bucket C active-supply panel.
