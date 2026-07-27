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
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Log: logs/run_simulations.log"

SIMULATIONS_FAILED=0
if python backend/scripts/run_all_v2_sets.py >> logs/run_simulations.log 2>&1; then
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "✅ Simulation job completed
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Completed: $END_TIME
Log: logs/run_simulations.log"
else
  SIMULATIONS_FAILED=1
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "❌ Simulation job FAILED
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Failed: $END_TIME
Log: logs/run_simulations.log"
fi

# Public snapshots (market dashboards, explore rankings, set pages) are
# materialized read models — they only reflect today's simulations after this
# refresh runs. It must run AFTER the simulation batch, and it runs even when
# the batch partially failed so the sets that did complete still surface fresh
# Performance vs Cost history instead of a stale flatline. --strict makes the
# job exit nonzero (and Slack-alert) if any set page snapshot is still older
# than its simulation/market dependencies afterward.
REFRESH_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
REFRESH_FAILED=0
REFRESH_DEFERRED=0
REFRESH_EXIT=0
# Capture the exit code without tripping `set -e`. Exit codes:
#   0 = published / no work needed after an open gate
#   3 = publication DEFERRED by the batch-cohort gate (cohort not ready)
#   other nonzero = genuine refresh/build failure
# --gate-wait-attempts/--gate-wait-seconds give the day ONE deterministic,
# bounded automatic retry path: publication starts after the simulations, and if
# the day's scrape cohort is still finishing, the gate is re-evaluated up to 6
# times 10 minutes apart (<= 1 extra hour, inside the same daily window, a
# handful of indexed reads) instead of deferring the whole day until an operator
# reruns the command by hand. Exhausting the attempts still defers with exit 3.
python backend/scripts/refresh_stale_public_snapshots.py --commit --strict \
  --gate-wait-attempts 6 --gate-wait-seconds 600 \
  >> logs/refresh_public_snapshots.log 2>&1 || REFRESH_EXIT=$?
REFRESH_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$REFRESH_EXIT" -eq 0 ]; then
  notify_slack "✅ Public snapshot refresh completed
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/refresh_stale_public_snapshots.py --commit --strict
Started: $REFRESH_START_TIME
Completed: $REFRESH_END_TIME
Log: logs/refresh_public_snapshots.log"
elif [ "$REFRESH_EXIT" -eq 3 ]; then
  # Publication DEFERRED, not a build exception: the day's scrape cohort is not
  # observation-complete, so nothing was published and the previous good public
  # snapshots are preserved. This must NOT send the success message.
  REFRESH_DEFERRED=1
  DEFERRED_LINE=$(grep -a 'PUBLICATION_DEFERRED' logs/refresh_public_snapshots.log | tail -n 1 || true)

  notify_slack "⏸️ Public snapshot publication DEFERRED (cohort not ready; previous good snapshots preserved)
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/refresh_stale_public_snapshots.py --commit --strict
Started: $REFRESH_START_TIME
Deferred: $REFRESH_END_TIME
Details: ${DEFERRED_LINE:-see log}
Action: resolve/requeue the incomplete scrape batch, then rerun the refresh
Log: logs/refresh_public_snapshots.log"
else
  REFRESH_FAILED=1

  notify_slack "❌ Public snapshot refresh FAILED (stale snapshots may remain)
Host: $HOSTNAME_VALUE
Commit: $(git rev-parse HEAD)
Script: backend/scripts/refresh_stale_public_snapshots.py --commit --strict
Started: $REFRESH_START_TIME
Failed: $REFRESH_END_TIME
Exit: $REFRESH_EXIT
Log: logs/refresh_public_snapshots.log"
fi

# A deferred publication and a hard failure are distinct events (distinct Slack
# messages), but neither is a successful publication: the scheduled task must
# stay visibly non-successful so an operator acts before the next run. The
# simulation batch result is preserved independently above.
if [ "$SIMULATIONS_FAILED" -ne 0 ] || [ "$REFRESH_FAILED" -ne 0 ] || [ "$REFRESH_DEFERRED" -ne 0 ]; then
  exit 1
fi
