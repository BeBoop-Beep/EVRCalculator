import copy
from types import SimpleNamespace

import pytest

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_TYPE_FULL_MARKET, BUDGET_TYPE_STANDARD, CANONICAL_BUDGET_BANDS,
)
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION, EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_COLLECTOR_APPEAL_VERSION, EXPECTED_FINANCIAL_RIP_VERSION,
    EXPECTED_OVERALL_RIP_V12_VERSION, EXPECTED_OVERALL_RIP_VERSION,
)
from backend.db.services.budget_product_ranking_readiness import BudgetRankingStatus, EXIT_CODES
from backend.scripts import publish_budget_product_rankings_if_ready as wrapper


def _payload(n=2):
    snapshot = {"full_market_budget": 150.0, "max_eligible_sku_price": 101.0, "eligible_cohort_count": n,
                "pinned_price_as_of": "2026-08-22", "ranking_method_version": "budget_product_ranking_v1",
                "allocation_method_version": "budget_allocation_floor_quantity_v1"}
    rows=[]
    for budget, kind in [*((float(b), BUDGET_TYPE_STANDARD) for b in CANONICAL_BUDGET_BANDS), (150.0, BUDGET_TYPE_FULL_MARKET)]:
        for rank in range(1, n+1):
            price=10.0; quantity=int(float(budget)//price); committed=quantity*price
            row={"sealed_product_id":f"p{rank}","set_id":"s","product_family":"booster_box","target_budget":float(budget),"budget_type":kind,
                 "quantity":quantity,"actual_committed_capital":committed,"unused_capital":float(budget)-committed,
                 "unused_capital_percent":(float(budget)-committed)/float(budget),"capital_utilization":committed/float(budget),
                 "budget_rank":rank,"budget_cohort_size":n,"budget_tier":"B","financial_only_rank":rank,
                 "financial_rip_v4_score":50,"overall_rip_v10_score":51,"collector_appeal_score":60,
                 "chance_to_recover_capital":.2,"source_calculation_run_id":"r","price_as_of":"2026-08-22",
                 "full_market_anchor":None,"max_eligible_sku_price":None,"full_market_rounding_rule":None,
                 "full_market_rounding_increment":None,"full_market_rounding_rule_version":None}
            if kind == BUDGET_TYPE_FULL_MARKET:
                row.update(full_market_anchor=150.0,max_eligible_sku_price=101.0,full_market_rounding_rule="ceil",full_market_rounding_increment=50.0,full_market_rounding_rule_version="full_market_next_50_above_max_eligible_sku_v1")
            rows.append(row)
    return snapshot, rows


def test_payload_hard_gates_accept_dynamic_n_and_all_canonical_cohorts():
    snapshot, rows = _payload(3)
    assert wrapper.validate_publication_payload(snapshot, rows) == []


@pytest.mark.parametrize("mutation,gate", [
    (lambda s,r: r.pop(), "cohort_integrity"),
    (lambda s,r: r[0].update(budget_rank=9), "cohort_integrity"),
    (lambda s,r: r[0].update(financial_only_rank=9), "cohort_integrity"),
    (lambda s,r: r[0].update(quantity=0), "required_values"),
    (lambda s,r: r[0].update(unused_capital=1), "capital_reconciliation"),
    (lambda s,r: r[0].update(capital_utilization=.5), "utilization_complement"),
    (lambda s,r: s.update(full_market_budget=200), "canonical_cohorts"),
    (lambda s,r: r[0].update(full_market_anchor=150), "standard_metadata"),
])
def test_payload_gate_failures(mutation, gate):
    snapshot, rows = _payload(); mutation(snapshot, rows)
    assert gate in {x["gate"] for x in wrapper.validate_publication_payload(snapshot, rows)}


def test_warning_thresholds_do_not_block():
    results={"financialDominanceInversionRate":.02,"budgets":{"x":{"utilizationRankSpearman":.3}}}
    diagnostics, warnings=wrapper.health_diagnostics(results)
    assert len(warnings)==2 and diagnostics["periodic_research_audit_due"]


def test_status_exit_code_contract():
    assert EXIT_CODES[BudgetRankingStatus.PUBLISHED] == 0
    assert EXIT_CODES[BudgetRankingStatus.NO_NEW_AUTHORITY] == 0
    assert EXIT_CODES[BudgetRankingStatus.UPSTREAM_NOT_READY] == 3
    assert all(EXIT_CODES[s] == 1 for s in BudgetRankingStatus if s not in {BudgetRankingStatus.PUBLISHED, BudgetRankingStatus.NO_NEW_AUTHORITY, BudgetRankingStatus.UPSTREAM_NOT_READY})


def test_json_report_contract_has_every_field():
    assert set(wrapper.REPORT_FIELDS) <= set(wrapper._base_report())


def test_noop_skips_builder_and_rpc(monkeypatch):
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: {"pinned_price_as_of": "2026-08-22"})
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda *_a, **_k: SimpleNamespace(
        status=BudgetRankingStatus.NO_NEW_AUTHORITY, selected_price_as_of="2026-08-22",
        promoted_market_date="2026-08-22", candidate_authorities=[], gate_results=[],
        failure_reason=None, failed_gate=None))
    monkeypatch.setattr(wrapper, "build_rankings_for_cohort", lambda *_a: pytest.fail("builder called"))
    monkeypatch.setattr(wrapper, "publish_rankings", lambda *_a: pytest.fail("RPC called"))
    code, report = wrapper.run(commit=True, client=object())
    assert code == 0 and report["status"] == "NO_NEW_AUTHORITY"


