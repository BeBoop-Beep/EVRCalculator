# Best-Open Price — Bucket 0 methodology and performance

Date: 2026-09-12  
Source commit: `f21941155724917c87eb23515c4da9f618f6bc6d` (`develop`)  
Research method: `budget_product_best_open_price_full_market_v1_research`

## Result

Bucket 0 is **blocked at the source-authority gate**. No production threshold,
threshold distribution, or runtime projection is claimed. Bucket 1 must not be
treated as sufficient to unblock publication: the exact historical set-level
Chase Accessibility input also needs to be persistently recoverable from the
source snapshot identity.

## Pinned source

* Budget snapshot: `c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`
* Market date / pinned price date: `2026-09-08`
* Cohort fingerprint: `5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`
* Full Market budget: `$1,350.00`
* Cohort: 138 SKUs, 22 sets
* Ranking method: `budget_product_ranking_v1`
* Overall authority: `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
* `ranked_under_v12_authority`: true

The mutable simulation table contains multiple same-date calculation runs for
each SKU. The harness therefore joins the published rows back to simulation
inputs using the persisted `(sealed_product_id, source_calculation_run_id)` pair,
the pinned market date, and the exact published market price. Duplicate physical
rows are accepted only when all scoring-relevant identity fields agree.

## Authority discrepancy

The exact published product/run identities reconstruct all 138 products.
However, the cohort-wide canonical Chase Accessibility resolver reports:

* requested sets: 22
* ready sets: 0
* failures: 22
* failure reason for every set: `stale_calculation_run`

The ranking snapshot stores the resulting V12 score but does not store the raw
set-level Chase Accessibility input needed to calculate a new V12 score at a
counterfactual Financial V4 value. Reading the current/latest Accessibility row
would mix calculation-run authority. Algebraically inferring a rounded input
from a published rounded composite score would create a second methodology and
could change comparator ties. Both are rejected.

## Harness contract

`backend/scripts/research_best_open_price_bucket0.py` is read-only with respect
to external systems. It:

1. requires an explicit published snapshot ID;
2. rejects non-V12 or wrong-version snapshots;
3. loads exact Full Market rows and freezes their stored budget;
4. reconstructs physical products only from their exact source run identities;
5. validates the cohort fingerprint and SKU identity set;
6. resolves Chase Accessibility once for the exact set/run map;
7. only after all gates pass, loads artifacts and times distribution building,
   V3/V4/V12 scoring, comparator work, probes, quantities, and wall clock;
8. uses exact integer-cent quantity intervals
   `floor(B_cents/(q+1))+1 .. floor(B_cents/q)`;
9. exposes `--max-quantities` as a versioned research compute guard and reports
   `unresolved_compute_guard`; it never converts the guard into a price floor.

The current pinned run stops at step 6 by design. Consequently artifact loading,
Q-distribution construction, Financial scoring, comparator timing, threshold
distribution, and largest winning quantity are **not measured**. Reporting zero
for those stages would be misleading, so they are explicitly unavailable.

## Commands and observed timings

```text
python -m backend.scripts.research_best_open_price_bucket0 \
  --snapshot-id c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1 \
  --product-limit 1 --max-quantities 1
```

The authority audit completed in approximately 5 seconds on this workstation,
then failed closed before artifact work. A prior latest-snapshot lookup took
approximately 11 seconds. These are connectivity/source-read observations, not
threshold performance measurements.

## Required authority repair before continuing

Persist or immutably bind the exact V12 set-level input used by a budget ranking
snapshot. A production-safe solution can be either:

* an immutable reference to historical Chase Accessibility rows keyed by exact
  set and calculation run, with history retained; or
* the exact raw `A_raw` value and its version/transform provenance copied into
  the budget snapshot's private source authority.

After that repair, rerun this harness on the same pinned snapshot and require
all 22 sets to resolve. Only then can Bucket 0 measure the full cohort and
determine whether an explicit compute guard is necessary.

## Stop-gate decision

Not safe to proceed to production Bucket 1–6 implementation as though Bucket 0
passed. Prepared Financial scoring remains clearly necessary—the current V3
implementation performs a stable sort for every price probe—but optimization
cannot cure the missing immutable V12 input authority.
