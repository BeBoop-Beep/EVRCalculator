# Production TCGs Catalog Performance — Prompt 3 (2026-09-04)

## Scope

`/TCGs/Pokemon/Sets` → backend `get_pokemon_sets_catalog_payload()` in
`backend/db/services/pokemon_sets_catalog_service.py`, and the frontend
consumer `getPokemonSets()` in `frontend/lib/pokemon/pokemonSetsServer.js`.

## Before

### Request graph (per cold/revalidated request)
1. `tcgs` lookup (1 row) to resolve the Pokemon TCG id.
2. `sets` query with `.select("*")` filtered by `tcg_id`, ordered by
   `release_date desc, name` — one row per set, ALL columns.
3. **`pokemon_canonical_cards` paged scan**: for every 100-set chunk of
   `set_ids`, repeatedly `SELECT set_id FROM pokemon_canonical_cards WHERE
   set_id IN (...) RANGE offset..offset+999`, looping until a page returns
   fewer than 1000 rows, counting per `set_id` in a Python `Counter`.
4. `eras` lookup for the distinct `era_id`s present.

### Root cause
Step 3 scaled with the size of the **entire canonical card corpus** for the
requested sets, not with the number of sets. Every cold or revalidated
request to the Sets catalog transferred every `pokemon_canonical_cards` row
belonging to those sets (effectively the whole catalog's checklist rows) into
the Python process just to produce a per-set integer count, then discarded
the rows. This is unbounded by set count and grows without limit as the
canonical checklist grows.

### Card-count semantics (Phase B finding)
`sets[].card_count` in the payload is **the canonical checklist count**:
the number of rows in `pokemon_canonical_cards` for that `set_id`. This is
explicit in the code comment above the old computation:

> "Canonical checklist count is the frontend card-count source of truth. Do
> not fall back to public.cards/card_variants here; those rows can be
> marketplace or variant inflated."

`pokemon_canonical_cards` has a unique constraint on `(set_id, number, name)`
(migration `026_add_pokemon_canonical_cards.sql`), so counting rows per
`set_id` already reflects deduplicated canonical card identities, not
marketplace/variant-inflated rows. No other authoritative persisted count
(e.g. on `sets` itself) is treated as the display source — `official_card_count`,
`printed_total`, and `total_cards` are separate fields already passed through
unchanged for other consumers. This confirms the correct replacement is a
`GROUP BY set_id, count(*)` aggregate over the same table, not a different
data source.

## Fix

### Chosen architecture (Phase C, option 2 — single SQL aggregate)
Added `public.get_pokemon_canonical_card_counts_by_set(p_set_ids uuid[])`,
a `STABLE SECURITY DEFINER` SQL function returning one `(set_id, card_count)`
row per set that has at least one canonical card:

```sql
SELECT pcc.set_id, count(*)::bigint AS card_count
FROM public.pokemon_canonical_cards pcc
WHERE pcc.set_id = ANY(p_set_ids)
GROUP BY pcc.set_id;
```

Migration: `backend/db/migrations/20260904120000_add_pokemon_canonical_card_counts_by_set_rpc.sql`
(additive, `CREATE OR REPLACE FUNCTION`, `GRANT EXECUTE` to `service_role`
only — matching the existing RPC-grant convention in this codebase, e.g.
`20260828194500_add_set_rip_read_models.sql`). No destructive changes, no
unrelated schema work.

`backend/db/services/pokemon_sets_catalog_service.py::_load_canonical_card_counts`
now calls this RPC once per batch of up to 500 set ids (batching is
defensive headroom for catalog growth; the current Pokemon Sets catalog is a
few hundred sets, so in practice this is a single RPC round trip) and builds
the `{set_id: count}` dict directly from the returned rows. Sets absent from
the RPC result (zero canonical cards) are defaulted to `0` by the existing
`canonical_card_counts.get(set_id, 0)` call at the payload-assembly site —
unchanged from before, so the zero-card contract is preserved exactly.

Persistence/precomputation (Phase C option 3) was explicitly rejected: the
live aggregate is already O(sets-with-cards) per request, which is the
target complexity, so there was no case for adding a second maintenance
path with its own staleness semantics.

### `.select("*")` trim (Phase D)
`_load_primary_sets` now requests an explicit projection instead of `*`:

```
id, name, canonical_key, pokemon_api_set_id, era_id, series, release_date,
official_card_count, printed_total, total_cards, set_code, abbreviation,
logo_image_url, symbol_image_url, hero_image_url
```

This list was built by inventorying every `set_row.get(...)` access in
`get_pokemon_sets_catalog_payload()` (the only consumer of `_load_primary_sets`
rows) — `id` for identity/routing, `name`/`canonical_key` for
name/slug, `pokemon_api_set_id` for slug fallback and `set_code` fallback,
`era_id` for era lookup/join, `series`/`release_date` passed through as-is,
`official_card_count`/`printed_total`/`total_cards` passed through as-is,
`set_code`/`abbreviation` for the set-code fallback chain, and the three
image URL columns (`logo_image_url`, `symbol_image_url`, `hero_image_url`)
which are duplicated into both the legacy (`logo_url`/`symbol_url`/
`image_url`) and current key names in the response — both aliases are still
derived from the same three source columns, so nothing is dropped. `tcg_id`
is not needed in the row payload since it is already the query's filter
predicate, not a field read from the row.

### Index / query-plan verification (Phase E)
`pokemon_canonical_cards` already has `idx_pokemon_canonical_cards_set_id
ON public.pokemon_canonical_cards (set_id)` (migration
`026_add_pokemon_canonical_cards.sql`). The new aggregate's `WHERE set_id =
ANY(...) GROUP BY set_id` is served directly by that index (index scan +
group aggregate), so **no new index was added** — there was no plan
evidence to justify one, and the task explicitly disallows speculative
indexing.

No live DB access was available in this session to run
`EXPLAIN (ANALYZE, BUFFERS)` against production data; the plan-shape
conclusion above is based on the existing index definition and the query's
predicate/grouping column matching that index exactly (a standard btree
index scan is the expected plan for an equality/ANY predicate on the leading
indexed column). This is called out explicitly rather than asserting a
measured plan.

## Files changed
- `backend/db/migrations/20260904120000_add_pokemon_canonical_card_counts_by_set_rpc.sql` (new)
- `backend/db/services/pokemon_sets_catalog_service.py` (`_load_canonical_card_counts` rewritten to use the RPC; `_load_primary_sets` uses an explicit projection instead of `.select("*")`)
- `backend/tests/unit/db/services/test_pokemon_sets_catalog_service.py` (new — see Tests below)

Frontend: **no changes**. `frontend/app/TCGs/Pokemon/Sets/page.js` →
`getPokemonSets()` in `frontend/lib/pokemon/pokemonSetsServer.js` was
re-read after the backend fix. It already has: a 120s in-process success TTL
cache (`SUCCESS_TTL_MS = 120_000`) plus a shorter 404 TTL, an in-flight
promise join keyed on a constant cache key (so concurrent cold calls share
one backend fetch), and Next's own `fetch(..., { next: { revalidate: 900 } })`
layer. `normalisePayload()` reads only `id, name, slug, era, era_id, series,
release_date, card_count, set_code, logo_url, symbol_url, image_url` — every
one of those keys is still present, unchanged in shape, in the new backend
response, so no frontend change was required or made.

## After

### DB request count (per cold/revalidated request)
Unchanged shape at 4 logical steps (tcg lookup, sets, counts, eras), but
step 3 changed from "N page requests scaling with corpus size" to a fixed
small number of RPC calls (1 for the current catalog size, since it is well
under the 500-set batch size).

### Canonical-card rows transferred to Python
- **Before**: every `pokemon_canonical_cards` row belonging to the
  requested sets (effectively the full canonical checklist corpus for the
  Pokemon TCG) — unbounded, grows with catalog content.
- **After**: **zero** individual card rows. The RPC returns exactly one row
  per set that has ≥1 canonical card (a few hundred rows at most for the
  current catalog size, and that count is driven by number of *sets*, not
  number of *cards*).

### Response contract
Unchanged. `sets[].card_count` semantics are byte-for-byte identical
(canonical checklist count, 0 default for zero-card sets); all other set
fields, ordering (`release_date desc, name`), era grouping, image URLs, and
`meta.{warnings,sources,timings}` shape are unchanged. `sources.pokemon_canonical_cards`
still reports `"OK"` on success / `"FAILED"` with a warning on RPC failure,
matching the prior try/except contract.

### Latency / bytes
No live production DB access was available in this session to capture
before/after wall-clock p50/p95 or exact byte counts against the real
dataset. The structural before/after established here is the number of
DB round trips and rows transferred (see above), which is the dimension the
task identified as the actual scaling defect — request latency should track
that directly, but a live measurement pass is deferred to a follow-up
verification (same pattern as prior prompts' deferred live-browser
verification).

## Frontend re-audit (Phase G)

Re-read (not re-measured live, no browser available this session):
`frontend/app/TCGs/Pokemon/Sets/page.js` and `pokemonSetsServer.js`. No
structural change found or made — the process-level cache, in-flight join,
and Next revalidation are intact and were not touched. No additional
frontend bottleneck was identified through static reading that would justify
a code change without a live measurement to back it (per the task's
explicit instruction not to guess or redo stale image-optimization work).
**This is explicitly deferred**: a live-browser pass (cold/warm render time,
image request count/sizes, hydration cost) should be run once a live
environment is available, the same way Prompt 2 deferred live-browser
verification.

## Cache verification (Phase I)

Read-only verification of existing logic (not exercised against a live
backend this session):
- Cold: `setsCache` miss → no in-flight entry → fetch created, stored in
  `inflightRequests`, then cached with `SUCCESS_TTL_MS` on success.
- Concurrent cold: second caller sees `inflightRequests.has(cacheKey)` and
  awaits the same promise — one backend request for N concurrent callers.
- Warm (within 120s): `cached.expiresAt > now` returns cached data with zero
  backend requests.
- Refresh (after TTL expiry or explicit revalidate): one new backend
  request. No second cache layer was added.

## Tests (Phase F)

`backend/tests/unit/db/services/test_pokemon_sets_catalog_service.py` (new,
3 tests, all passing):
1. `test_card_counts_come_from_aggregate_rpc_not_full_corpus_scan` — proves
   counts (including a >1000-card set, no paging needed) come from exactly
   one RPC call, a zero-card set returns `0`, and any direct
   `.table("pokemon_canonical_cards")` access raises (a fake client that
   fails the test if the old per-row query path is used).
2. `test_catalog_ordering_and_metadata_preserved` — ordering and
   `meta.sources` contract preserved.
3. `test_no_pagination_helper_reintroduced` — static regression guard: fails
   if `.table("pokemon_canonical_cards")` reappears in the service source,
   and requires the RPC name to be present.

Run: `python -m pytest backend/tests/unit/db/services/test_pokemon_sets_catalog_service.py -q`
→ **3 passed**.

## Route smoke test (Phase K)

Structural/mocked proof only (no live backend/browser this session, labeled
accordingly): the same fake-client harness in the new test file exercises
`get_pokemon_sets_catalog_payload()` end-to-end (tcg lookup → sets → counts
→ eras → payload assembly) and asserts zero calls to
`pokemon_canonical_cards` as a table scan and exactly one aggregate RPC
call. A live cold→open-set→return→refresh browser pass is deferred pending
a live environment, consistent with Phase G/I deferrals above.

## Concurrent-work collisions

None. This work touched only `backend/db/services/pokemon_sets_catalog_service.py`,
one new migration file, and one new test file — none of which intersect the
listed concurrent-work areas (`market_explorer_query_planner.py`,
`OverallRipExplanationHierarchy*`, `chaseAccessibilityPresentationSelector*`,
`MarketBasedOpeningQualityBreakdown*`, `OVERALL_RIP_V12_UI_STANDARDIZATION.md`,
`logs/*.log`).

## Closure bar status

- Backend no longer scans/pages the canonical-card corpus in Python: **done**.
- Per-set counts correct (parity with prior semantics): **done**, verified by test.
- DB workload scales with sets, not cards: **done** (single GROUP BY aggregate).
- Unnecessary broad reads trimmed where safe: **done** (`sets` projection).
- Query plan healthy: **inferred from existing index**, not measured live — see Phase E note.
- Frontend cache/coalescing still correct: **verified by code re-read**, not live.
- Current bottleneck remeasured: **not performed live** (no browser/DB access this session) — explicitly deferred.
- Correctness (names/order/eras/images/routes/counts) unchanged: **done**, verified by test for counts; other fields verified by code inspection (projection matches every consumed field).

**Prompt 3 is NOT fully closed for live-measurement items** (Phase A/G/I/K
live timing numbers, and Phase E `EXPLAIN ANALYZE`), due to no live DB/browser
access in this session. All structural/code-level engineering work
(RPC + migration, service rewrite, projection trim, tests) is complete and
verified via unit tests. A follow-up session with DB/browser access should
run the deferred measurements and append them here rather than re-deriving
the architecture.
