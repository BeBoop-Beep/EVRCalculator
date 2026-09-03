# EVRCalculator Scraper VM Operations Runbook

## 1. Overview

This runbook explains how to operate the EVRCalculator scraper Virtual Machine (VM) end-to-end.

The scraper VM is responsible for:

- Running the Pokemon scrape job for EVRCalculator.
- Writing scrape diagnostics and scrape results to Supabase (PostgreSQL).
- Dispatching queued alert events to Slack (when enabled).
- Running scheduled jobs via cron (nightly scrape, heartbeat, optional alert dispatcher).

High-level flow:

1. Scraper job runs on the VM.
2. Scraper writes run/failure diagnostics and data to Supabase.
3. Database-triggered or app-triggered alert rows are queued in `public.alert_events`.
4. Alert dispatcher sends pending alerts to Slack webhook and marks sent rows.

Repository on VM:

- `~/repos/EVRCalculator`

Core script:

- `backend/scripts/run_pokemon_set_scrape.py`

---

## 2. Oracle Cloud Login

Use these steps to locate and verify the scraper VM in Oracle Cloud Infrastructure (OCI).

1. Open the OCI Console:
   - https://cloud.oracle.com
2. Sign in with your tenant/account credentials.
3. In the top-left navigation menu, go to:
   - `Compute` -> `Instances`
4. Find the scraper VM instance (name may vary by environment, typically includes "scraper").
5. Click the instance to open details.

What to check on the instance details page:

- **State**: Should be `Running`.
- **Public IP address**: Needed for SSH.
- **Compartment**: Confirm you are in the expected compartment.
- **Boot volume health / monitoring metrics**: Optional, useful for diagnostics.

If the instance is not running:

- Use `Start` from the instance actions menu.
- Wait until state changes to `Running` before SSH attempts.

---

## 3. SSH Access to the VM

### Prerequisites

- You have the correct private SSH key on your local machine.
- The VM security list / NSG allows inbound SSH (TCP 22).
- You know the VM public IP.

### Standard SSH command

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<VM_IP>
```

Example:

```bash
ssh -i ~/.ssh/id_rsa ubuntu@129.146.xx.yy
```

### `ubuntu` vs `opc` user

Oracle Linux images commonly default to `opc`, while Ubuntu images default to `ubuntu`.

- Use `ubuntu` when the VM image is Ubuntu.
- Use `opc` when the VM image is Oracle Linux.

Try this if `ubuntu` fails:

```bash
ssh -i ~/.ssh/id_rsa opc@<VM_IP>
```

### Verify access and identity

```bash
whoami
hostname
pwd
```

---

## 4. Repository Management

After logging into the VM:

```bash
cd ~/repos/EVRCalculator
```

Update to latest main branch code:

```bash
git fetch origin
git checkout main
git pull origin main
```

When to run `git pull`:

- Before any manual scraper run.
- After a deployment/merge to `main`.
- During incident response if a fix was just merged.

Optional validation:

```bash
git status
git log --oneline -n 5
```

---

## 5. Python Environment Setup

From the repository root:

```bash
source .venv/bin/activate
```

Your shell prompt should show `(.venv)`.

Install or refresh dependencies:

```bash
pip install --upgrade pip
pip install -r backend/requirements.txt
```

If scraper-specific requirements are separated, also run:

```bash
pip install -r backend/Scraper/requirements.txt
```

Verify interpreter and key imports:

```bash
which python
python --version
python -c "import requests, dotenv; print('deps ok')"
```

---

## 6. Environment Variables

The backend reads environment variables from:

- `backend/.env`

Purpose:

- Database credentials and URLs.
- Feature toggles.
- Alert webhook configuration.

Example `.env` structure:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_ANON_KEY=your_anon_key
JWT_SECRET=your_jwt_secret

# Alerts
ALERTS_ENABLED=true
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
# Legacy naming in some docs/scripts may appear as:
# SLACK_WEBHOOK_URL=...

# Optional
ALERT_BATCH_SIZE=25
SCRAPER_ENABLED=true
```

Important rules:

- Never commit `.env` into Git.
- Restrict file permissions:

```bash
chmod 600 backend/.env
```

- Rotate secrets if exposure is suspected.

---

## 7. Running the Scraper Manually

From repository root (with venv active):

```bash
python backend/scripts/run_pokemon_set_scrape.py --run
```

Common targeted runs:

```bash
python backend/scripts/run_pokemon_set_scrape.py --run --era scarletAndVioletEra --limit 3
python backend/scripts/run_pokemon_set_scrape.py --run --set blackBolt
python backend/scripts/run_pokemon_set_scrape.py --run --limit 5 --no-db-ingest
```

When manual runs are useful:

