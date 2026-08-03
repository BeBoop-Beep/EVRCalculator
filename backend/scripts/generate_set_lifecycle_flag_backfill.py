"""Generate the canonical-key lifecycle-flag lists used by migration 058.

The migration must not hand-maintain its catalog-only / simulation lists: they are
derived here from the *actual* ``SET_CONFIG_MAP`` classes and their attributes, and
``backend/tests/unit/db/test_set_lifecycle_flag_backfill.py`` asserts the committed
migration still matches what this generator produces.

Usage:
    python backend/scripts/generate_set_lifecycle_flag_backfill.py           # JSON
    python backend/scripts/generate_set_lifecycle_flag_backfill.py --sql     # SQL arrays
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.services.pokemon_set_lifecycle_flags import resolve_config_lifecycle_flags
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry


def build_lifecycle_backfill() -> Dict[str, Any]:
    registry = build_valid_set_key_registry()
    config_map: Dict[str, Any] = registry["config_map"]

    rows: List[Dict[str, Any]] = []
    for canonical_key in sorted(config_map):
        flags = resolve_config_lifecycle_flags(config_map[canonical_key])
        rows.append(
            {
                "canonical_key": canonical_key,
                "catalog_only": flags["catalog_only"],
                "supports_opening_simulation": flags["supports_opening_simulation"],
                "has_card_details_url": flags["has_card_details_url"],
                "ready_for_daily_scrape": flags["ready_for_daily_scrape"],
            }
        )

    catalog_only_keys = [r["canonical_key"] for r in rows if r["catalog_only"]]
    no_simulation_keys = [
        r["canonical_key"] for r in rows if not r["supports_opening_simulation"]
    ]
    daily_ready_keys = [r["canonical_key"] for r in rows if r["ready_for_daily_scrape"]]

    return {
        "total_configs": len(rows),
        "catalog_only_count": len(catalog_only_keys),
        "simulation_supported_count": len(rows) - len(no_simulation_keys),
        "daily_scrape_ready_count": len(daily_ready_keys),
        "catalog_only_keys": catalog_only_keys,
        "no_simulation_keys": no_simulation_keys,
        "daily_scrape_ready_keys": daily_ready_keys,
        "rows": rows,
    }


def _sql_array(keys: List[str]) -> str:
    if not keys:
        return "ARRAY[]::text[]"
    body = ",\n    ".join(f"'{key}'" for key in keys)
    return f"ARRAY[\n    {body}\n]::text[]"


def render_sql(backfill: Dict[str, Any]) -> str:
    return (
        "-- catalog_only canonical keys\n"
        f"{_sql_array(backfill['catalog_only_keys'])}\n\n"
        "-- non-simulation canonical keys\n"
        f"{_sql_array(backfill['no_simulation_keys'])}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql", action="store_true", help="Emit SQL array literals.")
    args = parser.parse_args()

    backfill = build_lifecycle_backfill()
    if args.sql:
        print(render_sql(backfill))
    else:
        print(json.dumps(backfill, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
