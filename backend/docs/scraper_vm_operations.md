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

The daily scrape now has THREE scheduled roles that must be kept separate. The
worker must never implicitly create the daily queue — batch creation is its own
scheduled step keyed on the **America/Phoenix** market date (Arizona has no DST).

| Role | Command | Schedule (UTC) | Schedule (Arizona) |
|------|---------|----------------|--------------------|
| Batch creation | `python backend/scripts/create_daily_scrape_batch.py` | `0 10 * * *` | 03:00 |
| Worker dispatch | `python backend/scripts/run_next_scrape_job.py` | `* * * * *` | every minute |
| Batch-missing monitor | `python backend/scripts/create_daily_scrape_batch.py --check-only` | `30 11 * * *` | 04:30 |

Open crontab:

```bash
crontab -e
```

Recommended entries (adjust absolute paths to your VM):

```cron
# 1. Create the daily batch at 03:00 America/Phoenix (10:00 UTC). Reconciles stale
#    jobs first, derives the cohort dynamically, enqueues one job per ready set.
0 10 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/create_daily_scrape_batch.py >> scraper.log 2>&1

# 2. Worker dispatch — claim + run ONE job per minute under a lease. Creates no batch.
#    When the queue drains it runs the batch completeness/cohort-repair check.
* * * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/run_next_scrape_job.py >> scraper.log 2>&1

# 3. Alert if the batch was not created by the deadline.
30 11 * * * cd /home/ubuntu/repos/EVRCalculator && ./.venv/bin/python backend/scripts/create_daily_scrape_batch.py --check-only >> scraper.log 2>&1
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

Manual dispatcher run:

```bash
python -m backend.alerts.dispatcher
```

Why this is safe:

- Failed Slack delivery does not mark rows sent.
- Alerts are retried in the next run (inline or cron).

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
