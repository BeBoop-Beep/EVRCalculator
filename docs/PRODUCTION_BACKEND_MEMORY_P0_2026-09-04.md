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
catastrophic-but-not-both-unbounded axes (correction from an earlier draft of
this doc, which described key growth as literally unbounded — it is not;
`_sanitize_limit()` clamps every `limit` to the closed range 1..200 before it
is used as a dict key, so key cardinality was bounded at 200):

1. **Key growth, bounded but still catastrophic**: every distinct clamped
   `limit` in 1..200 ever requested got its own full `deepcopy()`'d entry,
   forever — up to 200 entries, each a deep copy of the entire mega-contract
   (hundreds of nested dicts/lists, including the unrelated
   `productFamilyRankings` block). 200 full mega-contract copies retained
   simultaneously is enough on its own to exhaust a ~2GB instance; "bounded"
   here means "finite," not "safe."
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

## Pass 2 (this update): compacting what the fallback cache retains

`1ee37cf9` fixed the cache's key cardinality and per-request deep-copy cost,
but its single slot still cached `base_payload=payload` — the entire
resolved Rankings mega-contract, including `productFamilyRankings`,
`setRip`, and `eraSetStrengthV1` — by reference. That keeps those unrelated
blocks alive in memory for the life of the process (or until the next
publication), even though every traced runtime consumer of
`getRipStatisticsTargets()` (`frontend/lib/landing/landingHeroServer.js`,
`frontend/app/TCGs/Pokemon/Sets/[setSlug]/analysis/page.js`,
`frontend/app/Articles/how-representative-is-pokemon-pack-expected-value/page.js`,
`frontend/app/sitemap.js`, `frontend/app/Explore/rip-statistics/page.js`,
and the contract tests that exercise them) reads only `targets`,
`default_target`, and `meta`.

This pass adds `_compact_rankings_fallback_base_payload()` and uses it at
both `_update_rankings_fallback_cache()` call sites in
`get_pokemon_explore_rankings_snapshot_payload()`, excluding
`productFamilyRankings`/`setRip`/`eraSetStrengthV1` (and the
separately-cached `targets`/`default_target`/`meta`) from what the slot
retains. TDD: `test_fallback_cache_does_not_retain_unrelated_mega_contract_blocks`
in `backend/tests/unit/db/services/test_pokemon_rankings_fallback_cache.py`
fails against the pre-this-pass code (asserts `productFamilyRankings` is
absent from the cached slot and from a served fallback response) and passes
after. All 6 tests in that file pass; no regression in
`backend/tests/unit/api/test_paid_response_boundary.py` (10/11 pass,
identical to the pre-existing baseline both with and without this change —
the 1 failing test, `test_product_rankings_http_projection_plus_then_base`,
exercises `/explore/product-rankings/overall`, not
`/explore/rip-statistics/targets`, and its failure is unrelated to the
fallback cache; confirmed via `git stash`).

**Still outstanding, not done in this pass**: the NORMAL (non-fallback)
read path — `_load_pokemon_explore_rankings_snapshot_row()` — still selects
and materializes the complete `ranking_payload_json` mega-contract on every
healthy request, exactly as described in "Alternatives considered and
rejected" above (routing the normal `/explore/rip-statistics/targets` path
through the compact `get_pokemon_rankings_sets_lens` RPC/lens instead of the
full mega-contract reader). That refactor is architecturally preferable and
was traced as safe from a consumer-field standpoint in this pass (no
consumer needs `productFamilyRankings`/`setRip`/`eraSetStrengthV1`), but the
normal path also runs `upgrade_rankings_set_rip_contract_if_needed()`,
`attach_era_set_strength()`, and the checklist set-value compatibility
enrichment against the full persisted payload before slicing — verifying
those against the compact lens's projection without changing Set RIP/Era/
publication-identity semantics is a larger, higher-risk change than fit
safely in this pass. It remains the correct fast-follow: **do not conclude
from this doc that the fallback-cache fix alone explains the full ~560MB
production RSS increase** — the normal-path mega-contract materialization
on every request (not just the fallback cache) is a plausible material
contributor that this pass narrows but does not eliminate. A repeat of the
Render RSS-over-time observation after this deploy, compared against the
pattern in "Incident timeline" above, is the way to attribute the remaining
delta before claiming the normal path is also fixed.

## Pass 3 (this update): investigated the normal-path compact refactor; NOT shipped

Branch HEAD at the start of this pass: `76795836`. This pass did the required
tracing and root-cause work for the outstanding item above, confirmed the
refactor is directionally correct, found one concrete blocker, and — per the
task's explicit escape hatch — stopped short of changing the read path rather
than ship something unverified against a live publication. **No functional
code was changed in this pass.** No migration was added. Branch HEAD is
unchanged from `76795836`.

