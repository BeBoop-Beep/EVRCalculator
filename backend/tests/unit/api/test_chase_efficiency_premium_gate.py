from pathlib import Path

MAIN = Path(__file__).resolve().parents[4] / "backend" / "api" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")


def function_source(name):
    start = SOURCE.index(f"def {name}("); rest = SOURCE[start:]
    markers = [index for marker in ("\n@app.", "\ndef ", "\n@") if (index := rest.find(marker, 1)) != -1]
    return rest[:min(markers)] if markers else rest


def test_gate_uses_server_profile_capability_and_structured_403():
    gate = function_source("_require_card_chase_efficiency")
    assert "_require_authenticated_user_id" in gate
    assert "_resolve_index_plan" in gate
    assert "has_index_feature_access" in gate
    assert "FEATURE_CARD_CHASE_EFFICIENCY" in gate
    assert "status_code=403" in gate
    assert "CARD_CHASE_EFFICIENCY_PREMIUM_REQUIRED" in gate
    signature = gate[:gate.index(")")]
    assert "plan" not in signature


def test_both_endpoints_gate_before_any_premium_read():
    ranking = function_source("get_card_chase_efficiency_rankings")
    exact = function_source("get_pokemon_card_chase_efficiency")
    assert ranking.index("_require_card_chase_efficiency") < ranking.index("query_chase_efficiency")
    assert exact.index("_require_card_chase_efficiency") < exact.index("read_card_chase_efficiency")


def test_existing_card_detail_remains_separate_and_plus_payload_is_not_changed():
    detail = function_source("get_pokemon_card_detail")
    assert "get_pokemon_card_detail_payload" in detail
    assert "chase_efficiency" not in detail.lower()


def test_entitlement_matrix_behavior(monkeypatch):
    from backend.api import main
    from fastapi import HTTPException

    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_: "u1")
    for plan, allowed in ((None, False), ("plus", False), ("premium", True)):
        monkeypatch.setattr(main, "_resolve_index_plan", lambda *_args, value=plan: value)
        if allowed:
            assert main._require_card_chase_efficiency(authorization="Bearer x", token_cookie=None) == "u1"
        else:
            try: main._require_card_chase_efficiency(authorization="Bearer x", token_cookie=None)
            except HTTPException as exc:
                assert exc.status_code == 403
                assert exc.detail["requiredFeature"] == "card_chase_efficiency"
            else: raise AssertionError("Basic/Plus bypassed Premium gate")


def test_anonymous_is_denied_before_plan_resolution(monkeypatch):
    from backend.api import main
    from fastapi import HTTPException
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_: (_ for _ in ()).throw(HTTPException(status_code=401, detail="Not authenticated")))
    monkeypatch.setattr(main, "_resolve_index_plan", lambda *_: (_ for _ in ()).throw(AssertionError("plan lookup must not run")))
    try: main._require_card_chase_efficiency(authorization=None, token_cookie=None)
    except HTTPException as exc: assert exc.status_code == 401
    else: raise AssertionError("anonymous caller bypassed authentication")
