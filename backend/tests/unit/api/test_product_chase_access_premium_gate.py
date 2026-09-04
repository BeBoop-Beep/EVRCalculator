"""Server-side entitlement enforcement for Product Chase Intelligence (O_budget).

Mirrors ``test_chase_efficiency_premium_gate.py`` exactly, for the NEW,
DISTINCT ``FEATURE_PRODUCT_CHASE_INTELLIGENCE`` gate. These tests actually
CALL the gate function (and the route source-order check) rather than only
asserting the feature exists - a Plus or Free/anonymous request must be
rejected before any cohort/authority read happens, including via direct API
access, not merely a hidden frontend control.
"""

from pathlib import Path

MAIN = Path(__file__).resolve().parents[4] / "backend" / "api" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")


def function_source(name):
    start = SOURCE.index(f"def {name}("); rest = SOURCE[start:]
    markers = [index for marker in ("\n@app.", "\ndef ", "\n@") if (index := rest.find(marker, 1)) != -1]
    return rest[:min(markers)] if markers else rest


def test_gate_uses_server_profile_capability_and_structured_403():
    gate = function_source("_require_product_chase_intelligence")
    assert "_require_authenticated_user_id" in gate
    assert "_resolve_index_plan" in gate
    assert "has_index_feature_access" in gate
    assert "FEATURE_PRODUCT_CHASE_INTELLIGENCE" in gate
    assert "status_code=403" in gate
    assert "PRODUCT_CHASE_INTELLIGENCE_PREMIUM_REQUIRED" in gate


def test_route_gates_before_any_cohort_or_authority_read():
    route = function_source("get_product_chase_intelligence")
    assert route.index("_require_product_chase_intelligence") < route.index("load_pinned_cohort")
    assert route.index("_require_product_chase_intelligence") < route.index("resolve_product_chase_access")


def test_route_uses_its_own_contract_never_the_card_chase_efficiency_or_normal_rip_contract():
    route = function_source("get_product_chase_intelligence")
    assert "project_product_chase_access_response" in route
    assert "query_chase_efficiency" not in route
    assert "project_product_rankings_response" not in route


def test_entitlement_matrix_a_plus_or_free_request_is_rejected(monkeypatch):
    """THE actual negative test: simulate a Free, Plus, and Premium caller
    hitting the real gate function and confirm only Premium is let through."""
    from backend.api import main
    from fastapi import HTTPException

    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_: "u1")
    for plan, allowed in ((None, False), ("plus", False), ("premium", True)):
        monkeypatch.setattr(main, "_resolve_index_plan", lambda *_args, value=plan: value)
        if allowed:
            assert main._require_product_chase_intelligence(
                authorization="Bearer x", token_cookie=None) == "u1"
        else:
            try:
                main._require_product_chase_intelligence(authorization="Bearer x", token_cookie=None)
            except HTTPException as exc:
                assert exc.status_code == 403
                assert exc.detail["requiredFeature"] == "product_chase_intelligence"
            else:
                raise AssertionError(f"plan={plan!r} bypassed the Premium Chase Access gate")


def test_anonymous_request_is_denied_before_plan_resolution(monkeypatch):
    from backend.api import main
    from fastapi import HTTPException
    monkeypatch.setattr(
        main, "_require_authenticated_user_id",
        lambda **_: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Not authenticated")))
    monkeypatch.setattr(
        main, "_resolve_index_plan",
        lambda *_: (_ for _ in ()).throw(AssertionError("plan lookup must not run for an anonymous caller")))
    try:
        main._require_product_chase_intelligence(authorization=None, token_cookie=None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("anonymous caller bypassed authentication")


def test_response_projector_only_exposes_the_chase_access_allowlist():
    """The Premium payload never leaks fields outside the declared Chase Access
    contract (Phase 2 A/B/C/D sub-blocks) - e.g. no raw DB column names, no
    internal diagnostics beyond what the contract defines."""
    from backend.domain.access.index_plan_access import project_product_chase_access_response

    raw = {
        "budget": 100.0,
        "products": [{
            "sealedProductId": "sp1", "setId": "s1", "productName": "ETB",
            "productFamily": "elite_trainer_box", "productMarketCost": 42.0,
            "randomPackCount": 4, "effectivePackCost": 10.5, "aRaw": 0.07,
            "chaseAccessibilityReady": True, "chaseAccessibilityReasons": [],
            "calculationRunId": "run-1", "ece": 0.0067, "eceVersion": "v1",
            "version": "v1", "quantity": 2, "actualCommittedCapital": 84.0,
            "unusedCapital": 16.0, "capitalUtilization": 0.84, "effectivePacks": 8,
            "oBudget": 0.31, "oBudgetPct": 31.0, "oBudgetStatus": "ready",
            "oBudgetStatusReason": None, "oBudgetRank": 1,
            # A field that must NOT leak: an internal secret/other-authority field.
            "internalServiceRoleDebugPayload": {"secret": "should never appear"},
        }],
        "queryCount": {"accessibilityCohortReads": 1, "variantUniverseReads": 1, "totalDbReads": 2},
        "distinctSetCount": 1, "productCount": 1,
        "chaseAccessibilityVersion": "chase_accessibility_v1_hc_value_squared_modeled_probability",
        "version": "product_chase_access_v1_hc_weighted_budget_reachability_modeled_probability",
    }
    projected = project_product_chase_access_response(raw, "premium")
    assert "internalServiceRoleDebugPayload" not in projected["products"][0]
    assert projected["products"][0]["oBudget"] == 0.31
    assert projected["budget"] == 100.0
