"""Stage VI analysis: does Chase deserve to be a third Overall RIP pillar?

RESEARCH ONLY. Reads the Stage VI dataset and prints the phase analyses. Writes
nothing and touches no production state.

    python -m backend.scripts.report_chase_pillar_stage6

The reporting posture is falsification. The default answer is that the current
two-pillar Overall RIP stands; every phase below is an opportunity for the Chase
hypothesis to fail, and the summary lines are written so that a failure is
legible rather than buried.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.research.chase_pillar_stage6 import candidates as families
from backend.research.chase_pillar_stage6 import control as control_module
from backend.research.chase_pillar_stage6 import stats
from backend.research.chase_pillar_stage6 import transforms

DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
SCENARIOS = Path("docs/research/chase_pillar_stage6_scenarios.json")

CHASE_CANDIDATES = ("anyChasePerProduct", "chaseSpend50", "coreK", "chaseEvReturn")
FINANCIAL_COMPONENTS = tuple(
    "fin_" + name for name in (
        "true_win_frequency", "typical_retention", "loss_resilience",
        "realistic_upside", "jackpot_upside", "base_economic_efficiency"))
COLLECTOR_COMPONENTS = ("ca_rosterDesirability", "ca_desirableOutcomeFrequency")


def _column(rows: Sequence[Mapping[str, Any]], key: str) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for row in rows:
        value = row.get(key)
        try:
            out.append(None if value is None else float(value))
        except (TypeError, ValueError):
            out.append(None)
    return out


def _complete(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]
              ) -> List[Mapping[str, Any]]:
    """Rows with every named key present. Reported, never silently applied."""
    return [r for r in rows if all(r.get(k) is not None for k in keys)]


def _fmt(value: Optional[float], spec: str = "%+.3f") -> str:
    return "-" if value is None else spec % value


# --------------------------------------------------------------------------
# Phases 1-3 - the audit, restated from what the dataset actually recorded
# --------------------------------------------------------------------------

def phase123_audit(payload: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASES 1-3 - pillar authority audit (read from code, not notes) ===")
    versions = payload["canonicalVersions"]
    print("  canonical Overall RIP     %s" % versions["overallRip"])
    print("  canonical Financial RIP   %s" % versions["financialRip"])
    print("  canonical Collector Appeal%s" % (" " + versions["collectorAppeal"]))
    print("  public RIP contract       %s" % versions["publicRipContract"])
    print("  Overall weights           %s" % versions["overallWeights"])
    print("  CONTROL: %s" % payload["controlDefinition"])
    print("  stored overall_rip_v10_score populated: %s"
          % payload["controlStoredColumnPopulated"])
    print("  -> %s" % payload["controlStoredColumnNote"])
    print("  dates: %s" % json.dumps(payload["dates"]))
    print("  rows %d | sets %d | unusable %d"
          % (payload["rowCount"], payload["setCount"], payload["unusableCount"]))

    # The single most consequential structural fact in the whole study.
    appeal_per_set = {}
    for row in rows:
        appeal_per_set.setdefault(row["set"], set()).add(row["collectorAppeal"])
    varying = [s for s, values in appeal_per_set.items() if len(values) > 1]
    print("  Collector Appeal is SET-level: sets whose products differ on it: %d/%d"
          % (len(varying), len(appeal_per_set)))
    print("  => within a set, CONTROL is a strictly increasing function of")
    print("     Financial RIP alone. Chase is the only candidate that can separate")
    print("     two products of one set on anything other than money.")


# --------------------------------------------------------------------------
# Phase 5 / 13 - directional contract, normalization, anchor stress
# --------------------------------------------------------------------------

def phase5_13_normalization(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASES 5 & 13 - directional contract and fixed-anchor normalization ===")
    print("  direction of merit: %s" % transforms.DIRECTION)
    print("  NO cohort min/max anywhere: every transform is a fixed function of one")
    print("  product's own numbers, so adding a product cannot rescore the others.")

    print("\n  raw distributions (n=%d)" % len(rows))
    print("  %-24s %10s %10s %10s %10s" % ("metric", "min", "median", "max", "missing"))
    for key in CHASE_CANDIDATES:
        values = [v for v in _column(rows, key) if v is not None]
        missing = len(rows) - len(values)
        if values:
            print("  %-24s %10.4f %10.4f %10.4f %10d"
                  % (key, min(values), st.median(values), max(values), missing))
        else:
            print("  %-24s %10s %10s %10s %10d" % (key, "-", "-", "-", missing))

    print("\n  Core K transform comparison (Phase 5 curvature question)")
    core_values = _column(rows, "coreK")
    print("  %-14s %8s %8s %8s %8s %10s" % (
        "transform", "K=0", "K=4", "K=10", "K=14", "rho vs raw"))
    raw_scores = [transforms.core_k_raw(v) for v in core_values]
    for name, function in transforms.CORE_K_TRANSFORMS.items():
        scores = [function(v) for v in core_values]
        print("  %-14s %8.1f %8.1f %8.1f %8.1f %10s" % (
            name, function(0), function(4), function(10), function(14),
            _fmt(stats.spearman(raw_scores, scores), "%+.4f")))
    print("  All four are monotone in K, so they cannot reorder products on K alone;")
    print("  they differ only in how much a marginal chase is worth. The choice is")
    print("  therefore about weight against the OTHER factors, not about ranking K.")

    print("\n  anchor stress (Phase 13): does the ranking survive moved anchors?")
    grids = {
        "anyChasePerProduct": (transforms.normalize_any_chase, "anyChasePerProduct", {
            "wider":  {"floor": 0.005, "ceiling": 0.70},
            "tighter": {"floor": 0.02, "ceiling": 0.35},
        }),
        "chaseSpend50": (transforms.normalize_chase_spend, "chaseSpend50", {
            "wider":  {"best": 50.0, "worst": 20000.0},
            "tighter": {"best": 200.0, "worst": 5000.0},
        }),
        "chaseEvReturn": (transforms.normalize_ev_return, "chaseEvReturn", {
            "wider":  {"ceiling": 0.60},
            "tighter": {"ceiling": 0.20},
        }),
    }
    print("  %-22s %-10s %10s %12s %10s %10s" % (
        "metric", "variant", "rho vs base", "mean shift", "at 100", "at 0"))
    for label, (function, key, variants) in grids.items():
        values = _column(rows, key)
        report = transforms.anchor_stress(function, values, variants)
        for variant, block in report.items():
            print("  %-22s %-10s %10s %12s %10d %10d" % (
                label, variant, _fmt(block["spearmanVsBase"], "%+.4f"),
                _fmt(block["meanAbsoluteScoreShift"], "%.2f"),
                block["saturatedAtCeiling"], block["saturatedAtFloor"]))


# --------------------------------------------------------------------------
# Phase 6 - the overlap matrix
# --------------------------------------------------------------------------

def phase6_overlap(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 6 - full overlap matrix ===")
    print("  strong redundancy |rho| >= %.2f ; moderate overlap %.2f <= |rho| < %.2f"
          % (stats.STRONG_REDUNDANCY, stats.MODERATE_OVERLAP, stats.STRONG_REDUNDANCY))
    targets = (
        ("financialRip", "Financial RIP V4"),
        ("collectorAppeal", "Collector Appeal V5"),
        ("overallControl", "Overall CONTROL"),
        ("valueToCostRatio", "EV / cost"),
        ("p95Value", "P95 value"),
        ("p99Value", "P99 (jackpot)"),
        ("expectedValue", "expected value"),
    ) + tuple((k, k.replace("fin_", "FIN ")) for k in FINANCIAL_COMPONENTS) \
      + tuple((k, k.replace("ca_", "CA ")) for k in COLLECTOR_COMPONENTS)

    print("\n  %-30s %s" % ("", "".join("%14s" % c[:13] for c in CHASE_CANDIDATES)))
    flags: List[str] = []
    for key, label in targets:
        line = "  %-30s" % label[:29]
        for candidate in CHASE_CANDIDATES:
            rho = stats.spearman(_column(rows, candidate), _column(rows, key))
            line += "%14s" % _fmt(rho, "%+.3f")
            verdict = stats.classify_overlap(rho)
            if verdict != "distinct":
                flags.append("%s vs %s: rho=%s (%s)"
                             % (candidate, label, _fmt(rho, "%+.3f"), verdict))
        print(line)

    print("\n  among the Chase candidates themselves (Spearman above, Pearson below)")
    print("  %-24s %s" % ("", "".join("%14s" % c[:13] for c in CHASE_CANDIDATES)))
    for i, left in enumerate(CHASE_CANDIDATES):
        line = "  %-24s" % left
        for j, right in enumerate(CHASE_CANDIDATES):
            if i == j:
                line += "%14s" % "+1.000"
            elif j > i:
                line += "%14s" % _fmt(
                    stats.spearman(_column(rows, left), _column(rows, right)), "%+.3f")
            else:
                line += "%14s" % _fmt(
                    stats.pearson(_column(rows, left), _column(rows, right)), "%+.3f")
        print(line)
        for right in CHASE_CANDIDATES[i + 1:]:
            rho = stats.spearman(_column(rows, left), _column(rows, right))
            if stats.classify_overlap(rho) != "distinct":
                flags.append("%s vs %s: rho=%s (%s)"
                             % (left, right, _fmt(rho, "%+.3f"),
                                stats.classify_overlap(rho)))

    print("\n  FLAGGED (%d):" % len(flags))
    for flag in flags:
        print("    %s" % flag)
    if not flags:
        print("    none")


# --------------------------------------------------------------------------
# Phase 7 - reconstruction
# --------------------------------------------------------------------------

def _predictor_sets(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[float]]]:
    return {
        "A financial only": {"financialRip": _column(rows, "financialRip")},
        "B collector only": {"collectorAppeal": _column(rows, "collectorAppeal")},
        "C financial+collector": {
            "financialRip": _column(rows, "financialRip"),
            "collectorAppeal": _column(rows, "collectorAppeal")},
        "D all components": {
            **{k: _column(rows, k) for k in FINANCIAL_COMPONENTS},
            **{k: _column(rows, k) for k in COLLECTOR_COMPONENTS}},
    }


def phase7_reconstruction(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 7 - can the existing pillars reconstruct each Chase candidate? ===")
    print("  cvR2 is leave-one-SET-out. A random row split would leak a set's chase")
    print("  structure between train and test and inflate every number here.")
    print("  %-22s %-24s %8s %8s %8s %10s" % (
        "candidate", "predictors", "R2", "adjR2", "cvR2", "resid/sd"))
    for candidate in CHASE_CANDIDATES:
        usable = _complete(rows, [candidate, "financialRip", "collectorAppeal"]
                           + list(FINANCIAL_COMPONENTS) + list(COLLECTOR_COMPONENTS))
        if len(usable) < 20:
            print("  %-22s insufficient complete rows (%d)" % (candidate, len(usable)))
            continue
        groups = [r["set"] for r in usable]
        for label, predictors in _predictor_sets(usable).items():
            result = stats.reconstruct(name=candidate, target=_column(usable, candidate),
                                       predictors=predictors, groups=groups)
            print("  %-22s %-24s %8s %8s %8s %10s" % (
                candidate, label, _fmt(result["r2"], "%.3f"),
                _fmt(result["adjustedR2"], "%.3f"),
                _fmt(result["crossValidatedR2"], "%.3f"),
                _fmt(result["residualShareOfSd"], "%.3f")))


# --------------------------------------------------------------------------
# Phase 8 - partial correlations
# --------------------------------------------------------------------------

PARTIAL_PLAN = {
    "anyChasePerProduct": (
        ("financialRip", "collectorAppeal", "productMarketCost", "randomPackCount"),
        "the pack-count and price confound plus both pillars: what is left is the"
        " part of per-unit accessibility that size and money do not explain"),
    "coreK": (
        ("collectorAppeal", "chaseEvReturn", "productMarketCost"),
        "Collector Appeal is the roster-breadth incumbent and Chase EV Return is the"
        " value incumbent; Core K must survive both to be structural rather than a proxy"),
    "chaseEvReturn": (
        ("valueToCostRatio", "p95Value", "p99Value"),
        "the three Financial quantities that already reward the same expensive cards"),
    "chaseSpend50": (
        ("productMarketCost", "anyChasePerProduct", "financialRip"),
        "cost-normalized accessibility must not be merely price, nor merely the"
        " un-normalized probability restated"),
}


def phase8_partials(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 8 - partial correlations against Overall CONTROL ===")
    print("  Each candidate's relationship with CONTROL once the named constructs")
    print("  are removed from BOTH sides.")
    for candidate, (controls, why) in PARTIAL_PLAN.items():
        usable = _complete(rows, [candidate, "overallControl", *controls])
        if len(usable) < 20:
            print("  %-22s insufficient rows" % candidate)
            continue
        result = stats.partial_correlation(
            x=_column(usable, candidate), y=_column(usable, "overallControl"),
            controls={c: _column(usable, c) for c in controls})
        print("\n  %s (n=%d)" % (candidate, result["n"]))
        print("    controls: %s" % ", ".join(controls))
        print("    why: %s" % why)
        print("    raw     Pearson %s  Spearman %s"
              % (_fmt(result["rawPearson"]), _fmt(result["rawSpearman"])))
        print("    partial Pearson %s  Spearman %s"
              % (_fmt(result["partialPearson"]), _fmt(result["partialSpearman"])))


# --------------------------------------------------------------------------
# Phase 9 - Core K versus Collector Appeal
# --------------------------------------------------------------------------

def phase9_core_k_vs_collector(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 9 - is Core K just a proxy for Collector Appeal? ===")
    comparisons = (
        ("collectorAppeal", "Collector Appeal V5"),
        ("ca_rosterDesirability", "roster desirability (D)"),
        ("ca_desirableOutcomeFrequency", "desirable outcome frequency (H)"),
        ("ca_eligibleDesirableCardCount", "eligible desirable CARD count"),
        ("ca_eligibleDesirableSubjectCount", "eligible desirable SUBJECT count"),
        ("ca_modeledSubjectCount", "modeled subject count"),
        ("ca_chaseAppeal", "Chase Appeal diagnostic"),
        ("ca_eliteScarcity", "elite scarcity"),
        ("extK", "Extended K (breadth diagnostic)"),
    )
    print("  %-38s %12s %12s %s" % ("versus", "Spearman", "Pearson", "verdict"))
    for key, label in comparisons:
        rho = stats.spearman(_column(rows, "coreK"), _column(rows, key))
        r = stats.pearson(_column(rows, "coreK"), _column(rows, key))
        print("  %-38s %12s %12s %s"
              % (label, _fmt(rho), _fmt(r), stats.classify_overlap(rho)))

    print("\n  Core K varies WITHIN a set while Collector Appeal cannot:")
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_set.setdefault(row["set"], []).append(row)
    ranges = [(max(g, key=lambda r: r["coreK"])["coreK"]
               - min(g, key=lambda r: r["coreK"])["coreK"], name)
              for name, g in by_set.items() if len(g) > 1]
    print("    sets where Core K differs across products: %d/%d ; median range %.1f"
          % (sum(1 for r, _ in ranges if r > 0), len(ranges),
             st.median([r for r, _ in ranges])))

    print("\n  disagreement cases (set-level, since Collector Appeal is set-level)")
    per_set = []
    for name, group in by_set.items():
        per_set.append({
            "set": name, "ca": group[0]["collectorAppeal"],
            "medianCoreK": st.median([g["coreK"] for g in group]),
        })
    ca_rank = stats.rank([p["ca"] for p in per_set])
    k_rank = stats.rank([p["medianCoreK"] for p in per_set])
    for i, entry in enumerate(per_set):
        entry["caRank"] = float(ca_rank[i])
        entry["kRank"] = float(k_rank[i])
        entry["gap"] = float(k_rank[i] - ca_rank[i])
    ordered = sorted(per_set, key=lambda e: e["gap"])
    print("  %-30s %8s %10s %8s %8s" % ("set", "CA", "medCoreK", "caRank", "kRank"))
    print("  -- HIGH Collector Appeal / LOW Core K --")
    for entry in ordered[:4]:
        print("  %-30s %8.2f %10.1f %8.1f %8.1f"
              % (entry["set"][:29], entry["ca"], entry["medianCoreK"],
                 entry["caRank"], entry["kRank"]))
    print("  -- LOW Collector Appeal / HIGH Core K --")
    for entry in ordered[::-1][:4]:
        print("  %-30s %8.2f %10.1f %8.1f %8.1f"
              % (entry["set"][:29], entry["ca"], entry["medianCoreK"],
                 entry["caRank"], entry["kRank"]))


# --------------------------------------------------------------------------
# Phase 10 - the pack-count confound
# --------------------------------------------------------------------------

def phase10_pack_confound(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 10 - is per-product accessibility just a pack-count bonus? ===")
    drivers = (("randomPackCount", "random pack count"),
               ("anyChasePerPack", "per-PACK chase probability"),
               ("productMarketCost", "product price"))
    print("  %-32s %12s %12s" % ("driver", "Spearman", "Pearson"))
    for key, label in drivers:
        print("  %-32s %12s %12s"
              % (label, _fmt(stats.spearman(_column(rows, "anyChasePerProduct"),
                                            _column(rows, key))),
                 _fmt(stats.pearson(_column(rows, "anyChasePerProduct"),
                                    _column(rows, key)))))

    usable = _complete(rows, ["anyChasePerProduct", "randomPackCount",
                              "anyChasePerPack", "productMarketCost"])
    groups = [r["set"] for r in usable]
    print("\n  reconstruction of per-product accessibility (n=%d)" % len(usable))
    print("  %-42s %8s %8s %8s" % ("predictors", "R2", "adjR2", "cvR2"))
    plans = {
        "pack count alone": ["randomPackCount"],
        "per-pack probability alone": ["anyChasePerPack"],
        "pack count + per-pack probability": ["randomPackCount", "anyChasePerPack"],
        "+ product price": ["randomPackCount", "anyChasePerPack", "productMarketCost"],
    }
    for label, keys in plans.items():
        result = stats.reconstruct(
            name="anyChasePerProduct", target=_column(usable, "anyChasePerProduct"),
            predictors={k: _column(usable, k) for k in keys}, groups=groups)
        print("  %-42s %8s %8s %8s" % (
            label, _fmt(result["r2"], "%.3f"), _fmt(result["adjustedR2"], "%.3f"),
            _fmt(result["crossValidatedR2"], "%.3f")))
    print("\n  NOTE: p_product = 1 - (1 - p_pack)^n is an exact identity, so a high")
    print("  R2 on the last two rows is arithmetic, not a finding. The question that")
    print("  matters is whether the pillar INHERITS the pack-count tilt - see the")
    print("  family fairness phase, which is where that gets decided.")

    print("\n  the three accessibility views, ranked against pack count")
    for key, label in (("anyChasePerProduct", "per-product probability"),
                       ("anyChasePerPack", "per-pack probability"),
                       ("chaseSpend50", "50% chase spend (dollars)")):
        print("    %-30s rho(packs) = %s"
              % (label, _fmt(stats.spearman(_column(rows, key),
                                            _column(rows, "randomPackCount")))))


# --------------------------------------------------------------------------
# Phases 11 / 14 / 15 - build the candidates and gate them
# --------------------------------------------------------------------------

def build_chase_scores(rows: List[Dict[str, Any]], *, core_k_transform: str = "saturating"
                       ) -> Dict[str, List[Optional[float]]]:
    normalized = [transforms.normalize_row(row, core_k_transform=core_k_transform)
                  for row in rows]
    out: Dict[str, List[Optional[float]]] = {}
    for candidate in families.enumerate_candidates():
        out[candidate.key] = [candidate.score(n) for n in normalized]
    return out


def phase11_15_candidates(rows: List[Dict[str, Any]], scores: Dict[str, List[Any]]
                          ) -> List[Dict[str, Any]]:
    print("\n=== PHASES 11, 14 & 15 - Chase pillar candidates and the redundancy gate ===")
    print("  A useful third pillar must retain a residual that is material, stable")
    print("  and interpretable. cvR2 is leave-one-set-out; high cvR2 = reconstructable")
    print("  = redundant.")
    groups = [r["set"] for r in rows]
    financial = _column(rows, "financialRip")
    collector = _column(rows, "collectorAppeal")
    components = {**{k: _column(rows, k) for k in FINANCIAL_COMPONENTS},
                  **{k: _column(rows, k) for k in COLLECTOR_COMPONENTS}}

    print("\n  %-16s %-34s %7s %7s %7s %7s %8s" % (
        "candidate", "family", "F R2", "C R2", "F+C R2", "cvR2", "resid/sd"))
    summaries: List[Dict[str, Any]] = []
    for candidate in families.enumerate_candidates():
        column = scores[candidate.key]
        if any(v is None for v in column):
            continue
        fin = stats.reconstruct(name=candidate.key, target=column,
                                predictors={"financialRip": financial}, groups=groups)
        col = stats.reconstruct(name=candidate.key, target=column,
                                predictors={"collectorAppeal": collector}, groups=groups)
        both = stats.reconstruct(name=candidate.key, target=column,
                                 predictors={"financialRip": financial,
                                             "collectorAppeal": collector}, groups=groups)
        full = stats.reconstruct(name=candidate.key, target=column,
                                 predictors=components, groups=groups)
        summaries.append({
            "key": candidate.key, "label": candidate.label,
            "factors": candidate.factors, "weights": candidate.weights,
            "financialR2": fin["r2"], "collectorR2": col["r2"],
            "bothR2": both["r2"], "bothCvR2": both["crossValidatedR2"],
            "componentsR2": full["r2"], "componentsCvR2": full["crossValidatedR2"],
            "residualShare": both["residualShareOfSd"],
            "scores": column,
        })
        print("  %-16s %-34s %7s %7s %7s %7s %8s" % (
            candidate.key, candidate.label[:33], _fmt(fin["r2"], "%.3f"),
            _fmt(col["r2"], "%.3f"), _fmt(both["r2"], "%.3f"),
            _fmt(both["crossValidatedR2"], "%.3f"),
            _fmt(both["residualShareOfSd"], "%.3f")))
    return summaries




# --------------------------------------------------------------------------
# Finalists
# --------------------------------------------------------------------------

#: Chosen on stated grounds after Phases 6-15, not by score:
#:  A_100  - lowest reconstructability of any candidate, and therefore the
#:           strongest prima facie case for a third pillar. Also the candidate
#:           most exposed to the pack-count confound, so it must be carried
#:           forward to be tested, not assumed.
#:  C_100  - the only candidate whose partial correlation with CONTROL survives
#:           its controls.
#:  G_50-50 and H_33-33-33 - the best-motivated multi-factor blends.
#:  I_25-25-25-25 - the deliberate double-counting control.
FINALISTS = ("A_100", "C_100", "G_50-50", "H_33-33-33", "I_25-25-25-25")


def _finalist_map(scores):
    return {key: scores[key] for key in FINALISTS if key in scores}


# --------------------------------------------------------------------------
# Phase 16 - disagreement quadrants
# --------------------------------------------------------------------------

def phase16_quadrants(rows, scores, chase_key="C_100"):
    print("\n=== PHASE 16 - disagreement quadrants (Chase = %s) ===" % chase_key)
    chase = scores[chase_key]
    fin_rank = stats.rank(_column(rows, "financialRip"))
    col_rank = stats.rank(_column(rows, "collectorAppeal"))
    chase_rank = stats.rank([v if v is not None else 0.0 for v in chase])
    n = len(rows)

    enriched = []
    for i, row in enumerate(rows):
        enriched.append({
            **row, "chaseScore": chase[i],
            "finPct": 100.0 * fin_rank[i] / n,
            "colPct": 100.0 * col_rank[i] / n,
            "chasePct": 100.0 * chase_rank[i] / n,
        })

    quadrants = {
        "HIGH Financial / LOW Chase": lambda e: e["finPct"] >= 70 and e["chasePct"] <= 30,
        "LOW Financial / HIGH Chase": lambda e: e["finPct"] <= 30 and e["chasePct"] >= 70,
        "HIGH Collector / LOW Chase": lambda e: e["colPct"] >= 70 and e["chasePct"] <= 30,
        "LOW Collector / HIGH Chase": lambda e: e["colPct"] <= 30 and e["chasePct"] >= 70,
        "HIGH Financial+Collector / LOW Chase":
            lambda e: e["finPct"] >= 60 and e["colPct"] >= 60 and e["chasePct"] <= 40,
        "MODERATE Financial+Collector / exceptional Chase":
            lambda e: 30 <= e["finPct"] <= 70 and 30 <= e["colPct"] <= 70 and e["chasePct"] >= 85,
    }
    for label, predicate in quadrants.items():
        members = [e for e in enriched if predicate(e)]
        print("\n  %s  (%d products)" % (label, len(members)))
        if not members:
            print("    NONE - this quadrant is empty, which is itself a finding")
            continue
        members.sort(key=lambda e: abs(e["chasePct"] - e["finPct"]), reverse=True)
        for entry in members[:3]:
            print("    %s" % entry["productName"][:70])
            print("      set %s | %s | cost $%.2f | %d random packs"
                  % (entry["set"], entry["family"], entry["productMarketCost"],
                     entry["randomPackCount"]))
            print("      Core K %d | anyChase/product %s | 50%% spend %s | EV return %s"
                  % (entry["coreK"], _fmt(entry["anyChasePerProduct"], "%.4f"),
                     _fmt(entry["chaseSpend50"], "$%.0f"),
                     _fmt(entry["chaseEvReturn"], "%.4f")))
            print("      Financial %.2f (p%.0f) | Collector %.2f (p%.0f) | Chase %.1f (p%.0f)"
                  % (entry["financialRip"], entry["finPct"], entry["collectorAppeal"],
                     entry["colPct"], entry["chaseScore"], entry["chasePct"]))


# --------------------------------------------------------------------------
# Phase 17 - controlled counterfactuals
# --------------------------------------------------------------------------

def phase17_counterfactuals(scores_unused=None):
    print("\n=== PHASE 17 - controlled counterfactuals (expectations stated first) ===")
    print("  Synthetic products. Financial and Collector are held EXACTLY equal in")
    print("  cases A-D, so any Overall difference is attributable to Chase alone.")

    weights = control_module.donor_weights(0.10, "financial")
    base_fin, base_col = 60.0, 70.0

    def overall(chase_norm, candidate_key="H_33-33-33"):
        candidate = {c.key: c for c in families.enumerate_candidates()}[candidate_key]
        chase = candidate.score(chase_norm)
        return control_module.with_chase(financial=base_fin, appeal=base_col,
                                         chase=chase, weights=weights), chase

    def norm(any_chase, spend, k, ev=0.05):
        return transforms.normalize_row(
            {"anyChasePerProduct": any_chase, "chaseSpend50": spend,
             "coreK": k, "chaseEvReturn": ev})

    cases = [
        ("A same F+C, different any-chase probability",
         "the higher-probability product must score higher",
         norm(0.05, 1500, 4), norm(0.30, 1500, 4)),
        ("B same F+C, different Core K",
         "the broader Core must score higher",
         norm(0.15, 1500, 2), norm(0.15, 1500, 10)),
        ("C same F+C, different 50% chase spend",
         "the CHEAPER chase must score higher (lower is better)",
         norm(0.15, 6000, 4), norm(0.15, 400, 4)),
        ("D same F+C, different Chase EV Return",
         "no change: EV Return is not in the three-factor pillar",
         norm(0.15, 1500, 4, ev=0.02), norm(0.15, 1500, 4, ev=0.30)),
    ]
    print("\n  %-46s %10s %10s %10s %s" % ("case", "left", "right", "delta", "verdict"))
    for label, expectation, left, right in cases:
        left_overall, left_chase = overall(left)
        right_overall, right_chase = overall(right)
        delta = right_overall - left_overall
        expected_change = not label.startswith("D")
        passed = (delta > 1e-9) if expected_change else (abs(delta) < 1e-9)
        print("  %-46s %10.4f %10.4f %+10.4f %s"
              % (label[:45], left_overall, right_overall, delta,
                 "PASS" if passed else "FAIL"))
        print("      expected: %s" % expectation)

    print("\n  E same Financial + Chase, different Collector")
    chase_norm = norm(0.15, 1500, 4)
    for appeal in (40.0, 90.0):
        value, _ = (control_module.with_chase(
            financial=base_fin, appeal=appeal,
            chase={c.key: c for c in families.enumerate_candidates()}["H_33-33-33"]
            .score(chase_norm), weights=weights), None)
        print("    Collector %5.1f -> Overall %.4f" % (appeal, value))

    print("\n  F same Collector + Chase, different Financial")
    for financial in (40.0, 90.0):
        value = control_module.with_chase(
            financial=financial, appeal=base_col,
            chase={c.key: c for c in families.enumerate_candidates()}["H_33-33-33"]
            .score(chase_norm), weights=weights)
        print("    Financial %5.1f -> Overall %.4f" % (financial, value))

    print("\n  G same per-pack chase economics, 1-pack vs 36-pack product")
    print("     EXPECTATION: the pillar must not treat pack quantity as quality.")
    print("     Same cost per pack ($10) and same per-pack hit rate (2%), so the")
    print("     50%% chase SPEND and Core K are identical; only the per-UNIT")
    print("     probability differs, which is a real difference in what one unit is.")
    p_pack = 0.02
    single = norm(p_pack, 1000.0, 4)
    box = norm(1 - (1 - p_pack) ** 36, 1000.0, 4)
    for key in ("A_100", "C_100", "G_50-50", "H_33-33-33"):
        candidate = {c.key: c for c in families.enumerate_candidates()}[key]
        a, b = candidate.score(single), candidate.score(box)
        print("     %-14s single-pack %6.2f  36-pack box %6.2f  gap %+6.2f"
              % (key, a, b, b - a))
    print("     Candidates without the per-unit factor show a gap of exactly 0.")
    print("     Candidate A is pure pack-count leverage; H dilutes it to one third.")

    print("\n  H one hero Core card vs many Core cards, matched Financial")
    print("     EXPECTATION: Core K rewards breadth; a hero-only product should")
    print("     score lower on structure while the accessibility factor is free to")
    print("     disagree, which is the point of keeping them separate.")
    hero = norm(0.12, 1500.0, 1)
    broad = norm(0.12, 1500.0, 12)
    for key in ("A_100", "C_100", "G_50-50", "H_33-33-33"):
        candidate = {c.key: c for c in families.enumerate_candidates()}[key]
        print("     %-14s hero-only %6.2f  broad %6.2f  gap %+6.2f"
              % (key, candidate.score(hero), candidate.score(broad),
                 candidate.score(broad) - candidate.score(hero)))


# --------------------------------------------------------------------------
# Phases 18-21 - Overall candidates, donors, rank movement, contribution
# --------------------------------------------------------------------------

CHASE_SHARES = (0.05, 0.10, 0.15, 0.20)
DONORS = ("financial", "collector", "proportional")


def phase18_21_overall(rows, scores):
    print("\n=== PHASES 18-21 - Overall candidates, donor study, rank movement ===")
    control = _column(rows, "overallControl")
    financial = _column(rows, "financialRip")
    collector = _column(rows, "collectorAppeal")
    labels = [r["productName"] for r in rows]

    print("\n  Phase 19 donor feasibility, from the CANONICAL 90/10 split:")
    for share in CHASE_SHARES:
        line = "    chase %4.0f%% :" % (share * 100)
        for donor in DONORS:
            weights = control_module.donor_weights(share, donor)
            line += "  %-13s %s" % (donor, "INFEASIBLE" if not weights else
                                    "%.3f/%.3f/%.3f" % (weights["financial_rip"],
                                                        weights["collector_appeal"],
                                                        weights["chase"]))
        print(line)
    print("    Collector holds only 0.10, so it cannot fund a 15%% or 20%% Chase")
    print("    pillar at all. That is a structural fact about the donor question,")
    print("    not a tuning choice.")

    print("\n  Phase 20/21 - rank movement vs CONTROL and variance contribution")
    print("  %-16s %-13s %5s %8s %8s %8s %6s %6s %9s %9s" % (
        "chase", "donor", "share", "spearman", "kendall", "medMove", "maxMv",
        "T5out", "finVarSh", "chsVarSh"))
    results = []
    for key in FINALISTS:
        chase = [v if v is not None else 0.0 for v in scores[key]]
        for share in CHASE_SHARES:
            for donor in DONORS:
                weights = control_module.donor_weights(share, donor)
                if not weights:
                    continue
                candidate = [control_module.with_chase(
                    financial=financial[i], appeal=collector[i], chase=chase[i],
                    weights=weights) for i in range(len(rows))]
                movement = stats.rank_movement(control, candidate, labels=labels)
                contribution = stats.variance_contribution(
                    {"financial_rip": financial, "collector_appeal": collector,
                     "chase": chase}, weights)
                shares = contribution["shares"]
                results.append({
                    "chase": key, "donor": donor, "share": share,
                    "spearman": movement["spearman"], "kendall": movement["kendallTau"],
                    "medianMove": movement["medianAbsoluteMovement"],
                    "maxMove": movement["maxMovement"],
                    "top5Turnover": movement["turnover"]["top5"]["turnover"],
                    "top10Turnover": movement["turnover"]["top10"]["turnover"],
                    "financialVarianceShare": shares["financial_rip"]["varianceShare"],
                    "chaseVarianceShare": shares["chase"]["varianceShare"],
                    "movement": movement, "scores": candidate,
                })
                print("  %-16s %-13s %5.0f%% %8s %8s %8.1f %6.0f %6d %9s %9s" % (
                    key, donor, share * 100, _fmt(movement["spearman"], "%.4f"),
                    _fmt(movement["kendallTau"], "%.4f"),
                    movement["medianAbsoluteMovement"], movement["maxMovement"],
                    movement["turnover"]["top5"]["turnover"],
                    _fmt(shares["financial_rip"]["varianceShare"], "%.3f"),
                    _fmt(shares["chase"]["varianceShare"], "%.3f")))

    print("\n  Phase 21 leverage check: does a nominal 10%% behave like 10%%?")
    for key in FINALISTS:
        row = [r for r in results
               if r["chase"] == key and r["donor"] == "financial" and r["share"] == 0.10]
        if row:
            entry = row[0]
            print("    %-16s nominal 10%% -> variance share %s (%.1fx nominal)"
                  % (key, _fmt(entry["chaseVarianceShare"], "%.3f"),
                     (entry["chaseVarianceShare"] or 0) / 0.10))
    return results


def phase20_examples(results, rows):
    print("\n  Phase 20 - largest movers at 10% Chase funded from Financial")
    for entry in results:
        if entry["donor"] != "financial" or entry["share"] != 0.10:
            continue
        print("\n    %s" % entry["chase"])
        index = {r["productName"]: r for r in rows}
        for direction, key in (("RISERS", "largestRisers"), ("FALLERS", "largestFallers")):
            print("      %s" % direction)
            for mover in entry["movement"][key][:3]:
                row = index.get(mover["label"], {})
                print("        %+5.0f  %-52s CoreK %s p_prod %s"
                      % (-mover["delta"] if direction == "RISERS" else mover["delta"],
                         mover["label"][:52], row.get("coreK"),
                         _fmt(row.get("anyChasePerProduct"), "%.4f")))


# --------------------------------------------------------------------------
# Phase 22 - double counting
# --------------------------------------------------------------------------

def phase22_double_counting(rows, scores):
    print("\n=== PHASE 22 - double-counting test ===")
    print("  Where does one expensive chase card get paid? Correlation of each Chase")
    print("  candidate with the Financial quantities that already price that card.")
    money = (("p99Value", "P99 (the jackpot card)"),
             ("p95Value", "P95"),
             ("fin_jackpot_upside", "FIN jackpot_upside"),
             ("fin_realistic_upside", "FIN realistic_upside"),
             ("valueToCostRatio", "EV / cost"))
    print("  %-18s %s" % ("", "".join("%22s" % m[1][:21] for m in money)))
    for key in FINALISTS:
        column = [v if v is not None else 0.0 for v in scores[key]]
        line = "  %-18s" % key
        for metric, _ in money:
            line += "%22s" % _fmt(stats.spearman(column, _column(rows, metric)), "%+.3f")
        print(line)

    print("\n  Tracing one card: the highest-value Core member in the cohort.")
    richest = max(rows, key=lambda r: (r.get("p99Value") or 0))
    print("    %s (%s)" % (richest["productName"][:60], richest["set"]))
    print("      P99 $%.2f | P95 $%.2f | EV $%.2f | cost $%.2f"
          % (richest["p99Value"], richest["p95Value"], richest["expectedValue"],
             richest["productMarketCost"]))
    print("      that card is paid in: Financial EV, Financial P95 (realistic_upside),")
    print("      Financial P99 (jackpot_upside), Chase EV Return, and Core K membership")
    print("      -> a Chase pillar containing chaseEvReturn pays it a THIRD time;")
    print("         Core K pays only its EXISTENCE, once, and is capped by saturation.")


# --------------------------------------------------------------------------
# Phase 25 - product-family fairness
# --------------------------------------------------------------------------

def phase25_family_fairness(rows, scores):
    print("\n=== PHASE 25 - product-family fairness ===")
    print("  Does the pillar become a booster-box bonus? Family medians, and the")
    print("  rank correlation of each candidate with random pack count.")
    by_family = {}
    for i, row in enumerate(rows):
        by_family.setdefault(row["family"], []).append(i)

    print("\n  %-34s %5s %7s %s" % (
        "family", "n", "packs", "".join("%13s" % k for k in FINALISTS)))
    for family, indices in sorted(by_family.items(),
                                  key=lambda kv: -st.median([rows[i]["randomPackCount"]
                                                             for i in kv[1]])):
        line = "  %-34s %5d %7.0f" % (
            family[:33], len(indices),
            st.median([rows[i]["randomPackCount"] for i in indices]))
        for key in FINALISTS:
            values = [scores[key][i] or 0.0 for i in indices]
            line += "%13.1f" % st.median(values)
        print(line)

    print("\n  %-18s %14s %14s %14s" % (
        "candidate", "rho(packs)", "rho(cost)", "boxVsPackGap"))
    packs = _column(rows, "randomPackCount")
    costs = _column(rows, "productMarketCost")
    box = [i for i, r in enumerate(rows) if r["family"] == "booster_box"]
    pack = [i for i, r in enumerate(rows) if r["family"] == "loose_booster_pack"]
    for key in FINALISTS:
        column = [v if v is not None else 0.0 for v in scores[key]]
        gap = (st.median([column[i] for i in box])
               - st.median([column[i] for i in pack]))
        print("  %-18s %14s %14s %14.1f" % (
            key, _fmt(stats.spearman(column, packs)),
            _fmt(stats.spearman(column, costs)), gap))
    print("\n  A large positive boxVsPackGap combined with a high rho(packs) is the")
    print("  booster-box bonus the brief says to reject.")


# --------------------------------------------------------------------------
# Phase 26 - complexity penalty
# --------------------------------------------------------------------------

def phase26_complexity(rows, scores):
    print("\n=== PHASE 26 - complexity penalty ===")
    print("  Information gain must justify each additional Chase variable.")
    control = _column(rows, "overallControl")
    ladder = (("CONTROL (2 pillars, 0 chase vars)", None),
              ("+1 chase variable (C_100, Core K)", "C_100"),
              ("+1 chase variable (A_100, accessibility)", "A_100"),
              ("+2 chase variables (G_50-50)", "G_50-50"),
              ("+3 chase variables (H_33-33-33)", "H_33-33-33"),
              ("+4 chase variables (I_25-25-25-25)", "I_25-25-25-25"))
    weights = control_module.donor_weights(0.10, "financial")
    financial = _column(rows, "financialRip")
    collector = _column(rows, "collectorAppeal")
    print("  %-44s %5s %10s %10s %12s" % (
        "architecture", "vars", "spearman", "medMove", "newInfo(1-cvR2)"))
    groups = [r["set"] for r in rows]
    for label, key in ladder:
        if key is None:
            print("  %-44s %5d %10s %10s %12s"
                  % (label, 0, "1.0000", "0.0", "-"))
            continue
        chase = [v if v is not None else 0.0 for v in scores[key]]
        candidate = [control_module.with_chase(
            financial=financial[i], appeal=collector[i], chase=chase[i],
            weights=weights) for i in range(len(rows))]
        movement = stats.rank_movement(control, candidate,
                                       labels=[r["productName"] for r in rows])
        reconstruction = stats.reconstruct(
            name=key, target=chase,
            predictors={"financialRip": financial, "collectorAppeal": collector},
            groups=groups)
        cv = reconstruction["crossValidatedR2"]
        variables = len({c.key: c for c in families.enumerate_candidates()}[key].factors)
        print("  %-44s %5d %10s %10.1f %12s" % (
            label, variables, _fmt(movement["spearman"], "%.4f"),
            movement["medianAbsoluteMovement"],
            _fmt(None if cv is None else 1.0 - cv, "%.3f")))
    print("\n  No third pillar is better than an unnecessary third pillar. A row that")
    print("  adds variables without adding newInfo or movement has not earned them.")


def _extra_phases(payload, rows, scores):
    results = phase18_21_overall(rows, scores)
    phase20_examples(results, rows)
    phase16_quadrants(rows, scores)
    phase17_counterfactuals()
    phase22_double_counting(rows, scores)
    phase25_family_fairness(rows, scores)
    phase26_complexity(rows, scores)
    return results




# --------------------------------------------------------------------------
# Phases 23-24 - price shocks and short-window temporal stability
# --------------------------------------------------------------------------

def _scenario_entries(rows, observations, kind):
    """Per-scenario observations, keyed by the base dataset's row position."""
    index = {r["sealedProductId"]: i for i, r in enumerate(rows)}
    per_scenario = {}
    for observation in observations:
        if observation.get("kind") != kind:
            continue
        position = index.get(observation["sealedProductId"])
        if position is None:
            continue
        per_scenario.setdefault(observation["scenario"], {})[position] = observation
    return per_scenario