@pytest.mark.parametrize("status,exit_code", [
    (BudgetRankingStatus.UPSTREAM_NOT_READY, 3),
    (BudgetRankingStatus.METHOD_VERSION_MISMATCH, 1),
    (BudgetRankingStatus.HEALTH_GATE_BLOCKED, 1),
    (BudgetRankingStatus.STALE, 1),
])
def test_prebuild_statuses_return_contract_exit(monkeypatch, status, exit_code):
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: None)
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda *_a, **_k: SimpleNamespace(
        status=status, selected_price_as_of=None, promoted_market_date="2026-08-22",
        candidate_authorities=[], gate_results=[], failure_reason="blocked", failed_gate="authority"))
    code, report = wrapper.run(commit=True, client=object())
    assert code == exit_code and report["status"] == status.value


def _v12_row(sealed_product_id, rank, size, *, rankable=True, version=EXPECTED_OVERALL_RIP_V12_VERSION):
    return {
        "sealedProductId": sealed_product_id, "setId": "s", "budgetRank": rank, "budgetCohortSize": size,
        "overallRipV12Rankable": rankable, "overallRipV12Score": 70.0 if rankable else None,
        "overallRipV12Version": version,
    }


def _v12_results(n=2, mutate=None):
    rows = [_v12_row("p%d" % i, i, n) for i in range(1, n + 1)]
    results = {
        "authority": {
            "overallRipVersion": EXPECTED_OVERALL_RIP_VERSION,
            "financialRipVersion": EXPECTED_FINANCIAL_RIP_VERSION,
            "collectorAppealVersion": EXPECTED_COLLECTOR_APPEAL_VERSION,
            "productCount": n, "calculationRunIds": ["r"],
        },
        "v12Readiness": {
            "overallRipV12Version": EXPECTED_OVERALL_RIP_V12_VERSION,
            "chaseAccessibilityVersion": EXPECTED_CHASE_ACCESSIBILITY_VERSION,
            "transformVersion": EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
            "perSet": {"s": {"eligible": True}},
            "eligibleSetIds": ["s"], "allSetsEligible": True, "unexpectedAuthorityMix": False, "ready": True,
        },
        "accessibilityResolution": {
            "chaseAccessibilityVersion": EXPECTED_CHASE_ACCESSIBILITY_VERSION,
            "transformVersion": EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
            "batchReadCount": 1, "requestedSetCount": 1, "readySetCount": 1, "failures": [],
        },
        "productCount": n,
        "batchAccessibilityReadCount": 1,
        "budgets": {"standard:25": {"rows": rows, "unrankable": []}},
    }
    if mutate:
        mutate(results)
    return results


def test_v12_candidate_passes_when_all_authority_matches():
    assert wrapper.validate_v12_publication_payload(_v12_results(3)) == []


def test_v12_dry_run_never_touches_publish_rpc_and_never_writes(monkeypatch):
    monkeypatch.setattr(wrapper, "build_v12_shadow_rankings_for_cohort", lambda *_a, **_k: _v12_results(2))
    monkeypatch.setattr(wrapper, "publish_rankings", lambda *_a, **_k: pytest.fail("RPC called"))
    out = wrapper.run_v12_dry_run(client=object(), products=[], authority={})
    assert out["report"]["passed"] is True
    assert "commit" not in wrapper.run_v12_dry_run.__code__.co_varnames


def test_v12_fails_wrong_overall_version():
    results = _v12_results(2, mutate=lambda r: r["v12Readiness"].update(overallRipV12Version="wrong"))
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_overall_version" in gates


def test_v12_fails_stale_accessibility_run():
    results = _v12_results(2, mutate=lambda r: r["v12Readiness"].update(
        allSetsEligible=False, perSet={"s": {"eligible": False, "reason": "stale_calculation_run"}}))
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_set_eligibility" in gates


def test_v12_fails_insufficient_mapped_hc_mass():
    def mutate(r):
        r["v12Readiness"]["allSetsEligible"] = False
        r["v12Readiness"]["perSet"] = {"s": {"eligible": False, "reason": "insufficient_mapped_hc_mass", "detail": 0.5}}
    results = _v12_results(2, mutate=mutate)
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_set_eligibility" in gates


def test_v12_fails_mixed_v10_v12_ranking_authority():
    def mutate(r):
        r["budgets"]["standard:25"]["rows"][0]["overallRipV12Rankable"] = False
        r["budgets"]["standard:25"]["rows"][0]["overallRipV12Score"] = None
    results = _v12_results(2, mutate=mutate)
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_mixed_authority_rows" in gates


