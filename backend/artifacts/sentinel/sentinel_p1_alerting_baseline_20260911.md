# inDex Sentinel — Prompt 1 Alerting Baseline

Date: 2026-09-11 (America/Phoenix)

Status: `SENTINEL_P1_CODE_COMPLETE_VM_VERIFICATION_PENDING`

## Scope

Prompt 1 hardens the existing alert-dispatch/watchdog foundation only. It does **not** build the Sentinel incident engine, enable self-healing, mutate production data, change cron, send notifications, deploy production, or repair current publication divergence.

## Repository

- Repository: `BeBoop-Beep/EVRCalculator`
- Isolated branch: `feature/sentinel-p1-alerting-baseline-20260911`
- Connected GitHub `develop` starting SHA: `05fadb2272bc657b2df1c5a3aa28b9f4b53b5f2b`
- Local operator state reported separately: Market Explorer Remap Phase 2 completed through `56be66b9b56b30780536385e3c0829df2c251b49`, but that commit was not visible on the connected GitHub remote during this run.
- Integration rule: **do not merge this branch directly until it has been rebased/cherry-picked onto the operator's newer local `develop` lineage once that lineage is visible remotely.**

Changed implementation/test files:

- `backend/alerts/market_freshness_watchdog.py`
- `backend/alerts/dispatcher.py`
- `backend/scripts/validate_alerting_deployment.py`
- `backend/tests/unit/alerts/test_market_freshness_watchdog.py`
- `backend/tests/unit/alerts/test_dispatcher.py`
- `backend/tests/unit/scripts/test_validate_alerting_deployment.py`

This report is the only additional artifact.

## Confirmed live observations

Read-only observations made before code changes:

### Alert delivery

- Pending, unsent, unsuppressed alert rows: **143**
- Pending error/critical rows: **69**
- Oldest pending row: **2026-08-25**
- Newest pending row: **2026-09-11**
- Rows ever marked sent: **0**
- `last_sent_at`: **null**
- New alert rows continue to be created.

Conclusion: detection is producing alert events, but successful delivery has not been demonstrated.

### 2026-09-11 scrape batch

- Batch id: `48`
- Status: `complete`
- Expected sets: `165`
- Succeeded sets: `165`
- Failed sets: `0`
- Missing sets: `0`
- Runtime branch recorded by batch: `main`
- Runtime SHA recorded by batch: `4de24f1bdf0635527cf0d4837d5a69d152c4dc2d`
- Runtime recorded as dirty: `true`

No attempt was made to clean or modify the VM runtime.

### Public publication authorities observed

At the read-only baseline, user-facing authorities were not aligned on one market date:

- Set Value latest: `2026-09-11`
- Sealed Market latest: `2026-09-10`
- Set Market dashboard latest: `2026-09-10`
- Global Market snapshot: `2026-09-09`
- Global Market Index latest: `2026-09-09`
- Rankings payload market date: `2026-09-08`

The latest market-quality row for `2026-09-11` was `INCOMPLETE`; it was not treated as permission to publish.

Prompt 1 intentionally does **not** repair this divergence.

### Render / dependency behavior

- Render production `/health` continued to return HTTP 200 during the observed window.
- Render application logs also recorded a Supabase/Cloudflare HTTP 522 timeout while reading the compact Homepage Rankings lens, after which application fallback behavior was used.

Conclusion: `/health` proves process liveness, not database/product correctness. Sentinel must keep these concerns separate.

## Confirmed root causes fixed in code

### 1. Watchdog schema-contract defect

`backend.alerts.market_freshness_watchdog.load_watchdog_state()` queried:

`pokemon_set_market_dashboard_snapshot_latest.market_date`

The live/repository contract uses:

`pokemon_set_market_dashboard_snapshot_latest.latest_market_date`

The watchdog can therefore fail while loading state before it reaches its stale/divergence alert logic.

Fix:

- use the canonical `latest_market_date` column explicitly
- add DB-loader contract coverage that rejects unknown columns

### 2. Watchdog execution failure was not structured

A state-load/schema/database exception could terminate the cron process without producing a normal watchdog result.

Fix:

- state-load exceptions now produce a bounded structured `market_watchdog_execution_failed` failure
- normal mode attempts one deduplicated critical alert
- read-only `--health` mode never queues that alert
- if alert insertion cannot succeed, the report remains unhealthy and the CLI still exits nonzero rather than pretending success

### 3. Dispatcher backlog did not participate in health

`get_dispatcher_health()` already measured backlog age/count and logged warnings/errors, but an old queue did not make `healthy=false`.

Fix:

