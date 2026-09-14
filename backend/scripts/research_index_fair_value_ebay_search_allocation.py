"""Search-efficiency research and a bounded deterministic allocation policy.

Analyzes retained E1 raw/matcher evidence for marginal yield per Browse
request, by page and by query formulation. Derives a deterministic allocator
for the E1 collector's CollectorConfig knobs -- this module does NOT call
eBay itself and does NOT optimize for raw listing count; the objective is
high-confidence usable evidence per API request.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RUNS_DIR = Path(__file__).resolve().parents[2] / "backend/artifacts/index_fair_value/ebay_evidence_runs"

ACCEPTED_STATES = frozenset({"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"})


def load_run(run_id: str) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    raw_path = RUNS_DIR / f"{run_id}.raw.jsonl"
    match_path = RUNS_DIR / f"{run_id}.matches.jsonl"
    raw = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    matches = {}
    if match_path.exists():
        for line in match_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                matches[(row["target_canonical_card_id"], row["ebay_item_id"])] = row
    return raw, matches


def load_runs(run_ids: Iterable[str]) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    all_raw: list[dict[str, Any]] = []
    all_matches: dict[tuple[str, str], dict[str, Any]] = {}
    for run_id in run_ids:
        raw, matches = load_run(run_id)
        all_raw.extend(raw)
        all_matches.update(matches)
    return all_raw, all_matches


def per_page_yield(raw: list[dict[str, Any]], matches: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (target, formulation, page): the marginal yield of that request."""
    by_key: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in raw:
        key = (row["target_canonical_card_id"], row["search_formulation"], row["page"])
        by_key[key].append(row)

    out = []
    seen_items_for_target_formulation: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key in sorted(by_key, key=lambda k: (k[0], k[1], k[2])):
        target, formulation, page = key
        rows = by_key[key]
        new_items = [r for r in rows if r["ebay_item_id"] not in seen_items_for_target_formulation[(target, formulation)]]
        seen_items_for_target_formulation[(target, formulation)].update(r["ebay_item_id"] for r in new_items)
        statuses = [matches.get((target, r["ebay_item_id"]), {}).get("match_status") for r in new_items]
        accepted = sum(1 for s in statuses if s in ACCEPTED_STATES)
        rejected = sum(1 for s in statuses if s == "REJECTED")
        ambiguous = sum(1 for s in statuses if s == "AMBIGUOUS")
        sellers = {r["seller_username"] for r in new_items if r.get("seller_username")}
        usable_price = sum(1 for r in new_items if r.get("price_value") is not None)
        usable_shipping = sum(1 for r in new_items if r.get("shipping_value") is not None)
        out.append({
            "target_canonical_card_id": target,
            "formulation": formulation,
            "page": page,
            "raw_listings": len(rows),
            "deduplicated_new_listings": len(new_items),
            "duplicate_rate": round(1 - len(new_items) / len(rows), 4) if rows else None,
            "accepted": accepted,
            "rejected": rejected,
            "ambiguous": ambiguous,
            "unique_new_sellers": len(sellers),
            "usable_price_count": usable_price,
            "usable_shipping_count": usable_shipping,
            "marginal_accepted_per_request": accepted,  # one request produced this page
        })
    return out


