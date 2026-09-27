# RIP Benchmark V1 — backend core / Bucket 2A

## Scope

This is the additive **offline core and private read boundary**, not the complete
live source publisher or public UI cutover. It depends on the SQL in PR #388 and
is stacked on `feat/rip-benchmark-db-v1-20260926`. Do not reapply the deployed
migration. No existing runtime file, score, rank, pointer or entitlement is changed.
No task is scheduled; no API route is registered; no production publisher is enabled.

## Completed here

- Decimal-based, centered-linear/clipped **shadow candidate** with exact neutrality,
  strict direction, finite values, immutable model/benchmark identity and explicit
  versioned slope. The production-approved calibration registry is empty. This
  implements the earlier proposed transform for evaluation, not its approval.
- Complete-cohort equal-native-entity reference helper. The caller must supply the
  exact expected cohort; partial UI filters, duplicates, inherited SKU copies and
  model/date mixing are refused. This helper does not choose the production cohort.
- Canonical score/rank, benchmark availability and financial evidence remain
  independent. No recalculation of Overall from benchmarked pillar values.
- Exact `(sealed_product_id, calculation_run_id)` source resolution with a
  set-to-run mapping. Duplicate matching results fail; unrelated runs cannot win.
- Compatible V3 evidence copying, explicit era UUID mapping through the same
  snapshot's members, and product-normalization helpers. Quantiles are not averaged;
  guaranteed value is not added twice; unsupported optional values remain NULL.
- Deterministically ordered offline publisher arguments, matching PR388's caller-
  owned fields. This is NOT a production write function or semantic source certificate.
- Bounded service-role read adapter requiring a server authorization callback
  before client creation. One RPC per current/history page; no hidden retries,
  stale entity fallback, interpolation or automatic restart across revisions.
- Read-only source-metadata audit CLI and offline request-preparation CLI.

The typed read adapter is not yet attached to a FastAPI route or existing plan
capability. Its client factory must set the supplied transport timeout; a separate
request-level deadline and endpoint entitlement tests remain integration work.

## Source audit: what the handoff's warnings mean

The inspected `rip_release.py` explicitly separates **release selection** from
**daily score authority**. V12 uses `live_v12_v4_storage`; the September 10 generic
ledger selects the release but is not the daily V12 score source. V14 instead uses
the generic ledger and needs its own certified adapter. Never choose this by date
or by silently defaulting an unknown release to V12.

Read-only production inspection after the DB handoff found:

- Active release still Overall V12 / Financial V4 / embedded Collector V5.
- Standalone Collector pointer is V7, as-of September 11. Preserve this separately;
  a newer standalone model cannot be substituted into V12's weighted Overall score.
- Latest Opening Economics is September 25; Rankings still has publication market
  date September 17 and simulation source September 15.
- Published product-family data contains 138 unique products. All 138 published
  `(product, calculation run)` pairs resolve to exactly one stored result; zero
  ambiguous/missing matches. All those runs are dated September 15.
- The handoff's 276 rows / 138 duplicate products concern the separate generic
  ledger. They are not a reason to average, deduplicate or rerank the live V12 source.
- Benchmark tables were empty: 0 headers and 0 rows. This work did not write to them.

These observations are not constants in the code. The audit CLI resolves current
pointers and dates afresh. It deliberately reports `not_publish_certified`: seven
metadata reads cannot certify a full economic cohort or Collector effective interval.
The full 138-pair verification above was a separate bounded read-only SQL audit.

## Required small database follow-up for the chart

PR388's compact row projection stores `benchmark_raw_value` for the **model score**
and `modeled_return_on_spend` for the **entity's economics**. It does not store the
same-day **Pokémon-wide return-on-spend reference** required by the planned historical
"Financial return versus Pokémon average" graph. No `global` entity type exists,
and the compact read omits source manifests. Do not overload `benchmark_raw_value`
with a return percentage, average set medians, or fetch full historical source JSON
at request time to hide this gap.

A focused additive follow-up should persist/project a typed publication-level
financial-economics reference (or equivalent typed financial-row reference fields),
including reference scope/basis, same-day V3 snapshot identity, global cost/pack,
EV/pack, and return-on-spend. Its values must come from that exact V3 global scope;
`meanOutcomeRetention` and `modeledReturnOnSpend` are distinct and cannot substitute.
The history response must bind each point to its own publication/reference revision.
A real global UUID must not be fabricated just to fit `entity_type='era'`.

## Gates still open

1. Full live/offline source adapter and source certification, including current
   Rankings mismatch, exact raw-score/rank semantics, and independently proven
   Collector effective intervals. The seven-read audit is not that builder.
2. Canonical era Financial/Chase/Collector/Overall model aggregation contract.
   Identity mapping is solved separately; EV or a guessed mean is not an era model.
3. Approve reference policies and calibration(s) after a side-by-side cohort report.
   A daily centered benchmark measures relative standing, not absolute market
   improvement. Keep raw dollar/return evidence visible. Clipping can create score
   ties, so preserve canonical ranks rather than sorting rounded benchmark values.
4. Implement the chart-reference database follow-up above.
5. Add source-certified publication, idempotent bounded retries, historical-date
   certification, scheduling, actual API entitlement integration, and frontend.
6. Complete independent V5/V14 readiness/cutover work; this feature does not activate it.

## Validation / commands

Unit tests (no database credentials required):

```text
python -m pytest -q --confcutdir=backend/tests/benchmark_v1 backend/tests/benchmark_v1/test_core.py
```

Read-only source audit (normal backend service-role environment):

```text
python -m backend.scripts.run_rip_benchmark_v1 audit-sources
```

Offline schema-shaped request preparation (caller-supplied candidate, not authority proof):

```text
python -m backend.scripts.run_rip_benchmark_v1 prepare --input candidate.json
```

The workflow tests Linux and Windows on Python 3.13. A separate disposable PG17
job submits backend-generated payloads to the exact deployed migration, proving
wire-format compatibility, precision, idempotency and fail-closed dates. It has
only fixture credentials and cannot target production. All SQL is applied only
to that disposable fixture database.

Local result: **85 tests passed** on Python 3.13.5. CI and the seven-check Postgres
smoke must be recorded from actual workflow results, not assumed from local tests.
