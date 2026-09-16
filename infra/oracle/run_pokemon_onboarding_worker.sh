#!/usr/bin/env bash
set -euo pipefail

export HOME=/home/ubuntu
export PATH=/usr/local/bin:/usr/bin:/bin

REPO="/home/ubuntu/repos/EVRCalculator"
PYTHON="$REPO/.venv/bin/python"
WORKER="$REPO/backend/scripts/run_pending_pokemon_set_onboarding.py"
ENABLE_FILE="/home/ubuntu/.pokemon_onboarding_enabled"

MODE="${1:-dry-run}"

case "$MODE" in
  dry-run)
    MODE_FLAG="--dry-run"
    ;;
  commit)
    MODE_FLAG="--commit"

    if [[ ! -f "$ENABLE_FILE" ]]; then
      exit 0
    fi
    ;;
  *)
    echo "Usage: $0 {dry-run|commit}" >&2
    exit 64
    ;;
esac

cd "$REPO"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python virtual environment not found: $PYTHON" >&2
  exit 2
fi

if [[ ! -f "$WORKER" ]]; then
  echo "Onboarding worker not found: $WORKER" >&2
  exit 2
fi

if [[ "$MODE" == "commit" ]]; then
  CURRENT_BRANCH="$(git branch --show-current)"

  if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo "Refusing onboarding run: checkout is on $CURRENT_BRANCH, not main." >&2
    exit 2
  fi

  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Refusing onboarding run: production checkout is dirty." >&2
    git status --short >&2
    exit 2
  fi
fi

exec "$PYTHON" "$WORKER" \
  "$MODE_FLAG" \
  --resume-all \
  --max-jobs 5 \
  --json
