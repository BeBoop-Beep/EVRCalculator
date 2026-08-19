"""Financial RIP V3 behavioural freeze.

WHY THIS EXISTS
---------------
Financial RIP V4 is built on the SAME outcome-profile engine as V3. Rather than
fork the engine - two implementations of one set of percentile mechanics, free to
drift apart silently - the version-specific data (identifiers, component-input
table, weights) was extracted into a ``FinancialRipModelSpec``, and V3 became one
binding of that engine.

That refactor touches ``financial_rip_v3.py``, so the branch-scoped file-diff
guard in ``test_stage1_sealed_product_finalization`` no longer covers V3. A
file-diff guard was always a proxy for the thing that actually matters, which is
that V3 SCORES DO NOT MOVE. This test asserts that directly, and is strictly
stronger: it would catch a behavioural change made anywhere in the engine, its
config, or its transforms - including one made in a file the diff guard never
listed.

THE HASH
--------
``V3_PAYLOAD_DIGEST`` is the SHA-256 of the canonicalized JSON of eight complete
V3 payloads - four distribution shapes at two pack costs each - captured from the
pre-refactor engine. It covers every published leaf: the score, all six component
scores, contributions, sub-scores, raw metrics, tail selection, disclosures and
the audit block. Any change to any of them moves the digest.

If this test fails, V3 changed. That is a promotion/versioning decision (V3 rows
are published and must stay reproducible), never a hash to update casually.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import (
    FINANCIAL_RIP_V3_SPEC,
    build_financial_rip_v3,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
    financial_rip_v3_weights_payload,
)

#: Captured from the engine as it stood before the V4 spec extraction.
V3_PAYLOAD_DIGEST = "ffac9610a57ed5a05e2fdf75742c318d5cbba9c94b11fdd6cc1285e95652312d"

COSTS = (4.0, 12.5)


def _vectors():
    """The exact vectors the digest was captured over. Do not re-tune."""
    rng = np.random.default_rng(20260818)
    return {
        "lognormal": np.round(np.exp(rng.normal(0.5, 1.2, 60000)), 4),
        "heavy_chase": np.round(
            np.concatenate([rng.gamma(1.5, 1.0, 59400), rng.gamma(2.0, 60.0, 600)]), 4
        ),
        "flat": np.round(rng.uniform(0.0, 8.0, 40000), 4),
        "cheap": np.round(np.exp(rng.normal(-0.2, 0.9, 25000)), 4),
    }


@pytest.fixture(scope="module")
def payloads():
    built = {}
    for name, vector in _vectors().items():
        values = [float(value) for value in vector]
        for cost in COSTS:
            built[f"{name}@{cost}"] = build_financial_rip_v3(values, cost)
    return built


def test_v3_payloads_are_byte_identical_to_the_frozen_capture(payloads):
    digest = hashlib.sha256(
        json.dumps(payloads, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert digest == V3_PAYLOAD_DIGEST, (
        "Financial RIP V3 behaviour changed. V3 rows are published and must stay "
        "reproducible; this is a versioning decision, not a hash to update."
    )


def test_the_freeze_actually_covers_all_eight_cases(payloads):
    assert len(payloads) == 8
    assert all(payload["status"] == "ready" for payload in payloads.values())


def test_the_freeze_covers_every_published_component(payloads):
    for payload in payloads.values():
        assert list(payload["components"]) == list(FINANCIAL_RIP_V3_COMPONENT_ORDER)
        for component in payload["components"].values():
            assert component["score"] is not None
            assert component["contribution"] is not None
            assert component["raw"]


def test_the_v3_spec_still_describes_v3(payloads):
    """The spec is the seam the V4 work introduced. It must still bind to V3."""
    assert FINANCIAL_RIP_V3_SPEC.score_version == FINANCIAL_RIP_V3_VERSION
    assert FINANCIAL_RIP_V3_SPEC.weights == FINANCIAL_RIP_V3_WEIGHTS
    assert FINANCIAL_RIP_V3_SPEC.component_inputs == FINANCIAL_RIP_V3_COMPONENT_INPUTS
    assert FINANCIAL_RIP_V3_SPEC.component_order == FINANCIAL_RIP_V3_COMPONENT_ORDER
    assert FINANCIAL_RIP_V3_SPEC.weights_payload is financial_rip_v3_weights_payload


def test_v3_realistic_upside_still_weights_both_of_its_inputs(payloads):
    """The specific thing V4 changes. V3 must not have been changed in place."""
    for payload in payloads.values():
        sub_scores = payload["components"]["realistic_upside"]["subScores"]
        assert set(sub_scores) == {"p95_threshold_ratio", "realistic_tail_mean_ratio"}
        assert sub_scores["p95_threshold_ratio"]["subWeight"] == 0.40
        assert sub_scores["realistic_tail_mean_ratio"]["subWeight"] == 0.60


def test_v3_still_stamps_its_own_version(payloads):
    for payload in payloads.values():
        assert payload["scoreVersion"] == FINANCIAL_RIP_V3_VERSION
        assert payload["audit"]["weights"]["scoreVersion"] == FINANCIAL_RIP_V3_VERSION
