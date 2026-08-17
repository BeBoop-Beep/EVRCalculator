from __future__ import annotations

import argparse
import json

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
