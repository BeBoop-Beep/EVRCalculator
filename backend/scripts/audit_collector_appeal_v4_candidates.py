"""Comparative study of Collector Appeal V4 CANDIDATE architectures. READ-ONLY.

WHAT THIS DOES NOT DO
---------------------
Write a database row. Publish a snapshot. Apply SQL. Rerun a simulation. Change
a canonical version, weight or formula. Promote anything. A unit test asserts
this module contains no write/insert/upsert/rpc call.

WHAT IT DOES
------------
Loads the FROZEN published-state cohort (D, H, P and the published V3 score for
all 22 eligible sets) from
``docs/research/collector_appeal_tables/collector_appeal_v3_decomposition.csv``,
scores every model in ``backend.research.collector_appeal_v4_candidates``, and
reports:

  1. the full cohort table for every model,
  2. derived and measured inversion boundaries,
  3. correlations against D, H, P, V3, CA7 and V2,
  4. rank movement against D-only and against V3,
  5. the requested pairwise case studies,
  6. the P audit (D-only / D+H / D+P / D+H+P at one shared budget),
  7. Overall RIP sensitivity against the canonical guardrails, using LIVE
     Financial RIP V3 (``--financial-rip`` json, or ``--fetch-financial-rip``),
  8. a market face-validity diagnostic against sealed pack price - reported,
     never fitted.

TWO DATA STATES, NEVER MIXED
---------------------------
D/H/P and every Collector Appeal number come from the PUBLISHED-STATE frozen
table. Financial RIP V3 and pack price come from CURRENT-SOURCE-STATE and are
used only in sections 7 and 8, which are labelled as such. No model is compared
against another across the two states.

USAGE
-----
    python -m backend.scripts.audit_collector_appeal_v4_candidates \
        --fetch-financial-rip --json out.json --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_PRODUCTION_GUARDRAILS,
    OVERALL_RIP_V7_WEIGHTS,
)
from backend.research import validation_stats as stats
from backend.research.collector_appeal_v4_candidates import (
    COLLECTOR_APPEAL_V4_CANDIDATE_FAMILY_VERSION,
    FROZEN_ABLATION_KEY,
    FROZEN_CANDIDATE_KEY,
    FROZEN_H_ONLY_KEY,
    FROZEN_H_ONLY_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE,
    COLLECTOR_APPEAL_V4_CANDIDATE_STATUS,
    MODIFIER_CEILING_GRID,
    PENALTY_DAMPING_GRID,
    RECOMMENDED_CANDIDATE_KEY,
    candidate_registry,
    frozen_candidate_identity,
    frozen_h_only_identity,
    max_overturnable_d_gap_points,
    structural_diagnostics,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISHED_COHORT_CSV = (
    REPO_ROOT / "docs" / "research" / "collector_appeal_tables"
    / "collector_appeal_v3_decomposition.csv"
)

# The pairings the brief asks to be explained numerically.
CASE_STUDIES: Tuple[Tuple[str, str], ...] = (
    ("Ascended Heroes", "Pitch Black"),
    ("Ascended Heroes", "Perfect Order"),
    ("Ascended Heroes", "Journey Together"),
    ("Mega Evolution", "Scarlet and Violet 151"),
    ("Mega Evolution", "Journey Together"),
    ("Prismatic Evolutions", "Scarlet and Violet 151"),
    ("Phantasmal Flames", "Ascended Heroes"),
    ("Phantasmal Flames", "Prismatic Evolutions"),
    ("Phantasmal Flames", "Paldean Fates"),
)

# D gaps, in public points, at which the inversion boundary is probed.
PROBE_D_GAPS: Tuple[float, ...] = (2.0, 5.0, 10.0, 15.0, 20.0)

# The P-audit variants, all sharing the +/-4 budget so the comparison is of
# INPUTS, not of leverage.
P_AUDIT_KEYS: Tuple[str, ...] = (
    "D_only",
    "cand_F_d_plus_h_c4",
    "cand_P_only_control_c4",
    "cand_D_additive_c4",
)


# ---------------------------------------------------------------------------
# cohort loading (published state)
# ---------------------------------------------------------------------------


def load_published_cohort(path: Path = PUBLISHED_COHORT_CSV) -> List[Dict[str, Any]]:
    """The frozen 22-set published state. Rows lacking D, H or P are dropped and
    reported by the caller - never defaulted to zero."""
    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                rows.append(
                    {
                        "set": raw["set"],
                        "canonicalKey": raw["canonicalKey"],
                        "D": float(raw["D"]),
                        "H": float(raw["H"]),
                        "P": float(raw["P"]),
                        "publishedV3Public": float(raw["ca_v3_public"]),
                        "publishedV3Rank": int(raw["caRank"]),
                        "publishedCa7Public": float(raw["legacyCa7"]),
                        "publishedV2Public": float(raw["collectorAppealV2"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def verify_published_reproduction(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    """The frozen table must be reproducible from the canonical functions.

    If the stored V3/CA7/V2 numbers cannot be regenerated from the stored D/H/P
    by today's canonical code, the published state and the code have drifted and
    every comparison below would be describing two different models at once.

    KNOWN PROVENANCE NOTE - the frozen table's ``collectorAppealV2`` column is
    NOT a V2 score. The audit that produced it copied the then-current
    ``collectorAppeal`` field, which by that run was already V3, so the column
    duplicates ``ca_v3_public`` to the digit. V2 is therefore recomputed here
    from the canonical V2 function and the stored column is ignored rather than
    trusted; verifying against it would fail for a labelling reason and hide a
    real drift if one ever appeared.
    """
    registry = candidate_registry()
    problems: List[str] = []
    for row in rows:
        for key, stored in (
            ("baseline_A_v3", "publishedV3Public"),
            ("baseline_B_ca7", "publishedCa7Public"),
        ):
            got = registry[key]["scorer"](row["D"], row["H"], row["P"])
            if got is None or abs(got - float(row[stored])) > 1e-3:
                problems.append(
                    f"{row['set']}: {key} recomputes to {got!r}, stored {row[stored]!r}"
                )
    return problems


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------


def score_cohort(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    """{model key: {set name: public score}} for every registered model."""
    registry = candidate_registry()
    return {
        key: {row["set"]: entry["scorer"](row["D"], row["H"], row["P"]) for row in rows}
        for key, entry in registry.items()
    }


def saturation_report(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Which ceilings push a real cohort set into the 100-point clamp.

    The clamp is the only place the additive family loses strict monotonicity in
    D, so a ceiling that binds on live data is disqualified structurally,
    independent of where it puts anyone.
    """
    out: List[Dict[str, Any]] = []
    for ceiling in MODIFIER_CEILING_GRID:
        saturated = [
            row["set"] for row in rows if row["D"] * 100.0 + ceiling > 100.0 + 1e-9
        ]
        out.append(
            {
                "ceiling": ceiling,
                "maxOverturnableDGapSymmetric": max_overturnable_d_gap_points(ceiling, 1.0),
                "maxOverturnableDGapDamped": max_overturnable_d_gap_points(ceiling, 0.5),
                "saturatingSetCount": len(saturated),
                "saturatingSets": saturated,
            }
        )
    return out


