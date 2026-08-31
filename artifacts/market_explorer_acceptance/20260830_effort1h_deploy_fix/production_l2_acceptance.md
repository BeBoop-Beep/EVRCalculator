# Effort 1H Deploy Fix — production L2 acceptance

Outcome: `L2_CACHE_PRODUCTION_FAILED`

## Corrective migration

- Forward migration: `20260831051014_bound_market_explorer_cache_state_invalidation.sql`
- Deployed after `20260831034744_add_market_explorer_query_cache.sql`.
- The invalidation function remains `SECURITY INVOKER`, service-role-only, and
  atomically marks bounded cache rows stale before incrementing the two bounded
  asset generations with `where asset in ('cards', 'sealed')`.
- Predeployment suites: 184 passed. Golden semantic fingerprint unchanged.

## Production invalidation acceptance

The single authorized invalidation invocation succeeded:

- affected ready rows: 2
- cards generation: 0 -> 1
- sealed generation: 0 -> 1
- both rows observed stale after commit
- old Cards and Sealed D:r0 worker entries did not hit after the metadata TTL
- both stale entries used `novel_interval` with a null prior anchor and returned
  to ready

Lease acceptance passed: active second claim false, wrong-token publish false,
owner publish true, expired lease reclaim true, and one row per fingerprint.
Normalization equivalence produced the same spec, fingerprint, and one row.
Sealed formal acceptance passed: miss `novel_interval`, ten fresh-worker
`persistent_cache` hits, twenty same-worker `memory_cache` hits, and preserved
`sealedProductId` identity.

## New blocker

Cards canonical publication metadata advanced to `2026-08-30`, while the Fossil
interval query's newest usable payload remains `2026-08-28`. A dedicated Cards
miss publishes the payload with `computed_through=2026-08-28`; every fresh
worker then sees L2 behind the `2026-08-30` canonical watermark and runs
`cache_incremental` again. Ten requested Cards L2 samples therefore produced
ten incremental executions, not persistent-cache hits.

This is outside the authorized safe-update correction. No application or source
change was made.

## Measured evidence

| Path | Median ms | p95 ms | Min ms | Max ms |
|---|---:|---:|---:|---:|
| Cards L1 planner | 0.714 | 0.832 | 0.699 | 0.832 |
| Cards direct L1 lookup | 0.342 | 0.412 | 0.333 | 0.503 |
| Cards generation metadata | 100.860 | 127.536 | 98.133 | 127.536 |
| Cards repeated behind-L2 incremental | 661.250 | 892.021 | 577.905 | 892.021 |
| Sealed L2 | 162.365 | 199.291 | 146.535 | 199.291 |
| Sealed L1 planner | 0.921 | 1.269 | 0.890 | 1.269 |
| Sealed direct L1 lookup | 0.435 | 0.530 | 0.424 | 0.706 |
| Sealed generation metadata | 109.316 | 129.866 | 97.983 | 129.866 |

The cache-only Cards incremental comparison itself passed all semantic fields:
trend, index value, tracked history and changes, family changes, current
constituents, unique dates, one prior anchor, and one new point.

## Final production state

- cache rows: 2 ready, 0 stale, 0 failed, 0 building
- cards generation: 1
- sealed generation: 1
- Cards ordinary row: 65,744 bytes, payload 38,943 bytes, 136 points,
  186 constituents, through 2026-08-28
- Sealed ordinary row: 7,144 bytes, payload 5,306 bytes, 119 points,
  2 constituents, through 2026-08-28
- synthetic/dedicated fingerprints remaining: 0
- source authority: 18,957 intervals, 211 variants, 2 sets,
  0 invalid instruments

## Required next step

Resolve why the Cards publication watermark reports `2026-08-30` while the
Fossil interval engine can only produce a payload through `2026-08-28`. Do not
deploy application changes or accept L2 until that contract is corrected and
the Cards miss -> L2 -> L1 sequence is rerun.
