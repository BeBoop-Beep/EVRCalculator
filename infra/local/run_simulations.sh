#!/bin/bash
set -euo pipefail

export PYTHONIOENCODING=utf-8

# Production should point this at an isolated checkout/worktree used only by the
# scheduler (for example /d/EVRCalculator-production). The compatibility default
# remains the historical path until the scheduled task is migrated.
REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"

# Checked BEFORE `cd`, and before anything is sourced. Under `set -e` a failing
# `cd` would abort with no message at all, and the Task Scheduler log would show
# an empty run - the least diagnosable possible failure for an unattended job
# whose whole purpose is to be trustworthy when nobody is watching.
if [ ! -d "$REPO_DIR" ]; then
  echo "[publication-checkout] REFUSED: repository directory does not exist: $REPO_DIR" >&2
  echo "  Create the production worktree first, or unset EVR_PRODUCTION_REPO_DIR to run" >&2
  echo "  against the development checkout in local mode." >&2
  exit 2
fi
cd "$REPO_DIR"

if [ -f backend/.env ]; then
  set -a
  source backend/.env
  set +a
fi

if [ ! -f .venv/Scripts/activate ]; then
  mkdir -p logs
  echo "[publication-checkout] REFUSED: no virtual environment at $REPO_DIR/.venv" \
    | tee -a logs/run_simulations.log >&2
  exit 2
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

# Checkout handling has exactly two paths:
#
#   local (the default) - development. Log what is checked out and continue.
#     Nothing about the branch, the HEAD, the working tree or origin can refuse
#     the run: the whole point is to exercise the code the developer currently
#     has in the tree, including uncommitted changes.
#   production - opt in with EVR_PUBLICATION_CHECKOUT_MODE=production. Strict and
#     fail-closed, so the scheduled task can never publish from an accidental
#     feature/research checkout or a dirty tree.
EVR_PUBLICATION_CHECKOUT_MODE="${EVR_PUBLICATION_CHECKOUT_MODE:-local}"
EXPECTED_PUBLICATION_BRANCH="${EXPECTED_PUBLICATION_BRANCH:-main}"
ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT="${ALLOW_UNVERIFIED_PUBLICATION_CHECKOUT:-0}"
PUBLICATION_FETCH_ORIGIN="${PUBLICATION_FETCH_ORIGIN:-0}"

# Reported in every log line and notification. EXPECTED_PUBLICATION_BRANCH is only
# ever a production requirement, never a report of what actually ran.
ACTUAL_PUBLICATION_BRANCH="$(git symbolic-ref --short -q HEAD || true)"
PUBLICATION_HEAD_SHA=""
PUBLICATION_WORKING_TREE_STATE="unknown"

log_local_checkout() {
  # Informational ONLY. This function must never return nonzero and must never
  # inspect the branch name, remote refs, or dirtiness as a pass/fail condition.
  ACTUAL_PUBLICATION_BRANCH=$(git symbolic-ref --short -q HEAD || true)
  PUBLICATION_HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || true)

  local dirty_files=""
  dirty_files=$(git status --porcelain --untracked-files=no 2>/dev/null || true)
  if [ -n "$dirty_files" ]; then
    PUBLICATION_WORKING_TREE_STATE="modified"
  else
    PUBLICATION_WORKING_TREE_STATE="clean"
  fi

  local checkout_line="[publication-checkout] mode=local repo=$REPO_DIR branch=${ACTUAL_PUBLICATION_BRANCH:-detached} head=${PUBLICATION_HEAD_SHA:-unknown} working_tree=$PUBLICATION_WORKING_TREE_STATE"
  echo "$checkout_line" | tee -a logs/run_simulations.log logs/refresh_public_snapshots.log
  return 0
}

