#!/bin/bash
# Sample crontab setup for scrape alerts on Oracle Linux
#
# These entries assume:
# - Project at: /home/scrape/EVRCalculator
# - Virtualenv at: /home/scrape/EVRCalculator/.venv
# - User: scrape (run as)
# - Logs: /var/log/scrape-alerts.log
#
# To install, save this as a file and run:
#   sudo crontab -u scrape /path/to/this/file
#
# Or add entries manually:
#   sudo crontab -u scrape -e

# =============================================================================
# Pattern 1: Send alerts every minute (catch-all)
# =============================================================================
# Use this if you want to ensure no alerts get stuck in the database
* * * * * /home/scrape/EVRCalculator/.venv/bin/python -m backend.alerts.dispatcher >> /var/log/scrape-alerts.log 2>&1

# =============================================================================
# Pattern 2: Send alerts after nightly scrape (recommended)
# =============================================================================
# Nightly scrape automatic alerts are sent inline during the run.
# This is just a safety check 30 minutes later for any stragglers.

# 2:00 AM - Start nightly Pokémon scrape (alerts sent at run completion)
0 2 * * * cd /home/scrape/EVRCalculator && PYTHONPATH=. /home/scrape/EVRCalculator/.venv/bin/python backend/scripts/run_pokemon_set_scrape.py --run >> /var/log/scrape-nightly.log 2>&1

# 2:30 AM - Safety check: send any remaining queued alerts
30 2 * * * /home/scrape/EVRCalculator/.venv/bin/python -m backend.alerts.dispatcher >> /var/log/scrape-alerts.log 2>&1

# =============================================================================
# Pattern 3: Separate scheduled scrape + always-on alerts
# =============================================================================
# If you want scrape and alerts as separate jobs:

# 1:00 AM - Run scrape (alerts NOT sent inline)
# (Add --run option and remove alert call to scraper)
# 0 1 * * * ...

# Every minute - Always-on alert dispatch
# * * * * * /home/scrape/EVRCalculator/.venv/bin/python -m backend.alerts.dispatcher >> /var/log/scrape-alerts.log 2>&1

# =============================================================================
# Logging & Rotation
# =============================================================================
# Create logrotate config to prevent logs from growing too large:
#
# File: /etc/logrotate.d/scrape-alerts
# ===============================
# /var/log/scrape-alerts.log
# /var/log/scrape-nightly.log
# {
#     daily
#     rotate 7
#     compress
#     missingok
#     notifempty
#     create 0640 scrape scrape
# }
#
# Apply with: sudo logrotate -f /etc/logrotate.d/scrape-alerts

# =============================================================================
# Monitoring & Debugging
# =============================================================================
# View cron logs for the scrape user:
#   sudo journalctl -u cron -f | grep scrape
#
# View alert dispatcher logs:
#   tail -f /var/log/scrape-alerts.log
#
# Manual test of dispatcher:
#   cd /home/scrape/EVRCalculator
#   /home/scrape/EVRCalculator/.venv/bin/python -m backend.alerts.dispatcher --limit 5
#
# Check pending unsent alerts:
#   psql ${DATABASE_URL} -c "SELECT id, alert_type, severity, sent FROM public.alert_events WHERE sent = false ORDER BY created_at DESC LIMIT 10;"
