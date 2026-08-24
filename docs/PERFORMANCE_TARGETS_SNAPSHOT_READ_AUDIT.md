# Persisted Rankings Snapshot DB-Read Audit

**Question:** why does reading the already-published RIP rankings snapshot take as
long as it does?

**Answer:** it is not the database, the query, the index, the object design, the
retry wrapper, the connection, or the validation logic. **~600 ms of a ~667 ms
PostgREST call is the cost of moving a 2.8 MB JSON document across the
DB → PostgREST → Python boundary.** No production change was made in this pass,
because the only honest fix is to make the document smaller — a separate phase.

All figures below are **same-window**: one isolated backend process
(`uvicorn --port 8010`, no `--reload`), one published snapshot, measurements taken
back-to-back. The prior session's "~670 ms median" was deliberately not reused.

Snapshot under test: `updated_at = 2026-08-12 22:14:10.871643+00`, 34 targets.

---

## Current read architecture

```
GET /explore/rip-statistics/targets?limit=N
  backend/api/main.py:440  get_explore_rip_statistics_targets
    └── pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload   :1870
          ├── _sanitize_limit(limit, default=DEFAULT_RANKINGS_LIMIT, max=MAX_RANKINGS_LIMIT)
          ├── run_public_read_with_retry(                                                :1873
          │       _load_pokemon_explore_rankings_snapshot_row,                           :1792
          │       operation_name="pokemon_explore_rankings_snapshot",
          │       initial_client=service_read_client,
          │       client_factory=create_short_timeout_service_client)
          │     └── supabase-py → PostgREST
          │           table("pokemon_explore_rankings_snapshot_latest")
          │           .select("tcg,scope,ranking_payload_json,default_target_json,updated_at")
          │           .eq("tcg","pokemon").eq("scope","rip-statistics").limit(1)
          │     └── _first_row(result)                      # list index, not .single()
          ├── payload = row["ranking_payload_json"]         # already a decoded dict
          ├── _rankings_publication_identity_mismatches(payload)          # identity gate
          ├── payload_guarantees_canonical_set_value(payload)             # Set Value capability
          │     └── TRUE here → compatibility enrichment SKIPPED (confirmed live)
          ├── [target for target in raw_targets if is_opening_set_row(t)][:clamped_limit]
          ├── build_opening_set_audit(raw_targets)
          ├── resolved_payload = {**payload, targets, default_target, meta}
          ├── _LAST_SUCCESSFUL_RANKINGS_PAYLOADS[limit] = deepcopy(resolved_payload)     :1994
          └── return resolved_payload → FastAPI JSON serialization
```

Confirmed live on every measured request:
`snapshot.source = pokemon_explore_rankings_snapshot_latest`,
`snapshot.publicationIdentity = current`,
`sources.checklist_set_value_enrichment = SKIPPED_PUBLICATION_GUARANTEES_SET_VALUE`.
The healthy path is the path being measured — no fallback, no live rebuild, no
compatibility enrichment.

---

## Database object

`pokemon_explore_rankings_snapshot_latest` is a **plain TABLE** (`relkind = 'r'`),
total relation size 8240 kB, containing **exactly one row**.

It is **not** a view, materialized view, or RPC-backed object. There is no
`DISTINCT ON`, no window function, no join, no history scan, no JSON aggregation and
no subquery. **§15 does not apply: there is no underlying storage to bypass, because
the "latest" object *is* the storage.**

| Column | Type | Bytes (this row) |
| --- | --- | ---: |
| `tcg` | text | — |
| `scope` | text | — |
| `ranking_payload_json` | jsonb | **2,796,448 text / 1,222,533 TOASTed** |
| `default_target_json` | jsonb | 75 |
| `created_at` | timestamptz | 8 (not selected) |
| `updated_at` | timestamptz | 8 |

---

## Exact query, plan and indexing

```sql
SELECT tcg, scope, ranking_payload_json, default_target_json, updated_at
FROM public.pokemon_explore_rankings_snapshot_latest
WHERE tcg = 'pokemon' AND scope = 'rip-statistics'
LIMIT 1;
```

