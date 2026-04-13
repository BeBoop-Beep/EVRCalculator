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

Nightly scraper runs should be controlled by cron on the VM user that owns the repo.

Open crontab:

```bash
crontab -e
```

Example nightly entry:

```cron
0 3 * * * /home/ubuntu/repos/EVRCalculator/run_scraper.sh >> /home/ubuntu/repos/EVRCalculator/scraper.log 2>&1
```

What this does:

- Runs daily at `03:00` server time.
- Appends both stdout and stderr to `scraper.log`.

List current cron jobs:

```bash
crontab -l
```

Recommended `run_scraper.sh` behavior:

- `cd` to repo root.
- Activate `.venv`.
- Export `PYTHONPATH=.` if needed.
- Run scraper command.

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

## 13. Updating the Scraper

Standard update procedure:

1. SSH to VM.
2. Move to repo and pull latest main.
3. Activate venv.
4. Install/refresh dependencies if needed.
5. Run a small manual validation scrape.

Commands:

```bash
cd ~/repos/EVRCalculator
git fetch origin
git checkout main
git pull origin main
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/scripts/run_pokemon_set_scrape.py --run --limit 1 --no-db-ingest
```

After success:

- Let cron continue on next schedule, or trigger a full run manually.

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