def _score_positions(entries, positions):
    catalogue = {c.key: c for c in families.enumerate_candidates()}
    normalized = [transforms.normalize_row(entries[p]) for p in positions]
    return {
        "coreK": [entries[p]["coreK"] for p in positions],
        "scores": {key: [catalogue[key].score(n) for n in normalized]
                   for key in FINALISTS},
    }


def _scenario_report(rows, scenarios, kind, title, note, baseline=None):
    """Every scenario compared to the baseline over the products BOTH cover.

    Coverage is intersected PAIRWISE with the baseline, not globally. The
    temporal window's earliest dates carry only a handful of products, and a
    global intersection would have silently reduced the whole temporal analysis
    to those few - or, as it first did, to nothing at all. Each row therefore
    prints the number of products it was actually computed over.
    """
    print("\n=== %s ===" % title)
    print("  %s" % note)
    per_scenario = _scenario_entries(rows, scenarios["observations"], kind)
    if not per_scenario:
        print("  no scenarios of this kind in the artifact")
        return
    failures = scenarios.get("failures") or []
    if failures:
        print("  build failures excluded here: %s"
              % ", ".join("%s (%s)" % (f["canonicalKey"], f["error"]) for f in failures))

    base_key = baseline if baseline in per_scenario else (
        "base" if "base" in per_scenario else sorted(per_scenario)[-1])
    base_entries = per_scenario[base_key]
    print("  baseline scenario: %s (covers %d products)"
          % (base_key, len(base_entries)))

    financial = _column(rows, "financialRip")
    collector = _column(rows, "collectorAppeal")
    weights = control_module.donor_weights(0.10, "financial")

    print("  %-12s %-16s %5s %9s %9s %9s %10s %9s" % (
        "scenario", "candidate", "n", "chaseRho", "meanAbsD", "maxAbsD",
        "overallRho", "coreKchg"))
    for scenario in sorted(per_scenario):
        if scenario == base_key:
            continue
        entries = per_scenario[scenario]
        positions = sorted(set(base_entries) & set(entries))
        if len(positions) < 3:
            print("  %-12s %-16s %5d  (too few shared products to compare)"
                  % (scenario, "-", len(positions)))
            continue
        base_block = _score_positions(base_entries, positions)
        block = _score_positions(entries, positions)
        core_changed = sum(1 for a, b in zip(base_block["coreK"], block["coreK"])
                           if a != b)
        labels = [rows[p]["productName"] for p in positions]
        for key in FINALISTS:
            left = [v or 0.0 for v in base_block["scores"][key]]
            right = [v or 0.0 for v in block["scores"][key]]
            deltas = [abs(a - b) for a, b in zip(left, right)]
            base_overall = [control_module.with_chase(
                financial=financial[p], appeal=collector[p], chase=left[i],
                weights=weights) for i, p in enumerate(positions)]
            overall = [control_module.with_chase(
                financial=financial[p], appeal=collector[p], chase=right[i],
                weights=weights) for i, p in enumerate(positions)]
            movement = stats.rank_movement(base_overall, overall, labels=labels)
            print("  %-12s %-16s %5d %9s %9.2f %9.2f %10s %9d" % (
                scenario, key, len(positions),
                _fmt(stats.spearman(left, right), "%.4f"),
                sum(deltas) / len(deltas), max(deltas),
                _fmt(movement["spearman"], "%.4f"), core_changed))


