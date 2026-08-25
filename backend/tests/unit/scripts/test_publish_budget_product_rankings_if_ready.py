import copy
from types import SimpleNamespace

import pytest

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_TYPE_FULL_MARKET, BUDGET_TYPE_STANDARD, CANONICAL_BUDGET_BANDS,
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


def test_default_client_factory_is_explicit_service_role(monkeypatch):
    sentinel = object(); calls=[]
    monkeypatch.setattr(wrapper, "create_service_role_client", lambda: calls.append(True) or sentinel)
    monkeypatch.setattr(wrapper, "_load_latest_snapshot", lambda _c: None)
    monkeypatch.setattr(wrapper, "resolve_budget_ranking_readiness", lambda client, **_k: SimpleNamespace(
        status=BudgetRankingStatus.UPSTREAM_NOT_READY, selected_price_as_of=None,
        promoted_market_date=None, candidate_authorities=[], gate_results=[], failure_reason="wait", failed_gate="authority"))
    wrapper.run(commit=False)
    assert calls == [True]