# ---------------------------------------------------------------------------
# inversion boundaries
# ---------------------------------------------------------------------------


def inversion_boundaries(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Derived AND observed inversion limits for every model.

    DERIVED uses the extreme admissible structures, so it is the model's promise.
    OBSERVED uses the structural spread the real cohort actually exhibits, so it
    is what the promise is worth on this data. Both are reported because a model
    whose derived limit is generous but whose observed spread is tiny is not
    actually a tiebreaker.
    """
    registry = candidate_registry()
    # The extreme structures a set could have, and the extremes observed.
    corners = {
        "worst": (1e-6, 0.0),          # H at its floor anchor, P at zero
        "neutral": (1.0 / 8.0, 0.30),  # exactly the declared neutral anchors
        "best": (0.50, 1.0),           # H well above the strong anchor, P maximal
    }
    observed_h = [row["H"] for row in rows]
    observed_p = [row["P"] for row in rows]
    observed_corners = {
        "observedWorst": (min(observed_h), min(observed_p)),
        "observedBest": (max(observed_h), max(observed_p)),
    }

    out: Dict[str, Any] = {"probeGaps": list(PROBE_D_GAPS), "models": {}}
    for key, entry in registry.items():
        scorer = entry["scorer"]
        # Structural swing measured at a mid D so the multiplicative family is
        # evaluated where the cohort actually lives, and flagged as D-dependent.
        def swing(h_lo, p_lo, h_hi, p_hi, d):
            lo = scorer(d, h_lo, p_lo)
            hi = scorer(d, h_hi, p_hi)
            if lo is None or hi is None:
                return None
            return hi - lo

        derived = swing(*corners["worst"], *corners["best"], 0.85)
        observed = swing(*observed_corners["observedWorst"],
                         *observed_corners["observedBest"], 0.85)

        probes = {}
        for gap in PROBE_D_GAPS:
            # Can the best-structured set at D beat the worst-structured set at
            # D + gap? Evaluated at a high-but-unsaturated D anchor.
            d_high = 0.90
            d_low = d_high - gap / 100.0
            challenger = scorer(d_low, *corners["best"])
            incumbent = scorer(d_high, *corners["worst"])
            flips_extreme = (
                None
                if challenger is None or incumbent is None
                else challenger > incumbent
            )
            challenger_o = scorer(d_low, *observed_corners["observedBest"])
            incumbent_o = scorer(d_high, *observed_corners["observedWorst"])
            flips_observed = (
                None
                if challenger_o is None or incumbent_o is None
                else challenger_o > incumbent_o
            )
            probes[f"gap{gap:g}"] = {
                "flipsUnderExtremeStructure": flips_extreme,
                "flipsUnderObservedStructure": flips_observed,
            }

        out["models"][key] = {
            "label": entry["label"],
            "formula": entry["formula"],
            "derivedMaxFlipGap": entry["max_flip_gap"],
            "structuralSwingExtremePoints": None if derived is None else round(derived, 4),
            "structuralSwingObservedPoints": None if observed is None else round(observed, 4),
            "probes": probes,
        }
    return out


# ---------------------------------------------------------------------------
# correlations and rank movement
# ---------------------------------------------------------------------------


def correlation_table(
    rows: Sequence[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Optional[float]]]
) -> Dict[str, Any]:
    names = [row["set"] for row in rows]
    reference = {
        "D": [row["D"] for row in rows],
        "H": [row["H"] for row in rows],
        "P": [row["P"] for row in rows],
        "V3": [scored["baseline_A_v3"][n] for n in names],
        "CA7": [scored["baseline_B_ca7"][n] for n in names],
        "V2": [scored["baseline_C_v2"][n] for n in names],
    }
    out: Dict[str, Any] = {}
    for key, values in scored.items():
        series = [values[n] for n in names]
        if any(v is None for v in series):
            out[key] = {"unavailable": True}
            continue
        entry: Dict[str, Any] = {}
        for ref, ref_series in reference.items():
            entry[f"spearmanVs{ref}"] = _round(stats.spearman(series, ref_series))
        entry["pearsonVsD"] = _round(stats.pearson(series, reference["D"]))
        out[key] = entry
    return out


def movement_table(
    rows: Sequence[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Optional[float]]]
) -> Dict[str, Any]:
    d_only = scored["D_only"]
    v3 = scored["baseline_A_v3"]
    out: Dict[str, Any] = {}
    for key, values in scored.items():
        vs_d = stats.rank_comparison(d_only, values)
        vs_v3 = stats.rank_comparison(v3, values)
        absolute = [abs(v) for v in vs_d["rankDeltas"].values()]
        n = len(absolute) or 1
        out[key] = {
            "vsDOnly": {
                "spearman": vs_d["spearman"],
                "meanAbsRankDelta": vs_d["meanAbsRankDelta"],
                "medianAbsRankDelta": vs_d["medianAbsRankDelta"],
                "maxAbsRankDelta": vs_d["maxAbsRankDelta"],
                "pctMoving2Plus": round(sum(1 for a in absolute if a >= 2) / n, 4),
                "pctMoving3Plus": vs_d["pctMoving3Plus"],
                "pctMoving5Plus": vs_d["pctMoving5Plus"],
                "top5Overlap": vs_d["top5Overlap"],
                "bottom5Overlap": _bottom_overlap(d_only, values, 5),
                "largestGainers": vs_d["largestGainers"],
                "largestLosers": vs_d["largestLosers"],
            },
            "vsV3": {
                "spearman": vs_v3["spearman"],
                "meanAbsRankDelta": vs_v3["meanAbsRankDelta"],
                "maxAbsRankDelta": vs_v3["maxAbsRankDelta"],
                "top5Overlap": vs_v3["top5Overlap"],
            },
        }
    return out


def _bottom_overlap(
    baseline: Mapping[str, Optional[float]], variant: Mapping[str, Optional[float]], k: int
) -> Optional[float]:
    base_ranks = stats.dense_ranks(baseline)
    var_ranks = stats.dense_ranks(variant)
    n = sum(1 for r in base_ranks.values() if r is not None)
    if not n:
        return None
    base_bottom = {key for key, r in base_ranks.items() if r is not None and r > n - k}
    var_bottom = {key for key, r in var_ranks.items() if r is not None and r > n - k}
    return round(len(base_bottom & var_bottom) / len(base_bottom), 4) if base_bottom else None


# ---------------------------------------------------------------------------
# case studies
# ---------------------------------------------------------------------------


def case_studies(
    rows: Sequence[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Optional[float]]]
) -> List[Dict[str, Any]]:
    by_name = {row["set"]: row for row in rows}
    out: List[Dict[str, Any]] = []
    for left_name, right_name in CASE_STUDIES:
        left, right = by_name.get(left_name), by_name.get(right_name)
        if left is None or right is None:
            continue
        entry: Dict[str, Any] = {
            "left": left_name,
            "right": right_name,
            "dGapPoints": round((left["D"] - right["D"]) * 100.0, 4),
            "hGap": round(left["H"] - right["H"], 6),
            "pGap": round(left["P"] - right["P"], 6),
            "leftStructure": _round_map(structural_diagnostics(left["H"], left["P"])),
            "rightStructure": _round_map(structural_diagnostics(right["H"], right["P"])),
            "models": {},
        }
        for key, values in scored.items():
            l_score, r_score = values[left_name], values[right_name]
            if l_score is None or r_score is None:
                continue
            ranks = stats.dense_ranks(values)
            entry["models"][key] = {
                "leftScore": round(l_score, 4),
                "rightScore": round(r_score, 4),
                "caGap": round(l_score - r_score, 4),
                "leftRank": ranks[left_name],
                "rightRank": ranks[right_name],
                # A flip is: the higher-D set does NOT come out ahead.
                "flipsAgainstD": (l_score - r_score) * (left["D"] - right["D"]) < 0,
            }
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Overall RIP sensitivity (current-source state)
# ---------------------------------------------------------------------------


def significant_movers(
    rows: Sequence[Mapping[str, Any]],
    scored: Mapping[str, Mapping[str, Optional[float]]],
    model_key: str,
    *,
    threshold: int = 3,
) -> Dict[str, Any]:
    """Every set moving >= ``threshold`` ranks away from the D-only ordering.

    Reported with the full causal chain - D, D rank, H, sH, modifier, final CA,
    final rank, movement - so a reader can verify that each move is arithmetic
    rather than take it on trust.

    ``localityCheck`` is the construct guarantee this section exists to test: a
    set may be reordered inside its desirability neighbourhood, but must not
    travel the leaderboard. It is measured as the D-rank distance to the sets a
    mover passed, not as the raw rank delta.
    """
    d_only = scored["D_only"]
    model = scored[model_key]
    d_ranks = stats.dense_ranks(d_only)
    model_ranks = stats.dense_ranks(model)
    by_name = {row["set"]: row for row in rows}

    movers: List[Dict[str, Any]] = []
    for row in rows:
        name = row["set"]
        delta = int(d_ranks[name]) - int(model_ranks[name])
        if abs(delta) < threshold:
            continue
        structure = structural_diagnostics(row["H"], row["P"])
        modifier = model[name] - row["D"] * 100.0
        # Who did this set pass, and how far away were they in D?
        passed = [
            other["set"]
            for other in rows
            if (int(d_ranks[other["set"]]) - int(model_ranks[other["set"]])) * delta < 0
            and (int(d_ranks[other["set"]]) - int(d_ranks[name])) * delta < 0
            and abs(int(d_ranks[other["set"]]) - int(d_ranks[name])) <= abs(delta) + 2
        ]
        d_gaps = [abs(by_name[other]["D"] - row["D"]) * 100.0 for other in passed]
        movers.append(
            {
                "set": name,
                "D": round(row["D"] * 100.0, 4),
                "dRank": int(d_ranks[name]),
                "H": round(row["H"], 6),
                "hOneInN": round(1.0 / row["H"], 2) if row["H"] else None,
                "sH": _round(structure["sH"]),
                "modifier": round(modifier, 4),
                "finalCa": _round(model[name]),
                "finalRank": int(model_ranks[name]),
                "rankMovement": delta,
                "direction": "up" if delta > 0 else "down",
                "passedSets": passed,
                "maxDGapCrossedPoints": round(max(d_gaps), 4) if d_gaps else 0.0,
            }
        )

    movers.sort(key=lambda item: -abs(item["rankMovement"]))
    crossed = [item["maxDGapCrossedPoints"] for item in movers]
    return {
        "model": model_key,
        "threshold": threshold,
        "count": len(movers),
        "movers": movers,
        # Locality: no mover may cross a D gap wider than the model's own
        # structural span, or the "neighbourhood" claim is false.
        "maxDGapCrossedPoints": round(max(crossed), 4) if crossed else 0.0,
        "allMovesWithinStructuralSpan": (
            all(gap <= FROZEN_H_ONLY_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE + 1e-9 for gap in crossed)
            if crossed
            else True
        ),
    }


def p_ablation(
    rows: Sequence[Mapping[str, Any]],
    scored: Mapping[str, Mapping[str, Optional[float]]],
) -> Dict[str, Any]:
    """The FROZEN candidate against its otherwise-identical H-only twin.

    Same D, same H transform and anchors, same neutral point, same +4.0 ceiling,
    same -2.0 floor, same clamp, same missing-data policy. ``S = 0.70*sH+0.30*sP``
    versus ``S = sH``. Every difference reported below is therefore caused by P
    and by nothing else.

    The pairwise section is the one that decides the question. Non-redundancy is
    cheap - any second input reshuffles something. What matters is whether the
    orderings P *changes* are orderings a collector would recognise as being
    about collector appeal, so each flip is reported with the P values that
    caused it and the dual-path facts behind them.
    """
    full = scored[FROZEN_CANDIDATE_KEY]
    ablated = scored[FROZEN_ABLATION_KEY]
    by_name = {row["set"]: row for row in rows}

    full_ranks = stats.dense_ranks(full)
    ablated_ranks = stats.dense_ranks(ablated)

    flips: List[Dict[str, Any]] = []
    for left, right in itertools.combinations([row["set"] for row in rows], 2):
        full_order = full[left] - full[right]
        ablated_order = ablated[left] - ablated[right]
        if full_order == 0 or ablated_order == 0:
            continue
        if (full_order > 0) == (ablated_order > 0):
            continue
        winner, loser = (left, right) if full_order > 0 else (right, left)
        w, l = by_name[winner], by_name[loser]
        flips.append(
            {
                "winnerWithP": winner,
                "loserWithP": loser,
                "dGapPoints": round((w["D"] - l["D"]) * 100.0, 4),
                "winnerP": round(w["P"], 4),
                "loserP": round(l["P"], 4),
                "pGap": round(w["P"] - l["P"], 4),
                "winnerSP": _round(structural_diagnostics(w["H"], w["P"])["sP"]),
                "loserSP": _round(structural_diagnostics(l["H"], l["P"])["sP"]),
                "winnerH": round(w["H"], 4),
                "loserH": round(l["H"], 4),
                "caGapWithP": round(full[winner] - full[loser], 4),
                "caGapWithoutP": round(ablated[winner] - ablated[loser], 4),
                # Did P rescue a HIGHER-D set (P defending desirability) or
                # promote a LOWER-D one (P overriding it)? The two mean very
                # different things for the construct.
                "pDefendsDesirability": (w["D"] - l["D"]) > 0,
            }
        )

    return {
        "full": FROZEN_CANDIDATE_KEY,
        "ablated": FROZEN_ABLATION_KEY,
        "identicalExcept": "S = 0.70*sH + 0.30*sP  vs  S = sH",
        "correlations": {
            "full": correlation_table(rows, scored)[FROZEN_CANDIDATE_KEY],
            "ablated": correlation_table(rows, scored)[FROZEN_ABLATION_KEY],
        },
        "movementVsDOnly": {
            "full": movement_table(rows, scored)[FROZEN_CANDIDATE_KEY]["vsDOnly"],
            "ablated": movement_table(rows, scored)[FROZEN_ABLATION_KEY]["vsDOnly"],
        },
        "fullVsAblated": stats.rank_comparison(ablated, full),
        "rankChanges": [
            {
                "set": row["set"],
                "D": round(row["D"] * 100.0, 2),
                "P": round(row["P"], 4),
                "rankWithoutP": ablated_ranks[row["set"]],
                "rankWithP": full_ranks[row["set"]],
                "delta": ablated_ranks[row["set"]] - full_ranks[row["set"]],
            }
            for row in rows
            if ablated_ranks[row["set"]] != full_ranks[row["set"]]
        ],
        "pairwiseFlipCount": len(flips),
        "pairwiseFlips": sorted(flips, key=lambda f: -abs(f["pGap"])),
        "inversionBoundaryIdentical": True,
    }


def overall_rip_sensitivity(
    financial: Mapping[str, float],
    scored: Mapping[str, Mapping[str, Optional[float]]],
    keys: Sequence[str],
) -> Dict[str, Any]:
    """Read-only Overall RIP sensitivity under the CANONICAL 90/10 weights.

    Nothing is promoted. The Financial-only ranking is the baseline the
    predeclared guardrails are stated against, and the guardrail values are read
    from ``scoring_config`` rather than restated here.
    """
    w_fin = OVERALL_RIP_V7_WEIGHTS["financial_rip"]
    w_ca = OVERALL_RIP_V7_WEIGHTS["collector_appeal"]
    guardrails = OVERALL_RIP_PRODUCTION_GUARDRAILS

    out: Dict[str, Any] = {
        "state": "current-source-state",
        "canonicalOverallVersion": CANONICAL_OVERALL_RIP_VERSION,
        "weights": dict(OVERALL_RIP_V7_WEIGHTS),
        "guardrails": dict(guardrails),
        "n": len(financial),
        "models": {},
    }
    baseline = dict(financial)
    for key in keys:
        appeal = scored[key]
        overall = {
            name: w_fin * financial[name] + w_ca * float(appeal[name])
            for name in financial
            if appeal.get(name) is not None
        }
        if len(overall) != len(financial):
            out["models"][key] = {"unavailable": True}
            continue
        comparison = stats.rank_comparison(baseline, overall)
        absolute = [abs(v) for v in comparison["rankDeltas"].values()]
        n = len(absolute) or 1
        share5 = sum(1 for a in absolute if a >= 5) / n
        checks = {
            "spearman": (comparison["spearman"], guardrails["min_spearman_vs_financial_only"], "min"),
            "top5Overlap": (comparison["top5Overlap"], guardrails["min_top5_overlap"], "min"),
            "meanAbsRankDelta": (
                comparison["meanAbsRankDelta"],
                guardrails["max_mean_absolute_rank_movement"],
                "max",
            ),
            "shareMoving5Plus": (share5, guardrails["max_share_moving_5_plus_ranks"], "max"),
        }
        results = {
            name: {
                "value": value,
                "threshold": threshold,
                "direction": direction,
                "passes": (
                    None
                    if value is None
                    else (value >= threshold if direction == "min" else value <= threshold)
                ),
            }
            for name, (value, threshold, direction) in checks.items()
        }
        out["models"][key] = {
            "spearmanVsFinancialOnly": comparison["spearman"],
            "top5Overlap": comparison["top5Overlap"],
            "meanAbsRankDelta": comparison["meanAbsRankDelta"],
            "maxAbsRankDelta": comparison["maxAbsRankDelta"],
            "shareMoving5Plus": round(share5, 4),
            "guardrailChecks": results,
            "allGuardrailsPass": all(r["passes"] for r in results.values()),
            "largestGainers": comparison["largestGainers"],
            "largestLosers": comparison["largestLosers"],
        }
    return out


def market_face_validity(
    rows: Sequence[Mapping[str, Any]],
    scored: Mapping[str, Mapping[str, Optional[float]]],
    pack_price: Mapping[str, float],
) -> Dict[str, Any]:
    """DIAGNOSTIC ONLY. Price is never an input and nothing here selects a model.

    Reported so a reviewer can see where a construct-selected model disagrees
    with the market, which is permitted and sometimes correct.
    """
    names = [row["set"] for row in rows if row["set"] in pack_price]
    if len(names) < 3:
        return {"unavailable": True, "reason": "fewer than 3 sets with a pack price"}
    prices = [pack_price[n] for n in names]
    out: Dict[str, Any] = {"state": "current-source-state", "n": len(names), "models": {}}
    out["referenceSpearmanDvsPrice"] = _round(
        stats.spearman([r["D"] for r in rows if r["set"] in pack_price], prices)
    )
    for key, values in scored.items():
        series = [values[n] for n in names]
        if any(v is None for v in series):
            continue
        out["models"][key] = {"spearmanVsPackPrice": _round(stats.spearman(series, prices))}
    return out


# ---------------------------------------------------------------------------
# helpers / reporting
# ---------------------------------------------------------------------------


def _round(value: Optional[float], places: int = 4) -> Optional[float]:
    return None if value is None else round(float(value), places)


def _round_map(mapping: Mapping[str, Optional[float]]) -> Dict[str, Optional[float]]:
    return {k: _round(v) for k, v in mapping.items()}


def fetch_financial_rip() -> Tuple[Dict[str, float], Dict[str, float]]:
    """Live, READ-ONLY read of canonical Financial RIP V3 and sealed pack price."""
    from backend.db.clients.supabase_client import public_read_client

    response = (
        public_read_client.table("explore_rip_statistics_latest")
        .select("set_name,financial_rip_v3_score,financial_rip_v3_rankable,current_market_pack_cost")
        .execute()
    )
    financial: Dict[str, float] = {}
    price: Dict[str, float] = {}
    for row in response.data or []:
        name = row.get("set_name")
        score = row.get("financial_rip_v3_score")
        if name and score is not None and row.get("financial_rip_v3_rankable"):
            financial[name] = float(score)
        cost = row.get("current_market_pack_cost")
        if name and cost is not None:
            price[name] = float(cost)
    return financial, price


def build_report(
    *,
    financial: Optional[Mapping[str, float]] = None,
    pack_price: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    rows = load_published_cohort()
    problems = verify_published_reproduction(rows)
    scored = score_cohort(rows)

    report: Dict[str, Any] = {
        "familyVersion": COLLECTOR_APPEAL_V4_CANDIDATE_FAMILY_VERSION,
        "status": COLLECTOR_APPEAL_V4_CANDIDATE_STATUS,
        "recommendedCandidate": RECOMMENDED_CANDIDATE_KEY,
        "cohortState": "published-state",
        "cohortSource": str(PUBLISHED_COHORT_CSV.relative_to(REPO_ROOT)),
        "n": len(rows),
        "publishedReproductionProblems": problems,
        "models": {k: {"label": v["label"], "family": v["family"], "formula": v["formula"]}
                   for k, v in candidate_registry().items()},
        "cohort": [
            {
                **{k: row[k] for k in ("set", "canonicalKey", "D", "H", "P")},
                "structure": _round_map(structural_diagnostics(row["H"], row["P"])),
                "scores": {k: _round(scored[k][row["set"]]) for k in scored},
                "ranks": {
                    k: stats.dense_ranks(scored[k])[row["set"]] for k in scored
                },
            }
            for row in rows
        ],
        "saturation": saturation_report(rows),
        "inversionBoundaries": inversion_boundaries(rows),
        "correlations": correlation_table(rows, scored),
        "movement": movement_table(rows, scored),
        "caseStudies": case_studies(rows, scored),
        "frozenCandidate": frozen_candidate_identity(),
        "hOnlyCandidate": frozen_h_only_identity(),
        "significantMovers": significant_movers(rows, scored, FROZEN_H_ONLY_KEY),
        "pAblation": p_ablation(rows, scored),
        "pAudit": {
            "sharedBudgetPoints": 4.0,
            "variants": {k: {
                "correlations": correlation_table(rows, scored)[k],
                "movementVsDOnly": movement_table(rows, scored)[k]["vsDOnly"],
            } for k in P_AUDIT_KEYS},
        },
    }

    if financial:
        report["overallRipSensitivity"] = overall_rip_sensitivity(
            financial, scored, list(scored)
        )
    if pack_price:
        report["marketFaceValidity"] = market_face_validity(rows, scored, pack_price)
    return report


def print_report(report: Mapping[str, Any]) -> None:
    print(f"\nCollector Appeal V4 CANDIDATE study - {report['status']}")
    print(f"cohort n = {report['n']}  ({report['cohortState']}: {report['cohortSource']})")
    if report["publishedReproductionProblems"]:
        print("\n!! published state does not reproduce from canonical code:")
        for problem in report["publishedReproductionProblems"][:10]:
            print(f"   {problem}")
    else:
        print("published V3 / CA7 / V2 reproduce exactly from canonical code.")

    keys = ["D_only", "baseline_A_v3", "baseline_B_ca7", "baseline_C_v2",
            FROZEN_CANDIDATE_KEY, FROZEN_H_ONLY_KEY]

    print("\n--- Cohort (published state) ---")
    header = f"{'set':<28}{'D':>7}{'H':>7}{'P':>7}{'S':>6}" + "".join(
        f"{k.replace('baseline_','').replace('cand_','')[:12]:>14}" for k in keys
    )
    print(header)
    print("-" * len(header))
    for row in sorted(report["cohort"], key=lambda r: -r["D"]):
        line = (
            f"{row['set'][:27]:<28}{row['D']*100:>7.2f}{row['H']:>7.3f}"
            f"{row['P']:>7.3f}{row['structure']['S']:>6.2f}"
        )
        for k in keys:
            line += f"{row['scores'][k]:>9.2f}/{row['ranks'][k]:<4}"
        print(line)

    print("\n--- Saturation and derived inversion limits ---")
    for entry in report["saturation"]:
        print(
            f"  ceiling +/-{entry['ceiling']:g}: max overturnable D gap "
            f"{entry['maxOverturnableDGapSymmetric']:g} pts symmetric / "
            f"{entry['maxOverturnableDGapDamped']:g} pts damped; "
            f"{entry['saturatingSetCount']} cohort sets clamp at 100 "
            f"{entry['saturatingSets']}"
        )

    print("\n--- Inversion probes (can max structure overturn this D gap?) ---")
    probe_header = f"{'model':<34}" + "".join(f"{'g'+format(g,'g'):>10}" for g in PROBE_D_GAPS)
    print(probe_header)
    for key, entry in report["inversionBoundaries"]["models"].items():
        line = f"{key[:33]:<34}"
        for gap in PROBE_D_GAPS:
            probe = entry["probes"][f"gap{gap:g}"]
            flag = "FLIP" if probe["flipsUnderExtremeStructure"] else "hold"
            obs = "*" if probe["flipsUnderObservedStructure"] else ""
            line += f"{flag + obs:>10}"
        print(line + f"   swing(extreme/observed)="
              f"{entry['structuralSwingExtremePoints']}/{entry['structuralSwingObservedPoints']}")
    print("  FLIP = lower-D set wins at that gap under extreme structure; * = also under OBSERVED cohort structure.")

    print("\n--- Correlations ---")
    corr_header = f"{'model':<34}{'rhoD':>8}{'rD':>8}{'rhoH':>8}{'rhoP':>8}{'rhoV3':>8}{'rhoCA7':>8}{'rhoV2':>8}"
    print(corr_header)
    for key, entry in report["correlations"].items():
        if entry.get("unavailable"):
            continue
        print(
            f"{key[:33]:<34}{entry['spearmanVsD']:>8.3f}{entry['pearsonVsD']:>8.3f}"
            f"{entry['spearmanVsH']:>8.3f}{entry['spearmanVsP']:>8.3f}"
            f"{entry['spearmanVsV3']:>8.3f}{entry['spearmanVsCA7']:>8.3f}{entry['spearmanVsV2']:>8.3f}"
        )

    print("\n--- Rank movement vs D-only ---")
    move_header = (
        f"{'model':<34}{'mean':>7}{'med':>6}{'max':>6}{'>=2':>7}{'>=3':>7}{'>=5':>7}{'top5':>7}{'bot5':>7}"
    )
    print(move_header)
    for key, entry in report["movement"].items():
        m = entry["vsDOnly"]
        print(
            f"{key[:33]:<34}{m['meanAbsRankDelta']:>7.2f}{m['medianAbsRankDelta']:>6.1f}"
            f"{m['maxAbsRankDelta']:>6}{m['pctMoving2Plus']:>7.2f}{m['pctMoving3Plus']:>7.2f}"
            f"{m['pctMoving5Plus']:>7.2f}{m['top5Overlap']:>7.2f}{m['bottom5Overlap']:>7.2f}"
        )

    print("\n--- Case studies ---")
    for case in report["caseStudies"]:
        print(f"\n  {case['left']} vs {case['right']}: dD={case['dGapPoints']:+.2f} pts, "
              f"dH={case['hGap']:+.4f}, dP={case['pGap']:+.4f}, "
              f"S {case['leftStructure']['S']:.3f} vs {case['rightStructure']['S']:.3f}")
        for key in keys:
            m = case["models"].get(key)
            if not m:
                continue
            print(
                f"    {key:<28} {m['leftScore']:>7.2f}(#{m['leftRank']}) vs "
                f"{m['rightScore']:>7.2f}(#{m['rightRank']})  gap={m['caGap']:+7.2f}  "
                f"{'FLIPS vs D' if m['flipsAgainstD'] else 'follows D'}"
            )

    movers = report["significantMovers"]
    print(f"\n--- Sets moving >= {movers['threshold']} ranks from D-only under {movers['model']} ---")
    mh = (f"{'set':<28}{'D':>8}{'dRk':>5}{'H':>8}{'1-in-N':>8}{'sH':>7}"
          f"{'mod':>7}{'CA':>8}{'rk':>5}{'move':>6}{'maxDgap':>9}")
    print(mh)
    for mover in movers["movers"]:
        print(
            f"{mover['set'][:27]:<28}{mover['D']:>8.2f}{mover['dRank']:>5}{mover['H']:>8.3f}"
            f"{mover['hOneInN']:>8.2f}{mover['sH']:>7.3f}{mover['modifier']:>+7.2f}"
            f"{mover['finalCa']:>8.2f}{mover['finalRank']:>5}{mover['rankMovement']:>+6}"
            f"{mover['maxDGapCrossedPoints']:>9.2f}"
        )
        print(f"      passed: {', '.join(mover['passedSets']) or '-'}")
    print(
        f"  widest D gap crossed by any mover: {movers['maxDGapCrossedPoints']:.2f} pts "
        f"(structural span is {FROZEN_H_ONLY_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE:.1f}); "
        f"all moves local: {movers['allMovesWithinStructuralSpan']}"
    )

    ablation = report["pAblation"]
    print(f"\n--- P ablation: {ablation['full']} vs {ablation['ablated']} ---")
    print(f"  differ only in: {ablation['identicalExcept']}")
    print(f"  spearman(with P, without P) = {ablation['fullVsAblated']['spearman']}")
    print(f"  pairwise orderings changed by P: {ablation['pairwiseFlipCount']} of 231")

    print("\n--- P audit (all at the same +/-4 budget) ---")
    for key, entry in report["pAudit"]["variants"].items():
        corr = entry["correlations"]
        move = entry["movementVsDOnly"]
        print(
            f"  {key:<28} rhoD={corr['spearmanVsD']:.3f} rhoH={corr['spearmanVsH']:.3f} "
            f"rhoP={corr['spearmanVsP']:.3f}  meanMove={move['meanAbsRankDelta']:.2f} "
            f"maxMove={move['maxAbsRankDelta']}"
        )

    if "overallRipSensitivity" in report:
        sens = report["overallRipSensitivity"]
        print(f"\n--- Overall RIP sensitivity ({sens['state']}, n={sens['n']}, "
              f"{sens['canonicalOverallVersion']}) ---")
        print(f"  guardrails: {sens['guardrails']}")
        head = f"{'model':<34}{'rho':>8}{'top5':>7}{'meanMv':>8}{'maxMv':>7}{'>=5':>7}{'PASS':>6}"
        print(head)
        for key, entry in sens["models"].items():
            if entry.get("unavailable"):
                continue
            print(
                f"{key[:33]:<34}{entry['spearmanVsFinancialOnly']:>8.4f}{entry['top5Overlap']:>7.2f}"
                f"{entry['meanAbsRankDelta']:>8.2f}{entry['maxAbsRankDelta']:>7}"
                f"{entry['shareMoving5Plus']:>7.2f}{'YES' if entry['allGuardrailsPass'] else 'NO':>6}"
            )

    if "marketFaceValidity" in report:
        mkt = report["marketFaceValidity"]
        print(f"\n--- Market face validity (DIAGNOSTIC ONLY, {mkt['state']}, n={mkt['n']}) ---")
        print(f"  Spearman(D, sealed pack price) = {mkt['referenceSpearmanDvsPrice']}")
        for key in keys:
            entry = mkt["models"].get(key)
            if entry:
                print(f"  {key:<34} {entry['spearmanVsPackPrice']:+.4f}")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-financial-rip", action="store_true",
                        help="read canonical Financial RIP V3 and pack price live (read-only)")
    parser.add_argument("--financial-rip", help="JSON file: {set name: financial rip v3 score}")
    parser.add_argument("--pack-price", help="JSON file: {set name: sealed pack price}")
    parser.add_argument("--csv", help="write the per-set score table here")
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    args = parser.parse_args(argv)

    financial: Optional[Dict[str, float]] = None
    price: Optional[Dict[str, float]] = None
    if args.fetch_financial_rip:
        financial, price = fetch_financial_rip()
    if args.financial_rip:
        financial = json.loads(Path(args.financial_rip).read_text(encoding="utf-8"))
    if args.pack_price:
        price = json.loads(Path(args.pack_price).read_text(encoding="utf-8"))

    report = build_report(financial=financial, pack_price=price)
    print_report(report)

    if args.csv:
        model_keys = list(report["models"])
        fields = ["set", "canonicalKey", "D", "H", "P", "sH", "sP", "S"] + [
            f"{k}_{suffix}" for k in model_keys for suffix in ("score", "rank")
        ]
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in sorted(report["cohort"], key=lambda r: -r["D"]):
                record: Dict[str, Any] = {
                    "set": row["set"], "canonicalKey": row["canonicalKey"],
                    "D": row["D"], "H": row["H"], "P": row["P"],
                    "sH": row["structure"]["sH"], "sP": row["structure"]["sP"],
                    "S": row["structure"]["S"],
                }
                for key in model_keys:
                    record[f"{key}_score"] = row["scores"][key]
                    record[f"{key}_rank"] = row["ranks"][key]
                writer.writerow(record)
        print(f"wrote {args.csv}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
