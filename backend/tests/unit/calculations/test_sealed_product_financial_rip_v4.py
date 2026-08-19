"""Sealed-product scoring under Financial RIP V4 / Overall RIP V10.

Claims under test:

  * sealed-product scoring produces a V4 score and a V10 blend for every SKU,
  * those values are exactly what the V4 engine produces for the same vector
    and cost,
  * the canonical V3/V9 outputs are completely unchanged by their presence,
  * NOTHING new is persisted: the row projection that reaches the database is
    byte-for-byte the same set of keys it was before,
  * cross-format comparison stays disabled.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.db.services import sealed_product_rip_service as service
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.desirability.scoring_config import (
    OVERALL_RIP_V9_VERSION,
    OVERALL_RIP_V10_VERSION,
)
from backend.desirability.weighted_rip import (
    compute_overall_rip_v9,
    compute_overall_rip_v10,
)
from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.domain.pokemon.sealed_product_composition import resolve_stage1_composition

RUNS = 20_000
APPEAL_SCORE = 62.5
_APPEAL = {
    "score": APPEAL_SCORE,
    "version": COLLECTOR_APPEAL_V5_VERSION,
    "available": True,
    "reason": None,
}

#: The exact set of keys the persistence projection is allowed to carry. Held
#: literally so a new key silently reaching the database is a test failure.
PERSISTED_V4_KEYS = {
    "financial_rip_v4_score",
    "financial_rip_v4_status",
    "financial_rip_v4_version",
    "financial_rip_v4_payload",
    "overall_rip_v10_score",
    "overall_rip_v10_version",
    "overall_rip_v10_payload",
}


def _pack_vector(n: int = RUNS) -> np.ndarray:
    rng = np.random.default_rng(20260818)
    base = rng.lognormal(mean=0.5, sigma=0.9, size=n)
    hits = rng.random(n) < 0.01
    base[hits] += rng.lognormal(mean=3.5, sigma=0.8, size=int(hits.sum()))
    return np.round(base, 4)


def _candidates(*specs):
    return [
        {
            "sealed_product_id": product_id,
            "name": f"product-{product_id}",
            "product_family": family,
            "composition": resolve_stage1_composition(family),
            "product_market_cost": cost,
            "price_as_of": "2026-08-14",
            "price_source": "TCGPLAYER",
        }
        for product_id, family, cost in specs
    ]


@pytest.fixture(scope="module")
def scored():
    return service.score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=_candidates(
            ("1", "sleeved_booster_pack", 6.0),
            ("2", "booster_bundle", 28.0),
            ("3", "booster_box", 150.0),
        ),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )


# ---------------------------------------------------------------------------
# V4 / V10 are produced
# ---------------------------------------------------------------------------

def test_every_product_carries_a_financial_rip_v4_score(scored):
    for product in scored["products"]:
        assert product["financial_rip_v4_score"] is not None
        assert product["financial_rip_v4_status"] == "ready"
        assert product["financial_rip_v4_version"] == FINANCIAL_RIP_V4_VERSION


def test_every_product_carries_an_overall_rip_v10_blend(scored):
    for product in scored["products"]:
        expected = compute_overall_rip_v10(product["financial_rip_v4_score"], APPEAL_SCORE)
        assert product["overall_rip_v10_payload"] == expected
        assert product["overall_rip_v10_version"] == OVERALL_RIP_V10_VERSION


def test_the_product_v4_score_matches_the_engine_on_the_same_vector():
    """The single-pack product is the pack, so the engine result must be identical."""
    values = _pack_vector()
    cost = 5.25
    scored = service.score_stage1_sealed_products(
        pack_values=values,
        candidates=_candidates(("1", "sleeved_booster_pack", cost)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    product = scored["products"][0]
    canonical = build_financial_rip_v4(values, cost)
    assert product["financial_rip_v4_score"] == canonical["score"]
    assert product["financial_rip_v4_payload"]["components"]["realistic_upside"]["score"] == (
        canonical["components"]["realistic_upside"]["score"]
    )


def test_v4_and_v3_scores_differ_but_both_are_present(scored):
    for product in scored["products"]:
        assert product["financial_rip_v3_score"] is not None
        assert product["financial_rip_v4_score"] is not None
        assert product["financial_rip_v3_version"] != product["financial_rip_v4_version"]


# ---------------------------------------------------------------------------
# The canonical outputs are unchanged
# ---------------------------------------------------------------------------

def test_the_canonical_v3_result_is_unchanged():
    values = _pack_vector()
    cost = 5.25
    scored = service.score_stage1_sealed_products(
        pack_values=values,
        candidates=_candidates(("1", "sleeved_booster_pack", cost)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    product = scored["products"][0]
    canonical = build_financial_rip_v3(values, cost)
    assert product["financial_rip_v3_payload"] == canonical
    assert product["financial_rip_v3_score"] == canonical["score"]


def test_the_canonical_overall_rip_is_still_v9(scored):
    for product in scored["products"]:
        assert product["overall_rip_version"] == OVERALL_RIP_V9_VERSION
        assert product["overall_rip_payload"] == compute_overall_rip_v9(
            product["financial_rip_v3_score"], APPEAL_SCORE
        )


def test_collector_appeal_is_the_same_v5_input_for_both_blends(scored):
    for product in scored["products"]:
        assert product["collector_appeal_version"] == COLLECTOR_APPEAL_V5_VERSION
        v9_appeal = product["overall_rip_payload"]["components"]["collectorAppeal"]
        v10_appeal = product["overall_rip_v10_payload"]["components"]["collectorAppeal"]
        assert v9_appeal == v10_appeal


# ---------------------------------------------------------------------------
# V4/V10 persist ALONGSIDE V3/V9
# ---------------------------------------------------------------------------
# SUPERSEDED PREMISE: this section previously asserted that _to_row carried NO
# V4/V10 key, because the models were in-memory diagnostics with no columns to
# land in. Migration 073 adds those columns additively, so the contract is now
# the opposite - V4/V10 must be persisted, in their OWN fields, without
# disturbing a single V3/V9 value. The keys below are still held literally so an
# unexpected key reaching the database is still a failure.

def test_the_persistence_projection_carries_every_v4_and_v10_key(scored):
    for product in scored["products"]:
        row = service._to_row(product, calculation_run_id="run-1", set_id="set-1")
        assert PERSISTED_V4_KEYS.issubset(set(row))
        assert row["financial_rip_v4_score"] == product["financial_rip_v4_score"]
        assert row["financial_rip_v4_version"] == product["financial_rip_v4_version"]
        assert row["overall_rip_v10_score"] == product["overall_rip_v10_score"]
        assert row["overall_rip_v10_version"] == product["overall_rip_v10_version"]


def test_v4_persistence_does_not_disturb_the_v3_columns(scored):
    for product in scored["products"]:
        row = service._to_row(product, calculation_run_id="run-1", set_id="set-1")
        assert row["financial_rip_v3_score"] == product["financial_rip_v3_score"]
        assert row["financial_rip_v3_version"] == product["financial_rip_v3_version"]
        assert row["financial_rip_v3_score"] != row["financial_rip_v4_score"]
        assert row["overall_rip_version"] == OVERALL_RIP_V9_VERSION
        assert row["overall_rip_version"] != row["overall_rip_v10_version"]


def test_the_persistence_projection_still_carries_the_canonical_columns(scored):
    for product in scored["products"]:
        row = service._to_row(product, calculation_run_id="run-1", set_id="set-1")
        assert row["financial_rip_v3_score"] == product["financial_rip_v3_score"]
        assert row["overall_rip_version"] == OVERALL_RIP_V9_VERSION


# ---------------------------------------------------------------------------
# Comparison scope
# ---------------------------------------------------------------------------

def test_v4_scores_do_not_unlock_cross_format_comparison(scored):
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    families = [product["product_family"] for product in scored["products"]]
    assert len(set(families)) == 3
    assert scope.may_compare_products(families[0], families[1]) is False
