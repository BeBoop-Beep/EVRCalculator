# Collector Appeal — production dry run

**Preview trustworthy: YES** · **Writes performed: 0** · Generated 2026-07-16T05:37:11.099232+00:00

- Formula: **CA7**, λ = **0.5**
- Fingerprint: `fbd2ccff9b8286e3dcdaf4e10283647834e3f761daf42341cc1b592d7f382764`
- Source manifest: `c852db59779972d72053438e6d63b895883b6ef367b56c3b31b71951428179c6` (171 rows)
- Normalized payload hash: `9f20a9af6db030838a56c3e3b0e4a1213d1334bb5bdbb353f4a8231722bbceaa`

## Counts

| Metric | Value |
|---|---|
| products total | **171** |
| booster supported | **135** |
| unsupported | **36** |
| would update | **171** |
| would insert | **0** |
| diagnostics only updates | **171** |
| score changing updates | **0** |
| unchanged | **0** |
| fingerprint current | **0** |
| fingerprint stale | **0** |
| fingerprint missing | **171** |
| collector appeal available | **21** |
| collector appeal unavailable | **150** |
| rip consumed rows | **33** |
| rows with warnings | **0** |

## Invariants

| # | Invariant | Result |
|---|---|---|
| 1 | exactly 171 catalogue products classified | ✅ pass |
| 2 | exactly 135 booster-supported | ✅ pass |
| 3 | exactly 36 unsupported non-booster products | ✅ pass |
| 4 | supported and unsupported are disjoint | ✅ pass |
| 5 | the two groups cover the full catalogue | ✅ pass |
| 6 | no classifier decision depends on the existing score value | ✅ pass |
| 7 | every booster-supported product has a positive existing score | ✅ pass |
| 8 | every unsupported product classified through metadata/evidence | ✅ pass |
| 9 | the ranked simulation cohort remains fully covered | ✅ pass |
| 10 | unsupported products have zero overlap with the ranked cohort | ✅ pass |
| 11 | no existing score value changes in the proposed payload | ✅ pass |
| 12 | no Profit/Safety/Stability/simulation/market field changes | ✅ pass |
| 13 | no RIP weight changes | ✅ pass |
| 14 | no frontend payload contract changes | ✅ pass |
| 15 | CA7 uses lambda = 0.50 everywhere | ✅ pass |
| 16 | every proposed diagnostics payload carries the current fingerprint | ✅ pass |
| 17 | normalized update payloads are deterministic | ✅ pass |
| 18 | missing or stale fingerprints are surfaced, not silently accepted | ✅ pass |
| 19 | no write request was executed | ✅ pass |
| 20 | no migration applied | ✅ pass |

## Pagination

- Pages read: 1 · total rows 511
- Final page partial (proves no truncation): **True**
- Truncation possible: **False**

## Read-only evidence

- Mutating client methods attempted: **0** 
- Tables read: explore_rip_statistics_latest, pokemon_canonical_cards, pokemon_card_desirability_links, pokemon_desirability_composite_scores, pokemon_set_desirability_component_scores, pokemon_set_page_snapshot_latest

## Anomalies

None.

## Future write command — NOT EXECUTED

```bash
python backend/scripts/collector_appeal_production_dry_run.py \
  --commit \
  --expected-fingerprint fbd2ccff9b8286e3dcdaf4e10283647834e3f761daf42341cc1b592d7f382764 \
  --expected-manifest c852db59779972d72053438e6d63b895883b6ef367b56c3b31b71951428179c6
```

The command refuses to run unless the fingerprint matches, the source manifest is unchanged since this preview, and every invariant passed.
