# Reliability boundary manifest — commit `2a51e351`

**Status: audit documentation only.** Nothing in this file reverts, moves, or
re-stages anything. Commit `2a51e351` ("more updates") is accepted as immutable
branch history on `fix/public-rankings-entitlement-regression`.

## Why this file exists

The daily RIP simulation publication reliability work was committed inside
`2a51e351`, a 46-file commit that also carries billing, Chase Stage XI research,
Market Explorer/frontend, and pricing/membership work. Separating it after the
fact would require rewriting a commit that is already on the remote. That was
rejected in favour of documenting the boundary, so a reviewer can audit the
reliability change in isolation without a history rewrite.

To read only the reliability portion of the commit:

```bash
git show 2a51e351 -- \
  backend/db/repositories/card_variant_prices_repository.py \
  backend/db/repositories/calculation_runs_repository.py \
  backend/db/services/calculation_run_persistence_service.py \
  backend/jobs/evr_runner.py \
  backend/scripts/run_all_v2_sets.py \
  backend/scripts/run_daily_opening_publication.py \
  infra/local/run_simulations.sh \
  infra/local/run_simulations_task.bat \
  supabase/migrations/20260901020000_add_calculation_run_market_date.sql \
  backend/db/migrations/076_add_calculation_run_market_date.sql \
  backend/tests/unit/db/repositories/test_card_variant_prices_api_error.py \
  backend/tests/unit/db/test_calculation_market_date_migration.py \
  backend/tests/unit/scripts/test_daily_opening_same_set_retry.py \
  backend/tests/unit/scripts/test_run_simulations_shell_contract.py
```

---

## IN SCOPE — the reliability change

### Production source

| Concern | File | Hunks in `2a51e351` |
| --- | --- | --- |
| **APIError fix** — `except APIError` at line 367 referenced an unimported name, so the intended handler raised `NameError` instead of catching the PostgREST failure | `backend/db/repositories/card_variant_prices_repository.py` | `@@ -7,6 +7,7 @@` — adds `from postgrest.exceptions import APIError` |
| **Calculation-run market-date persistence** — the promoted market date is written to the run row | `backend/db/repositories/calculation_runs_repository.py` | `@@ -598,6 +598,7 @@` (`market_date` parameter), `@@ -621,6 +622,8 @@` (payload write, truncated to 10 chars) |
| **Persistence-service propagation** | `backend/db/services/calculation_run_persistence_service.py` | `@@ -801,6 +801,7 @@` (parameter), `@@ -841,6 +842,7 @@` (forwards to the repository) |
| **EVR propagation** — the orchestrator forwards the promoted date from run metadata | `backend/jobs/evr_runner.py` | `@@ -643,6 +643,7 @@` — `market_date=metadata.get("market_date")` |
| **`--market-date` subprocess contract** + **exit 75** (transient) vs **exit 1** (deterministic) per-set classification | `backend/scripts/run_all_v2_sets.py` | `@@ -141,6 +141,7 @@`, `@@ -164,9 +165,10 @@`, `@@ -289,6 +291,11 @@` (argparse), `@@ -358,11 +365,17 @@` (exit-code selection) |
| **Coordinator: `--market-date` passthrough, same-set 15/30s retries, gate reread** | `backend/scripts/run_daily_opening_publication.py` | `@@ -77,6 +77,8 @@` (`SimulationOutcome` fields), `@@ -204,6 +206,9 @@` and `@@ -214,16 +219,26 @@` (retry loop + subprocess args), `@@ -454,7 +469,12 @@` (orchestration) |
| **Scheduler checkout guards** — production-mode verification, fail-closed refusals, optional origin fetch | `infra/local/run_simulations.sh` | `@@ -227,6 +227,8 @@`, `@@ -235,9 +237,12 @@`, `@@ -254,7 +259,7 @@`, `@@ -268,7 +273,7 @@`, `@@ -412,6 +417,17 @@` |
| **Invocation-local diagnostics** — failure text comes from this invocation, not the appended log | `infra/local/run_simulations.sh` | `@@ -412,6 +417,17 @@` |
| **Scheduled-task production opt-in** | `infra/local/run_simulations_task.bat` | `@@ -33,9 +33,10 @@` |

### Migrations

Both copies are added whole by `2a51e351` (+69 lines each, byte-identical):

- `supabase/migrations/20260901020000_add_calculation_run_market_date.sql`
- `backend/db/migrations/076_add_calculation_run_market_date.sql`