### Step 1 — consumer trace (verified, not just re-trusted)

Grepped all of `frontend/` for `getRipStatisticsTargets` (19 files) and for
`productFamilyRankings`/`eraSetStrengthV1`/`setRip`-family usage (17 files),
then checked each hit's actual data source:

- Real page consumers of `getRipStatisticsTargets()` — landing hero
  (`frontend/lib/landing/landingHeroServer.js`), the set analysis page
  (`frontend/app/TCGs/Pokemon/Sets/[setSlug]/analysis/page.js`), the Articles
  EV-representativeness page, `frontend/app/Explore/rip-statistics/page.js`,
  and `frontend/app/sitemap.js` — read only `targets`, `default_target`, and
  `meta` (via `frontend/lib/explore/ripStatisticsNormalizer.mjs`).
- The Rankings UI's Products and Eras tabs (`frontend/components/explore/RankingsLazyClient.jsx`
  lines ~92-122) get `productFamilyRankings`/`eraSetStrengthV1` from
  **separate** `fetch("/api/explore/rankings/lens?lens=products")` /
  `?lens=eras` calls — not from the targets payload at all, confirming they
  are wired to the already-compact lens endpoint, independent of this
  refactor.
- Confirms the previous pass's claim: no real consumer of the targets
  endpoint needs the top-level `productFamilyRankings`/`setRip`/
  `eraSetStrengthV1` blocks.

### Step 2 — why the refactor is directionally sound but not completed

Read `_load_pokemon_explore_rankings_snapshot_row`,
`get_pokemon_explore_rankings_lens_payload`/`get_pokemon_rankings_sets_lens`
(`supabase/migrations/20260830010000_tighten_compact_rankings_sets_lens_rpc.sql`),
`upgrade_rankings_set_rip_contract_if_needed`, `attach_era_set_strength`
(`backend/db/services/era_set_strength_service.py`),
`payload_guarantees_canonical_set_value`
(`backend/db/services/public_rip_publication_contract.py`), and
`_enrich_rankings_payload_with_checklist_set_values` in full.

**Good news**: three of the four enrichment steps the normal path runs
against the full mega-contract only ever touch `targets` and `meta`, both of
which the existing compact "sets" lens select clause already projects
(`targets:ranking_payload_json->targets,meta:ranking_payload_json->meta,default_target_json,updated_at`):
- `attach_era_set_strength` reads only `payload["targets"]`
  (`era_set_strength_service.py:89-92`) — each target's own `setRipV1.score`/
  `.rank`, which the compact RPC's `project_pokemon_rankings_set_target`
  already projects per-target.
- `payload_guarantees_canonical_set_value` reads only
  `meta.snapshot.setValueContract` — present in the compact `meta` projection.
- `_enrich_rankings_payload_with_checklist_set_values` reads only `targets`
  (for `set_id`) and hits a *different* table
  (`pokemon_set_market_dashboard_snapshot_latest`), independent of
  `ranking_payload_json` entirely.
- `upgrade_rankings_set_rip_contract_if_needed` is the one exception: its
  fallback branch (when `_has_enriched_set_rip_contract(payload)` is false)
  needs the top-level `productFamilyRankings` block to rebuild `setRipV1` via
  `build_set_rip()`. Traced the publisher
  (`backend/scripts/pokemon_snapshot_builders.py:4218`,
  `attach_set_rip_to_targets(payload["targets"], set_rip)`) and confirmed it
  already writes the enriched `setRipV1` shape onto every target **at publish
  time**, which strongly suggests `upgrade_rankings_set_rip_contract_if_needed`
  is a no-op safety net for legacy rows on every *current* publication, not
  something the normal path actually exercises today. This was **not**
  confirmed against a live production row — this sandbox has no production DB
  credentials — so it is an inference from the publisher code, not a proven
  fact about the currently-published row.

### Step 2 — the concrete blocker found

