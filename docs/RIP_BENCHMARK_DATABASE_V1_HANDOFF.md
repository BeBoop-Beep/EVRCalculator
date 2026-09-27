# RIP Benchmarking V1 — database handoff

Status: **DATABASE FOUNDATION DEPLOYED AND VERIFIED** on TheIndex, September 26, 2026. This is private additive storage and bounded reads, not a RIP-model change or a public feature activation. The scoring transform and source-certified daily builder remain backend work.

## Migration and verification

Mirrored migration:
- `backend/db/migrations/20260926233908_rip_benchmark_foundation_v1.sql`
- `supabase/migrations/20260926233908_rip_benchmark_foundation_v1.sql`

The Supabase CLI originally generated `20260926232343_rip_benchmark_foundation_v1.sql`. Both filenames were aligned to the actual version `20260926233908` assigned by `apply_migration`; SQL content is unchanged and no unrelated ledger history was repaired.

SQL: 32,790 bytes, SHA-256 `1950687e840d4694f38dde5e5df3f4de988857baa9cc7b86a18a04ca279688c5`. The production migration ledger and successful CI artifact match exactly. `backend/db/benchmarks/rip_benchmark_foundation_v1.sql` is the identical test source; CI enforces three-way byte parity.

Successful isolated PG17.6 workflow run: **36279959949**, source commit `38effa0896ab102cd4f06e69a4f6684a7fa8b2f6`, artifact `rip-benchmark-db-v1-evidence`. **46 checks passed**, including access denial, rollback, completeness, immutable history, idempotency, source/date checks, benchmark invariants, parent inheritance and bounded/cursor reads. Earlier predeployment syntax and alias failures were fixed before production application.

Production service-role smoke published four explicitly unavailable validation rows, retried idempotently, and read current plus two-row paginated history. The transaction was rolled back. Final counts: **0 headers, 0 rows**. Current correctly returns `unavailable/no_published_benchmark`; no backfill or invented scores exist. Both RLS flags, service-only policies, all six indexes, denied anon/authenticated access and invoker functions were verified live.

Before/after fingerprint of complete Overall-current and Collector-current rows, including Rankings/set-page generation IDs: `123867acf4d280e9f04e34fabde1702b`, unchanged. No existing model, source table, serving code or pointer was changed; no V14/V5 activation.

## Storage

`public.pokemon_rip_benchmark_publications_v1` is an immutable daily header/revision, uniquely published by `(benchmark_key, calibration_version, market_date)`. States are staged, published and superseded. Old revisions remain retained. It records four source-model versions, Collector run/lineage status, observed active Overall publication/model/date and both serving-generation IDs, V3 snapshot/contract/basis, cohort/source/request fingerprints, bounded manifest, predecessor, expected counts and timestamps.

`public.pokemon_rip_benchmark_rows_v1` stores exactly four metric rows per entity: financial, chase, collector and overall. Entities are set, era and sealed_product using canonical UUIDs. Products require parent_set_id. Row/header date consistency is enforced by a composite FK. No FK or cascade modifies canonical source authorities.

Model, benchmark and financial-evidence availability are independent. Missing model/benchmark values are NULL with explicit reasons, never zero. Missing calibration can retain an available canonical raw score/rank. Product Chase/Collector must be explicitly inherited from the parent set or unavailable; inherited rows cannot fabricate product ranks.

Rows hold raw model/reference values, 0–10 benchmark score, raw and score deltas, rank/cohort size, source model/date/entity/publication, calculation/result/Collector IDs, fingerprints, reconstruction status and bounded private lineage. Exact equal raw/reference requires exactly 5.0; greater/lower raw requires above/below 5. Finite numeric types reject NaN/infinities. SQL only subtracts deltas and validates invariants: it does not implement the scoring transform. Supply unrounded calibrated values; round only for display.

Typed financial fields: per-pack cost/EV, P05/P10/P25/P50/P75/P90/P95/P99, top-1% mean, recovery probability, conditional expected loss, modeled return-on-spend, mean outcome retention, normalized P10/P25/P50/P75/P90/P95/P99 and top-1% EV share. Missing optional statistics stay NULL. Available evidence requires cost, EV and matching date; products require exact calculation/result IDs. Set/era evidence requires compatible V3. Supplied quantiles remain monotone across NULL gaps.

## RPC contract

```sql
public.publish_pokemon_rip_benchmark_v1(
  p_header jsonb, p_rows jsonb, p_expected_previous_id uuid DEFAULT NULL
) RETURNS uuid

public.get_pokemon_rip_benchmark_current_v1(
  p_entities jsonb, p_benchmark_key text, p_calibration_version text
) RETURNS jsonb

public.get_pokemon_rip_benchmark_history_v1(
  p_entities jsonb, p_start_date date, p_end_date date,
  p_benchmark_key text, p_calibration_version text,
  p_limit integer DEFAULT 500, p_after jsonb DEFAULT NULL
) RETURNS jsonb
```

Writes: one atomic call, 1–1,250 entities / 4–5,000 metric rows, <=8 MiB row JSON. Header/row fields are allowlisted; row publication/date and generated deltas are server-owned. A benchmark/key/date advisory lock and predecessor comparison protect revisions; same-ID/same-content retries are idempotent. Order the row array deterministically because order participates in the request fingerprint. Entire invalid/incomplete writes roll back.

The publisher reads the active Overall pointer dynamically and compares the expected UUID; it records rather than locks or modifies that source pointer. Header source-model selections and the separately observed active release are distinct, especially for historical builds. Backend source proof remains mandatory: SQL shape checks do not certify semantic correctness of submitted fingerprints or cohorts.

