"""READ-ONLY live shadow of the Financial V5 / Overall V14 / Ranking V2 / contract-V12 candidate.

Reads production (sealed-product rows, pack-outcome artifacts, Collector Appeal V5, Chase Accessibility V1,
current V4/V12 columns) and computes everything in memory. There is NO write path in this module: no
client.table(...).insert/update/upsert/delete and no rpc call. Exact V5 evidence comes from the finalizer's
dry-run ``evidence_sink`` (bounded payloads, no outcome arrays), which lets the later stages run without
persisting V5 and without loosening the commit-capable paths' persisted-V5 requirement.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import budget_ranking_v2_orchestration as o2
from backend.db.services.overall_v14_candidate_publication import (
    build_v14_candidate,
    cohort_fingerprint,
    validate_v14_candidate,
)
from backend.db.services.sealed_product_financial_v5_finalization_service import finalize_financial_rip_v5
from backend.db.services.sealed_product_rip_finalization_service import resolve_finalization_cohort
from backend.db.services.sealed_product_rip_service import interpret_collector_appeal_payload
from backend.desirability.public_rip_contract_v12 import build_public_rip_contract_v12
from backend.desirability.scoring_config import OVERALL_RIP_V14_VERSION


def _pearson(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _ranks(scores: Mapping[str, float]) -> Dict[str, int]:
    ordered = sorted(scores, key=lambda k: (-scores[k], k))
    return {k: i for i, k in enumerate(ordered, 1)}


def compare_models(old: Mapping[str, float], new: Mapping[str, float], *, label: str) -> Dict[str, Any]:
    """Old-vs-new distribution comparison keyed by product id (identical key sets required)."""
    keys = sorted(set(old) & set(new))
    o, n = np.array([old[k] for k in keys], float), np.array([new[k] for k in keys], float)
    delta = n - o
    ro, rn = _ranks({k: old[k] for k in keys}), _ranks({k: new[k] for k in keys})
    move = np.array([abs(rn[k] - ro[k]) for k in keys], float)
    top = {}
    for t in (5, 10, 20):
        a = {k for k, r in ro.items() if r <= t}
        b = {k for k, r in rn.items() if r <= t}
        top[str(t)] = len(a & b)
    from scipy.stats import kendalltau, spearmanr

    movers = sorted(keys, key=lambda k: -abs(rn[k] - ro[k]))[:5]
    return {
        "label": label, "n": len(keys), "pearson": _pearson(o, n), "spearman": float(spearmanr(o, n)[0]),
        "kendallTau": float(kendalltau(ro_list := [ro[k] for k in keys], [rn[k] for k in keys])[0]),
        "deltaMean": float(delta.mean()), "deltaMedian": float(np.median(delta)),
        "deltaP10": float(np.percentile(delta, 10)), "deltaP90": float(np.percentile(delta, 90)),
        "deltaMin": float(delta.min()), "deltaMax": float(delta.max()),
        "rankMoveMean": float(move.mean()), "rankMoveMax": float(move.max()),
        "rankMoveCounts": {"unchanged": int((move == 0).sum()), "1-2": int(((move >= 1) & (move <= 2)).sum()),
                           "3-5": int(((move >= 3) & (move <= 5)).sum()), ">5": int((move > 5).sum())},
        "topOverlap": top,
        "largestMovers": [{"sealedProductId": k, "oldRank": ro[k], "newRank": rn[k],
                           "oldScore": old[k], "newScore": new[k]} for k in movers],
    }


def run_shadow(client: Any, *, market_date: str, read_rows_fn=None, collector_bundle_fn=None,
               accessibility_reader_fn=None, artifact_loader_fn=None, accessibility_resolver_fn=None,
               only_full_market: bool = True) -> Dict[str, Any]:
    """The whole candidate chain, in memory. Returns a JSON-friendly report plus the objects for later stages."""
    started = time.perf_counter()
    if read_rows_fn is None:
        from backend.db.repositories.sealed_product_results_repository import get_sealed_product_results_for_runs as read_rows_fn
    if collector_bundle_fn is None:
        from backend.db.services.collector_appeal_service import get_collector_appeal_bundle as collector_bundle_fn
    if accessibility_reader_fn is None:
        from backend.db.services.chase_accessibility_service import read_chase_accessibility_snapshots_for_sets

        def accessibility_reader_fn(set_ids):
            return read_chase_accessibility_snapshots_for_sets(set_ids=set_ids, client=client)

    cohort = resolve_finalization_cohort(client, market_date=market_date)
    if cohort.get("error") or not cohort.get("verificationPassed"):
        raise RuntimeError("live cohort is not verified: %s" % (cohort.get("error") or "freshness failed"))
    run_by_set = dict(cohort["runIdBySetId"])
    runs = sorted(set(run_by_set.values()))

    # -- Stage 1: exact-artifact V5, dry run, evidence captured (no writes) ------------------------
    evidence: Dict[str, Dict[str, Any]] = {}
    fin_kwargs = {} if artifact_loader_fn is None else {"artifact_loader_fn": artifact_loader_fn}
    v5_report = finalize_financial_rip_v5(client, market_date=market_date, dry_run=True, evidence_sink=evidence,
                                          **fin_kwargs)
    rows = [dict(r) for r in read_rows_fn(runs)]
    in_cohort = [r for r in rows if run_by_set.get(str(r.get("set_id"))) == str(r.get("calculation_run_id"))]
    v5_rows = [{**r, **{k: v for k, v in (evidence.get(str(r["id"])) or {}).items()}} for r in in_cohort]

    # -- Stage 2: Collector V5 + Chase V1 authorities ---------------------------------------------
    bundle = collector_bundle_fn() or {}
    payloads = bundle.get("payloads") or {}
    appeal = {sid: interpret_collector_appeal_payload(payloads.get(str(sid))) for sid in run_by_set}
    collector_by_set = {sid: {"score": a.get("score"), "version": a.get("version")} for sid, a in appeal.items()}
    accessibility = accessibility_reader_fn(list(run_by_set)) or {}

    # -- Stage 3: V14 candidate (in memory) --------------------------------------------------------
    candidate = build_v14_candidate(v5_rows, market_date=market_date, collector_by_set_id=collector_by_set,
                                    accessibility_by_set_id=accessibility, run_id_by_set_id=run_by_set)
    v14_validation = validate_v14_candidate(candidate)

    # -- Stage 4: Ranking V2 (explicit; persisted-V5 requirement satisfied by the captured evidence) --
    products = [{**r, "collector_appeal_score": (collector_by_set.get(str(r["set_id"])) or {}).get("score")}
                for r in v5_rows]
    ranking = o2.build_ranking_v2_for_cohort(
        client, products, method_version=BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2, only_full_market=only_full_market,
        **({} if accessibility_resolver_fn is None else {"accessibility_resolver_fn": accessibility_resolver_fn}),
        **({} if artifact_loader_fn is None else {"artifact_loader_fn": artifact_loader_fn}))
    fm_block = next(b for b in ranking["budgets"].values() if b["budgetType"] == "full_market")

    return {
        "marketDate": market_date, "cohort": cohort, "runByset": run_by_set, "v5Report": v5_report,
        "evidence": evidence, "rows": rows, "v5Rows": v5_rows, "appeal": appeal, "accessibility": accessibility,
        "candidate": candidate, "v14Validation": v14_validation, "ranking": ranking, "fullMarket": fm_block,
        "products": products, "elapsedSeconds": time.perf_counter() - started,
    }


def build_contract_v12_targets(shadow: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """One read-only ``publicRipContractV12`` per product target, from the shadow's ranked V14 rows."""
    ledger = {r["sealed_product_id"]: r for r in shadow["candidate"]["rows"]}
    size = len(ledger)
    out: List[Dict[str, Any]] = []
    v5_scores = {str(r["sealed_product_id"]): float(r["financial_rip_v5_score"]) for r in shadow["v5Rows"]
                 if r.get("financial_rip_v5_score") is not None}
    v5_rank = _ranks(v5_scores)
    for r in shadow["v5Rows"]:
        pid = str(r["sealed_product_id"])
        led = ledger.get(pid) or {}
        v14 = led.get("authority_json") or {}
        comps = (r.get("financial_rip_v5_payload") or {}).get("components") or {}
        acc = shadow["accessibility"].get(str(r["set_id"])) or {}
        target = {
            "financialRipV5": {"score": r.get("financial_rip_v5_score"), "status": r.get("financial_rip_v5_status"),
                               "rankable": r.get("financial_rip_v5_rankable"),
                               "scoreVersion": r.get("financial_rip_v5_version"), "components": comps,
                               "rank": v5_rank.get(pid), "cohortSize": len(v5_scores)},
            "overallRipV14": {**v14, "rank": led.get("rank"), "tier": led.get("tier"), "cohortSize": size,
                              "rankable": bool(v14.get("rankable")), "status": v14.get("status")},
            "financialRipV4": {"score": r.get("financial_rip_v4_score"), "version": r.get("financial_rip_v4_version")},
            "overallRipV10": r.get("overall_rip_v10_payload") or {},
            "overallRipV12": {**(r.get("overall_rip_v12_payload") or {}), "score": r.get("overall_rip_v12_score")},
            "chaseAccessibility": {"chaseAccessibility": acc.get("accessibility"),
                                   "chaseAccessibilityStatus": acc.get("status"),
                                   "chaseAccessibilityVersion": acc.get("version")},
            "collectorAppeal": {}, "openingExperience": {}}
        contract = build_public_rip_contract_v12(target)
        contract["_sealedProductId"] = pid
        out.append(contract)
    return out