- Post-deployment validation.
- Backfill or narrow-scope test run.
- Incident troubleshooting.
- Reproducing a reported failure.

---

## 8. Automated Execution (Cron)

The daily scrape has scheduled roles that must be kept separate. The worker must
never implicitly create the daily queue — batch creation is its own scheduled step
keyed on the **America/Phoenix** market date (Arizona has no DST, so Phoenix is
always UTC-7).

The production crontab sets `CRON_TZ=America/Phoenix`, so every cron expression
below is Phoenix-local. Do **not** mix UTC-converted expressions into the same
crontab; doing so is how a schedule can look correct on paper while firing at the
wrong local time.

### 8.1 The active daily schedule

| Time (Phoenix) | Cron expression (`CRON_TZ=America/Phoenix`) | Role | Command |
|----------------|---------------------------------------------|------|---------|
| 1:00 AM | `0 1 * * *` | Reset/reconcile stale scrape jobs | `backend/scripts/reconcile_stale_scrape_jobs.py --commit` |
| 1:05 AM | `5 1 * * *` | Create the daily scrape batch | `backend/scripts/create_daily_scrape_batch.py` |
| every minute | `* * * * *` | Run the next scrape job **and, the instant the batch completes, hand off to publication** — **REQUIRED to run under a non-blocking `flock`; see the OOM incident note below** | `flock -n /tmp/pokemon-scrape-dispatcher.lock -c '... backend/scripts/run_next_scrape_job.py'` |
| ~immediately after batch completion (NORMAL) | — | **Post-scrape canonical market publication**, launched detached for the exact batch market_date | `backend/scripts/rebuild_snapshots_after_scrape.sh <market_date>` |
| 6:00 AM | `0 6 * * *` | **Fallback/watchdog only** — publish if the day's completed batch has not already published | `backend/scripts/publish_post_scrape_if_needed.py` |
| later (Windows) | — | Simulations + full coordinated publication | Windows Task Scheduler → `infra/local/run_simulations.sh` |
| ~~1:00 PM~~ | ~~`0 13 * * *`~~ | **REMOVED from the canonical schedule** — legacy market-dashboard rebuild; see §8.3 | — |

**Sep 2-3, 2026 OOM incident — dispatcher flock is now REQUIRED, not optional.**
The every-minute cron previously ran `run_next_scrape_job.py` (a long-running
drain worker whose own module contract says it must run under the CALLER's
flock) **without** any `flock`. Overlapping dispatcher process trees
accumulated across minutes and exhausted the VM's ~956 MiB RAM + 2 GiB swap,
causing global OOM kills. Production has been hand-patched to the locked form
below; `backend/scripts/validate_dispatcher_cron_deployment.py` FAILS deploy
if the installed crontab ever regresses to the unlocked, every-minute form
again (requirement P). This is now the canonical, tested deployment shape —
not a one-off hotfix.

```cron
CRON_TZ=America/Phoenix

# 1:00 AM Phoenix — reclaim expired leases and clear stale prior-day jobs BEFORE
#         the new batch is derived.
0 1 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/reconcile_stale_scrape_jobs.py --commit >> scraper.log 2>&1

# 1:05 AM Phoenix — derive the cohort dynamically and enqueue one job per ready set.
5 1 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/create_daily_scrape_batch.py >> scraper.log 2>&1

# Every minute — claim + run ONE job under a lease. Creates no batch. When the
#         queue drains it runs the batch completeness/cohort-repair check, and
#         the moment that check reports the batch COMPLETE it launches the
#         post-scrape publisher DETACHED for the exact market_date, then exits.
#         It never waits for publication to finish.
#
#         REQUIRED: this MUST run under a non-blocking flock. run_next_scrape_job.py
#         is a long-running drain worker (its own module docstring says it must run
#         under the CALLER's flock) — the Sep 2-3, 2026 OOM incident was this exact
#         line running WITHOUT one: overlapping dispatcher trees accumulated across
#         minutes and exhausted RAM+swap. A held lock is a safe no-op (the flocked
#         invocation just exits immediately), never a failure.
* * * * * /usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c 'cd /home/ubuntu/repos/EVRCalculator && /home/ubuntu/repos/EVRCalculator/.venv/bin/python backend/scripts/run_next_scrape_job.py' >> /home/ubuntu/repos/EVRCalculator/backend/logs/cron_dispatcher.log 2>&1

# 6:00 AM Phoenix — FALLBACK ONLY. Publishes only if the day's batch is
#         complete AND publication has not already happened (durable check via
#         the post-scrape audit). Replaces the old unconditional rebuild call.
#         OLD LINE TO REMOVE:
#           0 6 * * * /home/ubuntu/repos/EVRCalculator/backend/scripts/rebuild_snapshots_after_scrape.sh >> publication.log 2>&1
#         NEW LINE:
0 6 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/publish_post_scrape_if_needed.py >> publication.log 2>&1

# REMOVED (requirement O): the legacy 1:00 PM Phoenix-local unconditional
#         market-dashboard rebuild —
#           0 13 * * * .../python backend/scripts/build_pokemon_market_dashboard_snapshots.py --all --commit --days 365 --window 365d
#         — is NOT part of the canonical schedule. The canonical post-scrape /
#         6:00 AM publication orchestrator now owns this entire family end to
#         end (see §8.3). Do not re-add it.
```