def phase23_shocks(rows, scenarios):
    _scenario_report(
        rows, scenarios, "shock", "PHASE 23 - price shocks",
        "One simulation per set; every shock shares those pack paths, so a "
        "difference here is the shock and nothing else.")


def phase24_temporal(rows, scenarios):
    _scenario_report(
        rows, scenarios, "temporal", baseline=scenarios.get("marketDate"),
        note="13-day, 9-date, SINGLE-REGIME window with card prices frozen at the "
        "build basis. This is NOT long-term or multi-regime validation.",
        title="PHASE 24 - short-window temporal stability within the available "
              "recent regime")


# --------------------------------------------------------------------------
# Phases 27-29 - interpretability, name, finalist tournament
# --------------------------------------------------------------------------

INTERPRETATION = {
    "A_100": ("How often does ONE UNIT of this product contain a chase?",
              "fails: the answer is dominated by how many packs the unit holds, "
              "so the sentence a reader hears is 'bigger boxes are better'"),
    "C_100": ("How many economically meaningful chases does this product actually have?",
              "holds: reads as roster breadth priced at THIS product's cost, and "
              "the movers are products whose Core breadth genuinely differs"),
    "G_50-50": ("How many chases, and how affordably can you reach one?",
                "holds, with a caveat: the two factors correlate at -0.60 so the "
                "sentence has one idea in it, not two"),
    "H_33-33-33": ("How rich and attainable is the hunt for economically "
                   "meaningful hits?",
                   "partly: the accessibility third reintroduces the pack-count "
                   "sentence at one third strength"),
    "I_25-25-25-25": ("As H, plus how much chase value comes back",
                      "fails the third-pillar test: the value quarter is another "
                      "representation of card value, which is the stated reject"),
}


