# inDex Fair Value forward-validation preregistration

## Decision and authority

This document freezes the prospective experiment before sufficient future observations
exist. Its status is **PREREGISTERED, NOT EVALUATED**. It does not fit, select, or approve
a Fair Value model.

The current authority remains **FAIR_VALUE_HISTORY_SIGNAL_PROMISING**. The frozen F1
cohort contains 4,349 cards from 22 canonical root sets. Direct selected-card history
runs approximately from 2026-06-27 through 2026-09-12, with 73 median prior observations.
The controlled PLUS_HISTORY diagnostic achieved log R² 0.9980, dollar R² 0.9996, MAE
$0.15, RMSE $0.94, MdAPE 2.83%, 98.18% within ±30%, Spearman 0.9953, and positive
dollar R² in 7/7 price bands.

Those numbers are context, not validation. Historical features and targets come from
successive snapshots of the same TCGplayer Market Price aggregate. There are no retained
individual sale rows, transaction counts, quantities, sale timestamps, or direct
liquidity measures. The result can therefore be dominated by persistence. TCGplayer
Market Price remains a transaction-derived aggregate; eBay active-listing asks are not
price authority.

## Persistence baselines

All windows are calendar-day windows ending strictly before prediction origin `T`.
They use observed daily points only.

| ID | Frozen definition | Availability |
|---|---|---|
| P0 | Most recent prior canonical TCGplayer Market Price | Carry for at most three calendar days; otherwise unavailable |
| P1 | Median over `[T-7 days, T)` | At least four observed days |
| P2 | Median over `[T-30 days, T)` | At least 14 observed days |
| P3 | Unweighted OLS of log price on elapsed calendar days over `[T-30 days, T)`, extrapolated exactly 1, 7, or 30 days | At least 14 observed days spanning at least 14 calendar days; no slope cap and no fallback |

MODEL 1's baseline is selected once, before final predictions, using only expanding-window
rolling-origin validation dates earlier than the final cutoff. The lexicographic order is
lowest global MdAPE, lowest RMSE, most price bands with positive dollar R², then simpler
baseline P0, P1, P2, P3. Final-holdout outcomes may not participate.

## Frozen feature families

Every feature must be assigned to exactly one registered family before the cutoff.

- **A — level/persistence:** prior absolute price; 7/30-day mean and median; fixed
  seven-day-half-life EWMA level.
- **B — dynamic history:** fixed-window log returns, velocity, volatility, drawdown,
  dimensionless distance from rolling median, unchanged-state persistence, capture and
  state-change staleness, target-excluded relative return versus set/era/Treatment peers,
  and fixed recent-versus-long-term regime indicators. B may not contain absolute lagged
  price or a transform from which it can be recovered.
- **C — structural:** Collector Appeal, Pull Scarcity, Treatment, lifecycle, era/set
  structure, and other already-frozen leakage-safe price-blind inputs.
- **D — market anchor:** existing frozen, defensible F2R target-blind peer/market-anchor
  inputs.

No feature may be silently moved or mixed between families after holdout outcomes exist.

## Frozen future comparisons

The learned comparison models use fixed Ridge `alpha=1.0` on log target. Median
imputation, missing indicators, and standardization are fit inside each training fold.
There is no hyperparameter search and no high-capacity substitute.

| Model | Inputs |
|---|---|
| MODEL 0 | P0 only |
| MODEL 1 | One pre-holdout-selected baseline among P0–P3 |
| MODEL 2 | B only; absolute lagged price level excluded |
| MODEL 3 | C + B |
| MODEL 4 | C + D + B |
| MODEL 5 | C + D + A + B |

The primary comparisons are MODEL 2 against the frozen F2 structural reference, MODEL 4
against the frozen failed F2R reference, and MODEL 5 against MODEL 1. References are
reproduced without adapting them to holdout outcomes.

## Temporal leakage contract

For every origin `T`, every input must have an immutable captured/available timestamp
strictly earlier than `T`. A date-`d` daily snapshot is eligible only after ingestion
completes, so it cannot predict date `d`; the minimum embargo is one calendar day.

Forbidden inputs include same-day target-derived values, future observations, centered
windows, future backfills or rollups, target-period normalization, post-`T` revisions,
and retrospective backfills without evidence that the row was originally available
before `T`. Peer aggregates are as-of `T` and exclude the target card.

Daily gaps are not filled synthetically. P0 can carry a prior observation for no more
than three calendar days and must expose its age. Other window minima are 4 of 7, 14 of
30, 30 of 60, and 45 of 90 observed days. Fold-local median imputation plus a missingness
indicator is permitted for learned features; global or future-informed imputation is not.
Persist source identifiers, captured timestamps, window bounds, feature-registry/code
hashes, cutoff, cohort hash, and prediction hash.

## Unseen future holdout

Do not evaluate now. Readiness requires at least 90% of the frozen eligible cohort to
have 180 directly retained daily observations, and each scored card must individually
have 180. Twelve complete selected-card monthly regimes are preferred where feasible.

After readiness, choose cutoff `C` before reading any later outcome. Development uses
expanding-window rolling origins strictly before `C`, with preprocessing confined to
each origin and root-set-grouped reports. Freeze all selected models and registries at
`C`.

The final temporal holdout comprises 30 contiguous daily origins, `C+1` through `C+30`.
At each origin, create predictions only from then-available data and hash them before
reading the corresponding outcome. Wait through `C+60` for the 30-day outcomes. No
model, feature, cohort, threshold, or conclusion gate may be optimized against this
period.

The primary recurring panel contains cutoff-eligible cards/root sets already observed.
A secondary genuinely unseen-root panel is reported separately only if it has at least
three new roots and 30 cards; it cannot rescue the primary conclusion. Report prediction
coverage and missingness. Pairwise comparisons use rows available to both models, but
unavailable rows remain in coverage denominators.

