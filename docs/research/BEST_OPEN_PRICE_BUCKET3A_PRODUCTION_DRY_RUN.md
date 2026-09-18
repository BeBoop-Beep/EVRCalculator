# Best-Open Price Bucket 3A: Production Dry-Run Attempt (2026-09-15)

## CRITICAL FINDING FIRST

Production already contains a **live, published** Best-Open Price snapshot. This was
**not** done by this session and predates it. This task was scoped as a pure
read-only dry run against a database with no existing Best-Open Price
publication; that premise is stale.

```
budget_product_best_open_price_snapshots.id = aab485d9-cf94-489e-b05f-fec68c6f1905
built_at / published_at = 2026-09-14 19:04:10.19248+00
source_budget_snapshot_id = c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1
source_budget_published_at = 2026-09-08 20:20:33.705413+00
source_market_date = 2026-09-08
source_cohort_fingerprint = 5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b
source_full_market_row_fingerprint = e436f6a1034e53d51b1f8740ba3502571f63d1b4ffa9fd12f4bf71f0c49b78f6
resolved_count = 138, unresolved_count = 0
diagnostics_json.publication_mode = "production_canary_import_validated_bucket2x_artifact"
diagnostics_json.validated_bucket2x_exact_parity = true
diagnostics_json.content_fingerprint = 77ca5fc82e26d3a79b5b08e7d0f5b8c6744f99ecb5caead008e61943215e43a9
```

No mutating SQL/RPC was run by this session. This row was discovered by
read-only `SELECT`. Its existence, and the fact that `diagnostics_json`
records a deliberate "canary import" publication mode distinct from the
`publish_best_open_price_if_ready.py` orchestrator's normal engine-run
provenance, means a production write already happened via some other path
(another session, another operator, or manual RPC invocation) before this
task started. That is outside the scope of what I can verify from here and
is a fact for the user to confirm, not something I caused or can undo
(no mutations permitted).

## What I actually ran

1. **Local script attempt (failed at the network layer, not the data layer).**
   Command:
   ```
   python -m backend.scripts.publish_best_open_price_if_ready --dry-run \
     --json-report logs/bucket3a_prod_dry_run.json
   ```
   Credentials came from `backend/.env` (`SUPABASE_URL=https://zwxzxuuawalvwioadhmf.supabase.co`,
   service role key), matching this repo's existing convention for
   production-reaching scripts. The run failed with a Cloudflare `525 SSL
   handshake failed` from this sandbox's network egress reaching
   `zwxzxuuawalvwioadhmf.supabase.co` directly — an environment/network
   limitation, not a script or data bug. No request reached Postgres.

2. **Fallback: Supabase MCP `execute_sql`, SELECT-only**, against project
   `zwxzxuuawalvwioadhmf` (confirmed via `list_projects` as the only project,
   name "TheIndex", matching the ref given in the task). All statements run
   were `SELECT`; none were `INSERT/UPDATE/DELETE/DDL`; the publish RPC was
   never called.

   Queries run (verbatim, abbreviated where noted):
   - `select * from budget_product_ranking_latest ... join budget_product_ranking_snapshots ...` (schema-corrected after an initial column-name miss)
   - `select id, count(*) from budget_product_best_open_price_snapshots group by id`
   - `select * from budget_product_best_open_price_snapshots where id='aab485d9-...'`
   - `select column_name, data_type from information_schema.columns where table_name='budget_product_ranking_latest'`
   - `select column_name from information_schema.columns where table_name='budget_product_best_open_price_rows'`
   - `select count(*), count(*) filter (where status='resolved_below_market'), count(*) filter (where status='current_number_one_with_headroom'), count(*) filter (where status not in (...)), min(threshold_quantity), max(threshold_quantity) from budget_product_best_open_price_rows where snapshot_id='aab485d9-...'`

## Live source identity (current production authority)

```
budget_product_ranking_latest (ranking_method_version=budget_product_ranking_v1,
  allocation_method_version=budget_allocation_floor_quantity_v1)
  -> snapshot_id = c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1
  -> market_date = 2026-09-08
  -> updated_at  = 2026-09-08 20:20:33.705413+00
  -> cohort_fingerprint = 5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b
  -> eligible_cohort_count = 138
  -> full_market_budget = 1350.0
```

