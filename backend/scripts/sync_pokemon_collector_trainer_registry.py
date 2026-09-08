"""Seed reviewed Trainer identities from first-party Pokemon sources."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.collector_identity import normalize_identity_text  # noqa: E402
from backend.scripts.sync_pokemon_collector_identities import (  # noqa: E402
    CollectorIdentityRepository,
)

REGISTRY = ROOT / "backend/config/pokemon_collector_trainer_registry_v1.json"


def build_rows(payload):
    sources = payload["sources"]
    version = payload["registryVersion"]
    rows = []
    seen = set()
    for item in payload["trainers"]:
        name = " ".join(str(item["name"]).split())
        normalized = normalize_identity_text(name)
        if not normalized or normalized in seen:
            raise ValueError("Trainer names must be nonblank and unique after normalization")
        source_key = item["source"]
        if source_key not in sources:
            raise ValueError("Unknown Trainer source: %s" % source_key)
        seen.add(normalized)
        rows.append({
            "entity_type": "trainer",
            "canonical_key": "trainer:" + normalized,
            "display_name": name,
            "normalized_name": normalized,
            "active": True,
            "identity_metadata_json": {
                "registryVersion": version,
                "authoritativeSource": sources[source_key],
                "sourceIdentityName": name,
                "matchMethod": "reviewed_first_party_exact_v1",
                "confidence": 1.0,
                "manualOverride": False,
            },
        })
    return rows


def sync(repository, payload, dry_run=True):
    desired = build_rows(payload)
    existing = {
        row["canonical_key"]: row
        for row in repository.list_entities()
        if row.get("entity_type") == "trainer"
    }
    inserts = [row for row in desired if row["canonical_key"] not in existing]
    updates = [
        row for row in desired
        if row["canonical_key"] in existing
        and any(existing[row["canonical_key"]].get(k) != v for k, v in row.items())
    ]
    if not dry_run and (inserts or updates):
        repository.upsert_entities(inserts + updates)
    return {
        "status": "dry_run" if dry_run else "committed",
        "registryVersion": payload["registryVersion"],
        "trainersDeclared": len(desired),
        "inserts": len(inserts),
        "updates": len(updates),
        "unchanged": len(desired) - len(inserts) - len(updates),
        "sources": payload["sources"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--registry", default=str(REGISTRY))
    args = parser.parse_args()
    load_dotenv(ROOT / "backend/.env", override=False)
    payload = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    print(json.dumps(sync(CollectorIdentityRepository(), payload, not args.commit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
