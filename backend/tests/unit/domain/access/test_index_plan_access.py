"""The server-side half of the Index plan hierarchy.

These exist because the frontend gate is presentation. If this module and
``frontend/lib/access/indexPlanAccess.mjs`` ever disagree, a feature is either
free on the API or unreachable in the UI, and neither failure announces itself.
"""

import pytest

from backend.domain.access.index_plan_access import (
    FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
    INDEX_PLAN_PLUS,
    INDEX_PLAN_PREMIUM,
    has_index_plus_access,
    has_index_premium_access,
    normalize_index_plan,
    resolve_market_explorer_plan_access,
)


@pytest.mark.parametrize(
    "plan,plus,premium",
    [
        ("premium", True, True),   # Premium inherits Plus.
        ("plus", True, False),
        ("PLUS", True, False),     # normalization is case/space insensitive
        ("  premium  ", True, True),
        (None, False, False),
        ("", False, False),
        ("free", False, False),
        ("pro", False, False),     # an unrecognised tier fails CLOSED
        (7, False, False),
        ({}, False, False),
    ],
)
def test_plan_hierarchy(plan, plus, premium):
    assert has_index_plus_access(plan) is plus
    assert has_index_premium_access(plan) is premium


def test_premium_satisfies_every_plus_check():
    assert has_index_plus_access(INDEX_PLAN_PREMIUM) is True
    assert has_index_premium_access(INDEX_PLAN_PLUS) is False


def test_unrecognised_plans_normalize_to_none_rather_than_to_a_tier():
    assert normalize_index_plan("enterprise") is None
    assert normalize_index_plan(None) is None


def test_market_explorer_ladder_has_three_levels():
    assert resolve_market_explorer_plan_access(None) == {
        "accessMode": "basic",
        "canUsePreparedMarketIntelligence": False,
        "canBuildCustomMarkets": False,
    }
    assert resolve_market_explorer_plan_access({"index_plan": "plus"}) == {
        "accessMode": "plus",
        "canUsePreparedMarketIntelligence": True,
        "canBuildCustomMarkets": False,
    }
    assert resolve_market_explorer_plan_access({"index_plan": "premium"}) == {
        "accessMode": "premium",
        "canUsePreparedMarketIntelligence": True,
        "canBuildCustomMarkets": True,
    }


def test_authentication_alone_grants_nothing():
    # The correction this encodes: PLAN entitlement decides access, not login.
    anonymous = resolve_market_explorer_plan_access(None)
    authenticated_basic = resolve_market_explorer_plan_access(
        {"id": "user-1", "email": "a@b.c", "index_plan": None}
    )
    assert authenticated_basic == anonymous


def test_the_gated_capability_is_named_as_a_feature_not_a_plan():
    # Commercial packaging is not final, so the API refuses by CAPABILITY.
    assert FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS == "market_explorer_custom_markets"


def test_the_two_runtimes_agree_on_the_plan_strings():
    # A drift here is silent and expensive, so it is asserted rather than
    # trusted to review. Read as text: importing the ESM module is not
    # available to pytest.
    from pathlib import Path

    source = Path(__file__).resolve().parents[5] / "frontend" / "lib" / "access" / "indexPlanAccess.mjs"
    text = source.read_text(encoding="utf-8")
    assert f'INDEX_PLAN_PLUS = "{INDEX_PLAN_PLUS}"' in text
    assert f'INDEX_PLAN_PREMIUM = "{INDEX_PLAN_PREMIUM}"' in text
    assert FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS in text
    # And on the rule that Premium satisfies Plus.
    assert "normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM" in text
