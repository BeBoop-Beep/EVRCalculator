# Alert Dispatcher — Production Configuration

## Overview

The alert dispatcher reads pending Slack alerts from `public.alert_events`, sends them via Slack incoming webhook, and marks them sent only after successful delivery. This ensures:

- **No lost alerts** — Alerts stuck in "pending" state are retried on the next run
- **Idempotent** — Can be run multiple times safely (from cron or inline after scrape)
- **Non-blocking** — Scraper completion doesn't depend on Slack success
- **Row-by-row marking** — Marks sent after each individual webhook POST, not bulk

---

## Database Schema

### `public.alert_events`

```sql
CREATE TABLE public.alert_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_type TEXT NOT NULL,           -- e.g., "scrape_failure", "rate_limit_pressure"
  severity TEXT NOT NULL,              -- "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"
  title TEXT NOT NULL,                 -- Short, human-readable title
  message TEXT NOT NULL,               -- Full message body
  payload JSONB DEFAULT '{}',          -- Optional structured data (run_id, metrics, etc.)
  sent BOOLEAN DEFAULT FALSE,
  sent_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_alert_events_sent_created 
  ON public.alert_events(sent, created_at);
```

### Trigger to Queue Alerts (Example)

When a scrape run fails, a database trigger could insert an alert:

```sql
-- Example: trigger on scrape_job_runs status change
CREATE OR REPLACE FUNCTION public.queue_scrape_failure_alert()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status IN ('failed', 'partial_failure') AND OLD.status != NEW.status THEN
    INSERT INTO public.alert_events (
      alert_type,
      severity,
      title,
      message,
      payload
    ) VALUES (
      'scrape_run_' || NEW.status,
      CASE WHEN NEW.status = 'failed' THEN 'CRITICAL' ELSE 'WARNING' END,
      'Scrape ' || NEW.status || ': ' || NEW.job_name,
      'Job ' || NEW.job_name || ' (' || NEW.source_system || ') ' || NEW.status,
      jsonb_build_object(
        'run_id', NEW.id,
        'job_name', NEW.job_name,
        'source_system', NEW.source_system,
        'status', NEW.status,
        'items_attempted', NEW.items_attempted,
        'items_failed', NEW.items_failed,
        'rate_limit_events', NEW.rate_limit_events,
        'error_summary', NEW.error_summary
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_scrape_runs_alert
  AFTER UPDATE ON public.scrape_job_runs
  FOR EACH ROW
  EXECUTE FUNCTION public.queue_scrape_failure_alert();
```

---

## Configuration

### Environment Variables

```bash
# Enable/disable alert dispatch (.env)
ALERTS_ENABLED=true

# Slack incoming webhook URL (get from Slack app management)
# https://api.slack.com/messaging/webhooks
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Max alerts to send per run (default: 25, safe for Slack rate limits)
ALERT_BATCH_SIZE=25
```

---

## Usage Patterns

### Pattern 1: Inline After Scrape (Recommended for Daily Runs)

When your scraper finishes, alerts are sent automatically:

```bash
cd /path/to/EVRCalculator
PYTHONPATH=. python backend/scripts/run_pokemon_set_scrape.py --run
# Alerts are sent automatically after the run completes (non-fatal)
```

The scraper already integrates `send_pending_alerts()` at the end of apply-mode runs. No additional code needed.

### Pattern 2: Standalone Cron Every Minute

For systems where alerts may be queued but the scraper isn't running, use cron:

```bash
# /etc/cron.d/scrape-alerts (Oracle Linux system crontab)

# Send alerts every minute
* * * * * scrape /home/scrape/env/bin/python -m backend.alerts.dispatcher >> /var/log/scrape-alerts.log 2>&1

# Or with explicit virtualenv
* * * * * scrape cd /home/scrape/EVRCalculator && source .venv/bin/activate && python -m backend.alerts.dispatcher >> /var/log/scrape-alerts.log 2>&1
```

### Pattern 3: Cron Before/After Nightly Scrape

With the existing scheduler service, route alerts through cron:

```bash
# /etc/cron.d/scrape-nightly

# 2 AM - nightly scrape run (alerts sent automatically at end)
0 2 * * * scrape cd /home/scrape/EVRCalculator && source .venv/bin/activate && python backend/scripts/run_pokemon_set_scrape.py --run

# 2:30 AM - catch any leftover alerts (from failed runs, etc.)
30 2 * * * scrape cd /home/scrape/EVRCalculator && source .venv/bin/activate && python -m backend.alerts.dispatcher
```

---

## When to Use Which Pattern

| Pattern | When to Use | Notes |
|---------|-----------|-------|
| **Inline** | Daily/scheduled scrape runs | Simplest, no extra cron job. Alerts sent right after metrics recorded. |
| **Cron every minute** | Always-on alerting for any queued alerts | Catches alerts from failed scrapes, manual runs, backfill jobs. Adds ~15 MB/month of `alert_events` rows if busy. |
| **Cron before/after nightly** | Hybrid: scrape runs + catch-all check | Best balance: alerts sent inline, plus a safety window to retry any stuck alerts. |

---

## Slack Message Format

Alerts are formatted as Slack rich attachments with:

- **Title & Severity** — Color-coded (red=critical/error, orange=warning, green=info)
- **Alert Type & Message** — User-provided context
- **Timestamp** — When alert was created
- **Key Metrics** (from payload):
  - `run_id`, `job_name`, `source_system`
  - `status`, `items_attempted`, `items_failed`
  - `rate_limit_events`, `error_summary`

Example:

```
🚨 CRITICAL | scrape_run_failed

Job pokemon_set_scrape (tcgplayer) failed

Run ID: f84b4583-0b57-4b4a-8813-325a3b93fbd7
Job: pokemon_set_scrape
Source: tcgplayer
Status: failed
Failed: 5
Rate Limit Events: 12
Error Summary: sustained_rate_limit
```

---

## Failure Handling

### Slack Webhook Fails

If the Slack POST fails (network error, invalid webhook, 5xx):

- ❌ Alert is **NOT** marked sent in DB
- ✅ Error is **logged**
- ✅ Dispatcher **continues** to next alert
- ✅ Alert will retry on next run

### Database Query Fails (fetch/mark sent)

If `SELECT` from `alert_events` or `UPDATE` sent status fails:

- ❌ Row is **NOT** marked sent
- ✅ Error is **logged**
- ✅ Dispatcher **continues**
- ✅ Row will retry on next run

### Configuration Missing (`ALERTS_ENABLED=false`)

If `ALERTS_ENABLED` is false or not set:

- ✅ Dispatcher **logs and exits quietly** (non-fatal)
- ✅ Scraper completes normally

---

## Security

### Webhook URL

- Store in `.env` (never in code or git)
- Use Slack's **incoming webhook**, not API token
- Webhooks are scoped to a single channel; they don't have full API access
- Rotate webhook if compromised

### Payload Sanitization