**The live Full Market ranking source has not moved since Bucket 2.x's
reference capture** (`docs/research/BEST_OPEN_PRICE_BUCKET2_FULL_COHORT_VALIDATION.md`
cites the identical `snapshot=c8853793-a2ac-4a62-a9a4-f5df7f9ed8a1`, identical
`cohort_fingerprint=5a33b0fa18fba5d30a7caf366af9ff4d32d7797040562d6480760426a5d30b6b`,
identical 138/22 products/sets, identical $1,350 budget). This is **zero
source drift**, not "expected drift" — the ranking authority is bit-identical
to the Bucket 2.x reference capture, which also means the already-published
row above is bound to that exact same source (not a newer one).

Because `already_published_for_identity()` in
`backend/scripts/build_budget_product_best_open_price_snapshot.py` keys
strictly on `(source_budget_snapshot_id, source_budget_published_at,
best_open_price_method_version)`, an actual dry run against this current
source would immediately short-circuit to `status: already_published` — it
would not re-run the 138-product engine at all, because there's nothing new
to compute.

## Parity check: published row vs Bucket 2.x reference

| Measure | Bucket 2.x reference | Live published (`aab485d9-...`) | Match |
|---|---:|---:|---|
| Source snapshot id | `c8853793-a2ac-...` | `c8853793-a2ac-...` | Yes |
| Cohort fingerprint | `5a33b0fa...` | `5a33b0fa...` | Yes |
| Products / sets | 138 / 22 | 138 rows | Yes |
| Full Market budget | $1,350 | $1,350.0 | Yes |
| Resolved | 138 | 138 (resolved_count) | Yes |
| Unresolved | 0 | 0 | Yes |
| `resolved_below_market` | 137 | 137 | Yes |
| `current_number_one_with_headroom` | 1 | 1 | Yes |
| Other statuses | 0 | 0 | Yes |
| Threshold quantity range | min 2 / P25 4 / median 11 / P75 33.25 / max 200 (quantity **delta**, not raw threshold_quantity) | raw `threshold_quantity` min 2, max 367 | Not directly comparable — reference table reports *quantity delta*, live rows store *absolute* `threshold_quantity`; ranges are plausible together (a delta max of 200 on top of a current allocation can land an absolute threshold near 367) but I did not do a per-row join to confirm exact delta = absolute − current for every row, so I am not asserting bitwise equality here, only that no row count/status figure is off. |
| `diagnostics_json.validated_bucket2x_exact_parity` | n/a (this is the reference itself) | `true` (self-reported by the publishing run) | Consistent, not independently re-derived by me |

Row-count-level statuses (138/138, 137/1/0 split) match the Bucket 2.x
reference exactly with the live, unchanged source. I did not re-run the
138-product engine myself (no re-computation happened; this was structural
verification against already-published data plus the unchanged live
source), so I cannot certify bit-exact P*/P*+1¢ values per row from this
session — that would require either working network access to actually
invoke the engine, or a row-by-row dump-and-diff against the Bucket 2.x
JSON artifact, which I did not do.

## Why I am not emitting the completion strings

1. **Production was not mutated by me** — confirmed: every statement I ran
   was a `SELECT`; the publish RPC was never called; `--commit` was never
   passed anywhere.
2. **But the task's premise — "the one remaining gate is a dry run before
   Bucket 3B canary" — is already stale.** Production already has a real,
   published Best-Open Price snapshot for this exact source identity, dated
   2026-09-14, produced through some other path outside this session
   (`diagnostics_json.publication_mode = "production_canary_import_validated_bucket2x_artifact"`).
   That means either (a) Bucket 3B canary already happened and this task's
   docs are out of date, or (b) something published to production without
   going through the reviewed dry-run gate described in this task. Both are
   facts the user needs to see and decide on — I should not paper over this
   with a clean "ready for canary" signal when canary-shaped production
   state already exists.
3. I could not actually execute the builder script against live production
   from this sandbox (network egress to the Supabase host failed at the TLS
   layer), so I cannot personally certify "the dry run ran cleanly" in the
   literal sense the task asked for — I only reproduced its read-only checks
   by hand via SQL.

## Bottom line

- No production mutation occurred in this session.
- Live Full Market ranking source is unchanged since Bucket 2.x's reference
  capture (same snapshot id, same fingerprint) — zero drift.
- A Best-Open Price snapshot for that exact source is **already published**
  in production (not by this session), with 138/138 resolved, 0 unresolved,
  and a 137/1/0 status split matching the Bucket 2.x reference exactly.
- I was not able to independently invoke the actual builder/engine script
  end-to-end due to a sandbox network limitation (Cloudflare 525 to the
  Supabase host), so this report substitutes direct read-only SQL
  verification of the same facts, as instructed as a fallback.
- **Flag for the user:** confirm who/what published `aab485d9-...` on
  2026-09-14 and whether that was an intended, reviewed Bucket 3B canary or
  an out-of-band write that should be investigated.
