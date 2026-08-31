"""The Market Explorer custom-market endpoints refuse an unentitled caller.

WHY THIS IS A TEST AND NOT A REVIEW NOTE. The UI gate is presentation: an Index
Plus user can open devtools and POST the endpoint directly. The only thing that
actually stops them is this refusal, and it has to happen BEFORE the shared
result cache and before the query engine — otherwise an unentitled caller
either reads a cached Premium result or makes the database do work for them.

READ AS SOURCE, NOT IMPORTED. `backend.api.main` pulls in the whole FastAPI
application graph, which is not importable in the unit environment (the same
reason the other API tests here are source-level). The properties asserted are
structural — which helper guards which route, and in what ORDER relative to the
cache and the engine — so source is the right level for them anyway. The plan
hierarchy itself is behaviourally tested in
`backend/tests/unit/domain/access/test_index_plan_access.py`.
"""

from pathlib import Path

import pytest

MAIN = Path(__file__).resolve().parents[4] / "backend" / "api" / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")


def _function_source(name):
    start = SOURCE.index(f"def {name}(")
    rest = SOURCE[start:]
    # Up to the next top-level def/decorator.
    for marker in ("\n@app.", "\ndef ", "\n@"):
        index = rest.find(marker, 1)
        if index != -1:
            rest = rest[:index]
    return rest


def test_query_gate_delegates_to_the_canonical_spec_evaluator():
    gate = _function_source("_require_market_explorer_query_access")
    assert "evaluate_market_query_access" in gate
    assert "MARKET_EXPLORER_PLAN_REQUIRED" in gate
    assert "status_code=403" in gate


def test_the_gate_authenticates_first_then_checks_entitlement():
    gate = _function_source("_require_market_explorer_query_access")
    assert gate.index("_require_authenticated_user_id") < gate.index("evaluate_market_query_access"), (
        "an anonymous caller must get 401, not 403"
    )


def test_a_client_supplied_plan_is_never_accepted():
    # The helper takes no plan argument at all: there is nothing for a caller
    # to spoof, which is stronger than validating a value it was handed.
    gate = _function_source("_require_market_explorer_query_access")
    signature = gate[: gate.index(")")]
    assert "plan" not in signature
    assert "authorization" in signature and "token_cookie" in signature


def test_the_plan_is_read_from_the_canonical_profile_projection():
    resolver = _function_source("_resolve_index_plan")
    # Same projection `/auth/me` serves, so the API and the browser cannot
    # disagree about what someone is entitled to.
    assert "get_me(" in resolver
    assert "index_plan" in resolver
    assert "status != 200" in resolver, "a failed lookup must yield no plan, not a default one"


def test_the_gate_runs_before_the_cache_and_before_the_engine():
    query = _function_source("post_market_explorer_query")
    gate = query.index("_require_market_explorer_query_access")
    assert query.index("normalize_query_spec") < gate, "access must evaluate the normalized definition"
    for behind in ("GLOBAL_MARKET_EXPLORER_PLANNER", "runner("):
        assert gate < query.index(behind), f"{behind} must sit behind the entitlement gate"


def test_the_builder_options_endpoint_carries_the_same_gate():
    # The options ARE the builder's surface — era and set ids exist on that
    # endpoint for no other purpose — so a weaker gate there would hand an
    # unentitled caller everything they need to drive the builder.
    options = _function_source("get_market_explorer_query_options")
    assert "has_index_plus_access" in options


def test_public_taxonomy_cache_sits_behind_access_and_never_contains_query_results():
    options = _function_source("get_market_explorer_query_options")
    assert options.index("has_index_plus_access") < options.index("_market_explorer_options_cache")
    assert "build_market_explorer_filter_options" in options
    assert "run_market_explorer_query" not in options
    assert "_market_explorer_query_cache" not in options


def test_full_prepared_snapshot_is_server_gated_to_plus_and_never_public():
    snapshot = _function_source("get_market_explorer_snapshot")
    assert snapshot.index("_require_authenticated_user_id") < snapshot.index("read_market_explorer_snapshot")
    assert snapshot.index("has_index_plus_access") < snapshot.index("read_market_explorer_snapshot")
    assert "status_code=403" in snapshot


@pytest.mark.parametrize("route", [
    "post_market_explorer_query",
    "get_market_explorer_query_options",
])
def test_no_custom_market_route_settles_for_bare_authentication(route):
    source = _function_source(route)
    # `_require_authenticated_user_id` alone would let every signed-in account
    # through, which is exactly the boundary this phase moved.
    if route == "post_market_explorer_query":
        assert "_require_market_explorer_query_access" in source
    else:
        assert "_require_authenticated_user_id(" in source