Indexes:

- `pokemon_explore_rankings_snapshot_latest_pkey` — `UNIQUE btree (tcg, scope)`,
  which is **exactly** the reader's two predicates.
- `idx_pokemon_explore_rankings_snapshot_payload_gin` — GIN on the payload; a
  write-side cost only, irrelevant to this read.

`EXPLAIN (ANALYZE, BUFFERS, VERBOSE)`:

```
Limit  (cost=0.00..1.01 rows=1 width=129) (actual time=0.050..0.051 rows=1 loops=1)
  ->  Seq Scan on pokemon_explore_rankings_snapshot_latest
        Filter: ((tcg = 'pokemon') AND (scope = 'rip-statistics'))
        Buffers: shared hit=1
Planning Time: 0.464 ms
Execution Time: 0.117 ms
```

The planner chooses a Seq Scan **because the table has one row** — on a single-page
relation that is strictly cheaper than an index descent. This is correct behaviour,
not a missing index. **No index should be created.**

That 0.117 ms defers TOAST detoasting. Forcing the payload to be fully detoasted,
decompressed and serialized:

```
EXPLAIN ANALYZE SELECT length(ranking_payload_json::text) FROM ... ;
  Seq Scan ... (actual time=47.048..47.969 rows=1)
  Buffers: shared hit=193
Execution Time: 48.068 ms
```

**True SQL-side floor ≈ 48 ms** (detoast + decompress + jsonb→text of 2.8 MB).
SQL/indexing is **not** the latency source.

---

## Layer timing

In-process harness re-executing the real service functions, n=25, warm-up discarded.

| Component | Min | P50 | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| C→D PostgREST call (incl. retry wrapper) | 663.5 | **713.9** | 740.5 | 748.1 |
| E payload extraction from row | 0.0 | 0.0 | 0.0 | 0.0 |
| F publication identity validation | 0.0 | 0.0 | 0.0 | 0.0 |
| G Set Value capability validation | 0.0 | 0.0 | 0.0 | 0.0 |
| H→I filter + slice + opening-set audit | 0.8 | 0.8 | 0.9 | 1.0 |
| H→I resolved payload dict spread | 0.0 | 0.0 | 0.0 | 0.0 |
| `deepcopy` into last-successful cache | 33.7 | **35.5** | 65.0 | 69.2 |
| J JSON serialization | 15.1 | 15.7 | 16.4 | 16.9 |
| **TOTAL service** | 715.2 | **766.4** | 792.9 | 799.7 |

End-to-end HTTP baseline, n=25, `limit=100`, warm-up excluded:

```
min=801 ms   p50=861 ms   p95=921 ms   max=930 ms
response bytes = 2,627,206   status = 200 (25/25)   retries = 0
warm-up (first request after process start) = 1121 ms
```

**The PostgREST call is 93% of service time.** Every validation step this
architecture added — publication identity, Set Value capability — is
**free at 0.0 ms**. They are not a cost worth optimizing.

---

## SQL vs PostgREST vs application

Same client, same window, n=15 per case:

| Query | P50 | Row bytes |
| --- | ---: | ---: |
| A. metadata only (`tcg,scope,updated_at`) | **67.5 ms** | 95 |
| B. `default_target_json` only | 49.2 ms | 100 |
| C. `ranking_payload_json` only | 696.0 ms | 2,796,474 |
| D. **production projection** | 666.8 ms | 2,796,669 |
| E. `select *` | 652.2 ms | 2,796,719 |

This is the decomposition the audit existed to produce:

```
SQL execution (detoast + serialize)      ~48 ms
Fixed PostgREST round trip               ~50-67 ms   (case A/B)
2.8 MB payload transfer                  ~600 ms     (D minus A)
Application deepcopy                      ~35 ms
Application JSON serialize                ~16 ms
FastAPI/HTTP response to client           ~95 ms     (861 HTTP - 766 service)
```

**Cases D and E are statistically indistinguishable.** Narrowing the projection buys
nothing, because the only column that costs anything is the one the reader genuinely
needs. The unused columns total 8 bytes (`created_at`). **§9's projection optimization
is already in place and has no headroom left.**

