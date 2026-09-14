# inDex Fair Value market-history readiness

## Decision

**FAIR_VALUE_HISTORY_SIGNAL_PROMISING.** Existing card-specific TCGplayer history adds
substantial information and repairs the seven-band failure in a controlled diagnostic.
It is not mature enough to justify a final Fair Value model: the directly retained
selected-card history is about 2.5 months, no selected card has 90 daily observations,
and the strongest feature is the same provider's immediately prior Market Price.

No production authority, valuation label, recommendation, or future-price claim follows.

## Source semantics

| Source | Retained object | Scale and depth | Correct meaning |
|---|---|---|---|
| TCGplayer cards | `card_variant_price_observations` | 17,901,056 rows; 39,774 variants; 156 source dates since 2026-04-07 | Daily snapshots of a transaction-derived provider Market Price estimate; not individual sale rows |
| Canonical card latest | `pokemon_canonical_card_market_prices_latest` | 19,856 cards | Near Mint USD selection over TCGplayer variants; current projection, not history |
| Price Storage V2 | events/current/ranges | 3,105,045 change events | Derived compact state/change history; no new transaction evidence |
| Monthly card rollups | `card_variant_price_monthly_rollups` | 716,204 rows; five months | Derived open/close/average/min/max of snapshots; `observation_count` is not sales volume |
| TCGplayer sealed | `sealed_product_price_observations` | 198,129 rows; 1,729 products; 141 dates | Transaction-derived Market Price estimate for sealed products, not card transactions |
| Calculation snapshots | `calculation_price_snapshots` | 4,115 rows across 2,444 runs | Internal reproducibility copies, not an independent source |
| Graded observations | `graded_card_variant_price_observations` | one row | Unusable |
| eBay research | frozen local D1–D3 captures | no canonical production history | Active listing asks/offered supply only; matcher not validated |

The repository's older F1 text calls TCGplayer `market_price` “listing-derived.” That is
not supported by current provider provenance. TCGplayer defines Market Price as compiled
from recent completed marketplace sales. The correction is narrow: the retained value
is a **transaction-derived aggregate estimate**, not a completed-sale row. TCGplayer
`low_price`/`high_price` remain listing/reference price points.

Condition is retained by `condition_id`; Fair Value uses Near Mint USD. Variant identity
is resolved through TCGplayer product/variant identity into `card_variant_id`, followed by
canonical printing-selection rules. Language is not persisted on price observations, so
English authority depends on the configured catalog identity rather than a per-row field.

Daily writes use `(card_variant_id, condition_id, source, captured_date)` uniqueness with
latest scrape winning. Raw rows are observed snapshots, not synthetic daily fills. V2
events store first state and subsequent changes, while range/as-of readers can carry an
observed state through an authorized interval.

## History depth

For the current 19,856 canonical selected variants, usable direct Near Mint history runs
from 2026-06-27 through 2026-09-12. There are 77 usable dates across 78 calendar days;
2026-08-29 is absent.

| Depth | All current canonical cards | Frozen F1 cards before target date |
|---|---:|---:|
| cards | 19,856 | 4,349 |
| ≥7 observations | 19,784 | 4,345 |
| ≥14 | 19,760 | 4,345 |
| ≥30 | 19,442 | 4,345 |
| ≥60 | 19,202 | 4,227 |
| ≥90 | 0 | 0 |
| p10 / median / p90 | 71 / 75 / 76 | 67 / 73 / 74 |

The broader raw/event system reaches 2026-04-07 and 156 source dates, but current
canonical variant selection does not provide that depth uniformly. Only five complete
monthly rollup buckets exist.

## Supported signals

Supported now: trailing returns, velocity, snapshot-price volatility, drawdown, rolling
median distance, set-relative strength, era-relative strength, price persistence,
observation staleness, observation frequency, price-level stability, and
treatment-relative price behavior.

Partially supported: recent-versus-long-term regime (history is short) and set-relative
demand proxy (price movement exists, but transaction counts do not).

Not supported: cross-source dispersion, transaction frequency, sold quantity, true
liquidity, sale-level dispersion, auction completions, or sell-through.

Observation frequency means collector/scrape frequency. Price persistence means the
provider estimate remained unchanged. Neither is sales velocity.

## Transaction-grounded evidence

TCGplayer Market Price is transaction-grounded at the aggregate level. The current
integration does **not** expose individual completed-sale prices, sale timestamps,
transaction counts, quantities, order counts, buylist transactions, or auction
completions.

No other configured no-cost integration supplies those rows. eBay Browse supplies active
listings, while the existing Marketplace Insights audit remains Limited Release and
unverified. No HTML scraping or credential inspection was performed.

## Controlled information-gain diagnostic

The diagnostic uses all 4,349 frozen F1 rows and leaves each of 22 canonical root sets
out in turn. Both variants use one fixed ridge estimator with fold-local imputation and
standardization. BASE receives the frozen F2R `R1_local_residual_10` target-blind
prediction. PLUS_HISTORY adds prior log Market Price, fixed-window returns, volatility,
drawdown, median distance, velocity, price-change age, history span, and relative
set/era/Treatment returns. Every history input predates its row's target date.

| Metric | BASE | PLUS_HISTORY | Change |
|---|---:|---:|---:|
| OOS log R² | 0.9352 | 0.9980 | +0.0628 |
| dollar R² | 0.5204 | 0.9996 | +0.4792 |
| MAE | $4.68 | $0.15 | −$4.53 |
| RMSE | $33.09 | $0.94 | −$32.15 |
| MdAPE | 27.84% | 2.83% | −25.01 pp |
| within ±30% | 53.18% | 98.18% | +45.00 pp |
| Spearman | 0.8847 | 0.9953 | +0.1106 |

The untouched frozen F2R reference is nearly identical to controlled BASE: log R²
0.9352, dollar R² 0.5113, MAE $4.68, RMSE $33.40, MdAPE 27.71%, ±30% 53.21%, and
Spearman 0.8848.

## Price bands

| Actual-price band | n | BASE dollar R² | PLUS_HISTORY dollar R² | PLUS_HISTORY MAE |
|---|---:|---:|---:|---:|
| <$5 | 3,509 | 0.0626 | 0.9966 | $0.02 |
| $5–10 | 257 | −36.9460 | 0.9769 | $0.15 |
| $10–25 | 292 | −10.2088 | 0.9940 | $0.21 |
| $25–50 | 145 | −14.8868 | 0.9905 | $0.43 |
| $50–100 | 83 | −5.3890 | 0.9896 | $1.01 |
| $100–250 | 36 | −5.7450 | 0.9916 | $2.51 |
| $250+ | 27 | −1.0406 | 0.9985 | $8.61 |

Positive dollar-R² bands improve from **1/7 to 7/7**. In the highest band, dollar R²
improves from −1.0406 to 0.9985, MAE is $8.61, MdAPE is 1.58%, and all 27 rows are
within ±30%.

This result is deliberately not called validation. The target and lag are successive
snapshots of the same TCGplayer aggregate, so the test strongly measures short-horizon
price persistence. It demonstrates market-history information value, not independent
intrinsic value, sale-level liquidity, or forecasting power.

## Next step

Continue append-only daily retention until at least 180 observed days and preferably 12
monthly regimes. Before another model attempt, freeze a genuinely forward-time holdout.
Separate a persistence-only lag baseline from slower return/regime features so copying
yesterday's provider estimate cannot masquerade as structural Fair Value. Seek legitimate
transaction counts or completed-sale detail for liquidity and expensive-card validation.
Do not substitute eBay asks.

Production mutations: **NONE**.