verify_production_checkout() {
  local head_sha=""
  local origin_sha=""
  local dirty_files=""
  local failure_reason=""

  if [ "$PUBLICATION_FETCH_ORIGIN" = "1" ]; then
    if ! git fetch --quiet origin "$EXPECTED_PUBLICATION_BRANCH"; then
      failure_reason="git fetch origin $EXPECTED_PUBLICATION_BRANCH failed"
    fi
  fi

  ACTUAL_PUBLICATION_BRANCH=$(git symbolic-ref --short -q HEAD || true)
  head_sha=$(git rev-parse HEAD 2>/dev/null || true)
  origin_sha=$(git rev-parse --verify --quiet "refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH" || true)
  dirty_files=$(git status --porcelain --untracked-files=no 2>/dev/null || true)

  PUBLICATION_HEAD_SHA="$head_sha"
  if [ -n "$dirty_files" ]; then
    PUBLICATION_WORKING_TREE_STATE="modified"
  else
    PUBLICATION_WORKING_TREE_STATE="clean"
  fi

  if [ -z "$failure_reason" ] && [ "$ACTUAL_PUBLICATION_BRANCH" != "$EXPECTED_PUBLICATION_BRANCH" ]; then
    failure_reason="expected branch $EXPECTED_PUBLICATION_BRANCH but checkout is ${ACTUAL_PUBLICATION_BRANCH:-detached}"
  elif [ -z "$failure_reason" ] && [ -z "$head_sha" ]; then
    failure_reason="unable to resolve checkout HEAD"
  elif [ -z "$failure_reason" ] && [ -z "$origin_sha" ]; then
    failure_reason="unable to resolve refs/remotes/origin/$EXPECTED_PUBLICATION_BRANCH"
  elif [ -z "$failure_reason" ] && [ "$head_sha" != "$origin_sha" ]; then
    failure_reason="checkout HEAD $head_sha does not match origin/$EXPECTED_PUBLICATION_BRANCH $origin_sha"
  elif [ -z "$failure_reason" ] && [ -n "$dirty_files" ]; then
    failure_reason="tracked working-tree changes are present"
  fi

  local checkout_line="[publication-checkout] mode=production repo=$REPO_DIR branch=${ACTUAL_PUBLICATION_BRANCH:-detached} head=${head_sha:-unknown} expected_branch=$EXPECTED_PUBLICATION_BRANCH origin_sha=${origin_sha:-unknown} working_tree=$PUBLICATION_WORKING_TREE_STATE fetch_origin=$PUBLICATION_FETCH_ORIGIN"
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
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
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
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Reason: $failure_reason
HEAD: ${head_sha:-unknown}
Expected: origin/$EXPECTED_PUBLICATION_BRANCH ${origin_sha:-unknown}
Action: deploy the latest clean $EXPECTED_PUBLICATION_BRANCH checkout or set the emergency override explicitly."
  return 2
}

# The repository path itself is the only thing both paths insist on. Beyond that,
# ONLY production mode can refuse a run; the local path never returns nonzero, so
# a feature branch with uncommitted tracked changes runs with no env vars set.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[publication-checkout] REFUSED: repository path is not a Git worktree: $REPO_DIR" \
    | tee -a logs/run_simulations.log logs/refresh_public_snapshots.log
  exit 2
fi

case "$EVR_PUBLICATION_CHECKOUT_MODE" in
  production)
    # Explicit `|| exit`: production mode is fail-closed, and relying on `set -e`
    # to notice a nonzero return from a function call is exactly the kind of
    # implicit behaviour an unattended publication job should not depend on.
    verify_production_checkout || exit $?
    ;;
  *)
    log_local_checkout
    ;;
esac

# Environment provenance, logged on every run. The Supabase PROJECT REF is an
# identifier, not a secret - it is in every request URL. No key, token or
# connection string is ever echoed.
SUPABASE_PROJECT_REF="$(printf '%s' "${SUPABASE_URL:-}" | sed -n 's#^https\?://\([^.]*\)\..*#\1#p')"
echo "[publication-environment] repo=$REPO_DIR python=$(command -v python) \
supabase_project=${SUPABASE_PROJECT_REF:-unknown} mode=$EVR_PUBLICATION_CHECKOUT_MODE" \
  | tee -a logs/run_simulations.log

notify_slack "🚀 Simulation job started
Host: $HOSTNAME_VALUE
Repo: $REPO_DIR
Mode: $EVR_PUBLICATION_CHECKOUT_MODE
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Commit: $(git rev-parse HEAD)
Working tree: $PUBLICATION_WORKING_TREE_STATE
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
  # Deliberately NO success notification here. "Publication exited 0" is not the
  # same claim as "what got published is current": the final read-only audit
  # below re-reads the published market-dashboard rows, and only after IT passes
  # has anything actually completed. Announcing success at this point is how a
  # green Slack message accompanied an Overview still serving the previous day's
  # Opening Profit vs Cost.
  echo "[publication] orchestrator exited 0; withholding success notification until the final audit passes" \
    >> logs/run_simulations.log