def contract_v12_problems(contracts: Sequence[Mapping[str, Any]]) -> List[str]:
    from backend.desirability.public_rip_contract_v11 import PUBLIC_RIP_CONTRACT_V11_KEY
    from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_WEIGHTS

    bad: List[str] = []
    for c in contracts:
        pid = c.get("_sealedProductId")
        o, f = c["overallRipV14"], c["financialRipV5"]
        if c["contractVersion"] != "public_rip_contract_v12":
            bad.append(f"{pid}: contractVersion")
        if o["status"] != "ready" or o["score"] is None or o["rank"] is None:
            bad.append(f"{pid}: overallRipV14 {o['status']}")
        if f["status"] != "ready" or f["score"] is None:
            bad.append(f"{pid}: financialRipV5 {f['status']}")
        if c["overallRip"]["score"] != o["score"] or c["financialRip"]["score"] != f["score"]:
            bad.append(f"{pid}: generic slot != explicit block")
        comp = c["overallRipV14Composition"]
        if comp["weights"] != {"financial_rip": .86, "chase_accessibility": .04, "collector_appeal": .10}:
            bad.append(f"{pid}: weights")
        if "financial_rip_v4" in str(comp) or "loss_resilience" in str(f.get("components")):
            bad.append(f"{pid}: V4 identity inside V14/V5")
        if c["overallRip"].get("version") != OVERALL_RIP_V14_VERSION or c["financialRip"].get("version") != FINANCIAL_RIP_V5_VERSION:
            bad.append(f"{pid}: generic slot version")
        if not c.get(PUBLIC_RIP_CONTRACT_V11_KEY, {}).get("contractVersion") == "public_rip_contract_v11":
            bad.append(f"{pid}: V11 not embedded")
        if f["components"] and set(f["components"]) != set(FINANCIAL_RIP_V5_WEIGHTS):
            bad.append(f"{pid}: component set")
    return bad