> **Superseded.** The versions committed in `2a51e351` used the rejected
> rename-and-wrap design. Both files are rewritten by the follow-up commit; see
> "Corrections applied after `2a51e351`" below. **Neither version has been
> applied to production** — the live view definitions were confirmed to be the
> original pre-migration ones.

### Tests

| File | Status in `2a51e351` |
| --- | --- |
| `backend/tests/unit/db/repositories/test_card_variant_prices_api_error.py` | added (+28) — APIError regression |
| `backend/tests/unit/db/test_calculation_market_date_migration.py` | added (+19) — **superseded**, see below |
| `backend/tests/unit/scripts/test_daily_opening_same_set_retry.py` | added (+34) — same-set retry/recovery |
| `backend/tests/unit/scripts/test_run_simulations_shell_contract.py` | modified (+14) — checkout guard contract |

---

## OUT OF SCOPE — unrelated work in the same commit

None of the following is part of the reliability change. It is listed so a
reviewer can skip it deliberately rather than by omission.

**Billing**
`backend/domain/billing/providers/stripe_provider.py`,
`backend/tests/unit/db/test_billing_effort4_migration.py`,
`backend/tests/unit/db/test_billing_migration_order.py`,
`backend/tests/unit/domain/billing/test_managed_payments_launch_contract.py`,
`backend/tests/unit/domain/billing/test_stripe_provider.py`,
`docs/BILLING_EFFORT2_STRIPE_BACKEND.md`, `docs/BILLING_EFFORT5_LAUNCH.md`,
and three renamed billing migrations
(`20260901000000_billing_effort1_foundation.sql`,
`20260901000001_billing_effort2_stripe_backend.sql`,
`20260901000002_billing_effort4_atomic_reliability.sql`).

**Chase Stage XI research**
`backend/research/chase_significance_stage11.py`,
`backend/scripts/build_chase_significance_stage11.py`,
`docs/research/CHASE_EXTREME_TAIL_STAGE11.md`,
`docs/research/CHASE_IDENTITY_SET_VALUE_STAGE9.md`,
`docs/research/CHASE_SEPARABILITY_STAGE10.md`,
`docs/research/chase_identity_blind_packet_v2.csv`,
`docs/research/chase_significance_stage11.json`.

**Market Explorer / frontend**
`MarketExplorerQueryBuilder.jsx` (+580) and its contract test,
`OpeningEconomicsEras.jsx`, `SetPackMetrics.jsx` (+435),
`CardChaseEfficiencyRankings.jsx`, `RankedProductTablePrimitives.jsx`,
`SetRipFamilyBreakdown.jsx`, `PokemonCardDetailClient.jsx`,
`ProductRipSection.jsx`, `SetMarketSignals.jsx`.

**Pricing / membership**
`PricingPageClient.jsx` (+263), `PlanLock.jsx`,
`PlanLockVisual.contract.test.mjs`, `upgradeFunnel.mjs`,
`upgradeFunnel.test.mjs`.

---

## Corrections applied after `2a51e351`

The follow-up commit is forward-only; it amends nothing.

### 1. The market-date migration partitioned on the wrong key

The `2a51e351` migration renamed both canonical views aside and wrapped them so
that the projected date became `COALESCE(market_date, legacy snapshot_date)`.

That relabels the date only **after** the legacy UTC-date partitioning has
already selected one row per UTC day. Both directions fail:

- two runs straddling UTC midnight that carry the **same** promoted date survive
  as two rows, then get relabelled identically — two "daily latest" rows for one
  business day;
- two runs sharing one UTC day that carry **different** promoted dates are
  collapsed before the wrapper can tell them apart.

**Correction.** `public.calculation_history_daily_latest` is rebuilt in place
with `COALESCE(cr.market_date, cr.created_at::date)` used in **both** the
projected `snapshot_date` and the `row_number()` PARTITION BY. Column names,
types, order, joins, filters and calculations are otherwise the production
definition verbatim. No rename, no legacy view, no second daily-history
contract, no backfill.

`public.calculation_history_trend` is **not** recreated. It selects from
`calculation_history_daily_latest`, so it inherits the corrected day identity
automatically, and its P95 carry-forward is preserved exactly by leaving it
alone. `CREATE OR REPLACE` (rather than `DROP`) is what makes this possible.

### 2. The migration broadened access

The `2a51e351` version ended with
`GRANT SELECT ON ... TO anon, authenticated, service_role`, directly undoing
migration `075_harden_remaining_calculation_authority.sql`, which had revoked
exactly those roles. It would also not have worked: the views are
`security_invoker` and neither role holds SELECT on `public.calculation_runs`.

