# Best-Open Price V2 — Fused Full Baseline

Date: 2026-09-19

## Decision

`FUSED_FULL_BASELINE_BLOCKED_ENVIRONMENT`

Bucket 0 did **not** produce a full fused 138-product result. The first full-cohort execution attempt stopped before candidate scoring because the local execution environment could not resolve the configured Supabase hostname (`getaddrinfo failed`).

This is an execution-environment blocker, not a Best-Open parity failure.

No V2 snapshot was published. No production database write, migration, pointer update, or frontend change occurred.

## Source state at the blocked run

The blocked local research run was prepared from verified `origin/develop` tip:

`f5137823e5bdd6d6f3ebd244afa8d712c0b10d92`

The local research work was originally committed only inside the detached Best-Open worktree as:

`7f704717`

That local Git object was never pushed and therefore was not available to GitHub for a literal cherry-pick. The research runner/report are now preserved directly on `develop` so this lane no longer depends on that worktree.

## Frozen authority

The intended frozen source remains:

- Budget Ranking snapshot: `0e65fb6d-ff33-4331-99d5-d6a214ecc712`
- Market date: 2026-09-14
- Eligible Full Market cohort: 138 products
- Expected Best-Open source-authority fingerprint:
  `faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0`

The completed sequential Phase-10 artifact remains the comparison authority for the fused run.

## Research runner

`backend/scripts/run_best_open_price_v2_phase10c_fused_full.py`

The runner is read-only and:

1. loads the completed sequential Phase-10 artifact;
2. reuses the validated V2 source/cohort orchestration;
3. swaps only the dual-search implementation to the fused streaming engine;
4. runs the complete 138-product frozen cohort;
5. requires exact cent parity for all 276 thresholds:
   - 138 RIP thresholds;
   - 138 Financial thresholds;
6. also requires matching threshold quantities and benchmark identities;
7. requires canonical exactness on both axes:
   - threshold wins;
   - one-cent maximality;
   - the legal next cent does not win;
8. requires maximum shared resident quantity count <= 1;
9. requires zero score-cache evictions;
10. records wall time, peak RSS, shared scoring work, and quantity-construction diagnostics.

It also supports a database-free reference self-check:

```powershell
py -3.11 -m backend.scripts.run_best_open_price_v2_phase10c_fused_full `
  --self-check-reference
```

The original local work reported that the 276-threshold parity gate passed this self-check against the existing sequential artifact.

## Blocked execution

The attempted real full-cohort run failed while creating/using the Supabase client, before any product was scored.

Observed failure class:

`socket.gaierror / getaddrinfo failed`

Therefore this run produced:

- no fused 138-product result;
- no 276-threshold parity result;
- no full-cohort runtime measurement;
- no full-cohort peak-RSS measurement;
- no new correctness claim.

The correct state is blocked, not failed parity.

A separate read-only Supabase connection on 2026-09-19 confirmed that the frozen Sep. 14 authority is still present with exactly 138 Full Market rows. That evidence narrows the blocker to the local DNS/network/environment path rather than missing frozen source data.

## Focused validation before the block

The local research report recorded:

- reference parity self-check: passed;
- focused tests: 27 passed.

Those checks validate the research harness itself but do **not** substitute for the real fused 138-product execution.

## Bucket 1 preliminary findings

Bucket 1 is not complete.

Static inspection already establishes two reasons unrestricted binary search cannot simply be assumed safe:

1. **Loss Resilience population changes**  
   As candidate cost crosses simulated outcome values, observations enter the losing population. Conditional Loss Resilience statistics can therefore move discontinuously and require explicit monotonicity analysis.

2. **Overall RIP V12 comparator tie-breaks**  
   The canonical V12 ordering is not only the V12 headline score. On score plateaus, Financial V4, chance-to-recover, committed-capital closeness, and deterministic product identity can bind. Within a fixed quantity interval, higher acquisition price increases committed capital and can improve the utilization tie-break.

These observations mean that the earlier five-sentinel binary-search design does not constitute a proof.

Exact enumeration remains the safe default until Bucket 1 completes:

- mathematical component monotonicity classification;
- synthetic adversarial counterexample search;
- exhaustive real-data threshold-interval audit;
- certified binary-safe conditions and/or conservative branch-and-bound bounds.

## Next step

1. Diagnose the local `SUPABASE_URL` / Windows DNS path.
2. Rerun the full Phase 10C fused baseline.
3. Require 276/276 exact threshold parity before promoting the Bucket 0 decision to:
   `FUSED_FULL_BASELINE_VALIDATED`.
4. Continue Bucket 1 synthetic/static work independently of the network blocker.

No optimized production search should be implemented before these gates close.
