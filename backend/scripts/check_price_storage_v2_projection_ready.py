"""Check whether Price Storage V2 is ready for a target post-scrape publication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import create_service_role_client, supabase
from backend.db.services.price_storage_v2_projection_gate import (
    REASON_AUTHORITY_UNAVAILABLE,
    _evaluate_projection_with_retry,
)

EXIT_READY = 0
EXIT_AUTHORITY_UNAVAILABLE = 1
EXIT_NOT_READY = 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    args = parser.parse_args()
    decision = _evaluate_projection_with_retry(
        supabase,
        args.market_date,
        client_factory=create_service_role_client,
        max_attempts=3,
    )
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True, default=str))
    if decision.ready:
        return EXIT_READY
    if decision.reason_code == REASON_AUTHORITY_UNAVAILABLE:
        return EXIT_AUTHORITY_UNAVAILABLE
    return EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