**Correction.** The migration issues no GRANT or REVOKE at all, and
`CREATE OR REPLACE` preserves the existing ACL.

Recorded production state (read-only query, taken **before** any migration —
the corrected migration has **not** been applied, so this is also the current
state):

| relation | owner | reloptions | relacl | RLS |
| --- | --- | --- | --- | --- |
| `calculation_history_daily_latest` | postgres | `{security_invoker=on}` | `{postgres=arwdDxtm/postgres, service_role=arwdDxtm/postgres}` | n/a (view) |
| `calculation_history_trend` | postgres | `{security_invoker=on}` | `{postgres=arwdDxtm/postgres, service_role=arwdDxtm/postgres}` | n/a (view) |
| `calculation_runs` | postgres | — | `{postgres=arwdDxtm/postgres, anon=awdDxtm/postgres, authenticated=awdDxtm/postgres, service_role=arwdDxtm/postgres}` | **enabled** |

Note that `anon` and `authenticated` hold `awdDxtm` on `calculation_runs` —
**no `r`**, i.e. no SELECT. The expected post-migration ACL is byte-identical to
the table above; `CREATE OR REPLACE VIEW` does not touch privileges, and the
migration contains no grant statements. Re-run this query after deployment and
compare:

```sql
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.reloptions, c.relacl
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('calculation_history_daily_latest',
                    'calculation_history_trend', 'calculation_runs');
```

### 3. The migration test proved nothing

`test_calculation_market_date_migration.py` as committed asserted SQL substrings
and then "tested" the rollover with:

```python
assert {promoted for _instant in utc_instants} == {"2026-08-31"}
```

The comprehension ignores its own loop variable, so the assertion is true for
every possible input. It could not have failed, and it never touched
partitioning — which is where the defect was.

**Correction.** The replacement extracts the `ranked` CTE **from the shipped
migration file**, translates it mechanically to SQLite, and executes it against
fixtures. Mutation-checked: reverting the PARTITION BY to `created_at::date`
fails 4 tests, including both rollover cases.

### 4. Scheduler hardening

- `PUBLICATION_FETCH_ORIGIN` `0` → `1`. Without a fetch, the HEAD-vs-origin
  check compares against whatever `origin/main` happened to be the last time
  git ran in that checkout; a worktree that has not fetched for a week validates
  cleanly against a week-old commit. A failed fetch is already fail-closed in
  `run_simulations.sh`.
- `ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT` is now pinned to `0` rather than left
  unset. A scheduled task inherits the ambient machine/user environment, so an
  override exported for an earlier manual emergency run would silently disable
  every checkout guard at 3am. The override remains available to an operator who
  sets it deliberately on the shell path.

---

## PostgreSQL evidence for the corrected day identity

Executed **read-only** against production PostgreSQL 17.6 (fixture rows supplied
as `VALUES` inside a CTE — no table read, no write, no DDL, no migration),
comparing the corrected partition key against the legacy one:

| target | fixture | LEGACY (UTC) | CORRECTED |
| --- | --- | --- | --- |
| `s1` | A 08-31T23:59Z, B 09-01T00:01Z, both promote **2026-08-31** | **2 rows** — 08-31→A, 09-01→B | **1 row** — 08-31→**B** (newest wins) |
| `s2` | C 09-01T02:00Z promotes 08-31; D 09-01T20:00Z promotes 09-01 | **1 row** — 09-01→D (08-31 lost) | **2 rows** — 08-31→C, 09-01→D |
| `s3` | E 08-31T23:59Z, F 09-01T00:01Z, both `market_date IS NULL` | 2 rows — 08-31→E, 09-01→F | **2 rows — identical** (history preserved) |
| `s4` | G 09-01T01:00Z legacy; H 09-01T05:00Z promotes 09-01 | 1 row — 09-01→H | 1 row — 09-01→H (deterministic) |

The same four fixtures are asserted in
`backend/tests/unit/db/test_calculation_market_date_migration.py`.

---

## Deployment status

**Nothing has been deployed and no production database mutation has been
performed.** The corrected migration is committed but **not applied**. The live
`calculation_history_daily_latest` and `calculation_history_trend` definitions
are still the original pre-migration ones, and `calculation_runs` does **not**
yet have a `market_date` column.

Deployment order matters: `calculation_runs.market_date` must exist before any
code path writes it. The reliability code from `2a51e351` sends `market_date` in
the insert payload whenever a promoted date is supplied, so running the daily
publication against an unmigrated database would fail on an unknown column.
