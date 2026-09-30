# Core Panel transaction primitives V1

Date: 2026-09-30

This artifact is descriptive research only. It defines no composite liquidity/scarcity score, performs no Fair Value fit, and does not mutate canonical pricing.

## Scope

- Core Panel: 207 frozen cards.
- Evidence: persisted PkmnPrices completed-sale transactions.
- Fixed observation date: 2026-09-30.
- Window: trailing 180 calendar days.
- Raw and graded transactions are analyzed separately.
- Raw turnover primitives: sales counts (7/30/90/180), distinct transaction days, sales/day, transaction-day frequency, recency, median gap between raw-sale days, median/IQR/MAD, exact-attribution share.
- Market-mix primitive: graded share of total completed sales.

## Cohort summary

- Cards with raw sales in 180d: **207 / 207**
- Cards with raw sales in 30d: **206 / 207**
- Cards with raw sales in 7d: **96 / 207**
- Median raw sales / 180d: **104**
- IQR raw sales / 180d: **72.5 – 158.5**
- Median raw sales/day: **0.5778**
- Median transaction-day frequency: **0.2889**
- Median days since most recent raw sale: **8**
- Median gap between distinct raw-sale days: **1 day(s)**
- Median exact-attribution share: **0.9118**
- Median graded share of completed sales: **0.4586**

## Interpretation boundary

These are primitives, not a verdict on desirability, scarcity, or Fair Value. The next research step is to test whether turnover/transaction-quality primitives add information after existing structural covariates and Collector Appeal, using grouped/forward validation where the target supports it. Active-supply interactions remain gated on the C longitudinal panel.
