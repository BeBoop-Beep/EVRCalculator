import json

import pytest

from backend.scripts.research_index_fair_value_ebay_search_allocation import (
    AllocationConfig,
    allocate,
    per_page_yield,
    project_requests_for_cohort,
    summarize_by_formulation,
    summarize_by_page,
)


def make_raw(item_id, target, formulation, page, seller="s1", price=10.0, cond="Ungraded"):
    return {
        "ebay_item_id": item_id, "target_canonical_card_id": target, "search_formulation": formulation,
        "page": page, "seller_username": seller, "price_value": price, "shipping_value": 2.0, "condition": cond,
    }


def make_match(target, item_id, status):
    return {"target_canonical_card_id": target, "ebay_item_id": item_id, "match_status": status}


# 9. per-page marginal-yield calculation
def test_per_page_marginal_yield_calculation():
    raw = [make_raw("A", "t1", "primary", 1), make_raw("B", "t1", "primary", 1), make_raw("C", "t1", "primary", 2)]
    matches = {("t1", "A"): make_match("t1", "A", "HIGH_CONFIDENCE"), ("t1", "B"): make_match("t1", "B", "REJECTED"),
               ("t1", "C"): make_match("t1", "C", "HIGH_CONFIDENCE")}
    pages = per_page_yield(raw, matches)
    page1 = next(p for p in pages if p["page"] == 1)
    page2 = next(p for p in pages if p["page"] == 2)
    assert page1["accepted"] == 1
    assert page1["rejected"] == 1
    assert page2["accepted"] == 1
    assert page2["deduplicated_new_listings"] == 1


# 10. duplicate listing handling
def test_duplicate_listing_across_pages_is_not_double_counted():
    raw = [make_raw("A", "t1", "primary", 1), make_raw("A", "t1", "primary", 2)]  # same item, appears again on page 2
    matches = {("t1", "A"): make_match("t1", "A", "HIGH_CONFIDENCE")}
    pages = per_page_yield(raw, matches)
    page2 = next(p for p in pages if p["page"] == 2)
    assert page2["deduplicated_new_listings"] == 0
    assert page2["duplicate_rate"] == 1.0


# 11. unique seller calculation
def test_unique_seller_calculation_counts_new_sellers_only():
    raw = [
        make_raw("A", "t1", "primary", 1, seller="s1"),
        make_raw("B", "t1", "primary", 1, seller="s2"),
        make_raw("C", "t1", "primary", 1, seller="s1"),  # repeat seller, still a new listing
    ]
    matches = {}
    pages = per_page_yield(raw, matches)
    assert pages[0]["unique_new_sellers"] == 2


def test_summaries_group_by_page_bucket_and_formulation():
    raw = [make_raw("A", "t1", "primary", 1), make_raw("B", "t1", "primary", 2), make_raw("C", "t1", "collector_number_focus", 1)]
    matches = {k: make_match(k[0], k[1], "HIGH_CONFIDENCE") for k in [("t1", "A"), ("t1", "B"), ("t1", "C")]}
    pages = per_page_yield(raw, matches)
    by_page = summarize_by_page(pages)
    assert "page_1" in by_page and "page_2" in by_page
    by_formulation = summarize_by_formulation(pages)
    assert "primary" in by_formulation and "collector_number_focus" in by_formulation


# 12. budget-aware allocation
def test_allocation_never_exceeds_budget():
    targets = [f"t{i}" for i in range(10)]
    result = allocate(targets, request_budget=15)
    assert result["requests_planned"] <= 15
    total_planned = sum(len(v) for v in result["plan"].values())
    assert total_planned == result["requests_planned"]


# 13. minimum allocation per target
def test_every_target_gets_minimum_allocation_before_any_gets_extra():
    targets = [f"t{i}" for i in range(5)]
    result = allocate(targets, request_budget=5)  # only enough for tier 1
    for t in targets:
        assert len(result["plan"][t]) == 1
        assert result["plan"][t][0] == {"formulation": "primary", "page": 1}


def test_insufficient_budget_for_minimum_allocation_raises():
    targets = [f"t{i}" for i in range(5)]
    with pytest.raises(ValueError):
        allocate(targets, request_budget=2)


# 14. marginal-yield stop rule
def test_primary_page_two_only_funded_below_usable_evidence_floor():
    targets = ["t1", "t2"]
    config = AllocationConfig(usable_evidence_target=15)
    current = {"t1": 20, "t2": 3}  # t1 already has enough evidence, t2 does not
    result = allocate(targets, request_budget=10, config=config, current_accepted_by_target=current)
    t1_pages2 = [s for s in result["plan"]["t1"] if s["formulation"] == "primary" and s["page"] == 2]
    t2_pages2 = [s for s in result["plan"]["t2"] if s["formulation"] == "primary" and s["page"] == 2]
    assert t1_pages2 == []
    assert t2_pages2 == [{"formulation": "primary", "page": 2}]


def test_allocation_does_not_starve_cohort_for_one_noisy_target():
    # even if one target "wants" more depth, every target still gets tier 1 + tier 2 first
    targets = [f"t{i}" for i in range(20)]
    result = allocate(targets, request_budget=40, current_accepted_by_target={"t0": 0})
    for t in targets:
        assert len(result["plan"][t]) >= 1


def test_projection_is_monotonic_and_budget_bounded():
    projection = project_requests_for_cohort(70)
    assert projection["minimum_requests"] == 70
    assert projection["worst_case_requests"] >= projection["typical_requests"] >= projection["minimum_requests"]
    assert projection["worst_case_requests"] <= 1000  # fits the E1 daily application budget
