#!/bin/bash
set -euo pipefail

export PYTHONIOENCODING=utf-8

# Production should point this at an isolated checkout/worktree used only by the
# scheduler (for example /d/EVRCalculator-production). The compatibility default
# remains the historical path until the scheduled task is migrated.
REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"
cd "$REPO_DIR"

if [ -f backend/.env ]; then
  set -a
  source backend/.env
  set +a
fi

source .venv/Scripts/activate
mkdir -p logs

notify_slack() {
  if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
    local message="$1"

    python - "$message" <<'PY' | curl -sS -X POST -H 'Content-type: application/json' --data @- "$SLACK_WEBHOOK_URL" >/dev/null
import json
import sys

print(json.dumps({"text": sys.argv[1]}))
PY

  else
    echo "SLACK_WEBHOOK_URL is not set; skipping Slack notification."
  fi
}

HOSTNAME_VALUE=$(hostname)
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
EXPECTED_PUBLICATION_BRANCH="${EXPECTED_PUBLICATION_BRANCH:-main}"
ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"
PUBLICATION_FETCH_ORIGIN="${PUBLICATION_FETCH_ORIGIN:-0}"

verify_publication_checkout() {
  local branch_name=""
  local head_sha=""
  local origin_sha=""
  local dirty_files=""
  local failure_reason=""

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    failure_reason="repository path is not a Git worktree: $REPO_DIR"
  else
    if [ "$PUBLICATION_FETCH_ORIGIN" = "1" ]; then
      if ! git fetch --quiet origin "$EXPECTED_PUBLICATION_BRANCH"; then
        failure_reason="git fetch origin $EXPECTED_PUBLICATION_BRANCH failed"
      fi
    fi

    branch_name=$(git symbolic-ref --short -q HEAD || true)
    head_sha=$(git rev-parse HEAD 2>/dev/null || true)
    origin_sha=$(git rev-parse "refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH" 2>/dev/null || true)
    dirty_files=$(git status --porcelain --untracked-files=no 2>/dev/null || true)

    if [ -z "$failure_reason" ] && [ "$branch_name" != "$EXPECTED_PUBLICATION_BRANCH" ]; then
      failure_reason="expected branch $EXPECTED_PUBLICATION_BRANCH but checkout is ${branch_name:-detached}"
    elif [ -z "$failure_reason" ] && [ -z "$head_sha" ]; then
      failure_reason="unable to resolve checkout HEAD"
    elif [ -z "$failure_reason" ] && [ -z "$origin_sha" ]; then
      failure_reason="unable to resolve refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH"
    elif [ -z "$failure_reason" ] && [ "$head_sha" != "$origin_sha" ]; then
      failure_reason="checkout HEAD $head_sha does not match origin/$EXPECTED_PUBLICATION_BRANCH $origin_sha"
    elif [ -z "$failure_reason" ] && [ -n "$dirty_files" ]; then
      failure_reason="tracked working-tree changes are present"
    fi
  fi

  local checkout_line="[publication-checkout] repo=$REPO_DIR branch=${branch_name:-unknown} head=${head_sha:-unknown} origin_${EXPECTED_PUBLICATION_BRANCH}=${origin_sha:-unknown} fetch_origin=$PUBLICATION_FETCH_ORIGIN"
  echo "$checkout_line" | tee -a logs/run_simulations.log logs/refresh_public_snapshots.log

  if [ -z "$failure_reason" ]; then
    return 0
  fi

  if [ "$ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT" = "1" ]; then
    local override_line="[publication-checkout] OVERRIDE enabled; continuing despite: $failure_reason"
    echo "$override_line" | tee -a logs/run_simulations.log logs/refresh_public_snapshots.log
    notify_slack "⚠️ Public snapshot publication checkout guard OVERRIDDEN
Host: $HOSTNAME_VALUE
Repo: $REPO_DIR
Reason: $failure_reason
HEAD: ${head_sha:-unknown}
Expected: origin/$EXPECTED_PUBLICATION_BRANCH ${origin_sha:-unknown}"
    return 0
  fi

  local failure_line="[publication-checkout] REFUSED: $failure_reason"
  echo "$failure_line" | tee -a logs/run_simulations.log logs/refresh_public_snapshots.log
  notify_slack "❌ Simulation/publication job REFUSED unsafe checkout
Host: $HOSTNAME_VALUE
Repo: $REPO_DIR
Reason: $failure_reason
HEAD: ${head_sha:-unknown}
Expected: origin/$EXPECTED_PUBLICATION_BRANCH ${origin_sha:-unknown}
Action: deploy the latest clean $EXPECTED_PUBLICATION_BRANCH checkout or set the emergency override explicitly."
  return 2
}

# Never run simulations or publish snapshots from an accidental feature/research
# checkout. A nonzero result exits immediately because set -e is enabled.
verify_publication_checkout

notify_slack "🚀 Simulation job started
Host: $HOSTNAME_VALUE
Repo: $REPO_DIR
Branch: $EXPECTED_PUBLICATION_BRANCH
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_daily_opening_publication.py
Started: $START_TIME
Log: logs/run_simulations.log"

