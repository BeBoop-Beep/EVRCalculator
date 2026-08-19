"""Prove that production Financial RIP V4 reproduces the frozen research candidate.

READ-ONLY. This script never writes to the database, never publishes, never
rebuilds a snapshot and never runs a simulation. It computes and compares.

WHAT "PARITY" MEANS HERE
------------------------
The frozen research candidate ``P95_ONLY_25`` was not a separate scoring engine.
``research_realistic_upside_candidate_matrix.score_candidate`` scored a product
as::

    sum over components of  weight[k] * component_score[k]

over the SAME Financial RIP V3 component scores, with the Realistic Upside term
replaced by ``normalize_metric("p95_threshold_ratio", p95Ratio)`` and the V3
weight vector left in place. That is exactly what production V4 computes, so
parity is an identity to prove, not a tolerance to hope for.

Proving it directly on the engine is STRONGER than replaying the August 17
cohort, because the identity holds for every outcome vector rather than for the
137 SKUs that happened to be in that cohort. The cohort diagnostics recorded in
the frozen artifact - 8 Layer-1 inversions at the 5% tolerance, 3 at 2%, zero
Layer-2/3/4 defects, zero top-strategy changes - are pure functions of those
candidate scores, so an exact score identity carries them over unchanged.

The frozen artifact is nonetheless read and reported, so the numbers this
promotion rests on are restated from the artifact rather than from memory.

Usage::

    python -m backend.scripts.research_financial_rip_v4_parity
    python -m backend.scripts.research_financial_rip_v4_parity --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import normalize_metric
from backend.calculations.evr.financial_rip_v4 import (
    build_financial_rip_v4,
    project_financial_rip_v4_from_v3_payload,
)
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE,
    FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID,
    FINANCIAL_RIP_V4_VERSION,
    FINANCIAL_RIP_V4_WEIGHTS,
)
from backend.scripts.research_financial_rip_final_validation import CANDIDATES
from backend.scripts.research_realistic_upside_candidate_matrix import score_candidate

ARTIFACT_PATH = ROOT / "research_financial_rip_final_validation_20260818.json"

#: The diagnostics the V4 decision record expects the frozen candidate to carry.
#: Restated here so a drifted artifact fails loudly rather than being narrated.
EXPECTED_DIAGNOSTICS: Dict[str, Any] = {
    "layer1InversionsAt5Pct": 8,
    "layer1InversionsAt2Pct": 3,
    "layer2Inversions": 0,
    "layer3Inversions": 0,
    "layer4Inversions": 0,
    "topStrategyChanges": 0,
    "comparisonsAt5Pct": 5796,
}

#: Deterministic scoring vectors spanning the shapes the model has to survive:
#: an ordinary lognormal booster, a chase-concentrated product, a flat
#: distribution, and a cheap high-variance one.
_VECTOR_SPECS: Sequence[Dict[str, Any]] = (
    {"name": "lognormal_booster", "kind": "lognormal", "seed": 20260818, "n": 60000,
     "params": (0.5, 1.2), "costs": (4.0, 12.5)},
    {"name": "chase_concentrated", "kind": "chase", "seed": 20260819, "n": 60000,
     "params": (1.5, 1.0, 2.0, 60.0), "costs": (4.5, 150.0)},
    {"name": "flat", "kind": "uniform", "seed": 20260820, "n": 40000,
     "params": (0.0, 8.0), "costs": (3.0, 40.0)},
    {"name": "cheap_high_variance", "kind": "lognormal", "seed": 20260821, "n": 25000,
     "params": (-0.2, 0.9), "costs": (1.5, 6.0)},
)


def _vector(spec: Dict[str, Any]) -> np.ndarray:
    rng = np.random.default_rng(spec["seed"])
    n = spec["n"]
    if spec["kind"] == "lognormal":
        mu, sigma = spec["params"]
        return np.round(np.exp(rng.normal(mu, sigma, n)), 4)
    if spec["kind"] == "uniform":
        low, high = spec["params"]
        return np.round(rng.uniform(low, high, n), 4)
    body_k, body_theta, tail_k, tail_theta = spec["params"]
    tail_n = max(1, n // 100)
    return np.round(
        np.concatenate(
            [rng.gamma(body_k, body_theta, n - tail_n), rng.gamma(tail_k, tail_theta, tail_n)]
        ),
        4,
    )


def check_engine_parity() -> Dict[str, Any]:
    """Score every vector under production V4 and under the research formula."""
    candidate = CANDIDATES[FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID]
    cases: List[Dict[str, Any]] = []
    worst = 0.0

    for spec in _VECTOR_SPECS:
        values = [float(value) for value in _vector(spec)]
        for cost in spec["costs"]:
            v3 = build_financial_rip_v3(values, cost)
            v4 = build_financial_rip_v4(values, cost)
            projected = project_financial_rip_v4_from_v3_payload(v3)

            component_scores = {
                key: block["score"] for key, block in v3["components"].items()
            }
            p95_ratio = v3["components"]["realistic_upside"]["raw"]["p95ThresholdRatio"]
            research = score_candidate(component_scores, p95_ratio, candidate)

            # THE EXACT IDENTITIES.
            #
            # A numeric comparison of the two headline scores can only ever be
            # approximate, because the two sides round at different stages: the
            # research formula consumes the 4dp-ROUNDED published component
            # scores, while production sums at full precision and rounds once at
            # the end. Chasing that with a tolerance would leave the parity claim
            # resting on a threshold.
            #
            # These three identities are exact, and together they ARE the
            # candidate definition:
            #   1. the V4 Realistic Upside score is the normalized P95 threshold
            #      ratio, at the same published precision the research formula
            #      used for it,
            #   2. the other five component scores are unchanged from V3,
            #   3. the weight vectors are identical.
            # Given those, the two scores are the same weighted sum of the same
            # numbers, and the residual is rounding by construction.
            research_realistic = round(
                float(normalize_metric("p95_threshold_ratio", p95_ratio)["score"]), 4
            )
            realistic_identical = (
                v4["components"]["realistic_upside"]["score"] == research_realistic
            )
            others_identical = all(
                v4["components"][key]["score"] == v3["components"][key]["score"]
                for key in v4["components"]
                if key != "realistic_upside"
            )

            # Residual budget, DERIVED rather than chosen: the weighted 4dp
            # rounding of the component scores the research side consumed
            # (bounded by 5e-5, since the weights sum to 1) plus the single 4dp
            # rounding of the production headline (5e-5).
            delta = abs(research - v4["score"])
            worst = max(worst, delta)
            cases.append(
                {
                    "vector": spec["name"],
                    "packCost": cost,
                    "financialRipV3Score": v3["score"],
                    "financialRipV4Score": v4["score"],
                    "researchCandidateScore": round(research, 10),
                    "absoluteDifference": round(delta, 12),
                    "realisticUpsideIsP95Only": realistic_identical,
                    "otherComponentsUnchangedFromV3": others_identical,
                    "engineMatchesProjection": v4["score"] == projected["score"],
                    "v3ScoreVersionDistinct": v3["scoreVersion"] != v4["scoreVersion"],
                }
            )

    rounding_budget = 1e-4
    return {
        "candidateId": FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID,
        "productionVersion": FINANCIAL_RIP_V4_VERSION,
        "weights": dict(FINANCIAL_RIP_V4_WEIGHTS),
        "weightsMatchCandidate": dict(FINANCIAL_RIP_V4_WEIGHTS) == dict(candidate["weights"]),
        "realisticUpsideDefinition": candidate["definition"],
        "caseCount": len(cases),
        "worstAbsoluteDifference": round(worst, 12),
        "roundingBudget": rounding_budget,
        "exactIdentitiesHold": all(
            case["realisticUpsideIsP95Only"]
            and case["otherComponentsUnchangedFromV3"]
            and case["engineMatchesProjection"]
            and case["v3ScoreVersionDistinct"]
            for case in cases
        ),
        "reproduced": (
            all(
                case["realisticUpsideIsP95Only"]
                and case["otherComponentsUnchangedFromV3"]
                and case["engineMatchesProjection"]
                and case["v3ScoreVersionDistinct"]
                for case in cases
            )
            and worst <= rounding_budget
            and dict(FINANCIAL_RIP_V4_WEIGHTS) == dict(candidate["weights"])
        ),
        "cases": cases,
    }


def read_frozen_diagnostics() -> Dict[str, Any]:
    """Restate the frozen artifact diagnostics and check them against expectations."""
    if not ARTIFACT_PATH.exists():
        return {"artifactPresent": False, "path": str(ARTIFACT_PATH)}

    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    states = artifact.get("states") or []
    authority = artifact.get("authority") or {}

    observed: Dict[str, Any] = {}
    per_state: List[Dict[str, Any]] = []
    for state in states:
        five = (state.get("cohort5") or {}).get("candidates", {}).get(
            FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID
        ) or {}
        two = (state.get("cohort2") or {}).get("candidates", {}).get(
            FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID
        ) or {}
        pack = (state.get("packAudit") or {}).get("summary", {}).get(
            FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID
        ) or {}
        observed = {
            "layer1InversionsAt5Pct": five.get("layer1Inversions"),
            "layer1InversionsAt2Pct": two.get("layer1Inversions"),
            "layer2Inversions": five.get("layer2Inversions"),
            "layer3Inversions": five.get("layer3Inversions"),
            "layer4Inversions": five.get("layer4Inversions"),
            "topStrategyChanges": five.get("topStrategyChanges"),
            "comparisonsAt5Pct": five.get("comparisons"),
        }
        per_state.append(
            {
                "marketDate": state.get("marketDate"),
                "skuCount": state.get("skuCount"),
                **observed,
                "packSpearman": pack.get("spearman"),
                "packMaxRankMovement": pack.get("maxRankMovement"),
                "packSetsMovingAtLeast3": pack.get("setsMovingAtLeast3"),
            }
        )

    mismatches = {
        key: {"expected": value, "observed": observed.get(key)}
        for key, value in EXPECTED_DIAGNOSTICS.items()
        if observed.get(key) != value
    }
    return {
        "artifactPresent": True,
        "path": str(ARTIFACT_PATH),
        "authorityDate": FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE,
        "stateDates": authority.get("stateDates"),
        "reconstructableDistinctStates": authority.get("reconstructableDistinctStates"),
        "expected": dict(EXPECTED_DIAGNOSTICS),
        "observed": observed,
        "states": per_state,
        "matchesExpected": not mismatches,
        "mismatches": mismatches,
        # Recorded honestly: the V4 decision has no independent temporal
        # validation, and this script must not imply otherwise.
        "temporalValidation": "none_independent_temporal_validation_at_promotion",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv)

    engine = check_engine_parity()
    frozen = read_frozen_diagnostics()
    report = {
        "reproduced": engine["reproduced"],
        "engineParity": engine,
        "frozenResearchDiagnostics": frozen,
        "databaseMutations": "NONE",
        "publicationMutations": "NONE",
        "simulationRuns": "NONE",
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"candidate                : {engine['candidateId']}")
        print(f"production version       : {engine['productionVersion']}")
        print(f"weights match candidate  : {engine['weightsMatchCandidate']}")
        print(f"cases compared           : {engine['caseCount']}")
        print(f"worst absolute difference: {engine['worstAbsoluteDifference']}"
              f" (rounding budget {engine['roundingBudget']})")
        print(f"exact identities hold    : {engine['exactIdentitiesHold']}")
        print(f"reproduced               : {engine['reproduced']}")
        if frozen.get("artifactPresent"):
            print(f"frozen diagnostics match : {frozen['matchesExpected']}")
            print(f"  observed               : {frozen['observed']}")
        else:
            print("frozen artifact          : NOT PRESENT")

    if not engine["reproduced"]:
        print("STOP: production V4 does not reproduce the frozen research candidate.", file=sys.stderr)
        return 1
    if frozen.get("artifactPresent") and not frozen["matchesExpected"]:
        print(f"STOP: frozen artifact diagnostics drifted: {frozen['mismatches']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
