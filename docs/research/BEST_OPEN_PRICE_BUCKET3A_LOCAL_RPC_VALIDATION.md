# Best-Open Price Bucket 3A — Local RPC Validation Attempt (2026-09-13)

## Outcome: BLOCKED before any live-DB step

No live Postgres instance could be started in this environment, so none of steps 3-7
of the requested task (apply migration locally, seed fixtures, run the RPC scenario
matrix, run regressions) were executed. No results were fabricated or simulated.

## What was checked (step 1)

- `supabase/config.toml` and `supabase/migrations/` exist — this repo does have a
  Supabase CLI project layout (`supabase/migrations/`, `supabase/tests/`).
- `supabase` CLI is **not** on PATH (`supabase --version` → command not found).
- `npx supabase --version` **does** work and resolves to `2.117.0` (fetched via npx,
  not installed as a repo devDependency — checked `package.json`, no `supabase` dep
  present at repo root).
- `docker --version` and `docker info` → `docker` is not installed/on PATH at all in
  this sandbox. There is no Docker daemon available, which `supabase start` requires.
- No PostgreSQL binary is present anywhere reachable: no `psql`, no `postgres`/`pg_ctl`
  executable found on PATH (checked via both Bash `which` and PowerShell
  `Get-Command`), and no `C:\Program Files\PostgreSQL` install.
- Python is available on Windows (`C:\Users\Owner\AppData\Local\Programs\Python\Python38\python.exe`,
  found via PowerShell) but the Bash tool's own `python3`/`py` invocations hit the
  Windows Store stub (no real interpreter on that PATH), and in any case `asyncpg`/
  `psycopg2`/`psycopg` are irrelevant without a Postgres server to connect to.
- Searched `backend/tests/` for any existing live-Postgres test convention (grepped for
  `DATABASE_URL`, `SUPABASE_DB_URL`, `localhost:5432`, `127.0.0.1:5432`). The only hit,
  `backend/tests/unit/scripts/test_accept_market_explorer_variant_engine.py`, **mocks**
  `create_service_role_client` and asserts a redacted `DATABASE_URL` string appears in
  a constructed CLI command — it does not open a real DB connection. There is **no
  existing live-Postgres/live-Supabase test harness anywhere in this repository** to
  fall back on.

## Why the task could not proceed

Step 2 required starting `supabase start` (needs Docker) or an equivalent local
Postgres "the repo already relies on for tests." Neither precondition holds in this
sandbox:
- Docker is entirely absent (no CLI, no daemon).
- No standalone Postgres binary is installed.
- The repo's existing test suite does not use a live database anywhere — it mocks the
  Supabase client universally, so there is no established fallback pattern to imitate.

Per the task's explicit instruction ("If Docker is unavailable ... do not silently
fabricate results if no live Postgres can be started"), I stopped here rather than
inventing pass/fail results for the 20-scenario RPC matrix, writing a pytest file that
could never actually run against a real database in this environment, or claiming a
regression-suite result that never executed.

## What was NOT done (and remains to do, once a live Postgres is available)

- Did not run `supabase start` / `supabase db reset` / `supabase migration up`.
- Did not apply `20260913220000_create_budget_product_best_open_price_store.sql` (or
  its prerequisite `budget_product_ranking_rows` migration) to any database.
- Did not seed fixture rows.
- Did not write or run the pytest integration file for the 20-scenario RPC matrix
  described in the task (happy path, duplicate/missing/extra product, wrong source
  identity fields, wrong per-field values, cent-precision violation, status-invariant
  violation, atomic rollback, latest-pointer immobility, idempotency, differing-content
  refusal).
- Did not identify or fix any SQL bugs, since the RPC was never exercised.
- Did not run the existing regression suite (it would only exercise mocked paths
  anyway, per the grep above, so it wasn't a substitute for the live-DB matrix either).

## What is needed to unblock this

One of:
1. Docker Desktop/Engine installed and running in this environment (or a runner with
   it preinstalled), so `npx supabase start` can bring up the local stack; or
2. A standalone local PostgreSQL server (binary or Windows service) reachable at a
   known connection string, with `psql` or a Python DB driver available, so the
   migrations can be applied directly with `psql`/`asyncpg` bypassing the Supabase CLI
   entirely.

Once either exists, steps 2-7 of the original task can be executed as specified,
including writing the durable pytest file under `backend/tests/` and fixing any real
SQL defects the matrix surfaces (not weakening assertions).

## Reproduce this finding

```
supabase --version        # command not found
npx supabase --version    # 2.117.0 (works, via npx)
docker --version          # command not found
docker info                # command not found
which psql postgres pg_ctl # none found
Get-Command psql,postgres,pg_ctl -ErrorAction SilentlyContinue  # (PowerShell, empty)
Test-Path "C:\Program Files\PostgreSQL"                          # False
grep -rl "DATABASE_URL\|SUPABASE_DB_URL\|localhost:5432" backend/tests/
  # only hit mocks the client, does not open a live connection
```
