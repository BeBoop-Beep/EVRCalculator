# Production Backend Memory P0 — 2026-09-04

## Incident timeline

- Render service `inDex` (Standard, ~2.147GB limit, `uvicorn backend.api.main:app`)
  had RSS creep to ~1.85GB with no deployment at the time.
- 15:08:30Z — Render measured ~2.074GB RSS and force-restarted the instance
  (7x HTTP 502 during the ~20s restart window).
- Post-restart, RSS was stable at ~513MB for 20+ minutes.
- 15:31:32Z — first request pair after restart:
  `GET /explore/rip-statistics/targets?limit=200`, then
  `GET /tcgs/pokemon/sets/<spotlight-set>/rip/simulation-evidence`.
- Immediately after, RSS jumped to ~1.073GB (+560MB). A similar pair preceded
  an earlier large step that morning too.

## Root cause

`get_pokemon_explore_rankings_snapshot_payload()` in
`backend/db/services/pokemon_public_snapshot_service.py` served
`/explore/rip-statistics/targets`. It read the full
`pokemon_explore_rankings_snapshot_latest.ranking_payload_json` mega-contract
(all targets, each with a `setRipV1.familyScores` block, plus the top-level
`productFamilyRankings` block — none of which the frontend consumer at
`frontend/lib/explore/ripStatisticsServer.js` reads), then on **every
successful request** wrote:

```python
_LAST_SUCCESSFUL_RANKINGS_PAYLOADS[clamped_limit] = deepcopy(resolved_payload)
```

`_LAST_SUCCESSFUL_RANKINGS_PAYLOADS` was `Dict[int, Dict[str, Any]]`, module
global, with **no TTL and no eviction**, keyed by the request's `limit`. Two
unbounded axes:

1. **Key growth**: every distinct `limit` ever requested got its own full
   `deepcopy()`'d entry, forever.
2. **Per-request cost**: even with a single `limit` value, every healthy
   request paid a full `deepcopy()` of the entire mega-contract object graph
   (hundreds of nested dicts/lists) just to refresh a cache entry that would
   only ever be read on failure.

A second `deepcopy()` happened again in `_stale_rankings_fallback()` on the
(rare) read path.

This matches the incident symptom precisely: a big one-off allocation
(materializing + enriching + deep-copying the full mega-contract) that
CPython's allocator does not return to the OS as freed arenas, so RSS steps
up and stays up. The frontend's own canonical-cohort comment
(`ripStatisticsServer.js` lines 30-38) already establishes that this endpoint
is normally called with a single fixed `limit=200`; but nothing on the
backend enforced that, and any other caller (tests, other API consumers,
future frontend code) passing a different `limit` would silently add another
full copy to the unbounded cache.

## Chosen fix

`backend/db/services/pokemon_public_snapshot_service.py`:

- Replaced `_LAST_SUCCESSFUL_RANKINGS_PAYLOADS: Dict[int, Dict]` with
  `_RANKINGS_FALLBACK_CACHE`, a **single-slot** dict
  (`identity_key`, `raw_targets`, `base_payload`, `meta`, `default_target`).
- `_update_rankings_fallback_cache()` replaces the slot **only when
  `identity_key` changes** (the publication's `updated_at`, or a fixed
  `"live_fallback"` marker for the rare missing-snapshot path) — a run of
  identical healthy requests does zero cache work.
- The cache stores `base_payload`/`raw_targets`/`meta` **by reference, no
  `deepcopy()`**. This is safe because nothing on the read path mutates
  these objects in place after caching — both the healthy path and
  `_rankings_fallback_from_cache()` only ever build *new* top-level
  dicts/lists (`{**cache["base_payload"], "targets": ..., "meta": ...}`,
  `list(...)[:clamped_limit]`) around the shared reference, never mutating
  the referenced nested structures.
- `_rankings_fallback_from_cache(clamped_limit, reason)` reslices the
  cached full (unclamped) opening-set cohort to the *fallback caller's own*
  `limit`, mirroring exactly how the healthy path already slices — so a
  single cached cohort correctly serves a fallback for any `limit`, instead
  of needing one cache entry per limit.
- Removed the second `deepcopy()` in the old `_stale_rankings_fallback()`
  (function deleted; folded into `_rankings_fallback_from_cache()`).