# ── Required daily order ────────────────────────────────────────────────────
# The scrape batch is created, worked and PROMOTED by the scrape job before this
# task runs. Everything after promotion is sequenced by one command:
#
#   1. resolve the promoted market date (never wall-clock)
#   2. run opening simulations for eligible sets not already current
#   3. VERIFY every supported set has a valid simulation for that date
#   4. rebuild coordinated market + set-page snapshots
#   5. refuse to report success when Opening Profit vs Cost is still behind
#
# The orchestrator exists because these used to be two independent commands with
# nothing reconciling them: the snapshot builders only republish whatever
# simulation rows already exist, so when the simulation batch stopped, market
# dashboards kept advancing while Opening Profit vs Cost silently froze (market
# 2026-07-31 vs OPvC 2026-07-27, undetected for five days). Simulation
# generation and snapshot publication remain separate responsibilities — the
# builders still never run a simulation — but the ORDER and the verification
# between them are now enforced in one place.
#
# --gate-wait-attempts/--gate-wait-seconds (passed through to the snapshot
# refresh) give the day ONE deterministic, bounded automatic retry path: if the
# day's scrape cohort is still finishing, the gate is re-evaluated up to 6 times
# 10 minutes apart (<= 1 extra hour, inside the same daily window) instead of
# deferring the whole day until an operator reruns it by hand.
PUBLICATION_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
PUBLICATION_FAILED=0
PUBLICATION_DEFERRED=0
PUBLICATION_EXIT=0
# Capture the exit code without tripping `set -e`. Exit codes:
#   0 = simulations current AND snapshots published
#   1 = a simulation failed, or publication cannot claim full freshness
#   2 = could not start (no promoted market date, unreadable authority)
#   3 = publication DEFERRED by the batch-cohort gate (cohort not ready)
python backend/scripts/run_daily_opening_publication.py \
  --gate-wait-attempts 6 --gate-wait-seconds 600 \
  >> logs/run_simulations.log 2>&1 || PUBLICATION_EXIT=$?
PUBLICATION_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$PUBLICATION_EXIT" -eq 0 ]; then
  notify_slack "✅ Simulation + publication completed
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_daily_opening_publication.py
Started: $PUBLICATION_START_TIME
Completed: $PUBLICATION_END_TIME
Log: logs/run_simulations.log"
elif [ "$PUBLICATION_EXIT" -eq 3 ]; then
  # Publication DEFERRED, not a build exception: the day's scrape cohort is not
  # observation-complete, so nothing was published and the previous good public
  # snapshots are preserved. This must NOT send the success message.
  PUBLICATION_DEFERRED=1
  DEFERRED_LINE=$(grep -a 'PUBLICATION_DEFERRED' logs/refresh_public_snapshots.log | tail -n 1 || true)

  notify_slack "⏸️ Public snapshot publication DEFERRED (cohort not ready; previous good snapshots preserved)
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_daily_opening_publication.py
Started: $PUBLICATION_START_TIME
Deferred: $PUBLICATION_END_TIME
Details: ${DEFERRED_LINE:-see log}
Action: resolve/requeue the incomplete scrape batch, then rerun the publication
Log: logs/refresh_public_snapshots.log"
else
  PUBLICATION_FAILED=1
  SUMMARY_LINE=$(grep -a 'daily-opening-publication] error=' logs/run_simulations.log | tail -n 1 || true)

  notify_slack "❌ Simulation/publication FAILED (Opening Profit vs Cost may be stale)
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_daily_opening_publication.py
Started: $PUBLICATION_START_TIME
Failed: $PUBLICATION_END_TIME
Exit: $PUBLICATION_EXIT
Details: ${SUMMARY_LINE:-see log}
Log: logs/run_simulations.log"
fi

# ── Final read-only parity audit ────────────────────────────────────────────
# Independent of the orchestrator's own verdict, and read-only: it re-reads what
# was actually published and reports, per supported opening set, whether the
# simulation date reached the market date and whether the Top Chase cards kept
# their canonical 1D/7D/30D movement windows. This is the tripwire that would
# have caught the 2026-07-27 freeze on day one.
AUDIT_EXIT=0
python backend/scripts/audit_opening_analytics_publication.py \
  >> logs/opening_analytics_audit.log 2>&1 || AUDIT_EXIT=$?

if [ "$AUDIT_EXIT" -ne 0 ]; then
  AUDIT_LINE=$(grep -a 'opening-analytics-audit] result=' logs/opening_analytics_audit.log | tail -n 1 || true)

  notify_slack "❌ Opening analytics publication audit FAILED
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/audit_opening_analytics_publication.py
Exit: $AUDIT_EXIT
Details: ${AUDIT_LINE:-see log}
Action: Opening Profit vs Cost and/or Top Chase windows are behind for at least one supported set
Log: logs/opening_analytics_audit.log"
fi

# A deferred publication, a hard failure and a failed audit are distinct events
# (distinct Slack messages), but none of them is a successful publication: the
# scheduled task must stay visibly non-successful so an operator acts before the
# next run.
if [ "$PUBLICATION_FAILED" -ne 0 ] || [ "$PUBLICATION_DEFERRED" -ne 0 ] || [ "$AUDIT_EXIT" -ne 0 ]; then
  exit 1
fi
