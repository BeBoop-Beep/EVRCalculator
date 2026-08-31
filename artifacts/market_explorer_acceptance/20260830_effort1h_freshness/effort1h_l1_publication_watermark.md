# Effort 1H Freshness — L1 publication watermark correction

Outcome: `L1_FRESHNESS_CORRECTED`

## Root cause

L1 was keyed only by the stable semantic query fingerprint and was consulted before canonical publication state. A D1 payload could therefore hide D2 or a historical repair for the full 300-second result TTL.

## Design

- Persistent L2 identity remains the unchanged semantic SHA-256 fingerprint.
- L1 interface is now `get(fingerprint, PublicationGeneration)` / `put(fingerprint, PublicationGeneration, payload)`.
- `PublicationGeneration.token` is `<canonical-through>:r<repair-generation>`.
- A two-second process-local cache stores only `(asset, era scope, set scope) -> PublicationGeneration`; it never stores market data.
- Maximum publication/repair propagation delay through L1 is explicitly two seconds, not 300 seconds.
- Canonical watermark resolution was narrowed to publication metadata: one query for common Cards scopes and one query for common Sealed scopes. The old Sealed resolver transported full snapshot payloads in batches.
- The undeployed migration now includes service-only `pokemon_market_explorer_cache_state` rows for Cards and Sealed. Historical invalidation marks L2 stale and increments both repair generations in the same transaction.

## Forward and repair flows

Normal D1 -> D2 publication changes the canonical date token, misses D1 L1, observes L2 behind D2, queries `[D1,D2]`, appends incrementally, and stores L1 under D2.

Historical repair increments the shared repair generation and marks L2 stale atomically. After the maximum two-second metadata-cache interval, every worker derives the new L1 token, misses its old process entry, and performs a full lazy rebuild. No cross-process `.clear()` is used.

Prepared registry loaders are invoked on every prepared request before process L1 and are not result-cached by the planner. Current production registry remains empty because existing prepared publications are not methodologically equivalent.

## Watermark cost audit (five production read-only samples)

| Scope | Original median ms | Optimized samples ms | Optimized median ms | Calls |
|---|---:|---|---:|---|
| Cards set | 179.656 | 316.017, 51.460, 56.276, 57.917, 53.807 | 56.276 | one coverage metadata read |
| Cards two-set | 175.419 | 54.393, 45.314, 61.712, 52.552, 69.060 | 54.393 | one coverage metadata read |
| Sealed global | 5,383.809 | 64.163, 43.381, 54.642, 91.738, 51.864 | 54.642 | one latest-snapshot metadata read |

After L2 deployment, a watermark-cache refresh also performs one narrow service-only repair-generation read. True requests within the two-second watermark interval perform neither database call.

## Local planner benchmarks

| Operation | Median ms | Min ms | Max ms |
|---|---:|---:|---:|
| complete same-generation L1 planner path | 0.9124 | 0.8751 | 1.3144 |
| watermark metadata-cache hit | 0.0003 | 0.0002 | 0.0012 |
| new-generation L1 dictionary miss | 0.0053 | 0.0051 | 0.0110 |
| incremental merge overhead | 2.5248 | 2.4449 | 3.4975 |

## Verification

- Relevant backend suites: 226 passed.
- Frontend normalization/proxy contracts: 20 passed.
- Golden semantic fingerprint remains `2cb8862bc86ab03be481ae12f163838a5c9a6371ffc5613cbac03d27b139541d`.
- Entitlement ordering and behavior remain unchanged.
- Cards and Sealed use the same publication/repair generation contract.
- Production cache table/state: absent.
- Migration `20260831034744`: not applied.
- Production interval rows: unchanged at 18,957.
- Production writes: none.

## Migration choice

`20260831034744_add_market_explorer_query_cache.sql` was edited in place because it remains undeployed and unrecorded in production. The only schema addition is the smallest cross-worker repair-generation authority; no superseding migration is needed before the initial deployment.

## Next recommendation

Review the updated undeployed migration, then authorize and execute the existing Effort 1H deployment sequence. Do not deploy or populate L2 until that explicit authorization is given.
