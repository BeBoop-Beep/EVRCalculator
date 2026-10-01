from __future__ import annotations

import numpy as np

from backend.scripts.research_treatment_hierarchy_v3 import (
    _fit,
    reference_treatment,
    spearman,
)


def test_reference_treatment_is_semantic_not_lexical():
    assert reference_treatment("common <> illustration_rare") == "common"
    assert reference_treatment("illustration_rare <> uncommon") == "uncommon"
    assert reference_treatment("double_rare <> ultra_rare") == "double_rare"
    assert (
        reference_treatment(
            "double_rare <> special_illustration_rare <> ultra_rare"
        )
        == "double_rare"
    )


def test_fit_fails_closed_on_rank_deficiency():
    x = np.asarray([[1.0, 1.0], [-1.0, -1.0]])
    y = np.asarray([1.0, -1.0])
    fit = _fit(x, y, ["a", "b"])
    assert fit["estimable"] is False
    assert fit["rank"] == 1


def test_fit_recovers_full_rank_coefficients():
    x = np.asarray([[1.0, 0.0], [0.0, 1.0], [-1.0, -1.0]])
    beta = np.asarray([0.4, -0.2])
    y = x @ beta
    fit = _fit(x, y, ["a", "b"])
    assert fit["estimable"] is True
    assert abs(fit["coefficients"]["a"] - 0.4) < 1e-12
    assert abs(fit["coefficients"]["b"] + 0.2) < 1e-12


def test_spearman_uses_rank_order_not_magnitude():
    assert abs(spearman([1, 2, 3], [10, 20, 30]) - 1.0) < 1e-12
    assert abs(spearman([1, 2, 3], [30, 20, 10]) + 1.0) < 1e-12