`build_opening_set_audit(raw_targets)`
(`backend/desirability/set_validation.py:225`), attached to
`meta.openingSetAudit`/`meta.opening_set_audit` on every normal-path
response, genuinely needs the **full, unfiltered** `targets` array — including
non-opening-set and subset rows — to report `total_raw_pokemon_set_rows`,
`subset_rows_missing_parent_mapping`, etc. The compact
`get_pokemon_rankings_sets_lens` RPC's `CROSS JOIN LATERAL ... WHERE
COALESCE((target->>'is_opening_set')::boolean, ..., true)` clause
(migration `20260830010000`, lines 76-82) discards non-opening rows in SQL
before they ever reach Python, so the compact projection cannot reproduce
this audit as-is.

Traced whether this field is actually load-bearing: grepped both
`frontend/` and `backend/` for `openingSetAudit`/`opening_set_audit`.
**Zero frontend consumers** — it is a backend-only diagnostic field, not
read by any page, component, or contract test that exercises the targets
endpoint. It is written by
`backend/scripts/refresh_stale_public_snapshots.py`,
`backend/scripts/pokemon_snapshot_builders.py`, and
`backend/scripts/build_pokemon_desirability_validation_snapshots.py` too,
but those are separate batch/build-time producers, not consumers of the
targets HTTP response.

This means the audit *could* be dropped from the compact response without
breaking any known consumer (falls under the task's "genuinely unrelated,
can be skipped" allowance) — or, more conservatively, reproduced by
extending the RPC to compute the count fields in SQL (a `jsonb_build_object`
aggregate over the *unfiltered* `payload->'targets'` array, before the
opening-set `WHERE` filter) rather than shipping the excluded rows back to
Python, which would preserve compactness. Either path is a legitimate
"small surgical extension" under the task's constraints, not a third
competing projection.

### Why this was not shipped in this pass

Two things are still unverified and both need production DB access this
sandbox does not have:
1. Whether `_has_enriched_set_rip_contract` is actually true for the
   *current* live-published row (making `upgrade_rankings_set_rip_contract_if_needed`
   dead code on the compact path) — inferred from publisher code, not
   observed. If it turns out false for some live edge case, the compact
   path would need a documented, non-silent fallback to the full
   mega-contract reader for that request (implementable, but its trigger
   condition needs a real row to test against).
2. Whether `openingSetAudit`'s exact SQL-aggregate reproduction (if kept)
   matches `build_opening_set_audit`'s Python output field-for-field against
   the real persisted `targets` array shape (subset-row parent-mapping
   fields in particular) — needs a representative row, not a synthetic
   fixture, to avoid shipping a silently-wrong audit count.

Given no production DB / representative fixture was available in this
sandbox (same limitation Pass 1/2 already noted for benchmark/latency
numbers), and the task's explicit instruction to stop and document rather
than guess when correctness can't be verified, this pass stopped after
confirming the refactor's shape and isolating its one real blocker, instead
of writing the migration extension and endpoint rewire un-verified. Steps
3-6 (production-shaped benchmark of the *new* path, `test_paid_response_boundary.py`
run, and new regression tests for the compact targets path) were not done
because there is no "final" implementation yet to benchmark or test.

### Recommended fast-follow (concrete, scoped)

1. Confirm against a real current publication row (staging DB, or a
   representative fixture pulled from prod) that
   `_has_enriched_set_rip_contract` is true for 100% of targets.
2. Extend `get_pokemon_rankings_sets_lens` (or add a sibling RPC) to also
   return the `openingSetAudit` counts as a SQL-computed aggregate over the
   unfiltered `payload->'targets'` array — or confirm with a product/eng
   decision that dropping the field from the targets response (it has no
   frontend consumer) is acceptable, which is the simpler fix.
3. Add `get_pokemon_rip_statistics_targets_compact_payload()`: RPC read
   (mirroring the existing sets-lens call pattern) → identity check → the
   three lens-compatible enrichment steps → non-silent fallback to
   `_load_pokemon_explore_rankings_snapshot_row`/full path only if
   `_has_enriched_set_rip_contract` is false or the RPC is unavailable → same
   response shape as today.
4. Regression tests: compact path never selects `ranking_payload_json`
   directly when the RPC is healthy; response byte-identical to the current
   full-path response for a real/representative row; `/explore/rankings/lens?lens=sets`
   itself unchanged; paid-response-boundary unaffected.
5. Re-run the Pass 1 memory benchmark methodology against the new path for
   the old/intermediate/final comparison table this pass could not produce.

## Pass 4 (this update): compact `/targets` reader shipped — the normal-path fix

Branch HEAD at the start of this pass: `8498d34a`. Using the production facts
supplied for this pass (34 targets, all opening; `setRipV1` enriched 34/34;
`meta.openingSetAudit`/`meta.opening_set_audit` already persisted with 0
subset/missing-mapping rows; full `ranking_payload_json` ≈2.74MB,
`productFamilyRankings` alone ≈245KB), this pass unblocked and shipped
Pass 3's fast-follow.

### What changed

- **New migration/RPC**:
  `supabase/migrations/20260904010000_add_rip_statistics_targets_compact_rpc.sql`
  adds `public.get_pokemon_rip_statistics_targets_compact(p_limit)` and its
  per-target projector `public.project_pokemon_rip_statistics_target(JSONB)`.
  Mirrors the existing `get_pokemon_rankings_sets_lens`
  (`20260830010000_tighten_compact_rankings_sets_lens_rpc.sql`) pattern —
  same publication CTE, same `is_opening_set` filter, same ordinality-ordered
  `LIMIT`/`GREATEST`/`LEAST` clamp to 1..200 — but projects the FULL
  Base+Plus target field contract `/targets` serves (every field in
  `_BASE_TARGET_FIELDS`/`_PLUS_TARGET_FIELDS`,
  `backend/domain/access/index_plan_access.py`), not the narrower Sets-lens
  contract. Several already-published nested objects (`setRipV1`,
  `financialRipV4`, `overallRipV10`, `publicRipContractV10`,
  `openingExperience`, `rankingsChase`, `rip`, `ripCore`) are passed through
  WHOLE rather than re-picked field-by-field, because
  `project_rankings_response`'s Plus branch expects the full published shape
  and does its own entitlement pick from there — no score/rank
  recomputation happens in SQL. `meta` is passed through unfiltered (it
  already excludes `productFamilyRankings`/`setRip`/`eraSetStrengthV1` —
  those are sibling top-level publication keys, not nested under `meta` —
  and it already carries the persisted `openingSetAudit`/`opening_set_audit`
  Pass 3 found this endpoint has zero frontend consumers to justify
  rebuilding). `get_pokemon_rankings_sets_lens` itself is untouched — a
  separate migration, a separate RPC, a separate function.
- **`backend/db/services/pokemon_public_snapshot_service.py`**: the old
  monolithic `get_pokemon_explore_rankings_snapshot_payload()` body was
  renamed to `_get_pokemon_explore_rankings_snapshot_payload_full()`
  unchanged, and the public entry point now: (1) calls the new compact RPC
  via `_load_pokemon_rip_statistics_targets_compact_row()`; (2) hands the row
  to `_build_compact_rankings_targets_response()`, which returns a response
  built ENTIRELY from the compact row (no mega-contract materialization) when
  the row's targets pass `_has_enriched_set_rip_contract()` and carry a
  persisted `openingSetAudit`/`opening_set_audit`, runs the same publication-
  identity check as the full reader (`_rankings_publication_identity_mismatches`,
  same fail-closed 503 `RIP_STATISTICS_TARGETS_PUBLICATION_SUPERSEDED` with
  the same fallback-cache-first behavior), and populates the same single-slot
  fallback cache (`base_payload={}` — the compact RPC never had
  `productFamilyRankings`/`setRip`/`eraSetStrengthV1` to exclude in the first
  place); (3) falls back EXPLICITLY (logged, never silent) to
  `_get_pokemon_explore_rankings_snapshot_payload_full()` when the compact
  RPC errors (rolling-deploy compatibility, same pattern
  `get_pokemon_explore_rankings_lens_payload` already uses for the Sets/Eras
  lenses), when `_has_enriched_set_rip_contract` is false (legacy
  publication — `upgrade_rankings_set_rip_contract_if_needed`'s
  `productFamilyRankings`-based rebuild only exists in the full reader), or
  when the persisted opening audit is absent. `attach_era_set_strength()` is
  NOT run on the compact path — Pass 3 confirmed no consumer of
  `getRipStatisticsTargets()` reads `eraSetStrengthV1` from this endpoint
  (the Rankings page's Eras tab calls the separate `lens=eras` endpoint), so
  omitting it is intentional, not a gap.
- **New tests**:
  `backend/tests/unit/db/services/test_pokemon_rip_statistics_targets_compact.py`
  (11 tests, all new, all pass) — healthy path never touches the table/mega-
  contract reader; response excludes `productFamilyRankings`/`setRip`/
  `eraSetStrengthV1`; persisted opening audit returned byte-identical;
  request-limit slicing/ordering; full `setRipV1` object survives the
  projection unmodified (Set RIP/Overall RIP parity); legacy incomplete
  Set RIP falls back to the full reader; missing persisted audit falls back
  to the full reader; compact RPC unavailable falls back to the full reader;
  publication-identity mismatch still fails closed with 503; fallback cache
  is populated from the compact contract after a healthy compact read; the
  Sets-lens RPC name/call path is untouched.
- **New benchmark**:
  `backend/scripts/benchmark_rip_statistics_targets_compact_memory.py` — see
  3-stage table below.

### Regression results

- `backend/tests/unit/db/services/test_pokemon_rankings_fallback_cache.py`:
  6/6 pass (unchanged from Pass 2 baseline; these tests' fake client has no
  `.rpc()`, so the compact attempt raises `AttributeError`, is caught, and
  falls through to the full reader exactly as these tests already expected —
  confirmed by rerunning them against this pass's code).
- `backend/tests/unit/db/services/test_pokemon_rip_statistics_targets_compact.py`:
  11/11 pass (new).
- `backend/tests/unit/db/services/test_rankings_lens_projection.py`: 5/5
  pass, unaffected.
- `backend/tests/unit/api/test_paid_response_boundary.py`: run this pass
  under `.venv-api-test` (has `fastapi`/`stripe` installed, unlike the
  sandbox default interpreter Pass 1-3 used) — **10/11 pass, identical to
  the documented baseline**. The 1 failure,
  `test_product_rankings_http_projection_plus_then_base`, exercises
  `/explore/product-rankings/overall` → `get_pokemon_explore_rankings_lens_payload(lens="products")`,
  a code path this pass did not touch; unchanged before/after this pass's
  edits.
- Base/Plus entitlement fields: `test_compact_response_keeps_full_set_rip_object`
  confirms the complete Plus `setRipV1` object (score/rank/tier/cohortSize/
  familyScores/participatingFamilies/...) survives the compact projection
  unmodified — `project_rankings_response()` in `index_plan_access.py` was
  NOT changed, so the full documented Plus field list (`calculation_run_id`,
  `run_at`, `pack_score`, `relative_pack_score`, `pack_rank`, `pack_tier`,
  `profit_score`, `relative_profit_score`, `profit_rank`, `profit_tier`,
  `safety_score`, `relative_safety_score`, `safety_rank`, `safety_tier`,
  `stability_score`, `relative_stability_score`, `stability_rank`,
  `stability_tier`, `prob_big_hit`, `roi_percent`,
  `p95_value_to_cost_ratio`, `p95_value_to_cost_rank`,
  `p95_value_to_cost_tier`, `rip`, `ripCore`, `openingExperience`,
  `collector_appeal_score`, `collector_appeal_rank`,
  `opening_desirability_score`, `opening_desirability_rank`,
  `opening_desirability_summary`) is projected by the new RPC's field list
  and left untouched by Python's `_pick`.
- Opening-audit parity: `test_compact_response_preserves_persisted_opening_audit_unchanged`
  asserts the served `meta.openingSetAudit`/`meta.opening_set_audit` equal the
  persisted fixture value exactly — no rebuild happens on the compact path.
- Ranking parity: `test_compact_response_respects_request_limit_and_ordering`
  asserts target order/identity is unchanged after slicing.

### Phase F — 3-stage memory/latency benchmark

Fixture: 34 targets (the verified live target count), 25 `familyScores`
entries/target, a 100-entry `productFamilyRankings` block — sized to the
same shape as the Pass 1/2 fixture, scaled to the real 34-target count
instead of a synthetic 200. No production DB credentials are available in
this sandbox; this is a representative fixture, consistent with every prior
pass's stated limitation.

| Metric | Stage 1 Original (pre-`1ee37cf9`) | Stage 2 Cache-only (`1ee37cf9`+`76795836`) | Stage 3 Compact-final (this pass) |
|---|---|---|---|
| RSS fresh | 96.64MB | 98.16MB | 98.68MB |
| RSS after 1st `limit=200` read | 96.92MB | 98.68MB | 98.69MB |
| RSS after 50 identical reads | 97.44MB (+0.52MB over 50) | 98.68MB (+0.00MB) | 98.69MB (+0.00MB) |
| Retained fallback-cache bytes (est.) | 152,200 (1 per-limit entry, unbounded key space in the real bug) | 145,667 (single slot) | 145,667 (single slot) |
| Source payload bytes (full mega-contract) | 152,200 | 152,200 | n/a — never read |
| Source payload bytes (compact) | n/a | n/a | 146,463 |
| Response bytes | n/a (not measured) | 152,933 | 146,662 |
| p50 latency | 10.38ms | 1.79ms | 0.78ms |
| p95 latency | 12.12ms | 2.65ms | 1.14ms |

Stage 1 vs Stage 2 reproduces Pass 1/2's finding at this fixture's smaller
(34-target, not 200-target) scale: both RSS-after-50 and retained-cache-bytes
stay flat in Stage 2/3, while Stage 1 keeps growing per distinct `limit`
(not exercised directly in this run, but the underlying per-limit `dict`
+ `deepcopy()` mechanism is unchanged from Pass 1's measurement).

**What Stage 2 → Stage 3 actually shows**: RSS-after-1/after-50 are flat and
statistically indistinguishable between Stage 2 and 3 at this fixture's
34-target scale (both ~98.7MB) — the RSS PLATEAU claim holds for both,
because Pass 2's single-slot cache already stopped the unbounded RSS growth.
What Stage 3 demonstrably improves over Stage 2, at this fixture's scale, is:
**response bytes** (146,662 vs 152,933, a ~4% reduction — small here because
this fixture's `productFamilyRankings` is only 100 entries; production's is
~245KB against a ~2.74MB total, a materially larger fraction) and **latency**
(p50 0.78ms vs 1.79ms, p95 1.14ms vs 2.65ms — roughly 2x faster, because the
compact path never deserializes/re-walks the excluded blocks). Do not read
this table as proof that the healthy-path mega-contract materialization was
a major RSS contributor at PRODUCTION scale beyond what Pass 2 already fixed:
this fixture is far smaller than the real ~2.74MB/34-target production
payload (152KB here vs 2.74MB in prod — the real `familyScores`/history/
image-URL fields are far larger per target than this fixture's padding), so
the per-request bytes/latency delta this table shows at 152KB scale should
be expected to be proportionally larger, not smaller, against the real
2.74MB payload. Confirming that scaling claim needs a production-shaped (or
production-pulled) fixture or a live Render RSS-over-time observation after
deploy — this pass's fixture size is a methodology limitation carried over
from Pass 1/2, not a new one introduced here.

### Remaining risks

- This pass's benchmark fixture (34 targets, ~152KB) is far smaller than the
  real production payload (34 targets, ~2.74MB) — the gap is per-target
  field richness (real `familyScores`, price history, image URLs) this
  fixture does not replicate at full size. The relative Stage 2→3 direction
  (smaller response, faster latency, RSS plateau preserved) should hold at
  production scale, but the absolute magnitude is unverified against
  production. Re-run the Render RSS-over-time observation (see "Production
  verification procedure" above) after this pass deploys.
- The compact RPC's rolling-deploy fallback path (RPC not yet migrated) was
  tested with a synthetic `RuntimeError`, not an actual PostgREST "function
  does not exist" error shape — the real error type/message from PostgREST
  was not verified against a live Supabase instance in this sandbox. The
  fallback is triggered by any exception from the RPC call (broad
  `except Exception`), so this is a low-confidence-but-likely-fine risk, not
  an unverified branch.
- `attach_era_set_strength()` is now skipped for the compact path's response,
  meaning a caller who happened to depend on `/explore/rip-statistics/targets`
  carrying a top-level `eraSetStrengthV1` block (undocumented, untraced by
  Pass 3, and not read by any file this pass or Pass 3 found) would silently
  stop receiving it. Pass 3's trace across all of `frontend/` found no such
  caller; this pass did not re-run that trace, only confirmed
  `attach_era_set_strength` reads/writes described in Pass 3 remain accurate
  against the current file.
- This P0 is now feature-complete per the assigned scope (Phases A-F,
  migration, tests, docs). The one open item is the production-scale RSS
  confirmation above — recommended as a post-deploy verification step, not a
  blocker to shipping this pass's code.

## Live-scale verification pass (2026-09-04, closing the fixture-scale gap)

Ran the ACTUAL `dd1d01c4` compact-reader code path against real production
data, read-only, via
`backend/scripts/verify_rip_statistics_targets_compact_live_scale.py`.

**Access method**: `backend/.env` carries real production
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` (the same credentials every other
backend script uses). The compact RPC migration
(`supabase/migrations/20260904010000_add_rip_statistics_targets_compact_rpc.sql`)
was confirmed NOT deployed to production yet (`PGRST202: Could not find the
function public.get_pokemon_rip_statistics_targets_compact`), and this pass
did not deploy it. So: option (a) from the verification brief — the real
`pokemon_explore_rankings_snapshot_latest` row for `tcg='pokemon'`,
`scope='rip-statistics'` was pulled ONCE, read-only, and the RPC's exact
projection logic (Plus scalar field allowlist + whole nested-object
passthrough, `is_opening_set` filter, `ORDER BY ordinality`, `LIMIT 200`) was
reproduced in Python and run in-process against the real payload through the
actual `_build_compact_rankings_targets_response` / `get_pokemon_explore_rankings_snapshot_payload`
code path. This is a live-DB-sourced payload run through the real code, not a
synthetic fixture.