No change to: response content/shape, ranking semantics, rank computation,
entitlement/tier boundaries, or the fail-closed publication-identity check
(`_rankings_publication_identity_mismatches` still runs first and still
raises 503 `RIP_STATISTICS_TARGETS_PUBLICATION_SUPERSEDED` with no cached
entry, and still never falls back to the live builder).

## Alternatives considered and rejected

- **Route through the compact Sets lens (`get_pokemon_rankings_sets_lens` /
  `get_pokemon_explore_rankings_lens_payload`)** — Phase B of the assigned
  scope. Confirmed the lens RPC (`get_pokemon_rankings_sets_lens`,
  `supabase/migrations/20260830010000_tighten_compact_rankings_sets_lens_rpc.sql`)
  already avoids `productFamilyRankings` at the SQL layer and is used by the
  normal Rankings page. This is the *architecturally* preferable long-term
  fix for `/explore/rip-statistics/targets` too, since it would avoid
  materializing the mega-contract in Python at all. It was **not** done in
  this change: it requires tracing every field the frontend consumer needs
  (`ripStatisticsNormalizer.mjs` and its downstream consumers) against the
  lens's current projection, and any gap needs a surgical migration +
  contract tests — a larger, higher-risk change than the confirmed cache
  root cause justified for a P0 fix. Recommended as a fast-follow (see
  Remaining risks).
- **TTL-based eviction on the existing per-limit dict** — rejected: still
  pays a full `deepcopy()` per distinct limit per TTL window, and does
  nothing about the per-request deep-copy cost, which the benchmark shows
  is the dominant term.
- **Drop the fallback cache entirely, rely on the existing 503** — rejected
  for this pass: the fallback exists specifically to avoid handing every
  visitor a 3.8-150s live rebuild or an outage during a transient DB blip,
  and the fail-closed 503 for incompatible-publication is preserved
  unchanged. Bounding the cache's memory removes the actual OOM risk
  without giving up that recovery behavior.

## Benchmark: before vs after

`backend/scripts/benchmark_rankings_fallback_cache_memory.py` runs the real
`get_pokemon_explore_rankings_snapshot_payload()` against a synthetic but
realistically-shaped snapshot row (200 targets, each with a `setRipV1`
block carrying 25 `familyScores` entries, plus a `productFamilyRankings`
block with 100 entries — reconstructed because this environment has no
production DB credentials; sized to match the incident's mega-contract
shape). `psutil` RSS, `tracemalloc` supplementary.

| Step | Before (old per-limit `deepcopy` cache) | After (single-slot, no-copy cache) |
|---|---|---|
| RSS before first request | 100.59MB | 99.19MB |
| After first `limit=200` request | 104.99MB (+4.41MB) | 99.19MB (+0.00MB) |
| After 50 more identical `limit=200` requests | 108.16MB (+3.17MB) | 99.19MB (+0.00MB) |
| After 200 requests spanning every distinct `limit` 1..200 | **402.01MB (+293.85MB)** | 99.21MB (+0.02MB) |
| Cache entries after the run | 200 (one per distinct limit) | 1 (single slot) |
| **Total RSS delta over the full run** | **+301.42MB** | **+0.02MB** |

The 200-distinct-limits step is deliberately adversarial (it's what an
unbounded key space allows); the incident's actual traffic is dominated by
the frontend's fixed `limit=200` calls, where the before/after gap is
smaller per-request but still present on every single successful call
(every healthy request paid a full deep copy before; now it pays one only
when the underlying publication actually changes).

### Wall time

The 200-distinct-limit loop: 3.21s before vs 2.05s after (deep-copy removal
also cuts CPU work, not just memory).

### Response bytes / p50/p95 latency

Not measured against a live backend/DB in this environment (no production
credentials available here). The change does not alter response content or
size — `resolved_payload` construction is unchanged; only the fallback
cache's own internal storage changed — so response bytes are expected to be
identical before/after. Latency should improve slightly (one fewer
`deepcopy()` of the whole payload per healthy request) but this needs
confirming against a running instance; see verification procedure below.

## Tests

- `backend/tests/unit/db/services/test_pokemon_rankings_fallback_cache.py`
  (new, 5 tests, all pass; all 5 fail with `AttributeError` against the
  pre-fix code, confirming they exercise the fix):
  - cache stays a single slot across many distinct limits
  - healthy requests do not deep-copy the payload (`is` identity check)
  - repeated identical requests do not replace the cache slot
  - stale fallback reslices the cached cohort to the requested limit
  - a cold cache still fails closed with 503 on transient failure
