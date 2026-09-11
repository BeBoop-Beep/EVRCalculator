# inDex Sentinel — Prompt 1 Alerting Baseline

Date: 2026-09-11
Status: `SENTINEL_P1_CODE_COMPLETE_VM_VERIFICATION_PENDING`

## Repository lineage

- Canonical target branch: `develop`
- `develop` observed at transplant time: `1cde8c9295218002680d514fbb30392514af58bc`
- Market Explorer Phase 2 report commit `56be66b9b56b30780536385e3c0829df2c251b49` is an ancestor of that head.
- Sentinel P1 source commit on the clean verification branch: `cb7dd11efd8e65c7f02f5f709f901ef15e86d77b`
- Branch: `feature/sentinel-p1-verified-20260911`

The six Sentinel source/test paths were verified byte-identical on the current `develop` lineage to the pre-transplant base before applying the tested Sentinel blobs. No Market Explorer, Collector Appeal, migration, root-authority, auth, frontend, or pricing files were changed by Sentinel P1.

## Code changes

### `backend/alerts/market_freshness_watchdog.py`

- Corrected the Set Market dashboard authority from the nonexistent `market_date` column to canonical `latest_market_date`.
- Added structured watchdog execution-failure handling so state-load/query failures return an unhealthy report and, when queueing is enabled and DB alert insertion remains available, attempt one deduplicated `market_watchdog_execution_failed` alert.
- Read-only `--health` never queues alerts.

### `backend/alerts/dispatcher.py`

- Preserved existing configuration and schedule checks.
- Added explicit `backlog_healthy` and `delivery_progress_healthy` fields.
- A fresh pending queue remains healthy.
- An oldest unsuppressed pending alert beyond `ALERT_BACKLOG_CRITICAL_AGE_MINUTES` now makes dispatcher health unhealthy.
- Webhook contents remain excluded from health output.

### `backend/scripts/validate_alerting_deployment.py`

- Parses active cron lines rather than substring-searching raw crontab text.
- Commented-out jobs cannot satisfy the deployment contract.
- Requires independent dispatcher and watchdog schedules.
- Requires nonblocking `flock -n` safety.
- Requires canonical 1-minute dispatcher and 5-minute watchdog cadence while remaining path/user agnostic.

## Regression coverage

Focused P1 test set:

- watchdog: 9 passed
- dispatcher: 13 passed
- cron/deployment validator: 7 passed
- total: 29 passed

The test set was run in an offline focused harness against the exact source/test blobs later transplanted onto current `develop`; Python compile validation also passed. A fresh full-repository test run from the final GitHub branch could not be executed from the ChatGPT container because that container has no outbound DNS access to clone GitHub. This limitation is intentionally not represented as a full-repo pass.

## Live read-only findings

Observed through connected production data/tools before code activation:

- `alert_events`: approximately 143 unsent, unsuppressed rows.
- Approximately 69 were error/critical.
- Historical `sent=true` rows: 0; `last_sent_at`: null.
- Daily 2026-09-11 scrape batch: complete, 165 expected / 165 succeeded / 0 failed / 0 missing.
- The production scraper provenance recorded by the batch reported branch `main`, SHA `4de24f1bdf0635527cf0d4837d5a69d152c4dc2d`, and a dirty worktree. No attempt was made to clean or modify that runtime.
- Public market authorities observed during the baseline were spread across multiple dates rather than one coordinated date; Prompt 1 deliberately did not repair publication state.
- Render `/health` remained responsive while a Supabase/Cloudflare 522 occurred on a data read, confirming that process liveness is not sufficient product/data correctness monitoring.

## Historical backlog activation safety

The existing `suppress_historical_alert_backlog.py` must not be executed blindly because it can suppress all matching unsent rows regardless of severity.

Before enabling real delivery:

1. Snapshot and summarize the current backlog by type/severity/date.
2. Choose an explicit activation cutoff.
3. Run backlog suppression in dry-run mode only.
4. Human-review the exact rows/counts that would be suppressed.
5. On explicit approval, mark pre-activation rows suppressed without deleting them.
6. Verify only post-activation rows remain deliverable.
7. Send exactly one explicit dispatcher test notification.
8. Verify one controlled post-activation alert is delivered and marked `sent=true`.
9. Re-run dispatcher health and deployment validation.

None of those mutating/notification steps were executed by Prompt 1.

## Production mutations

`NONE`

Prompt 1 did not:

- deploy Render or Vercel,
- modify `main`,
- mutate Supabase rows/schema,
- suppress or mark alerts sent,
- send Slack notifications,
- edit VM cron/environment,
- clean the VM worktree,
- force-publish or repair market data.

## Remaining verification before integration

Direct VM access was not available in this ChatGPT environment. Before P1 is merged/activated, run read-only verification on the scraper VM:

```bash
cd /home/ubuntu/repos/EVRCalculator
set -a; . backend/.env; set +a
python -m backend.alerts.dispatcher --health
python -m backend.alerts.market_freshness_watchdog --health
python backend/scripts/validate_alerting_deployment.py
crontab -l
```

Do not use `--send-test` yet and do not run normal watchdog mode until the historical alert backlog activation procedure is approved.

## Next Sentinel phase

After P1 is integrated and the alert path is proven operational, Prompt 2 should build the deterministic Sentinel kernel/state machine. AI remains disabled and no AI API key is required.
