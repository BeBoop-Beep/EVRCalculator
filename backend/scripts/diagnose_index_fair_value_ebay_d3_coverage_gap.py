"""Diagnose the historical 55/70 card-coverage failure using retained D1/E1/E2
evidence only (never the historical blind cohorts). Classifies each of the 15
uncovered cards into a concrete cause rather than guessing, so any fix targets
search allocation, not matcher safety.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "backend/artifacts/index_fair_value"

MISSING_CARD_IDS = [
    "152906c9-3b9f-4f16-bb22-cb4241c7386b", "21e9ddc5-2751-4886-9e08-a1c6e2cc14e4",
    "24f40ecd-605f-4d62-b748-afed33706583", "2a67a99c-dbba-4c41-846c-39ed4659c916",
    "2bf67447-75e1-4e97-ac08-c7f3e7f2c88c", "3c75f577-62ee-4bdf-865c-ab2384f4379b",
    "50f67b41-059d-4c14-842f-8b48fba46bc2", "55096ab6-1773-47c4-bbff-20c1db011223",
    "740ad74c-8c0c-411f-9ec7-2c734210b8f1", "8a2827bc-48b7-4dfd-b240-501fe24100b9",
    "8a2cce32-ad4f-4468-8a28-8a9ea9653365", "cdfc0223-40ef-4e4b-a9f2-3a809ae1c3df",
    "d09b2fb5-41b6-4d1e-88cf-629402434501", "ec8fec81-b57d-442a-baf0-91882c40de6e",
    "ecfe51fb-3435-4e1c-8542-8809cd6f95ff",
]

# CAUSE codes: A=no useful inventory, B=query formulation failed to retrieve,
# C=inventory existed but matcher rejected it, D=identity ambiguity inherent,
# E=insufficient sample size, F=other.
SPARSE_EXACT_THRESHOLD = 3        # D1 exact-match count at/below this -> thin inventory
AMPLE_EXACT_THRESHOLD = 8         # at/above this -> ample inventory, coverage-cohort miss is a sampling artifact


def classify_card(card_result: dict[str, Any] | None) -> dict[str, Any]:
    if card_result is None:
        return {"cause": "F", "reason": "no D1 pilot result on file for this card"}
    exact = card_result["metrics"]["exact_match_listing_count"]
    returned = card_result["returned_count"]
    counts = card_result["counts"]
    ambiguous_rate = counts.get("AMBIGUOUS", 0) / returned if returned else 0
    if returned == 0:
        return {"cause": "A", "reason": "D1 retrieval returned zero listings", "d1_exact": exact, "d1_returned": returned}
    if exact <= SPARSE_EXACT_THRESHOLD and ambiguous_rate > 0.5:
        return {
            "cause": "D", "reason": "even a permissive title-only classifier found mostly ambiguous/near-zero exact matches",
            "d1_exact": exact, "d1_returned": returned, "ambiguous_rate": round(ambiguous_rate, 3),
        }
    if exact >= AMPLE_EXACT_THRESHOLD:
        return {
            "cause": "E", "reason": "ample exact-match inventory existed (D1); the 6-row coverage-cohort sample "
                                     "simply missed it -- a search-allocation/sampling-depth issue, not a matcher-safety issue",
            "d1_exact": exact, "d1_returned": returned,
        }
    return {"cause": "C", "reason": "moderate inventory existed but is thin enough that matcher rejection plausibly dominates",
            "d1_exact": exact, "d1_returned": returned}


def main() -> dict[str, Any]:
    pilot = json.loads((ARTIFACTS / "ebay_pilot_results.json").read_text(encoding="utf-8"))
    by_id = {c["canonical_card_id"]: c for c in pilot["card_results"]}
    per_card = {card_id: classify_card(by_id.get(card_id)) for card_id in MISSING_CARD_IDS}
    cause_counts: dict[str, int] = {}
    for entry in per_card.values():
        cause_counts[entry["cause"]] = cause_counts.get(entry["cause"], 0) + 1
    recoverable_via_allocation = sum(1 for e in per_card.values() if e["cause"] in {"E", "B"})
    result = {
        "version": "ebay_d3_coverage_gap_diagnosis_v1",
        "missing_card_count": len(MISSING_CARD_IDS),
        "per_card": per_card,
        "cause_counts": cause_counts,
        "recoverable_via_search_allocation_alone": recoverable_via_allocation,
        "methodology": "Uses only D1 pilot single-page retrieval evidence (a different, more permissive "
                        "classifier than v3) as a proxy for 'did useful inventory exist at all' -- never opens "
                        "the historical blind cohorts.",
    }
    (ARTIFACTS / "ebay_d3_coverage_gap_diagnosis.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