### Test A — source scale + parity

- Real production full `ranking_payload_json`: **8,146,015 bytes** (34
  targets). This is materially larger than the ~2.74MB figure carried in
  earlier session notes for this same row/scope — the earlier figure was an
  approximation from a different check, not a re-measurement in this pass;
  this pass's number is a direct `len(json.dumps(...).encode())` on the row
  actually pulled.
- Real compact-equivalent payload (Plus-field projection, same 34 targets):
  **3,252,697 bytes** — about 40% of the full mega-contract's bytes. This is
  NOT comparable to the previously-cited ~246,575-byte `get_pokemon_rankings_sets_lens`
  figure: that RPC serves the narrower Rankings-page "Sets lens" contract,
  while this one serves the full Base+Plus `/rip-statistics/targets` field
  contract (per the migration's own design comment, several nested objects —
  `setRipV1`, `financialRipV4`, `overallRipV10`, `publicRipContractV10`,
  `openingExperience`, `rankingsChase` — are passed through WHOLE rather than
  re-picked, which is why it stays large relative to the Sets lens). Still a
  ~60% reduction vs. the mega-contract, from dropping
  `productFamilyRankings`/`setRip`/`eraSetStrengthV1` and unused Base/Plus
  scalar fields per target.
- Compact target count: 34/34. Target ordering parity: **true**. Base
  source-field parity: **true**. Plus source-field parity: **true**.
  Persisted `openingSetAudit`/`opening_set_audit` parity: **true**. Set RIP
  rank parity, Overall RIP rank parity, Financial RIP rank parity (by
  `target_id`): all **true**. No semantic difference found between the
  compact projection and the full mega-contract's canonical values.