- `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py`
  — pre-existing suite. **Baseline discovery, not caused by this change**:
  158/170 tests in this file already fail at `origin/main` HEAD
  (`e85a257d`, the exact revision deployed at incident time) with
  `AttributeError: ... has no attribute 'public_read_client'` — the module
  was refactored to `service_read_client` but this test file was never
  updated. Confirmed via `git stash` that this file fails identically with
  and without this change (158 failed / 12 passed both times). The four
  `.clear()` call sites and one dict-index read that referenced the
  removed `_LAST_SUCCESSFUL_RANKINGS_PAYLOADS` were mechanically updated to
  the new cache API so they'd be correct *if/when* that file's broken
  `public_read_client` references are fixed separately — out of scope for
  this P0.
- `backend/tests/unit/db/services/test_rankings_lens_projection.py` — 5/5
  pass, unaffected (this file doesn't touch the fallback cache).
- `backend/tests/unit/api/test_paid_response_boundary.py` — could not run
  in this environment (`ModuleNotFoundError: No module named 'fastapi'`,
  pre-existing environment gap, not related to this change). Needs running
  in an environment with the full backend dependency set installed before
  deploy sign-off.

## Remaining risks

- Response-bytes/p50/p95 latency and the paid-response-boundary suite were
  not confirmed against a live backend in this sandbox (missing `fastapi`
  and no production DB credentials). Run both before merging/deploying, per
  the verification procedure below.
- The mega-contract read itself (`select("...,ranking_payload_json,...")`)
  is unchanged — this fix bounds the *fallback cache's* retention, not the
  per-request materialization cost of the full payload. If profiling after
  deploy shows the per-request read/enrich work (not the cache) is still a
  material RSS contributor, Phase B (routing through the existing compact
  `get_pokemon_rankings_sets_lens` projection) is the next step — deferred
  here because it needs frontend field-parity tracing this pass didn't do.
- The rare "missing snapshot; live fallback" cache branch uses a fixed
  `"live_fallback"` identity marker, so it only refreshes the cache once
  per process even if the live-rebuilt content changes between calls in
  that degenerate state. Low risk: this path only triggers when
  `pokemon_explore_rankings_snapshot_latest` is missing entirely, which is
  already an operator-visible warning-logged condition.

## Production verification procedure (after deploy)

1. Render dashboard → `inDex` service → Metrics: watch RSS over the first
   30-60 minutes after deploy. Compare against the pre-fix pattern (stable
   ~513MB post-restart, then a step to ~1.07GB on the first
   `/explore/rip-statistics/targets` + `/rip/simulation-evidence` request
   pair). Expect RSS to stay materially flatter after that first request
   pair — a small one-time rise from the first read is expected and fine;
   a further unbounded climb on subsequent requests is not.
2. Render logs: grep for
   `[pokemon-snapshot] persisted rankings snapshot is not the canonical publication`
   and `[pokemon-snapshot] explore rankings snapshot read failed` — confirm
   these still occur only on genuine incompatible-publication/transient-DB
   events (unchanged fail-closed behavior), and that stale-fallback
   responses still carry `meta.snapshot.isStaleFallback: true` with a
   `fallbackReason`.
3. `GET /explore/rip-statistics/targets?limit=200` a few times in a row in
   production (or staging) and confirm response body is byte-for-byte
   stable across calls when the underlying publication hasn't changed
   (proves the single-slot cache isn't corrupting content).
4. No further forced restarts attributable to this endpoint over the
   following 24-48h of normal traffic.

## Files changed

- `backend/db/services/pokemon_public_snapshot_service.py` — cache redesign
  (see "Chosen fix" above).
- `backend/tests/unit/db/services/test_pokemon_rankings_fallback_cache.py`
  — new regression suite (TDD-verified against pre/post-fix code).
- `backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py`
  — mechanical rename of the four `_LAST_SUCCESSFUL_RANKINGS_PAYLOADS`
  references to the new cache reset API (does not fix the file's
  pre-existing, unrelated `public_read_client` breakage).
- `backend/scripts/benchmark_rankings_fallback_cache_memory.py` — new
  memory benchmark used for the before/after table above.

No database migrations. No frontend changes.
