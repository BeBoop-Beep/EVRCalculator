"""Final SELECT-only validation of the two frozen P95-only Financial RIP finalists.

This module never publishes, persists, migrates, or simulates.  It reconstructs
only complete published states from their exact persisted outcome artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER, normalize_metric
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.research_equal_spend_product_rip import (
    BUDGET_BANDS, PRIMARY_TOLERANCE, SENSITIVITY_TOLERANCE, StrategyEngine,
    fixed_budget_quantity, load_authoritative_products, load_run_fingerprints,
)
from backend.scripts.research_realistic_upside_candidate_matrix import cohort_matrix, enrich_row

CANDIDATES = {
    "P95_ONLY_25": {"definition": "P95_THRESHOLD_ONLY", "realisticWeight": .25,
        "weights": {"true_win_frequency": .25, "typical_retention": .20, "loss_resilience": .15,
                    "realistic_upside": .25, "jackpot_upside": .10, "base_economic_efficiency": .05}},
    "P95_ONLY_20": {"definition": "P95_THRESHOLD_ONLY", "realisticWeight": .20,
        "weights": {"true_win_frequency": .269231, "typical_retention": .215385, "loss_resilience": .161538,
                    "realistic_upside": .20, "jackpot_upside": .10, "base_economic_efficiency": .053846}},
}
PARAMETERS = tuple((a, lam, gp, gm) for lam in (1., 1.5, 2.25) for a in (.88, 1.)
                   for gp in (.61, .75, 1.) for gm in (.69, .85, 1.))
CANONICAL = (.88, 2.25, .61, .69)
DEVELOPMENT_DATE = "2026-08-17"


def _rows(response: Any) -> list[dict[str, Any]]:
    return list((response.data if response else []) or [])


def probability_weight(p: float, gamma: float) -> float:
    if p <= 0: return 0.
    if p >= 1: return 1.
    return p ** gamma / (p ** gamma + (1. - p) ** gamma) ** (1. / gamma)


def cpt_value(values: np.ndarray, cost: float, params: tuple[float, float, float, float]) -> float:
    """Rank-dependent TK92 cumulative prospect value around net outcome zero."""
    alpha, lam, gamma_gain, gamma_loss = params
    net = np.asarray(values, float) - float(cost)
    unique, counts = np.unique(net, return_counts=True)
    probs = counts.astype(float) / len(net)
    total = 0.
    gain_idx = np.flatnonzero(unique >= 0)
    if gain_idx.size:
        tail = np.cumsum(probs[gain_idx][::-1])[::-1]
        next_tail = np.r_[tail[1:], 0.]
        weights = np.asarray([probability_weight(x, gamma_gain) for x in tail]) - np.asarray([
            probability_weight(x, gamma_gain) for x in next_tail])
        total += float(np.sum(weights * np.power(unique[gain_idx], alpha)))
    loss_idx = np.flatnonzero(unique < 0)
    if loss_idx.size:
        cumulative = np.cumsum(probs[loss_idx])
        previous = np.r_[0., cumulative[:-1]]
        weights = np.asarray([probability_weight(x, gamma_loss) for x in cumulative]) - np.asarray([
            probability_weight(x, gamma_loss) for x in previous])
        total += float(np.sum(weights * (-lam * np.power(-unique[loss_idx], alpha))))
    return total


def cpt_values(values: np.ndarray, cost: float) -> list[float]:
    """Evaluate the preregistered grid while sorting/grouping the vector once."""
    net = np.asarray(values, float) - float(cost)
    unique, counts = np.unique(net, return_counts=True)
    probs = counts.astype(float) / len(net)
    gain_idx = np.flatnonzero(unique >= 0); loss_idx = np.flatnonzero(unique < 0)
    gain_tail = np.cumsum(probs[gain_idx][::-1])[::-1] if gain_idx.size else np.asarray([])
    gain_next = np.r_[gain_tail[1:], 0.] if gain_idx.size else np.asarray([])
    loss_cum = np.cumsum(probs[loss_idx]) if loss_idx.size else np.asarray([])
    loss_prev = np.r_[0., loss_cum[:-1]] if loss_idx.size else np.asarray([])
    def weighted(array: np.ndarray, gamma: float) -> np.ndarray:
        powered = np.power(array, gamma)
        return np.divide(powered, np.power(powered + np.power(1. - array, gamma), 1. / gamma),
                         out=np.zeros_like(array), where=(array > 0) & (array < 1)) + (array >= 1)
    out = []
    for alpha, lam, gamma_gain, gamma_loss in PARAMETERS:
        total = 0.
        if gain_idx.size:
            wg = weighted(gain_tail, gamma_gain) - weighted(gain_next, gamma_gain)
            total += float(np.sum(wg * np.power(unique[gain_idx], alpha)))
        if loss_idx.size:
            wl = weighted(loss_cum, gamma_loss) - weighted(loss_prev, gamma_loss)
            total += float(np.sum(wl * (-lam * np.power(-unique[loss_idx], alpha))))
        out.append(total)
    return out


def p95_class(ratio: float) -> str:
    # Descriptive bins only; continuous ratio remains the scored research input.
    if ratio < .95: return "P95_BELOW_COST"
    if ratio <= 1.05: return "P95_NEAR_BREAK_EVEN"
    if ratio < 2.: return "P95_MEANINGFUL_WIN"
    return "P95_LARGE_WIN"


def resolve_states(client: Any) -> list[dict[str, Any]]:
    snapshots = _rows(client.table("pokemon_public_rip_leaderboard_snapshots")
        .select("*").eq("publication_status", "complete").not_.is_("published_at", "null")
        .like("financial_rip_version", "financial_rip_v3_%").order("market_date").order("published_at", desc=True).execute())
    unique: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        authority = _rows(client.table("pokemon_public_rip_leaderboard_rows").select("*")
            .eq("snapshot_id", str(snap["id"])).order("overall_rip_rank").execute())
        expected = int(snap.get("eligible_cohort_count") or 0)
        if len(authority) != expected or expected != 22: continue
        run_ids = sorted(str(r.get("simulation_calculation_run_id") or "") for r in authority)
        if any(not x for x in run_ids) or len(set(run_ids)) != 22: continue
        signature = hashlib.sha256("\n".join(run_ids).encode()).hexdigest()
        if signature not in unique:
            unique[signature] = {"snapshot": snap, "authority": authority, "signature": signature,
                                  "duplicateSnapshotIds": []}
        else:
            unique[signature]["duplicateSnapshotIds"].append(str(snap["id"]))
    return sorted(unique.values(), key=lambda x: (str(x["snapshot"]["market_date"]), str(x["snapshot"]["published_at"])))


def audit_reconstructability(client: Any, states: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    audited = []
    for state in states:
        run_ids = [str(r["simulation_calculation_run_id"]) for r in state["authority"]]
        artifacts: list[dict[str, Any]] = []; products: list[dict[str, Any]] = []
        for start in range(0, len(run_ids), 20):
            chunk = run_ids[start:start + 20]
            artifacts.extend(_rows(client.table("simulation_pack_outcome_artifacts")
                .select("calculation_run_id,outcome_count").in_("calculation_run_id", chunk).execute()))
            products.extend(_rows(client.table("simulation_sealed_product_results")
                .select("calculation_run_id,financial_rip_v3_rankable,financial_rip_v3_status")
                .in_("calculation_run_id", chunk).execute()))
        artifact_runs = {str(r["calculation_run_id"]) for r in artifacts if int(r.get("outcome_count") or 0) == 1_000_000}
        product_runs = {str(r["calculation_run_id"]) for r in products
                        if r.get("financial_rip_v3_rankable") is True and r.get("financial_rip_v3_status") == "ready"}
        missing_artifacts = sorted(set(run_ids) - artifact_runs); missing_products = sorted(set(run_ids) - product_runs)
        audited.append({"state": state, "marketDate": state["snapshot"]["market_date"],
            "snapshotId": state["snapshot"]["id"], "artifactRunCount": len(artifact_runs),
            "productRunCount": len(product_runs), "reconstructable": not missing_artifacts and not missing_products,
            "missingArtifactRunCount": len(missing_artifacts), "missingProductRunCount": len(missing_products)})
    return audited


def strategy_rows(engine: StrategyEngine, products: Sequence[Mapping[str, Any]], authority: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    authority_by_run = {str(r["simulation_calculation_run_id"]): r for r in authority}
    result: dict[str, list[dict[str, Any]]] = {}
    for budget in BUDGET_BANDS:
        rows = []
        for product in products:
            allocation = fixed_budget_quantity(budget, float(product["product_market_cost"]))
            if allocation["quantity"] < 1: continue
            strategy = engine.strategy(product, allocation["quantity"]); metrics = strategy["metrics"]
            base = {"sealedProductId": str(product["sealed_product_id"]), "productName": product["product_name"],
                "productFamily": product["product_family"], "setKey": authority_by_run[str(product["calculation_run_id"])]["set_canonical_key"],
                "unitPrice": float(product["product_market_cost"]), "budget": budget, "quantity": allocation["quantity"],
                "actualCommittedCapital": allocation["actualCommittedCapital"], "leftoverBudget": allocation["leftoverCapital"],
                "financialRipV3": metrics["financialRipV3"], "rtp": metrics["rtp"], "medianRetention": metrics["medianRetention"],
                "chanceToRecoverCapital": metrics["chanceToRecoverCapital"], "lossResilience": metrics["lossResilience"],
                "components": metrics["components"]}
            rows.append(enrich_row(base, metrics, CANDIDATES))
        result[str(budget)] = rows
    return result


def behavioral_summary(budgets: Mapping[str, Sequence[Mapping[str, Any]]], engine: StrategyEngine,
                       product_by: Mapping[str, Mapping[str, Any]], tolerance: float) -> dict[str, Any]:
    counts = Counter(); cases = []
    utility_cache: dict[tuple[str, int], list[float]] = {}
    def utilities(row: Mapping[str, Any]) -> list[float]:
        key = (str(row["sealedProductId"]), int(row["quantity"]))
        if key not in utility_cache:
            product = product_by[key[0]]; values = engine.strategy(product, key[1])
            array = engine.base[key[0]] if key[1] == 1 else None
            if array is None:
                # StrategyEngine has already materialized this deterministic aggregate.
                base = engine.base[key[0]]
                from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
                array = build_stage1_product_distributions(base, pack_counts=[key[1]], canonical_set_key=f"cpt:{key[0]}",
                    run_fingerprint=str(product["calculation_run_id"]))["distributions"][key[1]]
            cost = float(values["actualCommittedCapital"])
            utility_cache[key] = cpt_values(array, cost)
        return utility_cache[key]
    canonical_index = PARAMETERS.index(CANONICAL)
    for budget, rows in budgets.items():
        for i, a in enumerate(rows):
            for b in rows[i+1:]:
                mismatch = abs(a["actualCommittedCapital"] - b["actualCommittedCapital"]) / max(a["actualCommittedCapital"], b["actualCommittedCapital"])
                if mismatch > tolerance: continue
                ua, ub = utilities(a), utilities(b)
                prefs = ["A" if x > y else "B" if y > x else "TIE" for x, y in zip(ua, ub)]
                canonical = prefs[canonical_index]
                w25 = "A" if a["candidateScores"]["P95_ONLY_25"] >= b["candidateScores"]["P95_ONLY_25"] else "B"
                w20 = "A" if a["candidateScores"]["P95_ONLY_20"] >= b["candidateScores"]["P95_ONLY_20"] else "B"
                rtp = "A" if a["rtp"] >= b["rtp"] else "B"; v3 = "A" if a["financialRipV3"] >= b["financialRipV3"] else "B"
                majority = Counter(prefs).most_common(1)[0][0]; sensitive = len(set(prefs)) > 1
                counts["comparisons"] += 1; counts["bothFinalistsAgree"] += w25 == w20
                counts["finalistsDisagree"] += w25 != w20; counts["benchmarkSensitive"] += sensitive
                counts["canonical25Agreement"] += w25 == canonical; counts["canonical20Agreement"] += w20 == canonical
                counts["envelope25MajorityAgreement"] += w25 == majority; counts["envelope20MajorityAgreement"] += w20 == majority
                counts["pureRtpCanonicalAgreement"] += rtp == canonical; counts["v3CanonicalAgreement"] += v3 == canonical
                if w25 != w20:
                    winner = a if w25 == "A" else b; loser = b if winner is a else a
                    cases.append({"budget": int(budget), "skuA": a["sealedProductId"], "skuB": b["sealedProductId"],
                        "canonical": canonical, "envelopeMajority": majority, "sensitive": sensitive, "p95Winner25": w25,
                        "p95Winner20": w20, "rtpWinner": rtp, "v3Winner": v3,
                        "rtpTrade": float(winner["rtp"] - loser["rtp"]),
                        "medianTrade": float(winner["medianRetention"] - loser["medianRetention"]),
                        "recoveryTrade": float(winner["chanceToRecoverCapital"] - loser["chanceToRecoverCapital"]),
                        "p95Trade": float(winner["p95ThresholdRatio"] - loser["p95ThresholdRatio"])})
    n = counts["comparisons"]
    rates = {k + "Rate": v / n for k, v in counts.items() if k != "comparisons"} if n else {}
    return {**dict(counts), **rates, "disagreementCases": cases}


def pack_audit(engine: StrategyEngine, products: Sequence[Mapping[str, Any]], authority: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_run = defaultdict(list)
    for p in products: by_run[str(p["calculation_run_id"])].append(p)
    rows = []
    for auth in authority:
        run_id = str(auth["simulation_calculation_run_id"]); artifact = load_pack_outcome_artifact(engine.client, run_id)
        cost = float(auth["pack_price"]); payload = build_financial_rip_v3(artifact.outcomes, cost)
        components = {k: float(payload["components"][k]["score"]) for k in FINANCIAL_RIP_V3_COMPONENT_ORDER}
        raw = {k: v["raw"] for k, v in payload["audit"]["normalizedInputs"].items()}
        p95 = float(raw["p95_threshold_ratio"]); realistic = float(normalize_metric("p95_threshold_ratio", p95)["score"])
        scores = {}
        for key, c in CANDIDATES.items():
            comps = {**components, "realistic_upside": realistic}
            scores[key] = sum(float(c["weights"][k]) * comps[k] for k in FINANCIAL_RIP_V3_COMPONENT_ORDER)
        rows.append({"setKey": auth["set_canonical_key"], "v3": float(payload["score"]), **scores,
            "componentsV3": components, "p95Component": realistic, "p95Cost": p95, "p95Class": p95_class(p95),
            "chanceToBeatCost": raw["true_win_probability"], "rtp": payload["distributionDisclosures"]["totalRtpRatio"],
            "medianRetention": raw["typical_retention_ratio"], "p99Cost": raw["p99_threshold_ratio"],
            "jackpotTailCost": raw["jackpot_tail_mean_ratio"]})
    def ranks(key: str) -> dict[str, int]:
        return {r["setKey"]: i + 1 for i, r in enumerate(sorted(rows, key=lambda x: (-x[key], x["setKey"])))}
    rv3 = ranks("v3"); summaries = {}
    for candidate in CANDIDATES:
        rc = ranks(candidate); movements = [abs(rc[k] - rv3[k]) for k in rv3]
        top = lambda rank, n: {k for k, v in rank.items() if v <= n}
        summaries[candidate] = {"spearman": float(np.corrcoef([rv3[k] for k in rv3], [rc[k] for k in rv3])[0, 1]),
            "top3Overlap": len(top(rv3, 3) & top(rc, 3)), "top5Overlap": len(top(rv3, 5) & top(rc, 5)),
            "meanAbsoluteRankMovement": float(np.mean(movements)), "maxRankMovement": max(movements),
            "setsMovingAtLeast3": sorted(k for k in rv3 if abs(rc[k] - rv3[k]) >= 3)}
        for row in rows:
            row.setdefault("ranks", {})[candidate] = rc[row["setKey"]]
    for row in rows: row["ranks"]["v3"] = rv3[row["setKey"]]
    return {"summary": summaries, "sets": rows}


def analyze_state(client: Any, state: Mapping[str, Any]) -> dict[str, Any]:
    snap, authority = state["snapshot"], state["authority"]
    products = load_authoritative_products(client, authority); by_run = defaultdict(list)
    for p in products: by_run[str(p["calculation_run_id"])].append(p)
    run_ids = list(by_run); engine = StrategyEngine(client, authority, products, load_run_fingerprints(client, run_ids))
    for run_id, members in by_run.items(): engine.build_set(run_id, members)
    budgets = strategy_rows(engine, products, authority); matrix5 = cohort_matrix(budgets, CANDIDATES, PRIMARY_TOLERANCE)
    matrix2 = cohort_matrix(budgets, CANDIDATES, SENSITIVITY_TOLERANCE)
    product_by = {str(p["sealed_product_id"]): p for p in products}
    behavioral = behavioral_summary(budgets, engine, product_by, PRIMARY_TOLERANCE)
    pack = pack_audit(engine, products, authority)
    p95_classes = Counter(p95_class(float(r["p95ThresholdRatio"])) for rows in budgets.values() for r in rows)
    return {"snapshotId": snap["id"], "marketDate": snap["market_date"], "runSignature": state["signature"],
        "duplicateSnapshotIds": state["duplicateSnapshotIds"], "runCount": len(run_ids), "skuCount": len(products),
        "cohort5": matrix5, "cohort2": matrix2, "behavioral": behavioral, "packAudit": pack,
        "p95Classes": dict(p95_classes)}


def decide(states: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    temporal = [s for s in states if s["marketDate"] != DEVELOPMENT_DATE]
    no_l4 = all(s["cohort5"]["candidates"][k].get("layer4Inversions", 0) == 0 for s in states for k in CANDIDATES)
    totals = {k: {"layer1": sum(s["cohort5"]["candidates"][k].get("layer1Inversions", 0) for s in temporal),
                  "behavior": sum(s["behavioral"].get("envelope" + ("25" if k.endswith("25") else "20") + "MajorityAgreement", 0) for s in temporal)} for k in CANDIDATES}
    comparisons = sum(s["behavioral"].get("comparisons", 0) for s in temporal)
    # Multi-gate: 20 must show material safety/behavior superiority to overcome the frozen parsimony tie-break.
    material_behavior20 = totals["P95_ONLY_20"]["behavior"] - totals["P95_ONLY_25"]["behavior"] > max(10, .01 * comparisons)
    materially_safer20 = totals["P95_ONLY_25"]["layer1"] - totals["P95_ONLY_20"]["layer1"] > max(5, .10 * max(1, totals["P95_ONLY_25"]["layer1"]))
    pack_safe = all(s["packAudit"]["summary"][k]["maxRankMovement"] < 6 for s in states for k in CANDIDATES)
    if not temporal or not no_l4 or not pack_safe: decision = "FINANCIAL_RIP_REVISION_INCONCLUSIVE"
    elif material_behavior20 and materially_safer20: decision = "P95_ONLY_20_VALIDATED"
    else: decision = "P95_ONLY_25_VALIDATED"
    return decision, {"temporalTotals": totals, "behavioralComparisons": comparisons, "noLayer4": no_l4,
                      "packSemanticSafety": pack_safe, "independentTemporalStateCount": len(temporal),
                      "materialBehavior20": material_behavior20,
                      "materialDominanceSafety20": materially_safer20}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="logs/financial_rip_final_validation.json")
    parser.add_argument("--state-limit", type=int)
    parser.add_argument("--state-offset", type=int, default=0)
    args = parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    client = get_client(); all_resolved = resolve_states(client); reconstructability = audit_reconstructability(client, all_resolved)
    resolved = [row["state"] for row in reconstructability if row["reconstructable"]]
    if args.state_offset: resolved = resolved[args.state_offset:]
    if args.state_limit: resolved = resolved[:args.state_limit]
    states = [analyze_state(client, state) for state in resolved]
    decision, gates = decide(states)
    report = {"authority": {"completePublishedDistinctStates": len(all_resolved),
               "reconstructableDistinctStates": len(resolved), "developmentDate": DEVELOPMENT_DATE,
               "stateDates": [s["marketDate"] for s in states],
               "reconstructability": [{k:v for k,v in row.items() if k != "state"} for row in reconstructability]},
              "cpt": {"canonical": CANONICAL, "grid": PARAMETERS,
               "referencePoint": "opening market value minus committed purchase cost", "fittedToCandidates": False},
              "candidates": CANDIDATES, "states": states, "gates": gates, "decision": decision,
              "databaseMutations": "NONE", "publicationMutations": "NONE"}
    path = Path(args.json); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "decision": decision, "states": len(states), "gates": gates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
