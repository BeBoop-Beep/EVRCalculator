# Effort 1H Freshness Fail-Closed — repair-generation read safety

Outcome: `REPAIR_GENERATION_FAILCLOSED`

## Correction

`PersistentMarketExplorerCache.repair_generation(asset)` now returns `int | None`.
Legitimate generations zero and one remain trusted values; an absent state row or
read exception returns `None`. `PublicationGeneration.trusted` makes that state
explicit, and an unknown generation has no token or L1 identity.

The planner bypasses both L1 read and L1 write while the generation is unknown.
It continues through L2 and the novel engine, preserving pre-migration
availability. Unknown resolutions are not inserted into the two-second
publication-watermark cache, so the next request retries the state read.

## L2 safety

The undeployed migration function
`invalidate_pokemon_market_explorer_query_cache(date)` first changes affected
ready rows to stale and then increments the repair-state generation in the same
PostgreSQL transaction. Consequently, when the generation SELECT fails:

- ready/current L2 is safe and may be returned;
- stale L2 performs a full rebuild;
- missing/unavailable L2 continues to the novel path;
- an active build lease retains follower behavior.

Migration blob before and after this effort:
`c0cea68cb06844b1df22ab3e61d99790f09b22b5` (unchanged).

## Verification

- Relevant backend planner, migration, fingerprint, and entitlement-order suites:
  87 passed.
- Frontend normalization/proxy contracts: 20 passed.
- Cards and Sealed unknown-generation cases pass.
- Independent two-worker D1:r0 regression passes: known r1 and unknown read both
  reject the old process-local entry.
- Legitimate r0/r1 repository values remain distinct from read failure.
- The next successful generation read recovers and can use the matching L1 entry.
- Golden semantic fingerprint remains
  `2cb8862bc86ab03be481ae12f163838a5c9a6371ffc5613cbac03d27b139541d`.
- No production DDL, writes, interval changes, or deployment occurred.

## Local benchmark

Representative 140-point/211-constituent payload (18,467 bytes):

| Operation | Median ms | Min ms | Max ms |
|---|---:|---:|---:|
| trusted-generation complete L1 planner path | 1.0600 | 1.0305 | 7.8236 |
| watermark metadata-cache hit | 0.0004 | 0.0003 | 0.0014 |
| untrusted generation, L1 bypass, ready/current L2 path | 1.0686 | 1.0356 | 1.4237 |
| trusted simulated L2 path | 1.5998 | 1.5502 | 2.1712 |

The unknown-generation measurement excludes downstream novel database
computation. The normal trusted L1 behavior is unchanged except for a boolean
guard before the existing dictionary lookup.

## Next recommendation

Review this fail-closed correction together with the already accepted Effort 1H
migration. Do not deploy or populate persistent L2 until the existing deployment
sequence receives explicit authorization.