elif [ "$PUBLICATION_EXIT" -eq 3 ]; then
  # Publication DEFERRED, not a build exception: the day's scrape cohort is not
  # observation-complete, so nothing was published and the previous good public
  # snapshots are preserved. This must NOT send the success message.
  PUBLICATION_DEFERRED=1
  DEFERRED_LINE=$(grep -a 'PUBLICATION_DEFERRED' logs/refresh_public_snapshots.log | tail -n 1 || true)

  notify_slack "⏸️ Public snapshot publication DEFERRED (cohort not ready; previous good snapshots preserved)
Host: $HOSTNAME_VALUE
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
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
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
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
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Commit: $(git rev-parse HEAD)
Script: backend/scripts/audit_opening_analytics_publication.py
Exit: $AUDIT_EXIT
Details: ${AUDIT_LINE:-see log}
Action: Opening Profit vs Cost and/or Top Chase windows are behind for at least one supported set
Log: logs/opening_analytics_audit.log"
fi

# ── Canonical public RIP leaderboard audit ──────────────────────────────────
# A SEPARATE tripwire from the opening-analytics audit above, gated on its own
# exit variable, because the two answer different questions and either can be
# green while the other is red:
#
#   audit_opening_analytics_publication  - did Opening Profit vs Cost and the Top
#     Chase movement windows reach the promoted market date?
#   audit_public_rip_leaderboard_publication - is the PUBLISHED leaderboard on
#     the canonical contract (Financial RIP V3, Collector Appeal V3, Overall RIP
#     V7, public contract v7) over the full authoritative supported cohort?
#
# The second is what would have caught the leaderboard that reported
# `overall_rip_v4_90_financial_10_ca7` while 22 fresh V3 simulations sat under
# it. A scoring-version regression moves no timestamp and changes no market
# date, so the opening-analytics audit passes straight through it.
PUBLIC_RIP_AUDIT_EXIT=0
python -m backend.scripts.audit_public_rip_leaderboard_publication --json \
  >> logs/public_rip_audit.log 2>&1 || PUBLIC_RIP_AUDIT_EXIT=$?

if [ "$PUBLIC_RIP_AUDIT_EXIT" -ne 0 ]; then
  PUBLIC_RIP_AUDIT_LINE=$(tail -n 1 logs/public_rip_audit.log || true)

  notify_slack "❌ Canonical public RIP leaderboard audit FAILED
Host: $HOSTNAME_VALUE
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Commit: $(git rev-parse HEAD)
Script: backend/scripts/audit_public_rip_leaderboard_publication.py
Exit: $PUBLIC_RIP_AUDIT_EXIT
Canonical versions expected:
  Financial RIP  : financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5
  Collector Appeal: collector_appeal_v4_h_only_d_baseline_up4_down2
  Overall RIP    : overall_rip_v10_90_financial_v4_10_collector_appeal_v5
  Public contract: public_rip_contract_v10
Details: ${PUBLIC_RIP_AUDIT_LINE:-see log}
Action: the published leaderboard is not on the canonical contract, or does not cover the full supported cohort. Rebuild and republish; do NOT treat the Explore RIP leaderboard as current.
Log: logs/public_rip_audit.log"
fi

# Private Budget Ranking is part of this same daily reconciliation lifecycle,
# not a second scheduler.  It runs only after the public publication and both
# independent final audits passed, and before the one success notification.
BUDGET_RANKING_EXIT=0
BUDGET_RANKING_STATUS="NOT_RUN"
BUDGET_RANKING_DETAIL=""
BUDGET_RANKING_SLACK_LINE=""
BUDGET_RANKING_REPORT="logs/budget_product_ranking_publication.json"
# Budget Ranking owns its readiness gates. Attempt it after the opening workflow
# regardless of unrelated Market/leaderboard audit outcomes; report each result
# independently and preserve the last-known-good ranking on a failed gate.
if [ "$PUBLICATION_EXIT" -ne 3 ]; then
  python -m backend.scripts.publish_budget_product_rankings_if_ready --commit \
    --json-report "$BUDGET_RANKING_REPORT" >> logs/run_simulations.log 2>&1 || BUDGET_RANKING_EXIT=$?
  BUDGET_RANKING_STATUS=$(python - "$BUDGET_RANKING_REPORT" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("status", "REPORT_UNREADABLE"))
