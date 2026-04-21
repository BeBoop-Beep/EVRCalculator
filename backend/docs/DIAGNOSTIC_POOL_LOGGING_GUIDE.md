# Diagnostic Logging Guide: Pool Composition and Pattern Overlays

This guide explains the new INFO-level diagnostics added to detect pattern leakage during EV and simulation runs.

## Where Logs Are Emitted

- Pool extraction: `backend/simulations/utils/extractScarletAndVioletCardGroups.py`
- Manual EV aggregation: `backend/calculations/packCalcsRefractored/evrCalculator.py`
- Simulation cross-check: `backend/simulations/evrSimulator.py`

## Log Prefixes

- `[POOL_COMPOSITION]`: Source and extracted pool counts, including pattern overlap checks.
- `[MANUAL_EV_COMPOSITION]`: EV contribution breakdown across base, pattern, and other special buckets.
- `[POOL_CROSS_CHECK]`: Simulation pre-run integrity checks for leakage and source-row coverage.

## Example Output (Pattern Set: Prismatic-like)

```text
[POOL_COMPOSITION] total_rows_in_source=487
[POOL_COMPOSITION] common_pool_size=46 pattern_rows_in_common=0
[POOL_COMPOSITION] uncommon_pool_size=33 pattern_rows_in_uncommon=0
[POOL_COMPOSITION] rare_pool_size=28 pattern_rows_in_rare=0
[POOL_COMPOSITION] hit_pool_size=35 (includes patterns)
[POOL_COMPOSITION] reverse_pool_size=487
[POOL_COMPOSITION] pokeball_pattern_count=7
[POOL_COMPOSITION] master_ball_pattern_count=3
[POOL_COMPOSITION] pattern_overlap_with_base_pools=0 (should always be 0 after fix)

[MANUAL_EV_COMPOSITION] total_ev_across_all_buckets=10.67
[MANUAL_EV_COMPOSITION] base_rarity_ev_total=7.95 (sum of common, uncommon, rare, reverse)
[MANUAL_EV_COMPOSITION] pattern_ev_total=2.72 (sum of pokeball_pattern, master_ball_pattern)
[MANUAL_EV_COMPOSITION] other_special_ev_total=0.00 (ace_spec, illustration_rare, etc)
[MANUAL_EV_COMPOSITION] pokeball_pattern_ev=1.030
[MANUAL_EV_COMPOSITION] master_ball_pattern_ev=1.690

[POOL_CROSS_CHECK] Verifying pool composition for simulation...
[POOL_CROSS_CHECK] base_pools_have_no_patterns=True
[POOL_CROSS_CHECK] patterns_in_hit_pool=10_rows
[POOL_CROSS_CHECK] all_rows_accounted_for=True (common+uncommon+rare+hit cover source rows)
```

## Example Output (Non-Pattern Set: Obsidian-like)

```text
[POOL_COMPOSITION] total_rows_in_source=92
[POOL_COMPOSITION] common_pool_size=29 pattern_rows_in_common=0
[POOL_COMPOSITION] uncommon_pool_size=20 pattern_rows_in_uncommon=0
[POOL_COMPOSITION] rare_pool_size=10 pattern_rows_in_rare=0
[POOL_COMPOSITION] hit_pool_size=12 (includes patterns)
[POOL_COMPOSITION] reverse_pool_size=92
[POOL_COMPOSITION] pokeball_pattern_count=0
[POOL_COMPOSITION] master_ball_pattern_count=0
[POOL_COMPOSITION] pattern_overlap_with_base_pools=0 (should always be 0 after fix)

[POOL_CROSS_CHECK] Verifying pool composition for simulation...
[POOL_CROSS_CHECK] base_pools_have_no_patterns=True
[POOL_CROSS_CHECK] patterns_in_hit_pool=0_rows
[POOL_CROSS_CHECK] all_rows_accounted_for=True (common+uncommon+rare+hit cover source rows)
```

## How To Use These Logs To Verify Pattern-Overlay Fixes

1. Confirm extraction-level isolation:
   - `pattern_rows_in_common=0`
   - `pattern_rows_in_uncommon=0`
   - `pattern_rows_in_rare=0`
   - `pattern_overlap_with_base_pools=0`

2. Confirm patterns still exist where expected:
   - `pokeball_pattern_count` and `master_ball_pattern_count` should be non-zero for pattern sets.
   - `patterns_in_hit_pool` should match the expected number of pattern rows routed to hit pool.

3. Confirm simulation readiness:
   - `base_pools_have_no_patterns=True`
   - `all_rows_accounted_for=True`

4. Confirm EV decomposition coherence:
   - `pattern_ev_total` should equal `pokeball_pattern_ev + master_ball_pattern_ev` (within rounding tolerance).
   - `base_rarity_ev_total` should include common, uncommon, rare, and reverse only.

## Fast Failure Signals

If any of these appears, investigate immediately:

- `[POOL_COMPOSITION] pattern_overlap_with_base_pools > 0`
- `[POOL_CROSS_CHECK] base_pools_have_no_patterns=False`
- `[POOL_CROSS_CHECK] all_rows_accounted_for=False`
- `[MANUAL_EV_COMPOSITION] pattern_ev_total` unexpectedly zero for a known pattern set
