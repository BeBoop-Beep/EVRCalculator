# Alert Dispatcher Implementation Summary

## What Was Built

A production-safe **alert dispatcher** for your scraping system that:

1. **Reads unsent alerts** from `public.alert_events` table
2. **Formats them** as rich Slack messages with severity colors and key metrics
3. **Sends to Slack** via incoming webhook
4. **Marks sent ONLY after successful delivery** (idempotent, no lost alerts)
5. **Continues on failure** (one failed alert doesn't block others)
6. **Integrates seamlessly** into your existing infrastructure

---

## Files Created

### Core Module
- **`backend/alerts/__init__.py`** — Package initialization, exports `send_pending_alerts`
- **`backend/alerts/dispatcher.py`** — Main dispatcher with 5 functions + CLI entry point

### Configuration & Setup
- **`backend/ALERTS.md`** — Comprehensive configuration, usage patterns, monitoring, SQL examples
- **`backend/SQL_ALERT_SETUP.sql`** — Table schema, indexes, and example triggers
- **`backend/crontab-alerts-sample.sh`** — Cron job templates for Oracle Linux

### Integration
- **Modified `backend/scripts/run_pokemon_set_scrape.py`** — Calls dispatcher at run completion (non-fatal)

---

## Key Features

### 1. Production-Safe Design
✅ **Idempotent** — Safe to run multiple times  
✅ **Non-blocking** — Scraper succeeds even if Slack fails  
✅ **Crash-resistant** — DB errors don't crash the dispatcher  
✅ **Graceful degradation** — Works with or without APScheduler, Slack webhook, alerts enabled  

### 2. Database Safety
- Alerts marked sent **only after successful Slack POST**
- If Slack fails → alert stays unsent → retried on next run
- If DB update fails → still logged, alert stays unsent
- Query parameterized (no SQL injection risk)

### 3. Slack Message Format
- **Color-coded by severity** (red=critical/error, orange=warning, green=info)
- **Includes run context** (job name, source system, status)
- **Shows metrics** (attempted, failed, rate-limit events)
- **Links to error summary** if present

### 4. Configuration-First
- **Environment variables** for all config (no hardcoding)
- **Clear error messages** when config is missing
- **Alerts can be disabled** without code changes (`ALERTS_ENABLED=false`)

### 5. Flexible Deployment
- **Inline in scraper** — Alerts sent automatically after scrape completes
- **Cron every minute** — Catch-all for any queued alerts
- **Cron after nightly** — Combined: inline alerts + safety check
- **Standalone CLI** — `python -m backend.alerts.dispatcher --limit 10`

---

## Main Functions

```python
from backend.alerts.dispatcher import send_pending_alerts

# Main entry point (process all pending alerts)
summary = send_pending_alerts(limit=25)
# Returns: {"fetched_count": 3, "sent_count": 3, "failed_count": 0, "errors": [...]}

# Also available (if needed separately):
alerts = fetch_pending_alerts(limit=10)          # Fetch unsent alerts
payload = format_slack_message(alert_row)        # Format for Slack
success = send_slack_alert(alert_row, url)       # Send to webhook
success = mark_alert_sent(alert_id)              # Mark sent in DB
```

---

## Configuration

### Environment Variables

Add to `backend/.env`:

```bash
# Enable/disable alert dispatch
ALERTS_ENABLED=true

# Slack incoming webhook URL (get from Slack app management)
# https://api.slack.com/messaging/webhooks
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Max alerts to process per run (optional, default: 25)
ALERT_BATCH_SIZE=25
```

### Database Setup

Run `backend/SQL_ALERT_SETUP.sql` in Supabase SQL editor or psql:

```sql
-- Creates:
-- - public.alert_events table
-- - Indexes for efficient unsent alert queries
-- - Example triggers to auto-queue alerts on scrape failures
```

---

## Integration Points

### 1. Inline After Scraper (Already Done)

Your scraper now calls the dispatcher automatically:

```python
# In backend/scripts/run_pokemon_set_scrape.py main()
# After scrape completes (apply mode only):
if args.run:
    try:
        from backend.alerts.dispatcher import send_pending_alerts
        alert_summary = send_pending_alerts()
    except Exception as exc:
        logger.exception("alert dispatcher failed, but scraper completed: %s", exc)
```

No action needed — already integrated! Just set env vars and it works.

### 2. Cron Job (Optional)

For always-on alerting or safety net. Templates in `backend/crontab-alerts-sample.sh`:

```bash
# Every minute
* * * * * cd /home/scrape/EVRCalculator && python -m backend.alerts.dispatcher

# Or after nightly scrape
30 2 * * * python -m backend.alerts.dispatcher
```

### 3. Scheduled Jobs (Optional)

Could integrate with your existing `backend/jobs/scheduler_service.py` if desired:

```python
from backend.alerts.dispatcher import send_pending_alerts

def _run_alert_dispatch():
    """Scheduled alert dispatch job"""
    logger.info("alert_dispatch_job: starting")
    summary = send_pending_alerts()
    logger.info("alert_dispatch_job: completed %s", summary)
```

(Not required — cron or inline is sufficient.)

---

## Usage Examples

### Basic Test (with alerts disabled)

```bash
cd /path/to/EVRCalculator
export PYTHONPATH=.
export ALERTS_ENABLED=false

python -m backend.alerts.dispatcher
# Output: [alert-dispatcher] ALERTS_ENABLED=false, skipping
```

### Manual Dispatch

```bash
export ALERTS_ENABLED=true
export SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

python -m backend.alerts.dispatcher --limit 5
# Sends up to 5 pending alerts to Slack
```

### Check Configuration

```bash
python -c "
from backend.alerts.dispatcher import _get_slack_webhook_url, _get_batch_size, _get_alerts_enabled
print('Enabled:', _get_alerts_enabled())
print('Batch size:', _get_batch_size())
try:
    print('Webhook URL:', _get_slack_webhook_url()[:40] + '...')
except ValueError as e:
    print('Webhook URL: NOT SET')
"
```

---

## Testing

### Unit Test Example

```python
def test_format_slack_message():
    from backend.alerts.dispatcher import format_slack_message
    
    alert_row = {
        'alert_type': 'test',
        'severity': 'WARNING',
        'title': 'Test Alert',
        'message': 'Test message',
        'created_at': '2026-04-12T00:00:00+00:00',
        'payload': {'run_id': 'abc123'}
    }
    
    payload = format_slack_message(alert_row)
    
    assert payload['text'] == 'WARNING | test'
    assert payload['attachments'][0]['color'] == 'warning'
    assert len(payload['attachments'][0]['fields']) > 0
```

### Integration Test (Mock Slack)

```python
from unittest.mock import patch, MagicMock

def test_send_pending_alerts_success():
    from backend.alerts.dispatcher import send_pending_alerts
    
    with patch('backend.alerts.dispatcher.supabase') as mock_db:
        with patch('backend.alerts.dispatcher.requests.post') as mock_post:
            # Mock DB to return 1 unsent alert
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {'id': 'test-id', 'alert_type': 'test', 'severity': 'INFO', 'title': 'Test', 'message': 'Msg', 'created_at': '2026-04-12T00:00:00+00:00', 'payload': {}}
            ]
            
            # Mock Slack to return 200
            mock_post.return_value.status_code = 200
            
            summary = send_pending_alerts(limit=1)
            
            assert summary['fetched_count'] == 1
            assert summary['sent_count'] == 1
            assert summary['failed_count'] == 0
```

---

## Monitoring

### SQL Queries

```sql
-- Pending alerts (waiting to send)
SELECT id, alert_type, severity, title, created_at
FROM public.alert_events
WHERE sent = false
ORDER BY created_at DESC LIMIT 10;

-- Recently sent alerts
SELECT id, alert_type, title, sent_at-created_at as time_to_send
FROM public.alert_events
WHERE sent = true
ORDER BY sent_at DESC LIMIT 10;

-- Alert backlog (sent-to-pending ratio)
SELECT 
  COUNT(*) FILTER (WHERE sent=false) as pending,
  COUNT(*) FILTER (WHERE sent=true) as sent,
  COUNT(*) as total
FROM public.alert_events
WHERE created_at > now() - interval '7 days';
```

### Logs

Alert dispatcher logs with tag `[alert-dispatcher]`:

```
[alert-dispatcher] fetched 3 pending alert(s)
[alert-dispatcher] sent alert id=abc-123 to Slack
[alert-dispatcher] marked alert id=abc-123 as sent
[alert-dispatcher] failed to mark alert id=def-456: <reason>
[alert-dispatcher] completed: fetched=3 sent=3 failed=0
```

---

## Dependencies

**Already installed in your project:**
- `requests` (for Slack webhook POST)
- `logging` (stdlib)
- Supabase Python client (already used by scraper)
- `dotenv` (already used)

**No new dependencies needed.**

---

## Troubleshooting

### "SLACK_ALERT_WEBHOOK_URL is not set"

Set it in `backend/.env`:

```bash
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Get webhook from: https://api.slack.com/messaging/webhooks

### "No alerts appearing in Slack"

1. Check `ALERTS_ENABLED=true`
2. Run dispatcher manually: `python -m backend.alerts.dispatcher`
3. Check logs: Should see `[alert-dispatcher]` messages
4. Test webhook: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' YOUR_WEBHOOK_URL`
5. Verify webhook URL is not expired (Slack webhooks can become invalid)

### "Alerts stuck in 'pending' state"

- Check Slack webhook in: Slack workspace → Settings → Apps → Incoming Webhooks
- If webhook is deleted, create new one and update `.env`
- Manually retry: `python -m backend.alerts.dispatcher --limit 10`

---

## Next Steps

1. **Set environment variables** in `backend/.env`:
   ```bash
   ALERTS_ENABLED=true
   SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

2. **Run DB setup** (Supabase SQL editor):
   - Execute `backend/SQL_ALERT_SETUP.sql`
   - Creates `public.alert_events` table and indexes

3. **Test inline handler**:
   ```bash
   python backend/scripts/run_pokemon_set_scrape.py --run --limit 1 --no-db-ingest
   # Alerts are sent automatically at end of run
   ```

4. **(Optional) Set up cron** for always-on alerting:
   ```bash
   # Use template from backend/crontab-alerts-sample.sh
   ```

5. **Monitor** with SQL queries and logs.

---

## Summary

✅ **Core module** — Ready to use  
✅ **Scraper integration** — Already done  
✅ **Configuration** — Template in ALERTS.md + SQL_ALERT_SETUP.sql  
✅ **Cron templates** — In crontab-alerts-sample.sh  
✅ **Documentation** — Complete in ALERTS.md  
✅ **Production-safe** — Idempotent, non-blocking, row-by-row marking  
✅ **No lost alerts** — Marked sent only after successful delivery  

**Ready to deploy.** Just set env vars and run DB setup!