def phase27_interpretability(rows, scores):
    print("\n=== PHASE 27 - interpretability ===")
    print("  Target language:")
    print("    Financial RIP    - How favorable are the complete money outcomes?")
    print("    Collector Appeal - How compelling is the card roster?")
    print("    Chase            - How rich and attainable is the hunt for")
    print("                       economically meaningful hits?")
    print("  A pillar that instead means 'another representation of card value' or")
    print("  'this box is bigger' is rejected.")
    for key in FINALISTS:
        sentence, verdict = INTERPRETATION[key]
        print("\n  %s" % key)
        print("    reads as: %s" % sentence)
        print("    verdict : %s" % verdict)


def phase28_name(chosen):
    print("\n=== PHASE 28 - public name ===")
    print("  Named AFTER the surviving construct is known, not before.")
    options = {
        "Chase Quality": "implies a judgement of how GOOD the chase cards are; the "
                         "surviving construct counts them, it does not rate them",
        "Chase Experience": "implies the felt process of opening - probability, "
                            "pacing, spend. Accurate for a multi-factor pillar; "
                            "overclaims for a count",
        "Chase Opportunity": "how many economically meaningful chances this product "
                             "puts in front of you, at its own price - matches a "
                             "Core-K construct exactly",
        "Chase Profile": "accurate but empty; describes any of the candidates and "
                         "therefore distinguishes none",
        "Chase Appeal": "already taken - `chaseAppeal` is a live desirability x "
                        "scarcity diagnostic in the Collector Appeal payload, so "
                        "this name would collide with a shipped field",
        "Chase RIP": "implies a peer of Financial RIP, a six-component model with "
                     "its own normalization contract. A single saturating count "
                     "is not that",
    }
    for name, note in options.items():
        marker = "->" if name == chosen else "  "
        print("  %s %-20s %s" % (marker, name, note))