Validate the installed crontab against this contract at any time:

```bash
python -m backend.scripts.validate_dispatcher_cron_deployment
```

It exits nonzero (and should gate deploy/CI) if the every-minute dispatcher
line is missing `flock -n`, if no every-minute dispatcher line exists at all,
or if the legacy 1:00 PM `--all` dashboard rebuild is still present.

### 8.2 The two publication phases

Publication happens in **two phases with different contracts**. Conflating them is
what allowed a promoted market date to appear on a set page while Explore Top
Rankings and Sealed Market stayed a day behind.

**Phase 1 — post-scrape (`rebuild_snapshots_after_scrape.sh`)**

* NORMAL trigger: launched **immediately** by the every-minute scrape dispatcher
  the instant `run_batch_completion_and_repair` (the authoritative batch-cohort
  completion boundary — see `backend/db/services/scrape_batch_service.py`)
  reports the batch `status == "complete"`. This is the ONLY completion
  authority; the trigger never fires merely because the scrape queue is empty,
  and it never bypasses cohort repair/requeue.
* FALLBACK trigger: the 6:00 AM Phoenix cron now calls
  `backend/scripts/publish_post_scrape_if_needed.py` instead of calling the
  rebuild wrapper unconditionally. It re-checks the same batch-completion gate
  and the post-scrape publication audit, and only launches the rebuild wrapper
  if the batch is complete AND publication is not already current for that
  exact market_date. Most days this is a no-op by the time 6:00 AM arrives.
* Advances every market **pricing** surface: Set Value, Cards, Top Chase, Sealed
  Market, Explore rankings (including the Explore Top Rankings Set Value), and the
  set-page market/header data.
* Runs **no simulations**. Opening Profit vs Cost therefore truthfully remains on
  the previous simulation date. This is expected, not a defect.
* Delegates the entire publication order to
  `backend/scripts/refresh_stale_public_snapshots.py` — the canonical orchestrator.
  The wrapper never calls individual builders, never uses `--force-publish`, and
  never uses `--strict` (which would fail on the OPvC staleness this phase allows).
* Waits on a closed publication gate up to 6 × 600s, then defers with **exit 3**
  and publishes nothing.
* Proves the result with
  `audit_pokemon_market_publication.py --phase post-scrape`, where OPvC is reported
  as **DEFERRED** (never as passed) and every other surface is required on the
  promoted date. A stale Explore or Sealed snapshot fails the run.

**Phase 2 — later, Windows Task Scheduler**

* Runs simulations, then the full coordinated publication.
* OPvC becomes current.
* Audited in the **default (full)** phase, where OPvC is required for every
  `supports_opening_simulation = true` set, alongside the same Explore Set Value
  and Sealed Market continuity checks.

Success in phase 1 means *"every market pricing surface reached date D"*. It does
**not** mean the day's publication is complete — only phase 2's full audit does.

### 8.1a Immediate post-scrape publication (NORMAL path) — how it works

Since the batch-cohort gate became the trigger authority, publication no longer
waits for the fixed 6:00 AM cron. The flow:

1. The every-minute worker (`run_next_scrape_job.py`) finds the queue idle and
   calls `run_batch_completion_and_repair(market_date)`. If active jobs remain,
   or cohort repair requeues missing/unreconciled sets, the batch stays
   `running` and nothing is triggered — the worker will pick the requeued work
   up on a later minute.
2. Only when that call returns `status == "complete"` (the batch is stamped
   `promoted_at` — see `complete_scrape_batch_if_ready`) does
   `backend.db.services.post_scrape_publication_trigger.trigger_post_scrape_publication_if_needed`
   run.
3. That trigger re-checks a **durable idempotence signal** before launching
   anything: the post-scrape publication audit
   (`audit_pokemon_market_publication.run_market_publication_audit(..., phase="post-scrape")`)
   evaluated for the EXACT batch market_date. If every required surface is
   already current for that date, it logs `already complete ... skipping
   launch` and does nothing — no new schema/table was added for this; the
   audit already reads the durable public snapshot tables that ARE the
   publication record.
