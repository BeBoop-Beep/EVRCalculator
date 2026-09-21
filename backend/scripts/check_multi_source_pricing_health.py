"""Read-only health report for the daily multi-source pricing pipeline (P6M).

Exit code is 0 when canonical TCGplayer pricing is healthy, even if eBay/multi-source coverage is degraded; it is
non-zero only for a CRITICAL check (an unexpected non-TCGPlayer source in canonical/current pricing).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    from dotenv import load_dotenv

    from backend.db.clients.supabase_client import create_service_role_client
    from backend.pricing_pipeline import health

    load_dotenv(ROOT / "backend/.env", override=False)
    snapshot = health.gather(create_service_role_client())
    results = health.assess(snapshot)
    summary = health.overall(results)
    print(json.dumps({"summary": summary, "checks": results}, indent=2, default=str))
    return 0 if summary["canonical_pricing_healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