- **One real (pre-existing, orthogonal) finding**: the live production row's
  persisted `meta.ripWeightsConfig` reports
  `overallRipVersion=overall_rip_v10_90_financial_v4_10_collector_appeal_v5`
  and `publicRipContractVersion=public_rip_contract_v10`, while this branch's
  `canonical_publication_identity()` now expects
  `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
  / `public_rip_contract_v11`. `_rankings_publication_identity_mismatches()`
  therefore flags this publication as superseded and both the healthy compact
  path AND the full mega-contract path would 503 "RIP Statistics rankings are
  being republished" against production RIGHT NOW — confirmed symmetric by
  running both paths against the same real payload. This is NOT a defect
  introduced by `dd1d01c4`: it is production not yet having been republished
  under the newer Overall RIP v12/CA7 identity, which is separately-tracked,
  already-known-pending work (see project memory: Overall RIP v4 CA7 blend —
  "backend done+tested, frontend/snapshots/live-validation pending"). The
  compact-reader P0 itself has zero interaction with this gate; it calls the
  exact same `_rankings_publication_identity_mismatches()` function the full
  reader always called. RSS/latency measurement below bypassed this
  orthogonal gate via monkeypatch (documented in the script) so the real
  payload could still be pushed through the compact code path end-to-end.

### Test B — fresh-process memory

Fresh interpreter, no `--reload`, real payload:

- RSS after imports + fetch settle: 160.09MB
- RSS immediately before first compact `limit=200` read: 160.09MB
- RSS immediately after the first read completes: 162.03MB (+1.94MB,
  consistent with materializing one ~3.25MB response payload, not the
  ~8.1MB mega-contract)
- RSS after a forced `gc.collect()`: 162.03MB (flat vs. post-read — nothing
  left to collect; the fallback cache intentionally retains the one compact
  slot, ~3.24MB, which is expected retained state, not a leak)

### Test C — production workload plateau (real payload, `limit=200`)

| checkpoint | RSS (MB) |
|---|---|
| before request 1 | 162.03 |
| after request 1 | 162.03 |
| after 5 | 162.03 |
| after 20 | 162.03 |
| after 50 | 162.04 |
| after 100 (extra confirmation round) | 162.04 |

RSS plateaus immediately and stays flat within measurement noise (±0.01MB)
across 100 consecutive real-payload requests — a genuine plateau, not a
zero-change artifact: the response object materializes once per request (not
retained beyond the fallback cache's single compact slot) and is released
each time.

Latency (100 requests, in-process, no network — measures the Python-side
build/slice/response-assembly cost only, not RPC round-trip time):
min=0.062ms, p50=0.065ms, p95=0.077ms, max=0.164ms.

Response bytes: 3,252,773. Source full bytes: 8,146,015. Source compact
bytes: 3,252,697. Cache slot count: 1. Estimated retained fallback-cache
bytes: 3,244,317 (the one compact slot — `base_payload={}` for the compact
path per `_build_compact_rankings_targets_response`'s design, so only
`raw_targets` + `meta` are retained).

### Test D — three-stage comparison table

| metric | Original (historical, above) | Cache-only (historical, above) | Compact-final (this pass, real payload) |
|---|---|---|---|
| Source scale | fixture, ~152KB | fixture, ~152KB | **real production, 8,146,015 bytes** |
| RSS fresh | n/a (reproduced standalone) | ~98.7MB (fixture) | 160.09MB (real payload + imports) |
| RSS after 1 | grows immediately (unbounded per-limit dict) | ~98.7MB | 162.03MB |
| RSS after 5/20/50 | keeps growing per distinct `limit` | ~98.7MB (flat) | 162.03-162.04MB (flat) |
| Peak RSS | unbounded across limit space | ~98.7MB | 162.03MB |
| Response bytes | full mega-contract, ~152,933 (fixture) | ~152,933 (fixture) | **3,252,773 (real)** |
| p50 latency | 10.38ms (fixture) | 1.79ms (fixture) | 0.065ms (real, in-process only) |
| p95 latency | 12.12ms (fixture) | 2.65ms (fixture) | 0.077ms (real, in-process only) |

Original/Cache-only columns are the historical fixture-scale numbers already
in this doc, not reproduced via git operations, per the verification brief.
The Compact-final column is the only one measured against real production
data in this pass; its absolute RSS/latency values are not directly
comparable to the fixture-scale Original/Cache-only columns (different
process, different payload scale, different measurement methodology —
in-process Python cost only vs. fixture-driven end-to-end), but the relative
shape (flat RSS plateau, smaller response, no growth across repeated
requests) is confirmed at real production scale, closing the gap the prior
two passes left open.

### Test E — fallback path sanity

Constructed the closest realistic PostgREST exception shape
(`PGRST202: Could not find the function public.get_pokemon_rip_statistics_targets_compact`
— this is, in fact, the literal exception string production currently raises
today, captured live during this pass's own RPC probe, not invented) and
exercised the compact-RPC-unavailable branch end-to-end against the real
payload:

- Healthy path used the compact reader (`snapshot.source =
  get_pokemon_rip_statistics_targets_compact`) when the RPC was reachable.
- RPC-unavailable condition followed the intentional legacy-compatibility
  fallback: `snapshot.source = pokemon_explore_rankings_snapshot_latest`,
  logged via the explicit `except Exception` branch and info-level fallback
  log line in `get_pokemon_explore_rankings_snapshot_payload`, not a silent
  degrade.
- No entitlement leakage observed (fallback response carries the same
  34-target opening cohort, same field contract as the full reader always
  served).
- No infinite retry/fallback loop: a second call after the RPC failure
  returned the same fallback source deterministically, not an escalating
  retry chain.
- Fallback cache stayed at exactly one compact slot (`identity_key` present,
  single slot, no per-limit growth) both before and after the fallback was
  exercised.

### Test F — entitlement smoke test

Ran `backend/tests/unit/api/test_paid_response_boundary.py` under
`.venv-api-test`: 10 passed, 1 failed. The failure
(`test_product_rankings_http_projection_plus_then_base`) is the known
pre-existing `/explore/product-rankings/overall` baseline failure (a
different endpoint's real-production-identity-gate 503, not this P0's
concern per the verification brief). The `/explore/rip-statistics/targets`
matrix test — `test_rip_statistics_http_matrix_cache_isolation_and_spoof_resistance`
(anonymous/Base/Plus/Premium-inheritance cache isolation and spoof
resistance for this exact endpoint) — **passed**.

### Verdict

No semantic defect found in the compact reader at real production scale.
Parity is exact. RSS plateaus immediately and stays flat across 100
consecutive real-payload requests. Fallback path behaves as designed. The one
real finding (production not yet republished under the newer Overall RIP
v12/CA7 canonical identity) is confirmed pre-existing, symmetric across both
the compact and full-mega-contract readers, and outside this P0's scope.

**P0 CLOSED.** The fixture-scale gap flagged at the end of the prior pass is
resolved: this pass ran the real code path against the real production
payload, read-only, without deploying the still-pending RPC migration.

### Production verification procedure

Render RSS trend to watch, post-deploy of `dd1d01c4` + the compact RPC
migration:
- Baseline context: ~513MB stable after a clean restart; ~1.073GB after the
  first heavy `/explore/rip-statistics/targets` request pre-fix; ~2.07GB
  immediately before the crash-triggering restart (against a ~2.147GB Render
  Standard instance limit). Post-fix, expect a substantially lower stable
  plateau (this pass's in-process measurement suggests the compact path adds
  only a few MB per request cycle, not hundreds) instead of any ratchet
  toward the instance limit.
- Watch Render's RSS graph for the first `?limit=200` request after deploy:
  expect a small, bounded step (single compact response + one retained
  fallback-cache slot), not the ~560MB jump seen pre-fix.
- Track HTTP 502/500/503 counts across the deploy window — a sustained
  503 `RIP_STATISTICS_TARGETS_PUBLICATION_SUPERSEDED` is expected until
  production is republished under the current canonical identity (separate,
  already-tracked work per project memory); 502s should not recur once RSS
  stops ratcheting.
- Check instance restart logs for absence of further forced restarts
  (Render's out-of-memory restart pattern from the original incident).
- Confirm health-check continuity (`/healthz` or equivalent) has no gaps
  correlated with `/explore/rip-statistics/targets` traffic.
- Correlate three traffic patterns against the RSS graph: (1)
  `/explore/rip-statistics/targets?limit=200` bursts, (2) homepage
  simulation-evidence requests
  (`/tcgs/pokemon/sets/<spotlight-set>/rip/simulation-evidence`), and (3)
  Market navigation bursts — before vs. after this deploy. Expect all three
  to show a flat-or-bounded RSS contribution post-deploy where pre-fix (1)
  in particular showed the ~560MB step.
