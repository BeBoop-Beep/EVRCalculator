from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import supabase
from backend.db.services.sealed_product_replay_service import replay_sealed_products_for_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay sealed-product scoring from an exact run artifact")
    parser.add_argument("calculation_run_id")
    args = parser.parse_args()
    result = replay_sealed_products_for_run(supabase, args.calculation_run_id)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") != "unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
