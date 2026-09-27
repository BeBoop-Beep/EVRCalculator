# RIP Benchmark V1 — global financial reference database follow-up

## Result and scope

**DEPLOYED AND VERIFIED.** The same-day Pokemon-wide Opening Economics financial reference is now a typed, immutable part of each new benchmark publication. Current/history reads carry that publication's reference alongside entity economics; `benchmark_raw_value` remains the model-score reference.

Branch: `feat/rip-benchmark-global-reference-v1-20260926`, based on PR389 commit `8b84b7477175a6eb5f232732a60880016ca13e41`, which includes PR388. Neither dependency was merged or changed. This follow-up adds only the mirrored migration, database test, scoped CI workflow and this handoff. No calibration, frontend, scheduler, model promotion or real benchmark publication was implemented.

Production: TheIndex, migration applied at **2026-09-27 01:49:58 UTC / September 26 18:49:58 America/Phoenix**.

## Migration identity

- `backend/db/migrations/20260927014958_rip_benchmark_global_reference_v1.sql`
- `supabase/migrations/20260927014958_rip_benchmark_global_reference_v1.sql`

SQL: **19,025 bytes**; SHA-256:

```text
7ea44b23458b4edd3635592fc8b773eebdc11947d47604fc98f08c6b0735cd0d
```

The CLI originally generated `20260927014427_rip_benchmark_global_reference_v1.sql` in disposable CI. Mirror filenames were aligned to the version assigned by production `apply_migration`; SQL bytes did not change. The tested artifact, Git blob `40876d165856cc19a17988ded40969490d9e33bb`, both mirrors and production ledger match. The original foundation migration was not edited or reapplied. Do not manually reapply either migration to production.

## Typed publication fields and source mapping

The existing `public.pokemon_rip_benchmark_publications_v1` gains ten columns:

| Added column | Meaning / exact source |
|---|---|
| `global_financial_reference_status` | `available` or `unavailable` |
| `global_financial_reference_reason` | Explicit missing/incomplete reason; NULL when available |
| `global_cost_per_pack` | `openingEconomics.global.averageCostPerPack` |
| `global_expected_value_per_pack` | `openingEconomics.global.averageModelBreakEvenPerPack` |
| `global_modeled_return_on_spend` | `openingEconomics.global.modeledReturnOnSpend` |
| `global_mean_outcome_retention` | Optional `openingEconomics.global.meanOutcomeRetention`, never a replacement for return-on-spend |
| `opening_economics_source_market_date` | Exact snapshot row date; must equal publication date |
| `opening_economics_source_fingerprint` | Exact snapshot `source_run_fingerprint` |
| `opening_economics_input_fingerprint` | Source `openingEconomics.inputFingerprint`, when present |
| `opening_economics_global_fingerprint` | SHA-256 bound to snapshot/date/contract/basis/source fingerprints and exact global scope |

Reuse the existing typed `opening_economics_snapshot_id`, `opening_economics_contract_version` and `opening_economics_basis`. No duplicate snapshot identity, global entity UUID, entity-type change or new table is needed. Four numeric columns use the existing finite-numeric domain. Cost must be positive; EV/return/mean retention nonnegative. Return ratios are not incorrectly capped at 1. Proven zero is distinct from missing evidence.

## Publication behavior

New INSERT-only trigger `rip_benchmark_global_reference_capture_v1` invokes `capture_rip_benchmark_global_reference_v1()`. It reads the supplied snapshot by primary key once and copies the global scalars, without averaging set values or recalculating any statistic. It validates published state, same date, V3 contract, basis, methodology and weighting in source metadata and payload, plus complete global coverage and numeric types.

An absent snapshot/global/required value or incomplete coverage yields an explicit unavailable reference with NULL numeric values. An incompatible contract/date/basis/methodology or malformed numeric value refuses the transaction. Optional mean retention may remain NULL while the three required values are available. Existing publication rows receive `unavailable/not_captured_before_reference_v1`; this migration does not backfill or mutate their existing fields.

The existing `publish_pokemon_rip_benchmark_v1(jsonb,jsonb,uuid)` definition, header allowlist, request fingerprint and retry behavior are unchanged. The backend supplies its already-supported exact snapshot ID/contract/basis; new values are server-owned. Attempts to inject new reference header keys are refused by the existing allowlist. The unmodified PR389-generated request was accepted in disposable PostgreSQL with automatic reference capture.

Existing immutable-header protection automatically covers all new columns. Correcting a source snapshot cannot rewrite an already captured reference. An identical retry returns its frozen publication; a new publication revision is required to capture corrected source content. Superseded references remain retained. No existing RIP/Rankings/Collector source is modified by the trigger.

## Read contract

RPC signatures, root `contract_version='rip-benchmark-read-v1'`, parameter defaults, cursor validation, entity bounds and date limits remain unchanged:

