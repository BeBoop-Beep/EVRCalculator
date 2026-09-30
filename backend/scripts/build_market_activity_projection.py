"""Manual FMA-1 projection entry point; imports no provider client.

Production execution requires an explicitly configured repository adapter.
The default and CI-safe mode is dry-run fixture reconciliation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.domain.pokemon.market_activity import (
    aggregate_group_activity, assemble_constituent_page, assemble_instrument_detail,
)
from backend.domain.pokemon.market_activity_contract import SchemaRegistry

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "docs" / "research" / "market_activity_v1" / "fixtures"
CONTRACTS = ROOT / "docs" / "research" / "market_activity_v1" / "contracts"


def reconcile_fixtures() -> dict[str, object]:
    registry = SchemaRegistry(CONTRACTS)
    assemblers = {"instrument_detail": assemble_instrument_detail,
                  "constituent_page": assemble_constituent_page,
                  "group_activity": aggregate_group_activity}
    checked = []
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        fixture = json.loads((FIXTURES / entry["file"]).read_text(encoding="utf-8"))
        actual = assemblers[entry["assembler"]](fixture["inputs"])
        if actual != fixture["expected"]:
            raise RuntimeError(f"fixture drift: {entry['fixtureId']}")
        errors = registry.validate(actual, entry["responseSchema"])
        if errors:
            raise RuntimeError(f"schema drift: {entry['fixtureId']}: {errors[:3]}")
        checked.append(entry["fixtureId"])
    return {"mode": "dry-run", "providerCalls": 0, "productionWrites": 0,
            "fixtureCount": len(checked), "fixtures": checked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="validate all accepted fixtures without database writes")
    args = parser.parse_args()
    print(json.dumps(reconcile_fixtures(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