4. If publication is missing/stale, it launches
   `backend/scripts/rebuild_snapshots_after_scrape.sh <exact_market_date>`
   **detached** via `subprocess.Popen` (new session, explicit executable/cwd,
   stdout/stderr appended to `publication.log`, no shell string). The scrape
   dispatcher process then finishes and exits normally — it never blocks on
   the multi-hour publisher.
5. Because the idle-completion check runs on every idle minute (cron runs the
   worker every minute even with an empty queue), the trigger can be invoked
   repeatedly. Step 3's audit-based check is what makes repeated invocations
   after a successful publish a no-op instead of relaunching the publisher.

**Concurrency / single-publisher lock.** `rebuild_snapshots_after_scrape.sh`
itself now holds a non-blocking `flock` (`/tmp/pokemon-post-scrape-publication.lock`
by default; override with `POST_SCRAPE_PUBLICATION_LOCK_PATH`) across its ENTIRE
body — the refresh AND the post-scrape audit. If a publisher is already running
when another launch races in (immediate trigger vs. 6 AM fallback vs. a manual
run), the second invocation logs `already running ... safe no-op, exiting 0`
and does nothing. A held lock is never treated as a scrape-batch failure.

**How to tell if a publisher is already running:**

```bash
# Non-zero / "held" if a publisher is currently running.
flock -n /tmp/pokemon-post-scrape-publication.lock -c true; echo $?
# 0 => lock was free (nothing running, or it just finished/released); 1 => held
ps aux | grep -i rebuild_snapshots_after_scrape
tail -n 50 /home/ubuntu/repos/EVRCalculator/publication.log
```

**Manually invoke publication for a specific market date** (recovery/backfill):

```bash
# Direct rebuild for one exact date (bypasses the "already current" check —
# use when you specifically want to force a rebuild attempt; the gate/audit
# inside the wrapper still applies, this never adds --force-publish):
./backend/scripts/rebuild_snapshots_after_scrape.sh 2026-08-15

# Same "publish only if needed" decision the 6 AM fallback uses, but for an
# arbitrary date:
./.venv/bin/python backend/scripts/publish_post_scrape_if_needed.py --market-date 2026-08-15
```

**Failure behavior.** If the detached launch itself fails to start (e.g. bad
interpreter path), the trigger logs `[post-scrape-trigger] launch failure ...`,
queues a best-effort `post_scrape_publication_launch_failed` alert (dedup keyed
per market_date), and returns — it never mutates the already-successful scrape
batch. The 6:00 AM fallback will retry via the same "publish if needed" check.
If the publication process itself starts and later fails (refresh error, or the
post-scrape audit failing a surface), the wrapper's existing exit-code semantics
are unchanged and authoritative; it does not cause the scraper to retry all 165
sets — scrape completion and publication remain separate failure domains.

### 8.3 The 1:00 PM market-dashboard rebuild is REMOVED from the canonical schedule

A legacy 1:00 PM Phoenix unconditional
`build_pokemon_market_dashboard_snapshots.py --all --commit --days 365 --window 365d`
cron entry predated the canonical orchestrator. It has been **disabled on
production** and is **not part of the canonical schedule** (requirement O):
the post-scrape / 6:00 AM publication orchestrator
(`backend/scripts/refresh_stale_public_snapshots.py`, invoked via
`rebuild_snapshots_after_scrape.sh`) now rebuilds the coordinated Cards +
Market Dashboard family itself, in order, on every publication run. Do not
re-add this cron entry; `backend/scripts/validate_dispatcher_cron_deployment.py`
fails deploy if it reappears in the installed crontab. For a genuine manual
mid-day repair, invoke `refresh_stale_public_snapshots.py --commit --set-id
<id>` directly rather than the standalone builder.

Open crontab (never edited automatically from application code):

```bash
crontab -e
```

Scheduled dispatcher runs record diagnostics as `trigger_source=scheduled`.
Manual targeted recovery runs (Section 7 / 11) remain `trigger_source=manual`.

Crash safety: each claimed job holds a **lease** (`SCRAPE_LEASE_SECONDS`, default
1800s). If a worker is SIGKILLed/OOMed, the next batch creation or claim reclaims
the expired lease automatically — a stale prior-day job can no longer block a
future batch. A stale prior-day job is terminally failed; a current-day job with
attempts remaining is requeued with bounded backoff.

List current cron jobs:

```bash
crontab -l
```

### One-time / incident recovery commands

```bash
# Reconcile stale queue + diagnostic rows (dry-run first, then commit).
python backend/scripts/reconcile_stale_scrape_jobs.py
python backend/scripts/reconcile_stale_scrape_jobs.py --commit

# Manually (re)create today's batch (e.g. after an incident). Keeps prior complete
# market date public until the cohort is observation-complete.
python backend/scripts/create_daily_scrape_batch.py

# Evaluate/repair a specific market date's batch.
python backend/scripts/complete_scrape_batch.py --market-date 2026-07-18
```