Reads: `p_entities` is 1–10 distinct objects containing exactly entity_type and entity_id. Explicit benchmark key/calibration required. Current returns one latest publication, no stale per-entity fallback, at most 40 rows. History uses 1–366 inclusive days and 1–1,000 rows/page, with has_more/next_cursor. Cursor binds entity/window/version and current published revisions; revision changes force restart. ALL means bounded non-overlapping windows plus pagination, not an unbounded RPC. Missing dates remain gaps. Reads omit source_lineage, manifests, empirical artifacts and full historical RIP payloads.

Set caller-level request/transaction deadlines; function-local timeout settings are not a replacement for an end-to-end timeout. Keep concurrency and retries bounded. Executable synthetic request examples are in `backend/tests/integration/rip_benchmark_v1_postgres.py`.

## Indexes and security

Header PK(id), unique(id,market_date), `rip_benchmark_pub_daily_v1` partial unique(key,calibration,date DESC) WHERE published, and `rip_benchmark_pub_previous_v1` on non-null predecessor. Row PK(publication_id,entity_type,entity_id,metric_key) and `rip_benchmark_row_history_v1` on (entity_type,entity_id,market_date,metric_key,publication_id).

Both tables have RLS with service-role policies only. PUBLIC/anon/authenticated table and function privileges are revoked. Service role can SELECT/INSERT/UPDATE headers and SELECT/INSERT rows; no DELETE/TRUNCATE or row UPDATE. Guard triggers enforce immutability. All functions are SECURITY INVOKER with fixed empty search_path. The publisher, reads and argument helper are service-only. No public projection was added; enforce paid entitlement at the backend and never expose service credentials to the browser.

## Scale evidence

Disposable PG17.6: 22 sets + 2 eras + 138 products = 162 entities/day, four metrics, 366 days: **237,168 synthetic rows**. No production credentials/data were used. Fixture triggers were disabled only for bulk synthetic scale seeding after full contract tests; normal constraints remained enabled. This proves storage/read behavior, not production-source validity.

| Read | Indexed SQL ms | Full RPC ms |
|---|---:|---:|
| Current | 0.059 header lookup | 6.460 |
| 1D | 0.583 | 8.402 |
| 7D | 1.300 | 20.686 |
| 30D | 3.721 | 60.338 |
| ALL / 366-day page | 51.349 | 122.835 |

Ten entities requested for history; return cap 1,000 metric rows. Every history plan used rip_benchmark_row_history_v1; current used rip_benchmark_pub_daily_v1. Full EXPLAIN ANALYZE/BUFFERS JSON and results.json are retained in the run artifact. RPC timings include DB JSON projection, not HTTP/network. These are single-run isolated measurements, not production SLAs or full multi-page ALL timings. Separate live empty-table plans used both intended indexes; they are not loaded-production benchmarks.

## Audited authority and historical coverage

Observed active Overall publication `0f83d958-95aa-40f1-bcfa-ec550ec3a379`, source date **2026-09-10**, Overall V12 / Financial V4 / Chase V1 / embedded Collector V5. Rankings generation `723e7fb8-e671-45b6-9676-89ac3e7d58a2`; set-page generation `42139262-fea1-4168-89b7-2470c048e675`. These are observations, not hardcoded authority constants.

Independent Collector-current is V7, run `e282f26e-2136-4105-b0a3-f0974c4d9d70`, as-of September 11. Active Overall's embedded V5 has a NULL Collector run UUID. Do not fabricate that UUID, mix versions or recalculate Overall from current V7. Latest Opening Economics and 22 ready Chase sets are September 25. The latest product source has 138 results/138 products/22 calculation runs on September 25. Do not re-date older scores as fresh; only Collector can use an older source date with a proven effective interval.

Active Overall rows have **276 results for 138 products, 22 sets, 44 calculation runs**. All products have two differing raw scores and ranks (maximum score spread 2.1887). Backend must resolve the existing serving-generation selection and exact result authority; do not choose an arbitrary duplicate, average or rerank. This audit did not certify that downstream selection and did not repair canonical data.

Compatible published V3 snapshot dates: **2026-08-27; 2026-09-02, 04, 08, 09, 10, 12, 13, 14, 15, 24, 25**. Each has 22 set and 2 era entries: 264 candidate set-day + 24 candidate era-day financial slices, not a continuous series or proof that all four model benchmarks are recoverable. Contract pokemon-rip-stats-v3; basis all_modeled_products_per_pack_equivalent; methodology hierarchical_product_per_pack_empirical_v1; weighting equal-set_equal-family_equal-sku-v1. No pre-V3 reconstruction or backfill was performed.

Reusable temporal source: 2,178 persisted-exact Financial V4 product rows spanning Aug17–Sep10, 828 Overall V12 rows spanning Sep1–10, and Sep11 Collector V7 set observations (22 ready/106 unavailable). Those spans do not imply every day exists. No equivalent Chase/era temporal series was identified.

## Backend responsibilities / source gaps

1. Certify exact source contracts, dates, cohort/fingerprints and serving-generation result selection before building rows. Resolve current vs embedded Collector lineage explicitly.
2. Map era summaries (which expose eraName but not eraId) to canonical UUIDs through member-set era IDs/registry; reject ambiguous mappings. Do not invent historical IDs or era model aggregates.
3. Keep canonical model values distinct from per-pack EV/quantiles. Build product evidence from exact simulation results and verified pack counts, with guaranteed value included once. Parent-set Chase/Collector is inherited, never product-specific.
4. Implement the versioned scoring transform, benchmark reference, publication scheduler, proved-date backfill and entitlement-checked API. Missing evidence or calibration remains explicit unavailability; do not interpolate gaps.

The database foundation is ready for that backend publisher. First real benchmark publication, public serving activation, source remediation and model promotions are not performed by this migration.