def test_v12_fails_unrankable_eligible_row_present_in_ranked_rows():
    def mutate(r):
        r["budgets"]["standard:25"]["unrankable"] = [{"sealedProductId": "p1", "reason": "should_have_been_excluded"}]
    results = _v12_results(2, mutate=mutate)
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_unrankable_eligible_row" in gates


def test_v12_fails_missing_v12_rank_field():
    def mutate(r):
        r["budgets"]["standard:25"]["rows"][0]["budgetRank"] = None
    results = _v12_results(2, mutate=mutate)
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_cohort_integrity" in gates or "v12_missing_rank_fields" in gates


def test_v12_fails_when_base_cohort_authority_is_not_v10():
    results = _v12_results(2, mutate=lambda r: r["authority"].update(overallRipVersion="something_else"))
    gates = {f["gate"] for f in wrapper.validate_v12_publication_payload(results)}
    assert "v12_base_cohort_authority" in gates


def test_v12_validation_performs_zero_publication_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(wrapper, "publish_rankings", lambda *_a, **_k: calls.append(True))
    results = _v12_results(2)
    frozen = copy.deepcopy(results)
    wrapper.validate_v12_publication_payload(results)
    assert results == frozen
    assert calls == []


def test_default_invocation_is_not_v12(monkeypatch):
    """`run()`'s default V10 path must never reach any V12 code path."""
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: {"pinned_price_as_of": "2026-08-22"})
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda *_a, **_k: SimpleNamespace(
        status=BudgetRankingStatus.NO_NEW_AUTHORITY, selected_price_as_of="2026-08-22",
        promoted_market_date="2026-08-22", candidate_authorities=[], gate_results=[],
        failure_reason=None, failed_gate=None))
    monkeypatch.setattr(wrapper, "build_v12_shadow_rankings_for_cohort",
                         lambda *_a, **_k: pytest.fail("V12 builder must never be called by default run()"))
    code, report = wrapper.run(commit=True, client=object())
    assert code == 0 and report["status"] == "NO_NEW_AUTHORITY"
    assert report.get("overall_rip_version") == EXPECTED_OVERALL_RIP_VERSION or "overall_rip_v12" not in str(report)


def test_default_client_factory_is_explicit_service_role(monkeypatch):
    sentinel = object(); calls=[]
    monkeypatch.setattr(wrapper, "create_service_role_client", lambda: calls.append(True) or sentinel)
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: None)
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda client, **_k: SimpleNamespace(
        status=BudgetRankingStatus.UPSTREAM_NOT_READY, selected_price_as_of=None,
        promoted_market_date=None, candidate_authorities=[], gate_results=[], failure_reason="wait", failed_gate="authority"))
    wrapper.run(commit=False)
    assert calls == [True]


def test_default_run_attaches_v12_canonical_validation_when_v12_is_canonical(monkeypatch):
    """Phase 11 cutover: the DEFAULT/NORMAL publisher path (not the explicit
    --v12 validator) now additionally reports whether the SAME cohort is
    V12-rankable under the backend-wide canonical selector, reusing
    `run_v12_dry_run`'s validator rather than a second implementation. This
    must be purely additive: it never changes `status`/`failed_gate`, and the
    V10-shaped `snapshot`/`rows` persisted by `publish_rankings` are untouched."""
    assert wrapper.default_budget_sort_authority_is_v12() is True

    products = [{"sealedProductId": "p1"}]
    authority = {"overallRipVersion": EXPECTED_OVERALL_RIP_VERSION, "calculationRunIds": ["r"]}
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: None)
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda *_a, **_k: SimpleNamespace(
        status=BudgetRankingStatus.PUBLISHED, selected_price_as_of="2026-09-03",
        promoted_market_date="2026-09-03", candidate_authorities=[], gate_results=[],
        failure_reason=None, failed_gate=None, products=products, authority=authority))
    snapshot = {"full_market_budget": 500.0, "max_eligible_sku_price": 480.0, "eligible_cohort_count": 1, "cohort_fingerprint": "fp"}
    rows = []
    monkeypatch.setattr(wrapper, "build_rankings_for_cohort", lambda *_a: {"productCount": 1, "budgets": {}})
    monkeypatch.setattr(wrapper, "to_publication_payload", lambda _r: (snapshot, rows))
    monkeypatch.setattr(wrapper, "validate_publication_payload", lambda *_a: [])
    monkeypatch.setattr(wrapper, "health_diagnostics", lambda _r: ({}, []))
    v12_report = {"passed": True, "mode": "v12_explicit_validation_only"}
    monkeypatch.setattr(wrapper, "run_v12_dry_run", lambda **_k: {"report": v12_report, "results": {}})

    code, report = wrapper.run(commit=False, client=object())

    assert code == 0
    assert report["status"] == "PUBLISHED"
    assert report["default_sort_authority"] == EXPECTED_OVERALL_RIP_V12_VERSION
    assert report["v12_canonical_validation"] == v12_report
    # never mutates the V10-shaped commit payload
    assert report.get("row_count") == 0