---

## Payload-size contribution

`ranking_payload_json` composition:

| Key | Bytes | % of payload |
| --- | ---: | ---: |
| `targets` | 2,788,813 | **99.7%** |
| `meta` | 7,517 | 0.3% |
| `default_target` | 75 | 0.0% |

Within `targets` (34 targets), largest keys:

| Key | Total bytes | % of targets |
| --- | ---: | ---: |
| `publicRipContractV7` | 586,608 | 22.4% |
| `publicRipContractV6` | 532,879 | 20.3% |
| `publicRipContractV5` | 394,150 | 15.0% |
| `financial_rip_v3_payload` | 297,824 | 11.4% |
| `financialRipV3` | 295,213 | 11.3% |
| `openingExperience` | 165,977 | 6.3% |
| `universalSetDesirability` | 73,205 | 2.8% |
| `publicRipContractV4` | 55,081 | 2.1% |

Two observations for the next phase, stated at the confidence the evidence supports:

- **Superseded contract versions V4 + V5 + V6 = 982,110 bytes, 37.4% of all target
  bytes.** Not removed here — out of scope by instruction — but this is where the
  document's mass is.
- `financialRipV3` and `financial_rip_v3_payload` together are 593,037 bytes (22.7%).
  They are **not** proven duplicates: 34 targets carry the camelCase object, 22 carry
  the snake_case one, and **0 pairs are byte-identical**. They are two co-existing
  representations that deserve a dedicated look, not an assumed redundancy.

### Limit semantics

| limit | HTTP p50 | Response bytes |
| ---: | ---: | ---: |
| 5 | 706 ms | 196,086 |
| 60 | 827 ms | 2,627,205 |
| 100 | 813 ms | 2,627,206 |
| 200 | 811 ms | 2,627,206 |

`limit=5` returns a **13× smaller response** but saves only ~105 ms (~12%). The full
2.8 MB persisted document crosses the DB/PostgREST boundary **before** slicing, so
the caller's `limit` reduces API response size only, not backend read cost. (Only 34
targets exist, so any limit ≥ 34 returns the whole cohort.) This is evidence for a
future storage/payload redesign; it was not redesigned here.

---

## Connection and retry contribution

| Measurement | Result |
| --- | ---: |
| Fresh client construction | 123.6 ms |
| First read on a fresh client | 920.1 ms |
| Second read on that same client | 651.2 ms |
| Warm shared client (p50) | 647.8 ms |
| First HTTP request after process start | 1121 ms |
| Steady-state HTTP (p50) | 861 ms |

Connection setup costs **~270 ms once** (920 − 651, corroborated by 1121 − 861) and
**0 ms thereafter**. It is a warm-up artifact, not a per-request cost, and is
correctly excluded from steady state.

Retry framework overhead, n=15:

```
bare operation        p50 = 706.3 ms
via retry wrapper     p50 = 669.3 ms
delta                       -36.9 ms
```

The wrapper measures *faster* than the bare call, i.e. its overhead is **below the
noise floor** of a ~670 ms network operation. It costs nothing. **Leave the retry
architecture exactly as it is** — reliability outranks an unmeasurable delta.

---

## Root-cause classification

### **C — 2.8 MB JSON payload size** (with a fixed ~50–67 ms of B underneath it)

Evidence:

1. SQL execution with full detoast is **48 ms** — 7% of the PostgREST call.
2. A metadata-only query over the identical table, index, client and connection is
   **67.5 ms**. That is the fixed cost of asking PostgREST anything at all.
3. Adding only `ranking_payload_json` takes the same request to **696 ms**.
   The delta — **~600 ms** — is attributable to nothing but the 2.8 MB document.
4. `select *` is no slower than the narrow production projection, so projection is
   not a lever.
5. Every application-side validation step measures **0.0 ms**.
6. Connection setup is one-time; retry overhead is unmeasurable.

Explicitly **not** the cause: A (database execution), E (connection setup),
F (object/view design — it is a one-row table), and the identity/Set Value validation
work this architecture added.

