"""Audit `stage1_composition_disqualifier` against the live sealed catalog.

The guard is a heuristic standing in for composition knowledge the canonical
classifier does not carry (a "Half Booster Box" is a booster box with 18 packs,
not 36). A heuristic that nobody re-checks against real data is how wrong numbers
get published, so this script enumerates EVERY sealed product of a Stage 1 family
across every simulation-supported set and reports exactly which SKUs the guard
rejects and why.

Read-only. Writes nothing.

    python backend/scripts/audit_stage1_composition_guard.py [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict, List

from backend.db.clients.supabase_client import supabase
from backend.db.repositories.sets_repository import get_set_by_canonical_key
from backend.db.services.pokemon_set_sealed_market_snapshot_service import read_snapshot
from backend.db.services.sealed_product_rip_service import select_stage1_products
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.domain.pokemon.sealed_product_composition import (
    COMPOSITION_INTEGRITY_VERSION,
    SUPPORTED_STAGE1_FAMILIES,
    stage1_composition_disqualifier,
)
from backend.jobs.evr_runner import _build_constants_config_map

logger = logging.getLogger(__name__)


def audit() -> Dict[str, Any]:
    rejected: List[Dict[str, Any]] = []
    accepted: List[Dict[str, Any]] = []
    sets_without_snapshot: List[str] = []
    family_counts: Dict[str, Dict[str, int]] = {}

    for canonical_key in sorted(_build_constants_config_map()):
        set_row = get_set_by_canonical_key(canonical_key)
        if not set_row:
            sets_without_snapshot.append(canonical_key)
            continue
        snapshot = read_snapshot(supabase, str(set_row["id"]))
        if not snapshot:
            sets_without_snapshot.append(canonical_key)
            continue

        for product in snapshot.get("products") or []:
            family = str(
                product.get("productFamily")
                or classify_sealed_product(product.get("name")).get("productFamily")
            )
            if family not in SUPPORTED_STAGE1_FAMILIES:
                continue

            bucket = family_counts.setdefault(family, {"seen": 0, "rejected": 0, "accepted": 0})
            bucket["seen"] += 1
            reason = stage1_composition_disqualifier(product.get("name"), product_family=family)
            entry = {
                "canonicalKey": canonical_key,
                "sealedProductId": product.get("sealedProductId"),
                "name": product.get("name"),
                "productFamily": family,
                "currentPrice": product.get("currentPrice"),
            }
            if reason is None:
                bucket["accepted"] += 1
                accepted.append(entry)
            else:
                bucket["rejected"] += 1
                rejected.append({**entry, "reason": reason})

        # Cross-check: the guard verdicts above must agree with what the real
        # selection path actually does, so this audit cannot drift from it.
        selection = select_stage1_products(snapshot)
        selected_ids = {str(c["sealed_product_id"]) for c in selection["candidates"]}
        guard_ids = {
            str(entry["sealedProductId"])
            for entry in accepted
            if entry["canonicalKey"] == canonical_key
        }
        priced_guard_ids = {
            gid
            for gid in guard_ids
            if gid not in {str(s["sealedProductId"]) for s in selection["skipped"]}
        }
        if priced_guard_ids != selected_ids:
            logger.warning(
                "Guard/selection disagreement for %s: guard=%s selection=%s",
                canonical_key,
                sorted(priced_guard_ids),
                sorted(selected_ids),
            )

    return {
        "compositionIntegrityVersion": COMPOSITION_INTEGRITY_VERSION,
        "supportedFamilies": sorted(SUPPORTED_STAGE1_FAMILIES),
        "familyCounts": family_counts,
        "rejected": sorted(rejected, key=lambda row: (row["productFamily"], row["canonicalKey"])),
        "accepted": sorted(accepted, key=lambda row: (row["productFamily"], row["canonicalKey"])),
        "setsWithoutSnapshot": sets_without_snapshot,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=None, help="Optional path to write the raw report.")
    args = parser.parse_args()

    report = audit()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    print(f"\ncompositionIntegrityVersion={report['compositionIntegrityVersion']}")
    print("\nStage 1 family SKU counts (live catalog):")
    for family, counts in sorted(report["familyCounts"].items()):
        print(f"  {family:24s} seen={counts['seen']:3d} accepted={counts['accepted']:3d} rejected={counts['rejected']:3d}")

    print(f"\nREJECTED SKUs ({len(report['rejected'])}):")
    for row in report["rejected"]:
        print(f"  [{row['reason']}] {row['canonicalKey']:22s} {row['productFamily']:22s} {row['name']}")

    print(f"\nACCEPTED SKUs ({len(report['accepted'])}):")
    for row in report["accepted"]:
        print(f"  {row['canonicalKey']:22s} {row['productFamily']:22s} {row['name']}")

    if report["setsWithoutSnapshot"]:
        print("\nSets with no sealed snapshot: " + ", ".join(report["setsWithoutSnapshot"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