---

## 9. Heartbeat Monitoring

Use a lightweight heartbeat cron entry to verify VM scheduler health.

Example hourly heartbeat:

```cron
0 * * * * echo "VM heartbeat $(date)" >> /home/ubuntu/repos/EVRCalculator/vm_heartbeat.log
```

Inspect heartbeat log:

```bash
tail -n 50 /home/ubuntu/repos/EVRCalculator/vm_heartbeat.log
```

Interpretation:

- Heartbeat entries every hour indicate cron is functioning.
- Missing entries suggest cron daemon/user crontab issues.

---

## 10. Monitoring Logs

Primary run log location (example):

- `/home/ubuntu/repos/EVRCalculator/scraper.log`

Inspect last lines:

```bash
tail -n 50 /home/ubuntu/repos/EVRCalculator/scraper.log
```

Follow live logs:

```bash
tail -f /home/ubuntu/repos/EVRCalculator/scraper.log
```

Useful log checks:

```bash
grep -i "error" /home/ubuntu/repos/EVRCalculator/scraper.log | tail -n 20
grep -i "rate-limit" /home/ubuntu/repos/EVRCalculator/scraper.log | tail -n 20
```

---

## 11. Troubleshooting

### A. Missing `.env` file

Symptoms:

- Runtime errors for missing `SUPABASE_URL` or service key.

Fix:

1. Confirm path: `backend/.env`.
2. Restore from secure secret source.
3. Verify values are non-empty.
4. Re-run scraper.

### B. Incorrect working directory

Symptoms:

- Import errors.
- File-not-found paths for config/constants.

Fix:

```bash
cd ~/repos/EVRCalculator
source .venv/bin/activate
python backend/scripts/run_pokemon_set_scrape.py --run
```

### C. Missing Python packages

Symptoms:

- `ModuleNotFoundError` for dependencies.

Fix:

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r backend/Scraper/requirements.txt
```

### D. Supabase authentication errors

Symptoms:

- Unauthorized/forbidden DB responses.
- Service role key errors.

Fix:

1. Validate `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`.
2. Ensure no expired/rotated key mismatch.
3. Test connectivity with a small script/health check.
4. Check Supabase dashboard for project status and API keys.

### E. Cron jobs not executing

Symptoms:

- No fresh `scraper.log` entries.
- No heartbeat updates.

Fix:

1. Verify cron entries:

```bash
crontab -l
```

2. Check cron service status (distribution-dependent):

```bash
sudo systemctl status crond || sudo systemctl status cron
```

3. Ensure absolute paths in cron commands.
4. Ensure scripts are executable:

```bash
chmod +x /home/ubuntu/repos/EVRCalculator/run_scraper.sh
```

5. Check system logs for cron failures:

```bash
sudo journalctl -u crond -n 100 --no-pager || sudo journalctl -u cron -n 100 --no-pager
```

---

## 12. Slack Alert Integration

Alerting model:

- Scraper/DB logic queues alert rows into `public.alert_events`.
- Dispatcher sends unsent rows to Slack webhook.
- Rows are marked sent only after successful webhook delivery.

Required env vars:

- `ALERTS_ENABLED=true`
- `SLACK_ALERT_WEBHOOK_URL=...`
- `ALERT_BATCH_SIZE=25`
- `ALERT_SCHEDULES_REQUIRED=true`
- `ALERT_DISPATCHER_SCHEDULED=true`
- `MARKET_FRESHNESS_WATCHDOG_SCHEDULED=true`

Optional controls:

- `PIPELINE_SUCCESS_ALERTS=true` — disable only major success-stage messages by setting `false`; failures remain queued.
- `SLACK_ALERT_TIMEOUT_SECONDS=10`
- `ALERT_BACKLOG_WARNING_COUNT=20`
- `ALERT_BACKLOG_CRITICAL_AGE_MINUTES=10`

Do not enable delivery until the historical backlog has been reviewed and
suppressed. Suppression preserves incident history; it does not delete rows or
pretend they were delivered:

```bash
# Preview count, oldest/newest timestamps, and alert type/severity breakdown.
python backend/scripts/suppress_historical_alert_backlog.py \
  --before 2026-08-25T00:00:00Z --dry-run

# After reviewing the preview, explicitly commit the exact same cutoff.
python backend/scripts/suppress_historical_alert_backlog.py \
  --before 2026-08-25T00:00:00Z --commit \
  --reason "pre-Slack historical backlog reviewed by operator"