def summarize_by_page(page_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate across targets: page 1 vs page 2 vs page 3+, primary formulation only."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in page_rows:
        if row["formulation"] != "primary":
            continue
        bucket = "page_1" if row["page"] == 1 else "page_2" if row["page"] == 2 else "page_3_plus"
        buckets[bucket].append(row)
    summary = {}
    for bucket, rows in buckets.items():
        n_requests = len(rows)
        total_accepted = sum(r["accepted"] for r in rows)
        total_new = sum(r["deduplicated_new_listings"] for r in rows)
        summary[bucket] = {
            "requests": n_requests,
            "total_deduplicated_listings": total_new,
            "total_accepted": total_accepted,
            "accept_rate": round(total_accepted / total_new, 4) if total_new else None,
            "accepted_per_request": round(total_accepted / n_requests, 2) if n_requests else None,
        }
    return summary


def summarize_by_formulation(page_rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in page_rows:
        buckets[row["formulation"]].append(row)
    summary = {}
    for formulation, rows in buckets.items():
        n_requests = len(rows)
        total_accepted = sum(r["accepted"] for r in rows)
        total_new = sum(r["deduplicated_new_listings"] for r in rows)
        summary[formulation] = {
            "requests": n_requests,
            "total_deduplicated_listings": total_new,
            "total_accepted": total_accepted,
            "accept_rate": round(total_accepted / total_new, 4) if total_new else None,
            "accepted_per_request": round(total_accepted / n_requests, 2) if n_requests else None,
        }
    return summary


# --------------------------------------------------------------------------
# Deterministic, budget-safe allocation policy
# --------------------------------------------------------------------------


class AllocationConfig:
    """Derived from the measured page/formulation yield above:

    - primary/page1 dominates accepted-evidence-per-request; always fund it first.
    - primary/page2 roughly halves accept rate vs page1 -- only fund it when a
      target's accepted-evidence count is still below the usable minimum.
    - collector_number_focus/page1 returns ZERO overlap with primary (pure
      incremental evidence, not duplicate volume) and comparable-or-better
      accept rates -- fund it second, for seller-diversity, once every target
      has its guaranteed minimum.
    - deeper pages of either formulation collapse to near-zero marginal
      listings once a search's `next` is naturally near-exhausted; never
      chase them speculatively.
    """

    def __init__(
        self,
        min_pages_per_target: int = 1,
        usable_evidence_target: int = 15,
        max_pages_primary: int = 2,
        max_pages_broad: int = 1,
    ) -> None:
        self.min_pages_per_target = min_pages_per_target
        self.usable_evidence_target = usable_evidence_target
        self.max_pages_primary = max_pages_primary
        self.max_pages_broad = max_pages_broad


def allocate(
    targets: list[str],
    request_budget: int,
    config: AllocationConfig | None = None,
    current_accepted_by_target: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Deterministic, budget-bounded allocation plan.

    Guarantees every target its `min_pages_per_target` (primary page 1)
    before any target receives a second search or a deeper page -- so one
    noisy/illiquid card can never starve the rest of the cohort. Never
    exceeds `request_budget`. Never uses `total` or raw listing volume as a
    stopping signal (those aren't inputs here at all).
    """
    config = config or AllocationConfig()
    current_accepted_by_target = current_accepted_by_target or {}
    plan: dict[str, list[dict[str, str]]] = {t: [] for t in targets}
    remaining = request_budget

    # Tier 1: guaranteed minimum -- primary formulation, page 1, every target.
    reserved_for_tier1 = len(targets) * config.min_pages_per_target
    if reserved_for_tier1 > request_budget:
        raise ValueError("request_budget too small for minimum per-target allocation")
    for t in targets:
        if remaining <= 0:
            break
        plan[t].append({"formulation": "primary", "page": 1})
        remaining -= 1

    # Tier 2: broad formulation page 1 for every target (pure incremental evidence).
    for t in targets:
        if remaining <= 0:
            break
        plan[t].append({"formulation": "collector_number_focus", "page": 1})
        remaining -= 1

    # Tier 3: primary page 2 ONLY for targets still below the usable-evidence floor.
    for t in targets:
        if remaining <= 0:
            break
        if current_accepted_by_target.get(t, 0) < config.usable_evidence_target:
            plan[t].append({"formulation": "primary", "page": 2})
            remaining -= 1

    return {
        "plan": plan,
        "requests_planned": request_budget - remaining,
        "requests_remaining": remaining,
    }


def project_requests_for_cohort(cohort_size: int, config: AllocationConfig | None = None) -> dict[str, int]:
    config = config or AllocationConfig()
    tier1 = cohort_size * config.min_pages_per_target
    tier2 = cohort_size  # broad formulation page 1 for everyone
    tier3_worst_case = cohort_size  # primary page 2 for everyone, if all under floor
    return {
        "tier1_primary_page1": tier1,
        "tier2_broad_page1": tier2,
        "tier3_primary_page2_worst_case": tier3_worst_case,
        "minimum_requests": tier1,
        "typical_requests": tier1 + tier2,
        "worst_case_requests": tier1 + tier2 + tier3_worst_case,
    }


if __name__ == "__main__":
    print(json.dumps(project_requests_for_cohort(70), indent=2))
