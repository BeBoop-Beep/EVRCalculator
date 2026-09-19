import pytest

from backend.desirability import scoring_config as sc
from backend.desirability.overall_rip_v14 import compute_overall_rip_v14
from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score

V = dict(
    financial_version=sc.OVERALL_RIP_V14_REQUIRED_FINANCIAL_VERSION,
    chase_accessibility_version=sc.overall_rip_v14_required_chase_accessibility_version(),
    collector_appeal_version=sc.overall_rip_v14_required_collector_appeal_version(),
)


def test_formula_weights_and_rounding():
    r = compute_overall_rip_v14(40.1234, 0.01, 55.5, **V)
    a = chase_accessibility_overall_score(0.01)
    assert r["status"] == "ready" and r["version"] == sc.OVERALL_RIP_V14_VERSION
    assert r["score"] == round(.86 * 40.1234 + .04 * a + .10 * 55.5, 4)
    assert r["weights"] == {"financial_rip": .86, "chase_accessibility": .04, "collector_appeal": .10}
    assert "financialRipV5" in r["components"]


@pytest.mark.parametrize("field,bad", [("financial_version", sc.FINANCIAL_RIP_V4_VERSION),
                                       ("chase_accessibility_version", "x"),
                                       ("collector_appeal_version", "collector_appeal_v7")])
def test_wrong_input_version_fails_closed(field, bad):
    r = compute_overall_rip_v14(40, 0.01, 55, **{**V, field: bad})
    assert r["score"] is None and r["rankable"] is False and r["mismatchedInputVersions"]


@pytest.mark.parametrize("args", [(None, 0.01, 55), (40, None, 55), (40, 0.01, None)])
def test_missing_pillar_no_renormalize_no_v4_fallback(args):
    r = compute_overall_rip_v14(*args, **V)
    assert r["score"] is None and r["missingInputs"]


def test_v12_v13_and_canonical_unchanged():
    assert sc.OVERALL_RIP_V14_VERSION not in (sc.OVERALL_RIP_V12_VERSION,)
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION
    assert sc.CANONICAL_FINANCIAL_RIP_VERSION == sc.FINANCIAL_RIP_V4_VERSION
    v12 = compute_overall_rip_v12(40.1234, 0.01, 55.5)
    assert v12["version"].startswith("overall_rip_v12_86_financial_v4")
    assert v12["score"] == compute_overall_rip_v14(40.1234, 0.01, 55.5, **V)["score"]  # same arithmetic, different identity
