# Historical RIP Phase 2

The existing Windows Task Scheduler chain remains the sole scheduler:

`run_simulations_task.bat` -> `run_simulations.sh` ->
`run_daily_opening_publication.py` -> simulation freshness -> missing simulations ->
Chase Accessibility -> sealed-product Financial/Overall finalization -> coordinated
public snapshots -> Chase/publication audits -> `operationalize_historical_rip.py`.

The final step distinguishes a daily observation from a source refresh. When all
five dynamic sources are fresh, it makes zero provider calls and idempotently
appends the currently published V7 authority for the promoted market date. When
any source is due it returns `SOURCE_REFRESH_REQUIRED` without appending and the
daily command fails closed. The repository's V7 builder still pins the frozen
September source IDs, so unattended stale-source capture/rebuild/promotion is
not represented as complete in this phase.

## Materialized authority

`pokemon_rip_temporal_history` is service-role-only, append-only, independently
versioned, and keyed by domain/entity/date/version/fingerprint. It stores model
or calculation run identity, model and cohort fingerprints, quality and
reconstruction states, and JSON source lineage.

- Collector V7: 2026-09-11, 128 set rows; 22 READY, 106 UNAVAILABLE.
- Financial V4: 2026-08-17 through 2026-09-10, 14 dates, 2,178 exact product/run
  rows, 22 sets overall. Missing calendar dates are Aug 18-21, 23, 29-30 and
  Sep 3, 5-6, 9. Aug 31, Sep 1, Sep 2 and Sep 7 are partial cohorts; they are
  retained as exact evidence rather than falsely presented as 22-set cohorts.
- Overall V12: 2026-09-01 through 2026-09-10, 5 dates, 828 exact product/run
  rows, 22 sets overall. Its embedded authorities remain Financial V4, Chase
  Accessibility V1 and Collector V5; V7 is not substituted.

Financial price authority is `price_as_of` on each source row and equals the
historical observation date for all materialized rows, so no future-price row
was admitted.

## Chase audit

Top-chase price history contains 351,647 rows, 472 dates (2025-05-27 through
2026-09-10), 169 sets and no source date later than its snapshot date. It does
not contain date-bound card-probability or desirability/card-selection run IDs,
and the only Chase Accessibility relation is a latest snapshot. Therefore all
472 candidate dates are `CHASE_HISTORY_BLOCKED_PROBABILITY` (and would next be
blocked on desirability lineage); reconstructable dates: zero. No pilot ran.

## Research gates

- 7 observations: basic short-history diagnostics; enough to expose a weekly
  sequence, not enough for stable distributional claims.
- 30 observations: 30-day stability and momentum; one conventional monthly
  window with enough points to avoid one/two-point pseudo-volatility.
- 60 observations: 60-day durability; requires persistence beyond one month.
- 90 observations: primary Historical Quality research eligibility; supports
  separated feature and forward-target windows without reusing the same few
  observations.

The readiness check also requires at least 20 sets, a valid forward target,
same-version series, no lookahead and predictor variation. Current result:
`HISTORICAL_QUALITY_RESEARCH_NOT_READY`.
