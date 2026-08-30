# Market Explorer Effort 1D acceptance runbook

The internal runner is `backend/scripts/accept_market_explorer_variant_engine.py`.
Every invocation writes `acceptance.json` and `acceptance.md` beneath a unique
UTC directory in `artifacts/market_explorer_acceptance/`. The database URL is
used only as a subprocess argument to `psql`; it is never written to artifacts.

Preflight requires direct PostgreSQL access to prove function signatures,
overload absence, indexes, RLS, and role privileges. REST-only preflight reports
those checks as `BLOCKED`, never `PASS`.

## Exact commands

Run from `D:\EVRCalculator` with `$env:DATABASE_URL` set to the separately
authorized representative database connection string.

```powershell
# 1. Preflight (read-only)
python backend/scripts/accept_market_explorer_variant_engine.py --preflight --database-url $env:DATABASE_URL --environment-label representative

# 2. Celebrations dry run (set be7c981b-c55e-4f60-a1b8-be922531452d)
python backend/scripts/accept_market_explorer_variant_engine.py --pilot celebrations --database-url $env:DATABASE_URL --environment-label representative

# 3. Celebrations bounded publication
python backend/scripts/accept_market_explorer_variant_engine.py --pilot celebrations --commit --batch-size 25 --database-url $env:DATABASE_URL --environment-label representative

# 4. Celebrations acceptance without another write
python backend/scripts/accept_market_explorer_variant_engine.py --pilot celebrations --verify-existing --database-url $env:DATABASE_URL --environment-label representative

# 5. Fossil dry run (set c86889c9-ea25-4caa-b63c-7aa0b9796da8)
python backend/scripts/accept_market_explorer_variant_engine.py --pilot fossil --database-url $env:DATABASE_URL --environment-label representative

# 6. Fossil bounded publication
python backend/scripts/accept_market_explorer_variant_engine.py --pilot fossil --commit --batch-size 25 --database-url $env:DATABASE_URL --environment-label representative

# 7. Fossil acceptance without another write
python backend/scripts/accept_market_explorer_variant_engine.py --pilot fossil --verify-existing --database-url $env:DATABASE_URL --environment-label representative

# 8. TEMP-only interval-vs-fact benchmark
python backend/scripts/accept_market_explorer_variant_engine.py --benchmark --database-url $env:DATABASE_URL --environment-label representative

# 9. Read-only high-impact coverage audit
python backend/scripts/accept_market_explorer_variant_engine.py --coverage --environment-label production-read-only

# 10. Resume a failed bounded publication after the last durable cursor
python backend/scripts/backfill_market_explorer_variant_intervals.py --commit --batch-size 25 --resume-after <LAST_DURABLE_SET_UUID:VARIANT_UUID>
```

The resume cursor is emitted by the failed run and therefore cannot be replaced
with a fixed UUID in this document. Preserve it exactly.

## Failure and deployment gates

- `--commit` is accepted only for a selected pilot or explicit full acceptance.
- Neither command contains a catalog-backfill mode. Full catalog population
  remains the separate Effort 1B backfill command and separate authorization.
- A non-PASS preflight prevents pilot execution.
- A backfill, integrity, current-basket, or parity failure stops the next pilot
  and benchmark.
- The benchmark creates only TEMP relations and retains raw psql output beside
  the structured report.
- Production migration deployment and both pilot writes require separate
  operator authorization; this effort performed neither.

## Deterministic architecture decision gates

The report refuses to choose without two paired interval/fact samples, fact
build time, and interval/fact storage ratio.

- `DECISION_A_INTERVALS`: every measured interval sample is at most 1 second
  and facts improve median latency by less than 25%.
- `DECISION_B_DAILY_FACT`: fact median is at least 40% faster, every fact sample
  is at most 1 second, and fact storage is at most four times interval storage.
- `DECISION_C_HYBRID`: interval wins at least one query class, facts win the
  broad tail, and fact median is at least 25% faster.
- Otherwise the result remains blocked or fails interactive gates.

These are mechanical gates over retained raw evidence, not an intuition score.

