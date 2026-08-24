# Recurring private Budget Ranking publication

This capability is private infrastructure. It does not add a public API,
frontend reader, public snapshot field, or grants for `anon`/`authenticated`.

## Daily trigger and authority

`infra/local/run_simulations.sh` invokes the wrapper after
`run_daily_opening_publication.py` and both final read-only audits pass, before
the single success Slack notification. There is no separate scheduler or
polling loop.

The automatic resolver re-evaluates opening freshness for the promoted market
date, extracts its exact `set_id -> calculation_run_id` mapping, and considers
only sealed-product rows from those runs. A candidate must have one price date,
unique products, positive prices with provenance, required artifacts and
rankability, the frozen V4/V10/V5 versions, and only V1-validated families.
Product count is dynamic. Newer partial or mixed evidence never replaces the
last-known-good snapshot.

## Status and retry behavior

| Status | Exit | Meaning |
|---|---:|---|
| `PUBLISHED` | 0 | Commit succeeded, or dry-run found a publishable authority. |
| `NO_NEW_AUTHORITY` | 0 | Exact authority equals latest; builder and RPC are skipped. |
| `UPSTREAM_NOT_READY` | 3 | New/coordinated evidence is incomplete; retry on the next normal workflow invocation. |
| `METHOD_VERSION_MISMATCH` | 1 | Frozen method/model identity drifted; manual review required. |
| `HEALTH_GATE_BLOCKED` | 1 | Authority or generated ranking failed a hard gate. |
| `PUBLICATION_FAILED` | 1 | Atomic RPC failed. |
| `POST_PUBLISH_VERIFICATION_FAILED` | 1 | Read-back differed; investigate without racing or restoring latest automatically. |
| `STALE` | 1 | Two expected daily cycles passed after 12:30 America/Phoenix while newer raw authority exists. |

Stability with no newer raw price evidence is `NO_NEW_AUTHORITY`, not stale.
All snapshot history is retained.

## Gates and diagnostics

Before publication the wrapper verifies all seven canonical cohorts, unique
identities, contiguous primary and financial ranks, dynamic cohort sizes,
required scores/recovery/tier, whole-unit quantity, both capital equations,
Full Market N/N coverage and next-$50 anchor, metadata placement, source runs,
families, and frozen versions. The RPC independently validates persisted row
count, ranks, price authority, Full Market metadata/count, required values and
capital reconciliation before advancing latest; an exception rolls back the
whole PostgreSQL transaction.

Capital-utilization/rank Spearman above `0.25` and financial-dominance inversion
rate above `1%` are warning-only. They request a periodic research audit and do
not turn the heavy methodology sweep into daily work.

## Commands and recovery

Normal automation:

```text
python -m backend.scripts.publish_budget_product_rankings_if_ready --commit
```

Safe observation:

```text
python -m backend.scripts.publish_budget_product_rankings_if_ready --dry-run
```

Controlled recovery may add `--force-price-as-of YYYY-MM-DD`. It only selects a
date within the exact coordinated runs and bypasses none of the gates. The
original canonical builder remains available for operator diagnostics with
`--price-as-of`; its scoring and allocation formulas are unchanged.