---

## Production change

### NONE — by rule, and by evidence.

§17 states: *"If the proven dominant cause is simply transferring the 2.8 MB JSON blob
through PostgREST then make NO production optimization here."* That is precisely what
was proven, so no production code was changed in this pass.

Each permitted safe example was evaluated and rejected on measurement:

| Candidate | Verdict |
| --- | --- |
| Narrow DB column projection | **Already implemented**; `select *` is no slower. Zero headroom. |
| Direct keyed lookup instead of a view | **Not applicable** — the object is a one-row table, not a view. |
| Stop retrieving unused large columns | **None exist**; unused columns total 8 bytes. |
| Remove redundant deep-copy work | **Rejected.** `deepcopy` is 35.5 ms — 4% of the 861 ms HTTP p50, below §17's "material improvement" bar, and it is the invariant that stops the stale-fallback cache from aliasing (and being corrupted by) the live returned payload. Trading a correctness guarantee for 4% is a bad trade. |
| Create an index | **Rejected.** Execution is 0.117 ms; the Seq Scan is optimal on one row. |

No change means §18 (semantic parity), §19 (before/after) and §20 (frontend sanity)
are not applicable — there is nothing to compare and nothing to regress.

---

## Tests

| Suite | Result |
| --- | --- |
| `test_explore_rip_statistics_service.py` + `tests/unit/api` | 13 passed |
| `test_pokemon_public_snapshot_service.py`, `test_public_read_retry.py`, `test_public_rip_publication_contract.py`, `test_publication_gate.py`, `test_set_publication_revalidation.py` | 225 passed, **1 pre-existing failure** |
| `ripStatisticsServerCacheIdentity.test.mjs` (frontend) | 6 passed |

The single failure is
`test_canonical_top_chase_history_forward_fills_only_missing_days_and_later_actual_wins`.
Its test file and the service it exercises are both unmodified at HEAD and no code
was changed in this pass, so it is pre-existing red, unrelated to this audit.

No production code was modified, so no build or frontend suite was required.

---

## Carry-forward reliability threads

### A. Top Chase load 503 — **UNRESOLVED LOAD-RELIABILITY THREAD**

40-way concurrency measured 6/40 (15%) `POKEMON_SET_TOP_CHASE_SNAPSHOT_READ_FAILED`
before the duplicate-request removal, and 0/40 in two runs after. The fix was
**client-side** and cannot have repaired a backend read failure; halving Top Chase
load may simply have moved the sample below the threshold. **Not fixed. Not claimed
fixed.** Needs its own backend investigation.

### B. Pull Rates duplicate — **REQUEST-LIFECYCLE FOLLOW-UP**

The original "instrumentation error" explanation was wrong: a duplicate Pull Rates
request **did** reproduce on 151 in the pre-Phase-2A production build. The Phase 2A
traces show 0 duplicate request kinds, but no focused lifecycle test yet pins
single-request semantics. Remains documented until such a test exists. It did not
reproduce during, and did not block, this audit.

---

## Next optimization

**A — targets public payload slimming.**

The measurements point at exactly one thing. The read is 861 ms; ~600 ms of it is one
2.8 MB document, and 99.7% of that document is `targets`. Nothing else on the read
path is worth touching: SQL is 48 ms, validation is 0 ms, retry is free, connection
setup is one-time, and projection is already optimal.

Payload slimming is also the only lever that compounds — it reduces the DB→PostgREST
transfer, the Python decode, the `deepcopy`, the JSON serialization and the 2.6 MB
HTTP response simultaneously, because all five are paid on the same bytes.

Best-evidenced starting point: the superseded `publicRipContractV4/V5/V6` blocks at
**982 kB, 37.4% of all target bytes** — with a consumer audit first, since removing
public fields is explicitly out of scope until proven unused.

Option B (snapshot storage/read architecture) is the correct *second* step and only
becomes attractive if slimming alone cannot bring the document down — the limit
semantics finding above (full cohort crosses the boundary regardless of `limit`) is
the evidence that would justify it.