```sql
get_pokemon_rip_benchmark_current_v1(
  p_entities jsonb, p_benchmark_key text, p_calibration_version text
) returns jsonb

get_pokemon_rip_benchmark_history_v1(
  p_entities jsonb, p_start_date date, p_end_date date,
  p_benchmark_key text, p_calibration_version text,
  p_limit integer default 500, p_after jsonb default null
) returns jsonb
```

Current includes `opening_economics_reference` at the top level and on each returned row. History includes it on **every row**, joined by the exact immutable `publication_id`, not by latest date or entity identity. The narrow helper `project_rip_benchmark_global_reference_v1(public.pokemon_rip_benchmark_publications_v1)` performs no queries. History projects once per distinct publication on the bounded page.

Reference object fields: `contract_version='rip-benchmark-global-reference-v1'`, `scope='pokemon'`, publication ID/date, status/reason, snapshot ID, source contract, basis, source date, three fingerprints, cost/pack, EV/pack, modeled return-on-spend and optional mean retention. A missing current publication has a NULL top-level reference and no rows.

For each financial chart row use:

```text
row.modeled_return_on_spend
row.cost_per_pack
row.expected_value_per_pack
row.opening_economics_reference.modeled_return_on_spend
row.opening_economics_reference.cost_per_pack
row.opening_economics_reference.expected_value_per_pack
```

Do not substitute `benchmark_raw_value`, `mean_outcome_retention`, or a set median. Check reference status independently of entity/model/benchmark availability.

Still **1–10 entities**, **366 inclusive days maximum per window**, **1,000 metric rows maximum per page**. ALL remains bounded windows and keyset pagination. Revision changes invalidate an outstanding cursor rather than mixing references. No source manifests, payload JSON or empirical artifacts are returned. No source-table read occurs in either read RPC; the test temporarily revoked source-table SELECT from service_role and both reads still succeeded.

## Security and performance

Existing RLS, service-role-only table grants/policies and all six indexes remain. New helper/trigger and updated reads are SECURITY INVOKER with empty search_path; PUBLIC/anon/authenticated execution is revoked. No public projection or client credential path is added. The existing paid entitlement boundary remains the backend's responsibility.

No new index is necessary: source capture uses the snapshot PK, page references use the publication PK, and history/current keep their existing indexed access paths. The source JSON is consulted only at publication INSERT, never for chart reads.

Disposable PostgreSQL 17.6 retained the foundation's **237,168 synthetic rows** (162 entities × four metrics × 366 days), then applied the additive extension and its available/missing-reference cases. Legacy scale rows intentionally remain unavailable; no evidence was invented for them.

| Full database RPC | Single-run execution ms |
|---|---:|
| Current | 6.277 |
| 1D | 8.854 |
| 7D | 22.676 |
| 30D | 58.256 |
| 366-day history page | 113.752 |

Ten entities requested; maximum 1,000 rows. The indexed 366-day row selection used `rip_benchmark_row_history_v1`. These are isolated fixture measurements, not production HTTP latency guarantees or the cost of retrieving every ALL-history page. Full EXPLAIN ANALYZE/BUFFERS plans are in the CI artifact.

## Validation evidence

Passing predeployment workflow **36286593838**, commit `a579bec771eb88eb3548ad72375c2f6fe48ec111`, artifact **10920294743** (`rip-benchmark-global-reference-v1-evidence`):

- **85** unchanged backend core tests passed.
- **46** unchanged foundation PostgreSQL checks passed.
- **44** new global-reference PostgreSQL checks passed.

Coverage includes exact source/date/precision, independent missing reference, wrong V3 contracts/bases/weights/dates, no averaging/recomputation, optional retention, zero vs missing, unsupported numerics, current/history source isolation, cross-date pagination, revision invalidation, retained superseded reference, immutability, public/authenticated denial, unchanged pointers, and PR389 request compatibility.

Initial CI passed the backend tests and 42 new database checks before a test-harness package-import error. The workflow was corrected to execute the harness as a module. No SQL change or production application occurred before the fully passing rerun.

Production service-role smoke used the actual **September 24 and 25** V3 snapshots, one real set and era, with all model scores deliberately unavailable. Exact global values and lineage matched, identical retries succeeded, current returned eight rows, and history returned **16 rows across six pages**. The entire transaction was **rolled back**. Final benchmark counts: **0 headers / 0 rows**. No real benchmark publication or historical backfill was retained.

Postdeployment verification at 2026-09-27 01:50:56 UTC confirmed the live migration checksum above, ten added columns, both validated constraints, six valid indexes, private grants, invoker functions, and:

```text
Overall/Rankings/embedded-set-page/Collector pointer fingerprint unchanged:
123867acf4d280e9f04e34fabde1702b
Existing publisher function definition SHA-256 unchanged:
893252a8d77fde3398802315ab3499d50bd0d041b307b7526820fc8621a4588a
Standalone set-page generation unchanged:
6bd24a8e-e0e1-4b33-86a1-a16d483f1b24
```

The twelve previously audited V3 dates have compatible global fields; this follow-up does not certify missing model history or fill date gaps. It does not activate Financial V5 or Overall V14. Database follow-up ends here; calibration and frontend work are outside this change.