- add explicit `backlog_warning`, `backlog_critical`, `backlog_healthy`, `recent_delivery`, and `delivery_progress_healthy` fields
- an oldest pending unsuppressed alert at/above `ALERT_BACKLOG_CRITICAL_AGE_MINUTES` now makes health fail
- a fresh queue remains healthy
- a high but fresh count is diagnostic only
- recent successful delivery is reported as progress but does not hide an already stale backlog

### 4. Cron validator accepted unsafe text matches

The old validator accepted any crontab text containing both module names, including commented-out or unlocked entries.

Fix:

- parse active five-field cron entries only
- ignore comments/environment lines
- dispatcher canonical cadence: every minute
- watchdog canonical cadence: every five minutes
- each canonical entry must use nonblocking `flock -n`
- validation is host-path agnostic

## Suspected but not yet proven operational cause of zero delivery

The database proves that no alert has ever been marked sent, but this run does **not** have direct SSH access to the scraper VM and therefore does not claim which of the following is the actual active cause:

- `ALERTS_ENABLED=false`
- missing/unconfigured Slack webhook
- dispatcher cron absent or malformed
- watchdog cron absent or malformed
- cron service issue
- dispatcher repeatedly failing at runtime
- some combination of the above

Those must be resolved with read-only VM verification before activation.

## Verification

Because the execution environment could not clone GitHub over the network, the focused changed modules/tests were mirrored into an offline Python harness with only the Supabase import stubbed. No production calls were made by the harness.

Results:

- Watchdog tests: **9 passed**
- Dispatcher tests: **13 passed**
- Cron-validator tests: **7 passed**
- Combined focused harness: **29 passed**
- Python compile validation of the three changed implementation modules: **passed**

Full repository test execution remains required after this branch is rebased onto the operator's newer `develop` lineage.

## Historical backlog activation procedure

Do **not** allow fixing the dispatcher to dump the historical queue into Slack.

Activation must happen in this order:

1. Record a fresh backlog snapshot grouped by `alert_type` and severity.
2. Choose an explicit UTC activation cutoff immediately before delivery activation.
3. Preserve every historical database row.
4. Run suppression in dry-run mode only:

```bash
python backend/scripts/suppress_historical_alert_backlog.py \
  --before <ACTIVATION_CUTOFF_UTC> \
  --dry-run
```

5. Human-review the row count, oldest/newest timestamps, and severity/type breakdown.
6. Only after explicit approval, suppress pre-activation delivery while preserving rows:

```bash
python backend/scripts/suppress_historical_alert_backlog.py \
  --before <ACTIVATION_CUTOFF_UTC> \
  --commit \
  --reason "historical backlog suppressed before Sentinel alert delivery activation"
```

7. Verify the pending unsuppressed queue contains only post-cutoff events.
8. Load production environment without printing secrets and run:

```bash
python -m backend.alerts.dispatcher --health
python backend/scripts/validate_alerting_deployment.py
```

9. Only with explicit operator approval, send exactly one dispatcher test message:

```bash
python -m backend.alerts.dispatcher --health --send-test
```

10. Generate or wait for one controlled post-activation alert and prove it transitions to `sent=true`.
11. Re-run dispatcher health and prove the delivery backlog is healthy.

Historical critical rows remain preserved for audit even when delivery is suppressed.

## Required read-only VM verification

Before Prompt 1 can be considered production-activated, verify on the scraper VM:

```bash
git status
git branch --show-current
git rev-parse HEAD
git diff --stat
crontab -l
sudo systemctl status cron --no-pager || sudo systemctl status crond --no-pager
```

Then, after loading `backend/.env` without printing secrets:

```bash
python -m backend.alerts.dispatcher --health
python -m backend.alerts.market_freshness_watchdog --health
python backend/scripts/validate_alerting_deployment.py
```

Expected behavior after the watchdog code fix:

- no invalid dashboard-column exception
- a structured report is printed
- current stale/divergent authorities produce unhealthy status/nonzero exit
- `--health` queues no new alert rows

## Production mutations

**NONE.**

This run did not:

- touch `main`
- deploy Render or Vercel
- modify production DB rows
- apply migrations
- suppress alerts
- mark alerts sent
- send Slack messages
- change VM cron
- change VM environment variables
- clean the dirty VM runtime
- force-publish or repair current market data

## Remaining blockers / next step

1. Push/surface the operator's newer local `develop` lineage containing Market Explorer Phase 2 (`56be66b9...`).
2. Rebase/cherry-pick this isolated Sentinel work onto that lineage.
3. Run the repository's real focused tests there.
4. Perform the read-only VM checks above.
5. Only after reviewing the historical backlog dry run should notification delivery be activated.

Once those steps pass, Prompt 1 can move from code-complete to production-verified and Prompt 2 (Sentinel Kernel) can begin.