def phase29_tournament(rows, scores, results):
    print("\n=== PHASE 29 - finalist tournament ===")
    groups = [r["set"] for r in rows]
    financial = _column(rows, "financialRip")
    collector = _column(rows, "collectorAppeal")
    packs = _column(rows, "randomPackCount")
    box = [i for i, r in enumerate(rows) if r["family"] == "booster_box"]
    pack_family = [i for i, r in enumerate(rows) if r["family"] == "loose_booster_pack"]

    print("  %-16s %8s %8s %9s %9s %9s %9s" % (
        "finalist", "cvR2", "newInfo", "rho(packs)", "boxGap", "10%varSh", "rho vs CTL"))
    for key in FINALISTS:
        column = [v if v is not None else 0.0 for v in scores[key]]
        reconstruction = stats.reconstruct(
            name=key, target=column,
            predictors={"financialRip": financial, "collectorAppeal": collector},
            groups=groups)
        cv = reconstruction["crossValidatedR2"]
        entry = [r for r in results if r["chase"] == key
                 and r["donor"] == "financial" and r["share"] == 0.10]
        gap = (st.median([column[i] for i in box])
               - st.median([column[i] for i in pack_family]))
        print("  %-16s %8s %8s %9s %9.1f %9s %9s" % (
            key, _fmt(cv, "%.3f"), _fmt(None if cv is None else 1 - cv, "%.3f"),
            _fmt(stats.spearman(column, packs)), gap,
            _fmt(entry[0]["chaseVarianceShare"] if entry else None, "%.3f"),
            _fmt(entry[0]["spearman"] if entry else None, "%.4f")))


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VI analysis.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--scenarios", default=str(SCENARIOS))
    parser.add_argument("--phases", default="all")
    args = parser.parse_args(list(argv))

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    rows = payload["rows"]
    print("Stage VI dataset: %s" % payload["stage"])
    print("chase artifact: %s (%s)" % (payload["chaseArtifact"],
                                       payload["chaseResearchVersion"]))
    print("tier contract: %s" % payload["chaseTierContract"])

    phase123_audit(payload, rows)
    phase5_13_normalization(rows)
    phase6_overlap(rows)
    phase7_reconstruction(rows)
    phase8_partials(rows)
    phase9_core_k_vs_collector(rows)
    phase10_pack_confound(rows)
    scores = build_chase_scores(rows)
    phase11_15_candidates(rows, scores)
    results = _extra_phases(payload, rows, scores)
    scenario_path = Path(args.scenarios)
    if scenario_path.exists():
        scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        phase23_shocks(rows, scenarios)
        phase24_temporal(rows, scenarios)
    else:
        print("\n=== PHASES 23-24 - scenarios artifact not built ===")
        print("  run python -m backend.scripts.build_chase_pillar_stage6_scenarios")
    phase27_interpretability(rows, scores)
    phase28_name("Chase Opportunity")
    phase29_tournament(rows, scores, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