```

Check configuration and the unsent, unsuppressed backlog without revealing the
webhook URL:

```bash
python -m backend.alerts.dispatcher --health
```

This command exits nonzero when alerts are disabled, the webhook is absent, or
required scheduler declarations are absent. Its JSON reports only booleans,
pending count, oldest pending age, and `last_sent_at`; it never prints the URL.
Use it as a mandatory scraper-VM deploy preflight after loading the same
`backend/.env` that cron loads.

Only when intentionally validating Slack delivery, send one test message:

```bash
python -m backend.alerts.dispatcher --health-check --send-test
```

Manual dispatcher run:

```bash
python -m backend.alerts.dispatcher
```

The dispatcher must run independently every minute. `flock` prevents overlapping
processes if a webhook call is slow:

```cron
* * * * * flock -n /tmp/evr-alert-dispatcher.lock sh -c 'cd /home/ubuntu/repos/EVRCalculator && set -a && . backend/.env && set +a && ALERT_DISPATCHER_SCHEDULED=true MARKET_FRESHNESS_WATCHDOG_SCHEDULED=true ALERT_SCHEDULES_REQUIRED=true ./.venv/bin/python -m backend.alerts.dispatcher' >> /home/ubuntu/repos/EVRCalculator/alert_dispatcher.log 2>&1
```

Install the watchdog as a separate cron entry. It must not be chained after the
03:00 batch creator or publication command it supervises:

```cron
*/5 * * * * flock -n /tmp/evr-market-watchdog.lock sh -c 'cd /home/ubuntu/repos/EVRCalculator && set -a && . backend/.env && set +a && ./.venv/bin/python -m backend.alerts.market_freshness_watchdog' >> /home/ubuntu/repos/EVRCalculator/market_freshness_watchdog.log 2>&1
```

The watchdog uses fixed America/Phoenix business time and independently checks:

- no daily batch after `MARKET_BATCH_DEADLINE_AZ` (default `03:10`);
- a pending/running batch with no progress for `MARKET_BATCH_STALL_MINUTES`
  (default `120`);
- accepted Market Quality older than today after
  `MARKET_PUBLICATION_DEADLINE_AZ` (default `07:00`);
- disagreement among accepted quality, standard Set Value, set dashboards,
  sealed snapshots, and the global market index.

Each failure uses `alert_type:market_date:failure_class` as its deterministic
dedupe key. Repeated five-minute runs reuse the existing row. The watchdog only
queues alerts and never changes scrape, quality, publication, or simulation state.
Deployment verification:

```bash
set -a; . backend/.env; set +a
export ALERT_SCHEDULES_REQUIRED=true
export ALERT_DISPATCHER_SCHEDULED=true
export MARKET_FRESHNESS_WATCHDOG_SCHEDULED=true
python -m backend.alerts.dispatcher --health
crontab -l | grep -E 'backend.alerts.(dispatcher|market_freshness_watchdog)'
python backend/scripts/validate_alerting_deployment.py
```

Both commands must succeed before the VM deployment is considered alert-capable.

Inspect it with `tail -f /home/ubuntu/repos/EVRCalculator/alert_dispatcher.log`.

Pipeline alerts are intentionally stage-level: daily batch created, authoritative
scrape completion, Market Quality READY/BLOCKED, raw/Top10 index publication,
global Market publication, post-scrape audit, and daily Market completion. Set
alerts are emitted only for deterministic or terminal failures—never for every
successful set or ordinary transient attempts. Simulation/full publication uses
separate alert types and never implies that morning Market publication included
fresh simulations.

Why this is safe:

- Failed Slack delivery does not mark rows sent.
- Alerts are retried in the next run (inline or cron).
- Suppressed alerts are excluded from delivery but retained for incident review.
- Deterministic dedupe keys prevent repeated orchestrator invocations from
  creating duplicate stage messages.

Troubleshooting:

- **Slack receives nothing:** run `--health-check`; verify enabled/configured
  booleans, then inspect `alert_dispatcher.log`. Never paste the webhook into logs.
- **Queue grows:** confirm the dispatcher cron and lock owner, then inspect pending
  count and oldest age. Do not recursively alert Slack about Slack delivery.
- **Webhook 4xx:** validate or rotate the incoming webhook secret. Rows remain unsent.
- **Webhook timeout:** check outbound VM networking; increase the finite timeout
  only if necessary. Rows remain unsent.
- **Old alerts repeat:** disable dispatch, inspect the backlog with `--dry-run`,
  explicitly suppress the reviewed historical cutoff, then re-enable dispatch.

Production activation order:

1. Apply the alert suppression/dedupe migration.
2. Deploy code with `ALERTS_ENABLED=false`.
3. Run the historical suppression dry-run and review its breakdown.
4. Commit suppression with the reviewed cutoff and reason.
5. Run `--health-check`; confirm pending unsuppressed count is expected.
6. Set the webhook secret and run the explicit `--send-test` command once. This
   actually posts one test message; it never marks a queued alert sent.
7. Install both independent flocked cron entries and verify them with `crontab -l`.
8. Set `ALERTS_ENABLED=true` and monitor `alert_dispatcher.log`.

---

## 13. Updating the Scraper — MANDATORY DEPLOYMENT ORDER

### Why the order is fixed

On **2026-08-03** the VM was running commit `e4ac8208`, 19 revisions behind
`main`, which predated 37 `otherEra` config files. Database set metadata had
already been synchronized from a **newer** code generation, so 34 database cohort
rows named canonical keys the deployed runtime could not resolve. Every one of
those jobs failed with `invalid_set_key_filter`, each burned three attempts, and
the batch stayed `incomplete` — correctly keeping August 2 public, but stalling
the pipeline with no actionable signal.

The invariant that prevents a recurrence:

> **Database set metadata must NEVER get ahead of the deployed runtime registry.**

Deploy code first, verify it, and only then let the database learn about new sets.

### The permanent order

Any code/config change that **adds or changes sets** must follow these steps in
this order. Do not reorder, and do not skip step 4.

| # | Step | Command / owner |
|---|------|-----------------|
| 1 | Merge the reviewed code | GitHub PR into `main` |
| 2 | Deploy **that exact approved commit** to the scraper VM | §13.1 below |
| 3 | Verify cron's repo path, branch, Python executable, `PYTHONPATH` | §13.2 below |
| 4 | Run the runtime preflight **on the VM** | `audit_pokemon_scrape_runtime.py` |
| 5 | Only after preflight passes: synchronize set metadata into the database | `sync_pokemon_eras_and_sets.py --apply` |
| 6 | Create the daily batch | `create_daily_scrape_batch.py` |
| 7 | Drain the required cohort | worker cron / `run_next_scrape_job.py` |
| 8 | Complete / promote the batch | `complete_scrape_batch_if_ready` |
| 9 | Run simulations | `run_all_v2_sets.py` |
| 10 | Build snapshots | snapshot builders |
| 11 | Run the complete publication audit | `audit_pokemon_market_publication.py` |
| 12 | Send success **only if every required audit passes** | `run_daily_opening_publication.py` |

At step 5 the preflight will still be re-run automatically inside
`create_daily_scrape_batch.py`. That is intentional: it is the enforcement point,
and it refuses to create a batch or enqueue a single job on any mismatch.

### 13.1 Deploy a specific, identifiable commit

Production runs a **deliberately deployed, identifiable commit** — never
"whatever `main` happens to be right now".

```bash
cd ~/repos/EVRCalculator
git fetch origin