except Exception:
    print("REPORT_UNREADABLE")
PY
)
  BUDGET_RANKING_DETAIL=$(python - "$BUDGET_RANKING_REPORT" <<'PY'
import json, sys
try:
    r=json.load(open(sys.argv[1], encoding="utf-8"))
    print("status=%s price_as_of=%s snapshot=%s rows=%s warnings=%s" %
          (r.get("status"), r.get("selected_price_as_of"), r.get("snapshot_id"),
           r.get("row_count"), len(r.get("warnings") or [])))
except Exception as exc:
    print("report_error=%s" % exc)
PY
)
  echo "[budget-ranking] $BUDGET_RANKING_DETAIL" >> logs/run_simulations.log

  if [ "$BUDGET_RANKING_STATUS" = "PUBLISHED" ]; then
    BUDGET_RANKING_SLACK_LINE="Private Budget Ranking: $BUDGET_RANKING_DETAIL"
  fi

  if [ "$BUDGET_RANKING_EXIT" -eq 3 ] && [ "$BUDGET_RANKING_STATUS" = "UPSTREAM_NOT_READY" ]; then
    # Public publication succeeded; private ranking remains on last-known-good
    # and naturally reconciles on the next invocation.  STALE is exit 1 and
    # alerts below, so a genuinely missed second cycle cannot hide here.
    BUDGET_RANKING_EXIT=0
  elif [ "$BUDGET_RANKING_EXIT" -ne 0 ]; then
    notify_slack "❌ Private Budget Ranking blocked after successful public publication
Host: $HOSTNAME_VALUE
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Commit: $(git rev-parse HEAD)
Status: $BUDGET_RANKING_STATUS
Details: $BUDGET_RANKING_DETAIL
Public publication: succeeded and audited; previous private ranking remains authoritative
Log: logs/run_simulations.log"
  fi
fi

# The ONLY success notification. It requires publication exit 0 AND BOTH final
# audits, so "completed" means the published rows actually reached the promoted
# market date AND the leaderboard is on the canonical contract — not merely that
# the commands ran. Deferred (⏸️) and failure (❌) notifications above remain
# distinct events and are never replaced by this one.
#
# A passing opening-analytics audit can NEVER produce this message on its own:
# the two audits certify different properties, and one standing in for the other
# is how a green Slack message accompanied a leaderboard published under a
# superseded scoring contract.
if [ "$PUBLICATION_EXIT" -eq 0 ] && [ "$AUDIT_EXIT" -eq 0 ] && [ "$PUBLIC_RIP_AUDIT_EXIT" -eq 0 ]; then
  if [ "$BUDGET_RANKING_EXIT" -eq 0 ]; then
  AUDIT_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
  notify_slack "✅ Simulation + publication completed (both final audits passed)
Host: $HOSTNAME_VALUE
Branch: ${ACTUAL_PUBLICATION_BRANCH:-detached}
Commit: $(git rev-parse HEAD)
Script: backend/scripts/run_daily_opening_publication.py
Started: $PUBLICATION_START_TIME
Published: $PUBLICATION_END_TIME
Audited: $AUDIT_END_TIME
Public RIP audit: passed
${BUDGET_RANKING_SLACK_LINE}
Log: logs/run_simulations.log"
  fi
fi

# A deferred publication, a hard failure and EITHER failed audit are distinct
# events (distinct Slack messages), but none of them is a successful
# publication: the scheduled task must stay visibly non-successful so an
# operator acts before the next run.
if [ "$PUBLICATION_FAILED" -ne 0 ] || [ "$PUBLICATION_DEFERRED" -ne 0 ] \
   || [ "$AUDIT_EXIT" -ne 0 ] || [ "$PUBLIC_RIP_AUDIT_EXIT" -ne 0 ]; then
  exit 1
fi
if [ "$BUDGET_RANKING_EXIT" -ne 0 ]; then
  exit 1
fi