## Horizons, metrics, and price bands

Report exact 1-, 7-, and 30-calendar-day horizons. For origin `T` and horizon `h`, only
the exact target-date observation `T+h` is valid; a later snapshot may not substitute.
These horizons diagnose persistence and do not redefine Fair Value as price forecasting.

For every model report log R², dollar R², MAE, RMSE, MdAPE, within ±30%, and Spearman.
Retain these target-price bands: `<$5`, `$5–<$10`, `$10–<$25`, `$25–<$50`, `$50–<$100`,
`$100–<$250`, and `$250+`. Band assignment uses the exact future target price only after
predictions are frozen. Each band reports `n`, dollar R², MAE, MdAPE, and within ±30%.
Mark inference descriptive for `n<30`; never merge bands to obscure a failure.

Every target worth at least $100 remains individually visible with card/root identity,
origin, horizon, actual, each prediction, absolute error, and percentage error.

## Preregistered materiality thresholds

Uncertainty uses a paired 2,000-replicate block bootstrap by canonical root set and
origin date with seed `20260913`, reporting 95% intervals. Decision-horizon coverage must
be at least 90% globally and 80% within every price band.

At 30 days, MODEL 5 must beat MODEL 1 on every item below:

- dollar R² gain of at least 0.05;
- MAE and RMSE reductions of at least 10% each;
- MdAPE reduction of at least 10% relatively and two percentage points absolutely;
- within-±30% gain of at least five percentage points;
- log R² and Spearman each no worse by more than 0.01; and
- the 95% bootstrap interval for paired MAE improvement excludes zero.

At seven days it must gain at least 0.02 dollar R², reduce MAE and RMSE by 5%, reduce
MdAPE by one point, and improve within-±30% by two points. One-day results are descriptive
and cannot decide the study.

Independently, at 30 days MODEL 2 versus the structural baseline and MODEL 4 versus F2R
must each gain at least 0.05 dollar R² and reduce both MAE and MdAPE by 10%. At least
two-thirds of eligible root sets must improve MODEL 5 MdAPE versus MODEL 1. MODEL 5 must
have positive dollar R² in at least 5/7 bands. Both high-value bands must have positive
dollar R², at least 10% lower MAE than MODEL 1, and `n>=30`; otherwise the high-value gate
is unresolved.

These deliberately material thresholds exceed routine provider noise/rounding, require
repair of the known F2/F2R dollar-tail weakness, and prevent excellent one-day copying
from masquerading as an independent valuation signal.

## Frozen interpretation gates

- **HISTORY_TRACKER_ONLY:** collection/coverage passes, but MODEL 5 does not clear the
  30-day persistence gate or dynamic models do not clear incremental gates. History may
  track or denoise provider price; independent Fair Value remains unproved.
- **FAIR_VALUE_HISTORY_SUPPORTED:** temporal integrity and coverage pass; all 30-day and
  supporting seven-day thresholds pass; MODEL 2 and MODEL 4 pass; root, price-band, and
  high-value consistency gates pass. This supports further Fair Value research, not an
  automatic production publication.
- **FAIR_VALUE_NEEDS_TRANSACTION_DATA:** history fails prospectively, data maturity or
  integrity is inadequate, or an expensive band remains negative, underpowered, or
  unstable, indicating that sale-level liquidity and/or independent multi-source data is
  still needed.

An integrity violation or unresolved high-value gate bars FAIR_VALUE_HISTORY_SUPPORTED.
If collection is healthy and persistence alone wins, choose HISTORY_TRACKER_ONLY;
otherwise choose FAIR_VALUE_NEEDS_TRANSACTION_DATA.

## Collection health and readiness

Status at 2026-09-12 is **HEALTHY_WITH_ONE_KNOWN_GAP**. The existing canonical daily
TCGplayer pathway already writes retained observations to
`card_variant_price_observations`; Price Storage V2 and monthly rollups are downstream
derivations. No second collector or code change is warranted.

Across 19,856 current canonical selected cards, 77 usable dates exist over 78 calendar
days; 2026-08-29 is missing. Depth is p10/median/p90 71/75/76, and zero cards have yet
reached 90, 120, or 180 observations. For frozen F1 rows before their target dates,
p10/median/p90 is 67/73/74 and zero have reached those milestones.

The future readiness report must state its as-of/latest dates and cohort fingerprint;
p10/median/p90 depth; counts and percentages at 90/120/180 days; global and per-card
gaps; complete selected-card monthly regimes; and ingestion failures, late rows, and
backfills separately. It must not mutate history.

Assuming one usable daily observation after 2026-09-12 and no further gaps, the current
all-canonical p10 implies approximate 90%-cohort milestones of **2026-10-01** (90),
**2026-10-31** (120), and **2026-12-30** (180). These are research-readiness estimates,
not promises.

The broader rollup has five monthly buckets, but selected-card direct history has only
two complete months (July and August 2026), plus partial June and September. Twelve
complete selected-card regimes are **NOT READY**; the earliest uninterrupted estimate is
**2027-07-01**, after July 2026 through June 2027 have closed.

## Separate security advisory

No database security change belongs to this study. Read-only inspection previously
observed RLS disabled on:

- `private.pokemon_card_chase_efficiency_publication_jobs`
- `private.pokemon_card_chase_efficiency_publication_rows`
- `public.pokemon_market_public_era_rollout_v1`

The public table merits a separate access/policy audit. Do not blindly enable RLS because
existing readers and writers may depend on current access.

No final Fair Value model was fit, no future holdout was inspected, no eBay asking price
was used as authority, no production code was changed, no database was written, and no
deployment or production mutation occurred.