- Messages are POST'd as JSON to Slack's webhook
- No SQL injection risk (parameterized Supabase queries)
- No code injection risk (Slack webhooks don't execute code)

---

## Monitoring & Debugging

### Check Pending Alerts

```bash
# SQL in psql or Supabase studio
SELECT id, alert_type, severity, title, sent, created_at
FROM public.alert_events
WHERE sent = false
ORDER BY created_at DESC;

# Last 10 sent alerts
SELECT id, alert_type, severity, title, sent_at, created_at
FROM public.alert_events
WHERE sent = true
ORDER BY sent_at DESC LIMIT 10;
```

### Manual Dispatch

```bash
cd /path/to/EVRCalculator
export ALERTS_ENABLED=true
export SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
python -m backend.alerts.dispatcher --limit 5
```

### Logs

The dispatcher logs to the standard Python logger with tag `[alert-dispatcher]`:

```
[alert-dispatcher] fetched 3 pending alert(s)
[alert-dispatcher] sent alert id=abc-123 to Slack
[alert-dispatcher] marked alert id=abc-123 as sent
[alert-dispatcher] completed: fetched=3 sent=3 failed=0
```

---

## Troubleshooting

### "SLACK_ALERT_WEBHOOK_URL is not set"

Set the webhook URL in your `.env`:

```
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Then re-run.

### "Alert marked sent in DB failed"

Indicates a database connectivity issue. Check:

- Supabase connection (same check as scraper)
- Network/VPN to Supabase cluster
- `public.alert_events` table exists and is accessible

### No Alerts Appearing in Slack

1. ✅ Verify ALERTS_ENABLED=true
2. ✅ Run dispatcher manually: `python -m backend.alerts.dispatcher`
3. ✅ Check logs for errors
4. ✅ Verify webhook URL in Slack app management (Settings > Incoming Webhooks)
5. ✅ Test webhook manually:
   ```bash
   curl -X POST \
     -H 'Content-type: application/json' \
     --data '{"text":"Test"}' \
     YOUR_WEBHOOK_URL
   ```

---

## Module Reference

### `backend.alerts.dispatcher`

**Main functions:**

```python
from backend.alerts.dispatcher import send_pending_alerts

# Fetch and send all pending alerts (main orchestration)
summary = send_pending_alerts(limit=25)
# Returns: {"fetched_count": 3, "sent_count": 3, "failed_count": 0, "errors": [...]}

# Fetch unsent alerts only
alerts = fetch_pending_alerts(limit=10)

# Format an alert for Slack
payload = format_slack_message(alert_row)

# Send alert to Slack webhook
success = send_slack_alert(alert_row, webhook_url)

# Mark alert as sent in DB (only after successful POST)
success = mark_alert_sent(alert_id)
```

**CLI:**

```bash
# Send up to ALERT_BATCH_SIZE pending alerts
python -m backend.alerts.dispatcher

# Send up to 10 alerts
python -m backend.alerts.dispatcher --limit 10
```

---

## Best Practices

1. **Start small** — Test with `ALERT_BATCH_SIZE=1` before prod
2. **Monitor webhook** — Check Slack audit logs for delivery status
3. **Disk usage** — Old alert rows are never deleted; archive older rows if `alert_events` grows large
4. **Idempotency** — Safe to call multiple times; skipped alerts stay unsent
5. **Non-blocking** — Run alerts async or in cron, never block scraper on Slack success
6. **Graceful degradation** — Scraper succeeds even if alerts fail

---

## Examples

### Querying Recent Failures with Alerts

```sql
SELECT
  r.id,
  r.job_name,
  r.status,
  r.started_at,
  COUNT(f.id) as failure_count,
  COUNT(a.id) as alert_count,
  MAX(a.created_at) as latest_alert_at
FROM public.scrape_job_runs r
LEFT JOIN public.scrape_job_run_failures f ON f.run_id = r.id
LEFT JOIN public.alert_events a ON a.payload->>'run_id' = r.id::text
WHERE r.started_at > now() - interval '7 days'
  AND r.status IN ('failed', 'partial_failure')
GROUP BY r.id, r.job_name, r.status, r.started_at
ORDER BY r.started_at DESC;
```

### Monitoring Alert Delivery

```sql
-- Alert lag (how long between creation and sending)
SELECT
  alert_type,
  AVG(EXTRACT(EPOCH FROM (sent_at - created_at))) as avg_seconds_to_send,
  MAX(EXTRACT(EPOCH FROM (sent_at - created_at))) as max_seconds_to_send,
  COUNT(*) as total_sent
FROM public.alert_events
WHERE sent = true AND sent_at > now() - interval '7 days'
GROUP BY alert_type
ORDER BY avg_seconds_to_send DESC;
```

---

## Summary

The alert dispatcher is production-ready and integrates seamlessly with your existing scrape infrastructure:

- ✅ Uses your existing Supabase client
- ✅ Follows your logging patterns
- ✅ Integrates into scraper's end-of-run flow
- ✅ Can run standalone via cron
- ✅ Non-blocking and idempotent
- ✅ No Slack alerts lost (retried on next run)
- ✅ Rows marked sent only after successful delivery