# Deploy the exact approved commit (use the merge SHA from the PR).
export DEPLOY_SHA=<approved-merge-sha>
git checkout main
git reset --hard "$DEPLOY_SHA"

source .venv/bin/activate
pip install -r backend/requirements.txt

# Record what is actually deployed.
git rev-parse HEAD
git status --porcelain    # MUST be empty
```

> **Do NOT put an unconditional `git pull` inside the cron job.** A self-updating
> cron makes the running code unidentifiable, deploys unreviewed commits at
> 03:00, and can pull a half-merged state mid-run. The preflight is designed to
> fail fast when database metadata gets ahead of the deployed runtime; a
> self-pulling cron hides exactly the signal that failure is meant to give you.

### 13.2 Verify cron's runtime matches the deployed checkout

A correct commit in the wrong checkout is the same defect. Confirm all four:

```bash
crontab -l | grep -E 'EVRCalculator|python'   # repo path + python executable
cd ~/repos/EVRCalculator && git rev-parse --abbrev-ref HEAD   # branch
cd ~/repos/EVRCalculator && git rev-parse HEAD                # SHA
ls -l ~/repos/EVRCalculator/.venv/bin/python                  # interpreter
echo "${PYTHONPATH:-<unset>}"                                 # import root
```

Every cron entry must use the **absolute** repo path and the **venv** Python:

```
/home/ubuntu/repos/EVRCalculator/.venv/bin/python /home/ubuntu/repos/EVRCalculator/backend/scripts/<script>.py
```

### 13.3 Run the runtime preflight (the gate)

```bash
cd ~/repos/EVRCalculator
source .venv/bin/activate
python backend/scripts/audit_pokemon_scrape_runtime.py --json
```

Exit code `0` means the deployed runtime registry and the database daily cohort
agree. Any nonzero exit means **stop** — do not sync metadata, do not create a
batch. The report names:

- `runtime.git_sha` / `git_branch` / `repository_root` / `python_executable` /
  `working_directory` / `pythonpath` — what is actually running
- `hashes.local_eligible_registry_sha256` vs `hashes.database_cohort_sha256`
- `mismatches.missing_local_key` — **the database is ahead of this runtime**
  (the August 3 signature); deploy the newer commit
- `mismatches.unexpected_db_key` — the runtime is ahead; run the metadata sync
- `mismatches.url_mismatch` / `mismatches.lifecycle_flag_mismatch`

### 13.4 Validation scrape

```bash
python backend/scripts/run_pokemon_set_scrape.py --run --limit 1 --no-db-ingest
```

After success, let cron continue on the next schedule, or trigger a full run
manually.

### 13.5 Catalog-only sets

Sets whose config declares `CATALOG_ONLY = True` (promos, trainer kits, product
catalogs — 37 as of migration 058) are stored with `catalog_only = true` and are
**excluded from the publication-critical daily cohort**. They remain in the
database and remain fully usable for manual, onboarding and historical catalog
backfills; they simply can never block public daily publication. The daily cohort
is `card_details_url IS NOT NULL AND NOT catalog_only`.

---

## 14. Useful Commands

Crontab:

```bash
crontab -e
crontab -l
```

System health:

```bash
htop
df -h
free -m
uptime
```

Network/process diagnostics:

```bash
ps aux | grep -i python
ss -tulpn
```

Repo state:

```bash
git status
git log --oneline -n 10
```

Logs:

```bash
tail -n 50 /home/ubuntu/repos/EVRCalculator/scraper.log
tail -f /home/ubuntu/repos/EVRCalculator/scraper.log
```

---

## 15. Disaster Recovery

### Scenario A: VM crashes or is stopped

1. Log into OCI console.
2. Navigate to `Compute` -> `Instances` -> scraper VM.
3. Start/reboot the instance.
4. Confirm `Running` state and public IP.
5. SSH in and run post-restart checks:

```bash
whoami
uptime
cd ~/repos/EVRCalculator
source .venv/bin/activate
python backend/scripts/run_pokemon_set_scrape.py --run --limit 1 --no-db-ingest
crontab -l
```

### Scenario B: SSH stops working

1. Confirm VM is `Running` and public IP has not changed.
2. Verify security list/NSG allows TCP 22 from your source IP.
3. Try alternate user (`ubuntu` vs `opc`).
4. Validate your private key and permissions:

```bash
chmod 600 ~/.ssh/id_rsa
```

5. If still blocked, use OCI serial console/recovery workflow.

### Scenario C: Scraper fails repeatedly

1. Pause automated runs (comment cron line via `crontab -e`).
2. Inspect logs for repeatable error signature.
3. Validate `.env` secrets and DB connectivity.
4. Run minimal command with `--limit 1` to isolate issue.
5. Roll forward with hotfix (preferred) or temporarily pin to last known good commit.
6. Re-enable cron after successful manual test.

### Scenario D: Alert pipeline failures

1. Verify webhook env vars.
2. Manually run dispatcher:

```bash
python -m backend.alerts.dispatcher --limit 10
```

3. Check pending rows in `public.alert_events`.
4. Rotate webhook if revoked/invalid.

---

## Operational Checklist (Quick)

Before run:

- VM is `Running`.
- SSH access works.
- Repo is up to date.
- `.venv` active.
- `.env` present and valid.

After run:

- Scraper log shows completion summary.
- Supabase run diagnostics were written.
- Alerts dispatched (or pending rows queued for retry).
- Cron and heartbeat remain healthy.
# Pokemon new-set discovery and onboarding

The 03:00 America/Phoenix daily batch creator remains the critical scheduled
operation. It creates the known-set cohort first and then invokes bounded,
best-effort TCGplayer discovery. Discovery failure or timeout is reported in the
batch JSON but does not change the successful batch exit code. The per-minute
scrape worker remains claim-only and has no onboarding responsibilities.

New-set onboarding is a separate lease-based process. A suggested later
schedule (the exact production time is an operator decision) is:

```cron
0 12 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/run_pending_pokemon_set_onboarding.py --resume-all --commit --json >> pokemon_set_onboarding.log 2>&1
```

Source registration requires an isolated Git worktree and defaults to no merge
or deploy:

```bash
export POKEMON_ONBOARDING_GIT_MODE=pr
export POKEMON_ONBOARDING_WORKTREE_DIR=/home/ubuntu/repos/pokemon-onboarding-worktrees
export POKEMON_ONBOARDING_BASE_BRANCH=main
export POKEMON_ONBOARDING_AUTO_MERGE=false
export POKEMON_ONBOARDING_AUTO_DEPLOY=false
```

Waiting API metadata, pull-rate research, PR merge, or deployment states do not
affect normal scraping. Pull rates must arrive as an approved JSON manifest
with provenance, citations/source URLs, capture date, positive rarity
denominators, slot assumptions, and product type.