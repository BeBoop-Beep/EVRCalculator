"""PRE-CUTOVER readiness of the Financial V5 / Overall V14 / public-contract-V12 candidate.

Two different questions that must never be conflated:

  * "Is current production canonical publication healthy?"  ->  V4 / V12 / contract V11. Answered
    by the existing canonical readiness/lifecycle code, which this module does not touch.
  * "Is the V5/V14/V12-contract candidate complete and internally coherent?"  ->  THIS module.

An absent or not-ready candidate therefore has NO effect on canonical health (``canonicalImpact`` is
always "none"), and a healthy canonical publication says nothing about candidate readiness. Passing
this gate does not make V14 canonical, does not move any pointer and does not select anything; it is
the gate the activation step must consult before it is even allowed to be requested.

Pure: every input is passed in (no DB access), so it is testable and cannot mutate state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
)
from backend.db.services.public_rip_publication_contract import (
    candidate_publication_identity,
    canonical_publication_identity,
)
from backend.desirability.public_rip_contract_v12 import PUBLIC_RIP_CONTRACT_V12_VERSION
from backend.desirability.scoring_config import OVERALL_RIP_V14_VERSION

READINESS_VERSION = "financial-v5-v14-candidate-readiness-v1"


def _check(ok: bool, detail: str = "", **extra: Any) -> Dict[str, Any]:
    return {"ok": bool(ok), "detail": detail, **extra}


def evaluate_v5_v14_candidate_readiness(
    *,
    expected_row_count: int,
    v5_finalization_report: Optional[Mapping[str, Any]] = None,
    v14_candidate: Optional[Mapping[str, Any]] = None,
    v14_validation: Optional[Mapping[str, Any]] = None,
    ranking_v2: Optional[Mapping[str, Any]] = None,
    best_open_v3: Optional[Mapping[str, Any]] = None,
    contract_v12_samples: Optional[Sequence[Mapping[str, Any]]] = None,
    require_best_open_v3: bool = True,
) -> Dict[str, Any]:
    """Every check, every reason. ``candidateReady`` is true only if every applicable check passes.

    ``ranking_v2`` / ``best_open_v3`` are summary mappings of the persisted snapshot rows
    (``ranking_method_version``, ``eligible_cohort_count`` / ``resolved_count``, ids, timestamps,
    fingerprints, model versions).
    """
    identity = candidate_publication_identity()
    checks: Dict[str, Dict[str, Any]] = {}

    # -- Financial V5: every supported current run has exact V5 on every row ------------------
    if v5_finalization_report is None:
        checks["financialV5Complete"] = _check(False, "financial_v5_not_finalized")
    else:
        rep = v5_finalization_report
        checks["financialV5Complete"] = _check(
            bool(rep.get("cohortComplete")) and rep.get("financialVersion") == identity["financialRipVersion"]
            and rep.get("rowsReady") == expected_row_count,
            "rowsReady=%s expected=%s unavailable=%s skipped=%s" % (
                rep.get("rowsReady"), expected_row_count, rep.get("rowsUnavailable"), rep.get("rowsSkipped")))

    # -- Overall V14: complete, rankable, coherent identities -----------------------------------
    if v14_candidate is None:
        checks["overallV14Complete"] = _check(False, "v14_candidate_not_built")
    else:
        run = v14_candidate.get("run") or {}
        problems: List[str] = list(v14_candidate.get("problems") or [])
        for key, want in (("model_version", OVERALL_RIP_V14_VERSION),
                          ("financial_version", identity["financialRipVersion"]),
                          ("collector_version", identity["collectorAppealVersion"])):
            if run.get(key) != want:
                problems.append(f"{key}={run.get(key)!r} != {want!r}")
        if run.get("expected_row_count") != expected_row_count:
            problems.append("expected_row_count=%s != %s" % (run.get("expected_row_count"), expected_row_count))
        if v14_candidate.get("readyCount") != expected_row_count:
            problems.append("ready=%s of %s" % (v14_candidate.get("readyCount"), expected_row_count))
        if v14_validation is not None and not v14_validation.get("passed"):
            problems.append("v14 validation did not pass: %s" % (v14_validation.get("problems"),))
        checks["overallV14Complete"] = _check(not problems, "; ".join(problems))

    # -- Ranking V2 ------------------------------------------------------------------------------
    if ranking_v2 is None:
        checks["rankingV2Complete"] = _check(False, "ranking_v2_not_published")
    else:
        bad = []
        if ranking_v2.get("ranking_method_version") != BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2:
            bad.append("method=%r" % (ranking_v2.get("ranking_method_version"),))
        if ranking_v2.get("overall_rip_v14_version") != OVERALL_RIP_V14_VERSION:
            bad.append("overall=%r" % (ranking_v2.get("overall_rip_v14_version"),))
        if ranking_v2.get("financial_rip_v5_version") != identity["financialRipVersion"]:
            bad.append("financial=%r" % (ranking_v2.get("financial_rip_v5_version"),))
        if ranking_v2.get("ranked_under_v14_authority") is not True:
            bad.append("not ranked under V14 authority")
        if ranking_v2.get("eligible_cohort_count") != expected_row_count:
            bad.append("cohort=%s expected=%s" % (ranking_v2.get("eligible_cohort_count"), expected_row_count))
        checks["rankingV2Complete"] = _check(not bad, "; ".join(bad))

    # -- Best-Open V3 (required by the release gate unless explicitly waived) --------------------
    if best_open_v3 is None:
        checks["bestOpenV3Complete"] = _check(not require_best_open_v3,
                                              "best_open_v3_not_published" if require_best_open_v3 else "waived",
                                              required=require_best_open_v3)
    else:
        bad = []
        if best_open_v3.get("best_open_price_method_version") != BEST_OPEN_PRICE_V3_METHOD_VERSION:
            bad.append("method=%r" % (best_open_v3.get("best_open_price_method_version"),))
        if best_open_v3.get("overall_rip_v14_version") != OVERALL_RIP_V14_VERSION:
            bad.append("overall=%r" % (best_open_v3.get("overall_rip_v14_version"),))
        if ranking_v2 is None or str(best_open_v3.get("source_budget_snapshot_id")) != str(ranking_v2.get("id")):
            bad.append("not bound to the Ranking V2 snapshot")
        elif (best_open_v3.get("source_budget_published_at") != ranking_v2.get("published_at")
              or best_open_v3.get("source_cohort_fingerprint") != ranking_v2.get("cohort_fingerprint")):
            bad.append("source timestamp/fingerprint differs from the Ranking V2 snapshot")
        if best_open_v3.get("resolved_count") != expected_row_count or best_open_v3.get("unresolved_count") != 0:
            bad.append("resolved=%s unresolved=%s" % (best_open_v3.get("resolved_count"), best_open_v3.get("unresolved_count")))
        checks["bestOpenV3Complete"] = _check(not bad, "; ".join(bad), required=require_best_open_v3)

    # -- Public contract V12 shape ---------------------------------------------------------------
    if not contract_v12_samples:
        checks["publicContractV12Valid"] = _check(False, "no_contract_v12_samples")
    else:
        bad = []
        for i, c in enumerate(contract_v12_samples):
            if c.get("contractVersion") != PUBLIC_RIP_CONTRACT_V12_VERSION:
                bad.append(f"[{i}] contractVersion={c.get('contractVersion')!r}")
            for block in ("overallRipV14", "financialRipV5"):
                b = c.get(block) or {}
                if b.get("status") != "ready" or b.get("score") is None or b.get("rank") is None:
                    bad.append(f"[{i}] {block} not ready: {b.get('status')!r}")
        checks["publicContractV12Valid"] = _check(not bad, "; ".join(bad[:5]), samples=len(contract_v12_samples))

    # -- Identity coherence between the pieces that exist ----------------------------------------
    identity_bad = []
    if v14_candidate and ranking_v2 and (v14_candidate.get("run") or {}).get("financial_version") != ranking_v2.get("financial_rip_v5_version"):
        identity_bad.append("V14 candidate and Ranking V2 disagree on the Financial version")
    checks["identityCoherent"] = _check(not identity_bad, "; ".join(identity_bad))

    reasons = [f"{name}: {c['detail'] or 'failed'}" for name, c in checks.items() if not c["ok"]]
    return {
        "readinessVersion": READINESS_VERSION, "candidateReady": not reasons, "reasons": reasons,
        "checks": checks, "candidateIdentity": identity,
        # The canonical identity is reported ONLY to make the separation visible; nothing here is derived
        # from it, and candidate state never changes canonical health.
        "canonicalIdentity": canonical_publication_identity(), "canonicalImpact": "none",
        "activated": False, "expectedRowCount": expected_row_count,
    }
