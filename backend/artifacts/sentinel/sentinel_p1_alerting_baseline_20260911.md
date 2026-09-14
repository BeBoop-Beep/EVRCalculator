# inDex Sentinel — Prompt 1 Alerting Baseline

Date: 2026-09-11
Status: `SENTINEL_P1_CODE_COMPLETE_PRODUCTION_ACTIVATION_PENDING`

## Repository lineage

- Canonical development target: `develop`
- `develop` observed at final transplant time: `1cde8c9295218002680d514fbb30392514af58bc`
- Market Explorer Phase 2 report commit `56be66b9b56b30780536385e3c0829df2c251b49` is an ancestor of that head.
- Sentinel P1 branch: `feature/sentinel-p1-verified-20260911`
- Sentinel P1 includes the original hardened alert/watchdog changes plus the direct-script import fix proven necessary by VM verification.

The Sentinel source/test paths were verified byte-identical on the current `develop` lineage to the pre-transplant base before the tested Sentinel blobs were applied. No Market Explorer, Collector Appeal, migration, root-authority, auth, frontend, or pricing source was changed by Sentinel P1.

## Production runtime policy

The scraper VM must remain on `main` only. `develop` is never checked out on the production scraper VM for Sentinel validation.

The operator confirmed that the VM may intentionally carry approved VM-specific files/changes that are not part of canonical application `main`. Therefore future Sentinel runtime provenance MUST NOT require strict `HEAD == origin/main` equality.

The correct future invariant is:

1. runtime branch is `main`;
2. runtime is based on an approved production `main` release;
3. any difference from that release is limited to an explicit approved VM-overlay manifest/fingerprint;
4. unexpected source/config drift outside that allowlist is an incident.

Raw SHA mismatch by itself is evidence to inspect, not proof of an unhealthy runtime.

## Code changes

### `backend/alerts/market_freshness_watchdog.py`

- Corrected the Set Market dashboard authority from nonexistent `market_date` to canonical `latest_market_date`.
- Added structured watchdog execution-failure handling so state-load/query failures return an unhealthy report and, when queueing is enabled and database alert insertion remains available, attempt one deduplicated `market_watchdog_execution_failed` alert.
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
- Adds the repository root to `sys.path` when invoked directly as documented, fixing the VM-proven `ModuleNotFoundError: No module named 'backend'` failure.

## Regression coverage

Focused P1 test set before final VM-derived direct-script patch:

- watchdog: 9 passed
- dispatcher: 13 passed
- cron/deployment validator: 7 passed
- total: 29 passed

The test set was run in an offline focused harness against the exact watchdog/dispatcher/validator contract later transplanted onto current `develop`; Python compile validation also passed. The later direct-script patch only adds the standard repository-root bootstrap before the existing backend import. A fresh full-repository run from the final GitHub branch could not be executed from the ChatGPT container because the execution container has no outbound DNS access to clone GitHub. This limitation is not represented as a full-repo pass.

## Live VM verification — confirmed

Read-only checks were performed by the operator on the production scraper VM.

### Runtime

- branch: `main`
- HEAD: `4de24f1bdf0635527cf0d4837d5a69d152c4dc2d`
- worktree: dirty
- cron daemon: active
- no attempt was made to switch branches, pull `develop`, clean files, reset commits, or modify runtime configuration.

The VM's SHA differs from remote `main`, but approved VM-specific overlay files/changes may intentionally exist. Future Sentinel provenance must model that overlay explicitly rather than enforcing raw SHA equality.

### Dispatcher

Live read-only `backend.alerts.dispatcher --health` returned unhealthy with:

- `ALERTS_ENABLED=false`
- Slack webhook configured: true
- dispatcher scheduled flag: false
- freshness watchdog scheduled flag: false
- pending unsuppressed alerts: 143
- oldest pending age: 25,137 minutes
- last successful send: null
- exit code: 1

This confirms alert generation exists but real delivery has never been activated/proven.

### Freshness watchdog

Live read-only watchdog health failed exactly on the P1 schema defect:

- PostgREST code: `42703`
- failure: `pokemon_set_market_dashboard_snapshot_latest.market_date does not exist`

This confirms the P1 `latest_market_date` correction is production-relevant rather than theoretical.

### Installed cron

The active VM crontab contains the normal scraper/publication/heartbeat and Market Explorer runtime jobs, but contains NO active schedule for:

- `backend.alerts.dispatcher`
- `backend.alerts.market_freshness_watchdog`

Cron itself is active. Therefore the missing alert/watchdog execution is a scheduling/configuration gap, not a stopped cron daemon.

### Deployment validator

The currently released VM script failed before validation with:

`ModuleNotFoundError: No module named 'backend'`

when invoked directly by its documented path. P1 now bootstraps the repository root before importing backend modules. The live cron absence is independently confirmed from `crontab -l` even though the old validator could not reach its schedule checks.

## Other live read-only findings

- `alert_events`: approximately 143 unsent, unsuppressed rows.
- Approximately 69 were error/critical at baseline inspection.
- Historical `sent=true` rows: 0; `last_sent_at`: null.
- Daily 2026-09-11 scrape batch: complete, 165 expected / 165 succeeded / 0 failed / 0 missing.
- Public market authorities observed during the baseline were spread across multiple dates rather than one coordinated date; Prompt 1 deliberately did not repair publication state.
- Render `/health` remained responsive while a Supabase/Cloudflare 522 occurred on a data read, confirming process liveness is not sufficient product/data correctness monitoring.

## Historical backlog activation safety

The existing `suppress_historical_alert_backlog.py` must not be executed blindly because it can suppress all matching unsent rows regardless of severity.

Before enabling real delivery:

1. Snapshot and summarize the current backlog by type/severity/date.
2. Choose an explicit activation cutoff.
3. Run backlog suppression in dry-run mode only.
4. Human-review the exact rows/counts that would be suppressed.
5. On explicit approval, mark pre-activation rows suppressed without deleting them.
6. Verify only post-activation rows remain deliverable.
7. Enable/confirm `ALERTS_ENABLED=true` only as part of the approved production activation.
8. Install the canonical independent dispatcher/watchdog schedules with nonblocking `flock -n`.
9. Send exactly one explicit dispatcher test notification.
10. Verify one controlled post-activation alert is delivered and marked `sent=true`.
11. Re-run dispatcher health and deployment validation.

None of those mutating/notification steps were executed by Prompt 1.

## Production mutations

`NONE`

Prompt 1 did not:

- deploy Render or Vercel,
- merge or deploy Sentinel code to `main`,
- switch the production VM away from `main`,
- mutate Supabase rows/schema,
- suppress or mark alerts sent,
- send Slack notifications,
- edit VM cron/environment,
- clean/reset the VM worktree or approved VM overlay,
- force-publish or repair market data.

## P1 completion and production activation gate

Read-only VM verification is complete. P1 code is ready for normal development integration/review, but the alert system is NOT production-active.

Production activation must wait for an intentional release to `main`. After that release reaches the VM while the VM remains on `main`, execute the historical-backlog activation procedure and install/validate the two alert schedules.

Do not enable the dispatcher before the historical backlog has been explicitly reviewed, because doing so could deliver old queued alerts.

## Next Sentinel phase

Prompt 2 may build the deterministic Sentinel kernel/state machine on `develop` without activating production delivery. AI remains disabled and no AI API key is required.
