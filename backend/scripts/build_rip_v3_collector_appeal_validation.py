"""Validate Financial RIP V3 and the Collector Appeal candidate family. READ-ONLY.

WHAT THIS IS
------------
The reproducible instrument behind
``docs/research/collector_appeal_v2_validation/``. It answers, from one seeded
run and with every input recorded in a manifest:

  * Are the six Financial RIP V3 components measuring six things or fewer?
  * Does H (Desirable Outcome Frequency) carry information D and P do not?
  * Does the revised Collector Appeal collapse back into D, or into Financial
    RIP, or into Chase Appeal?
  * How much does Overall RIP actually move as the appeal weight goes
    0 -> 10 -> 15 -> 20 -> 25%, and how much of that movement survives input
    uncertainty?

WHAT IT WILL NOT DO
-------------------
Write a database row. Publish a snapshot. Apply SQL. Change a canonical version.
Launch a simulation. Choose a winner by correlation.

It reads, computes, and writes files under ``--output-dir``. A test asserts the
module contains no write/insert/upsert/rpc call against a client.

THE V3 READINESS GATE
---------------------
Financial RIP V3 exists only for simulations that ran AFTER migration 060. There
is deliberately no fallback to Financial RIP V2: a V2 number analysed under a V3
label would make every finding in the report describe a model that is not the
one being validated. When V3 data is missing the script reports exactly which
sets are missing it, prints the exact commands to populate it, and - under
``--strict`` - exits nonzero without writing partial analytical artifacts.

USAGE
-----
    python -m backend.scripts.build_rip_v3_collector_appeal_validation
    python -m backend.scripts.build_rip_v3_collector_appeal_validation --strict
    python -m backend.scripts.build_rip_v3_collector_appeal_validation \
        --set-id <id> --set-id <id> --bootstrap-draws 2000 --seed 20260804
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
    COLLECTOR_APPEAL_V2_VERSION,
    DUAL_PATH_DEPTH_VERSION,
)
from backend.desirability.desirable_outcome_frequency import (
    DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION,
    DESIRABLE_OUTCOME_FREQUENCY_VERSION,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V6_WEIGHTS,
)
from backend.research import validation_stats as stats
from backend.research.collector_appeal_candidates import (
    CANDIDATE_KEYS,
    COMPARISON_KEYS,
    OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID,
    PRIMARY_CANDIDATE_KEY,
    candidate_registry,
    compute_all_candidates,
    compute_comparisons,
    compute_overall,
)
from backend.research.validation_uncertainty import scenario_registry

logger = logging.getLogger(__name__)

RESEARCH_VERSION = "rip_v3_collector_appeal_validation_v1"

DEFAULT_OUTPUT_DIR = Path("docs/research/collector_appeal_v2_validation")

# Reported in a dedicated section because they exercise different corners of the
# model. NOTHING is asserted about them and no direction is hardcoded; the
# report prints what the data says, including "moved down".
HIGHLIGHT_SETS = ("Perfect Order", "Journey Together", "Ascended Heroes", "Phantasmal Flames")

# Owner-defined PRODUCT decision rules, not statistical thresholds. Reported
# against, never used to auto-select or auto-reject a model.
STABILITY_GUARDRAILS = {
    "minAdjacentSpearman": 0.95,
    "minTop5Overlap": 0.80,
    "maxMeanAbsRankDelta": 1.5,
    "maxShareMoving5Plus": 0.10,
}
GUARDRAIL_NOTE = (
    "These are owner-defined product decision rules, NOT statistical truths and "
    "NOT significance tests. A model is not selected because it clears them and "
    "not rejected because it misses one. They exist so the report states its "
    "stability expectations in advance rather than rationalising whatever the "
    "data turns out to show."
)

REQUIRED_SIMULATION_COMMANDS = (
    "backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets",
    "backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --set <canonicalKey>",
)


# ---------------------------------------------------------------------------
# Cohort loading
# ---------------------------------------------------------------------------

def load_cohort(
    *, set_ids: Optional[Sequence[str]] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """The published RIP targets, read through the publication path.

    Reads ``get_rip_statistics_targets_payload`` rather than querying tables, so
    the study describes the objects that would actually be published - the same
    Collector Appeal bundle, the same Financial RIP V3 payload, the same ranks -
    instead of a parallel reconstruction that could disagree with production
    while looking authoritative.
    """
    warnings: List[str] = []
    from backend.db.services.explore_rip_statistics_service import (
        get_rip_statistics_targets_payload,
    )

    payload = get_rip_statistics_targets_payload()
    targets = list(payload.get("targets") or [])
    if set_ids:
        wanted = {str(s) for s in set_ids}
        filtered = [t for t in targets if str(t.get("target_id")) in wanted]
        missing = wanted - {str(t.get("target_id")) for t in filtered}
        if missing:
            warnings.append(f"requested set ids not present in cohort: {sorted(missing)}")
        targets = filtered
    return targets, warnings


def build_rows(targets: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten each target into the analysis row this study operates on.

    Every value is READ from the published payload. Nothing is recomputed here
    except the candidate grid itself, which is the object under study.
    """
    rows: List[Dict[str, Any]] = []
    for target in targets:
        opening = target.get("openingExperience") or {}
        appeal = opening.get("collectorAppeal") or {}
        inputs = appeal.get("inputs") or {}
        frequency = opening.get("desirableOutcomeFrequency") or {}
        dual_path = opening.get("dualPathDepth") or {}
        legacy = opening.get("legacyCollectorAppealCA7") or {}
        chase = opening.get("chaseAppeal") or {}
        coverage = opening.get("coverage") or {}

        financial_v3 = target.get("financialRipV3") or {}
        components = financial_v3.get("components") or {}

        d = stats._finite(inputs.get("rosterDesirability"))
        h = stats._finite(frequency.get("rawValue"))
        p = stats._finite(dual_path.get("rawValue"))
        m = stats._finite(chase.get("eliteScarcity"))

        row: Dict[str, Any] = {
            "setId": str(target.get("target_id") or ""),
            "setName": str(target.get("name") or target.get("target_id") or "unknown"),
            "canonicalKey": target.get("canonical_key") or target.get("canonicalKey"),
            # --- Collector Appeal inputs (H is production's F) ---------------
            "d": d,
            "h": h,
            "p": p,
            "m": m,
            # --- shipped scores, on the 0-100 scale --------------------------
            "collectorAppealShipped": stats._finite(appeal.get("score")),
            "legacyCa7": stats._finite(legacy.get("score")),
            "chaseAppeal": stats._finite(chase.get("score")),
            "financialRipV3": stats._finite(financial_v3.get("score")),
            "financialRipV3Status": financial_v3.get("status"),
            # --- coverage ----------------------------------------------------
            "eligibleCardCount": frequency.get("eligibleCardCount"),
            "eligibleSubjectCount": frequency.get("eligibleSubjectCount"),
            "desirableSubjectCount": frequency.get("desirableSubjectCount"),
            "coveredDemandShare": stats._finite(frequency.get("coveredDemandShare")),
            "slotGroupCount": frequency.get("slotGroupCount"),
            "frequencyStatus": frequency.get("status"),
            "pullModelAvailable": coverage.get("pullModelAvailable"),
            "availabilityReasons": "; ".join(
                str(r) for r in (coverage.get("reasons") or [])
            ) or None,
        }

        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
            row[f"v3_{key}"] = stats._finite((components.get(key) or {}).get("score"))

        # Candidates on 0-100 to match every other score in the study. D, H and
        # P are unit-scale; the candidate formula is unit-scale; the *100 is the
        # single conversion, done once, here.
        candidates = compute_all_candidates(d, h, p)
        for key, value in candidates.items():
            row[key] = None if value is None else value * 100.0
        comparisons = compute_comparisons(d=d, p=p, m=m)
        for key, value in comparisons.items():
            row[key] = None if value is None else value * 100.0

        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

def assess_readiness(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Which sets can support which half of the analysis, and what is missing.

    Financial readiness and appeal readiness are reported SEPARATELY because
    they fail for different reasons and are fixed by different commands. A set
    can have a complete Collector Appeal and no Financial RIP V3 (the current
    state of the whole cohort), and collapsing the two into one "ready" flag
    would send someone to rebuild desirability when the missing thing is a
    simulation run.
    """
    ready_v3, missing_v3 = [], []
    ready_appeal, missing_appeal = [], []
    for row in rows:
        label = row["setName"]
        (ready_v3 if row.get("financialRipV3") is not None else missing_v3).append(label)
        appeal_ok = all(row.get(k) is not None for k in ("d", "h", "p"))
        (ready_appeal if appeal_ok else missing_appeal).append(label)

    both = [
        row["setName"]
        for row in rows
        if row.get("financialRipV3") is not None
        and all(row.get(k) is not None for k in ("d", "h", "p"))
    ]
    return {
        "cohortSize": len(rows),
        "financialV3Ready": sorted(ready_v3),
        "financialV3Missing": sorted(missing_v3),
        "collectorAppealReady": sorted(ready_appeal),
        "collectorAppealMissing": sorted(missing_appeal),
        "fullyReady": sorted(both),
        "fullyReadyCount": len(both),
        "canRunEmpiricalAnalysis": len(both) >= 3,
        "missingReasons": {
            row["setName"]: row.get("availabilityReasons") or row.get("frequencyStatus")
            for row in rows
            if row.get("collectorAppealShipped") is None
        },
        "requiredSimulationCommands": list(REQUIRED_SIMULATION_COMMANDS),
        "noFallbackPolicy": (
            "Financial RIP V3 is never substituted with Financial RIP V2. A V2 "
            "score analysed under a V3 label would make every result describe a "
            "model other than the one under validation."
        ),
    }


# ---------------------------------------------------------------------------
# 9. Redundancy audits
# ---------------------------------------------------------------------------

def redundancy_matrix(
    rows: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    *,
    bootstrap_draws: int,
    seed: int,
    flag_threshold: float = 0.85,
) -> Dict[str, Any]:
    """Pairwise Spearman/Pearson with bootstrap CI, permutation p and BH q.

    Pairs at or above ``flag_threshold`` are FLAGGED, never removed. Two
    components can be highly correlated across a 22-set cohort and still earn
    their place: one may guard a failure mode the other misses, or be the more
    interpretable of the two. Automatic removal on a correlation would delete
    that judgement and record the deletion as a finding.
    """
    pairs: List[Dict[str, Any]] = []
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            xs, ys = stats.paired(rows, left, right)
            boot = stats.bootstrap_correlation_ci(
                xs, ys, draws=bootstrap_draws, seed=seed, method="spearman"
            )
            perm = stats.permutation_p_value(
                xs, ys, draws=bootstrap_draws, seed=seed + 1, method="spearman"
            )
            rho = stats.spearman(xs, ys)
            pairs.append(
                {
                    "a": left,
                    "b": right,
                    "n": len(xs),
                    "spearman": round(rho, 6) if rho is not None else None,
                    "pearson": (
                        round(stats.pearson(xs, ys), 6)
                        if stats.pearson(xs, ys) is not None
                        else None
                    ),
                    "ciLow": boot.get("ciLow"),
                    "ciHigh": boot.get("ciHigh"),
                    "permutationP": perm.get("pValue"),
                    "redundancyFlag": bool(rho is not None and abs(rho) >= flag_threshold),
                    "smallSample": boot.get("smallSample"),
                }
            )

    adjusted = stats.benjamini_hochberg([p["permutationP"] for p in pairs])
    for pair, q in zip(pairs, adjusted):
        pair["bhAdjustedP"] = q

    return {
        "keys": list(keys),
        "flagThreshold": flag_threshold,
        "pairs": pairs,
        "flaggedPairs": [f"{p['a']} ~ {p['b']}" for p in pairs if p["redundancyFlag"]],
        "note": (
            "Exploratory matrix. BH-adjusted p-values control the false discovery "
            "rate across THIS matrix only. A flagged pair is a finding to "
            "investigate, never an instruction to drop a component."
        ),
    }


# ---------------------------------------------------------------------------
# 10. Leave-one-component-out
# ---------------------------------------------------------------------------

def leave_one_component_out(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Both leave-one-out views for each of the six V3 components.

    The two answer genuinely different questions and are NOT alternatives:

      A. CONTRIBUTION REMOVAL - drop the component's weighted contribution and
         do not renormalize. "How much of the existing score does this component
         directly supply?" Scores fall by construction; the informative output
         is the RANK change, which isolates whether the component discriminates
         between sets or merely lifts them all.

      B. DROP AND RENORMALIZE - remove it and rescale the other five to sum to
         1. "How much does the ordering depend on this component relative to the
         others?" This is the fair ranking comparison; method A's ranking is
         confounded with the uniform level shift.

    Reporting only one would mislead: a component can supply a large share of
    the score (A) while barely affecting the ordering (B), which is precisely
    the profile of a component that is a level term rather than a discriminator.
    """
    usable = [
        row
        for row in rows
        if all(row.get(f"v3_{k}") is not None for k in FINANCIAL_RIP_V3_COMPONENT_ORDER)
    ]
    if len(usable) < 3:
        return {
            "available": False,
            "reason": "fewer than 3 sets carry all six Financial RIP V3 components",
            "n": len(usable),
        }

    def full_score(row: Mapping[str, Any]) -> float:
        return sum(
            row[f"v3_{k}"] * FINANCIAL_RIP_V3_WEIGHTS[k]
            for k in FINANCIAL_RIP_V3_COMPONENT_ORDER
        )

    baseline = {row["setId"]: full_score(row) for row in usable}
    results: Dict[str, Any] = {"available": True, "n": len(usable), "components": {}}

    for dropped in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        removal = {
            row["setId"]: full_score(row) - row[f"v3_{dropped}"] * FINANCIAL_RIP_V3_WEIGHTS[dropped]
            for row in usable
        }
        remaining = {
            k: w for k, w in FINANCIAL_RIP_V3_WEIGHTS.items() if k != dropped
        }
        total = sum(remaining.values())
        renormalized = {
            row["setId"]: sum(
                row[f"v3_{k}"] * (w / total) for k, w in remaining.items()
            )
            for row in usable
        }
        results["components"][dropped] = {
            "weight": FINANCIAL_RIP_V3_WEIGHTS[dropped],
            "contributionRemoval": stats.rank_comparison(baseline, removal),
            "dropAndRenormalize": stats.rank_comparison(baseline, renormalized),
        }

    results["note"] = (
        "A component causing little rank movement is NOT thereby unnecessary. It "
        "may guard a specific failure mode that this cohort does not contain, or "
        "carry interpretive weight the score needs even when it rarely changes "
        "an ordering."
    )
    return results


# ---------------------------------------------------------------------------
# 11 + 12. Overall weight sensitivity and variance decomposition
# ---------------------------------------------------------------------------

def overall_weight_sensitivity(
    rows: Sequence[Mapping[str, Any]], appeal_key: str
) -> Dict[str, Any]:
    """Overall RIP across the pre-registered weight grid for ONE appeal candidate.

    Reports each weight against the financial-only baseline AND against its
    adjacent weight. The adjacent comparison is what answers "are 15% and 20%
    practically distinguishable?"; a comparison against the baseline alone
    cannot, because both differ from the baseline in the same direction.
    """
    usable = [
        row
        for row in rows
        if row.get("financialRipV3") is not None and row.get(appeal_key) is not None
    ]
    if len(usable) < 3:
        return {
            "available": False,
            "appealKey": appeal_key,
            "reason": "fewer than 3 sets carry both Financial RIP V3 and this candidate",
            "n": len(usable),
        }

    financial = {row["setId"]: row["financialRipV3"] for row in usable}
    by_weight: Dict[float, Dict[str, Optional[float]]] = {}
    for weight in OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID:
        by_weight[weight] = {
            row["setId"]: compute_overall(row["financialRipV3"], row[appeal_key], weight)
            for row in usable
        }

    names = {row["setId"]: row["setName"] for row in usable}
    weights_payload: Dict[str, Any] = {}
    previous: Optional[float] = None
    for weight in OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID:
        scores = by_weight[weight]
        vs_financial = stats.rank_comparison(financial, scores)
        vs_adjacent = (
            stats.rank_comparison(by_weight[previous], scores) if previous is not None else None
        )
        decomposition = stats.variance_decomposition(
            [row["financialRipV3"] for row in usable],
            [row[appeal_key] for row in usable],
            weight,
        )
        guardrails = None
        if vs_adjacent is not None:
            guardrails = {
                "adjacentWeight": previous,
                "spearmanOk": _at_least(vs_adjacent["spearman"], STABILITY_GUARDRAILS["minAdjacentSpearman"]),
                "top5OverlapOk": _at_least(vs_adjacent.get("top5Overlap"), STABILITY_GUARDRAILS["minTop5Overlap"]),
                "meanRankMovementOk": _at_most(vs_adjacent["meanAbsRankDelta"], STABILITY_GUARDRAILS["maxMeanAbsRankDelta"]),
                "share5PlusOk": _at_most(vs_adjacent.get("pctMoving5Plus"), STABILITY_GUARDRAILS["maxShareMoving5Plus"]),
            }

        weights_payload[f"{weight:.2f}"] = {
            "weight": weight,
            "scores": {names[k]: v for k, v in scores.items()},
            "ranks": {
                names[k]: v for k, v in stats.dense_ranks(scores).items()
            },
            "vsFinancialOnly": vs_financial,
            "vsAdjacentWeight": vs_adjacent,
            "varianceDecomposition": decomposition,
            "guardrails": guardrails,
            "highlightSets": {
                row["setName"]: {
                    "overall": scores.get(row["setId"]),
                    "rank": stats.dense_ranks(scores).get(row["setId"]),
                }
                for row in usable
                if row["setName"] in HIGHLIGHT_SETS
            },
        }
        previous = weight

    return {
        "available": True,
        "appealKey": appeal_key,
        "n": len(usable),
        "weightGrid": list(OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID),
        "weights": weights_payload,
        "guardrailNote": GUARDRAIL_NOTE,
        "highlightNote": (
            "Highlight sets are reported, never asserted. No direction of "
            "movement is expected or preferred for any of them."
        ),
    }


def _at_least(value: Optional[float], threshold: float) -> Optional[bool]:
    return None if value is None else bool(value >= threshold)


def _at_most(value: Optional[float], threshold: float) -> Optional[bool]:
    return None if value is None else bool(value <= threshold)


# ---------------------------------------------------------------------------
# 15. Market relationships
# ---------------------------------------------------------------------------

MARKET_DISCLOSURE = (
    "Price is an external validation OUTCOME, never the definition of Collector "
    "Appeal and never an input to candidate selection. Read these with four "
    "cautions: (1) a high price correlation may indicate demand, scarcity, or "
    "both, and cannot separate them; (2) accessibility legitimately REDUCES "
    "price correlation while increasing collector friendliness, because "
    "accessibility mechanically reduces scarcity and scarcity is priced; (3) an "
    "appeal metric is not invalid because it correlates less with price - "
    "Collector Appeal measures general opening appeal, not resale value; (4) "
    "Chase Appeal (D x M) remains the price/scarcity-facing diagnostic and is "
    "the metric that SHOULD track price."
)


def market_relationships(
    rows: Sequence[Mapping[str, Any]],
    predictors: Sequence[str],
    outcomes: Sequence[str],
    *,
    bootstrap_draws: int,
    seed: int,
) -> Dict[str, Any]:
    """Spearman + CI + permutation p + leave-one-set-out for each predictor/outcome.

    BH correction is applied ACROSS THE WHOLE MATRIX, because that is the family
    of tests actually performed. Correcting within a row would understate the
    multiplicity of an exploratory grid this size.
    """
    entries: List[Dict[str, Any]] = []
    labels = [row["setName"] for row in rows]
    for predictor in predictors:
        for outcome in outcomes:
            xs, ys = stats.paired(rows, predictor, outcome)
            if len(xs) < 3:
                entries.append(
                    {"predictor": predictor, "outcome": outcome, "n": len(xs), "spearman": None}
                )
                continue
            boot = stats.bootstrap_correlation_ci(
                xs, ys, draws=bootstrap_draws, seed=seed, method="spearman"
            )
            perm = stats.permutation_p_value(
                xs, ys, draws=bootstrap_draws, seed=seed + 2, method="spearman"
            )
            paired_labels = [
                row["setName"]
                for row in rows
                if stats._finite(row.get(predictor)) is not None
                and stats._finite(row.get(outcome)) is not None
            ]
            loso = stats.leave_one_out_correlation(xs, ys, paired_labels)
            entries.append(
                {
                    "predictor": predictor,
                    "outcome": outcome,
                    "n": len(xs),
                    "spearman": boot.get("estimate"),
                    "ciLow": boot.get("ciLow"),
                    "ciHigh": boot.get("ciHigh"),
                    "permutationP": perm.get("pValue"),
                    "losoMin": loso.get("min"),
                    "losoMax": loso.get("max"),
                    "signFlips": loso.get("signFlips"),
                    "mostInfluentialSet": loso.get("mostInfluential"),
                    "smallSample": boot.get("smallSample"),
                }
            )

    adjusted = stats.benjamini_hochberg([e.get("permutationP") for e in entries])
    for entry, q in zip(entries, adjusted):
        entry["bhAdjustedP"] = q

    return {"entries": entries, "disclosure": MARKET_DISCLOSURE}


# ---------------------------------------------------------------------------
# Manifest and artifacts
# ---------------------------------------------------------------------------

def _git(*args: str) -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", *args], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:  # noqa: BLE001 - a missing git must not fail the study
        return None


def build_manifest(
    *,
    args: argparse.Namespace,
    rows: Sequence[Mapping[str, Any]],
    readiness: Mapping[str, Any],
    warnings: Sequence[str],
) -> Dict[str, Any]:
    """Everything needed to reproduce this run exactly.

    A result that cannot be traced to its inputs is an anecdote. This records
    the commit, the cohort, the seeds, the draw counts, every formula version
    and the literal command line.
    """
    return {
        "researchVersion": RESEARCH_VERSION,
        "gitCommit": _git("rev-parse", "HEAD"),
        "gitBranch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "gitWorkingTreeClean": _git("status", "--porcelain") == "",
        "runTimestampUtc": datetime.now(timezone.utc).isoformat(),
        "marketDate": args.market_date,
        "cliInvocation": " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        "cohort": {
            "definition": (
                "Targets published by explore_rip_statistics_service - the "
                "simulated, RIP-eligible cohort."
            ),
            "requestedSetIds": list(args.set_id or []),
            "allSupported": bool(args.all_supported),
            "includedSets": [row["setName"] for row in rows],
            "excludedSets": readiness.get("collectorAppealMissing"),
            "size": len(rows),
        },
        "seeds": {
            "master": args.seed,
            "bootstrap": args.seed,
            "permutation": args.seed + 1,
            "market": args.seed + 2,
            "uncertainty": args.seed + 3,
        },
        "draws": {
            "bootstrap": args.bootstrap_draws,
            "uncertainty": args.uncertainty_draws,
        },
        "formulaVersions": {
            "financialRipV3": FINANCIAL_RIP_V3_VERSION,
            "financialRipV3Normalization": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
            "collectorAppealShipped": COLLECTOR_APPEAL_V2_VERSION,
            "collectorAppealFormula": COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
            "legacyCa7": COLLECTOR_APPEAL_CA7_VERSION,
            "desirableOutcomeFrequency": DESIRABLE_OUTCOME_FREQUENCY_VERSION,
            "desirableOutcomeFrequencyCoveragePolicy": (
                DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION
            ),
            "dualPathDepth": DUAL_PATH_DEPTH_VERSION,
            "canonicalOverallRip": CANONICAL_OVERALL_RIP_VERSION,
            "canonicalOverallRipWeights": dict(OVERALL_RIP_V6_WEIGHTS),
        },
        "candidateRegistry": candidate_registry(),
        "uncertaintyScenarios": scenario_registry(),
        "stabilityGuardrails": {**STABILITY_GUARDRAILS, "note": GUARDRAIL_NOTE},
        "readiness": readiness,
        "warnings": list(warnings),
        "writePolicy": (
            "READ-ONLY. This run wrote no database row, published no snapshot, "
            "applied no SQL, launched no simulation and changed no canonical "
            "version."
        ),
    }


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in columns})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_analysis(
    rows: Sequence[Mapping[str, Any]], args: argparse.Namespace
) -> Dict[str, Any]:
    """Every statistical section, on whatever the cohort can actually support.

    Each section decides for itself whether it has enough data and says so.
    A section that cannot run returns ``available: False`` with a reason rather
    than an empty result that reads like a null finding.
    """
    financial_keys = [f"v3_{k}" for k in FINANCIAL_RIP_V3_COMPONENT_ORDER]
    collector_keys = [
        "d", "h", "p",
        "CA6_dual_path_utility",
        "CA7_legacy_bounded_bonus_50",
        "chase_appeal_D_times_M",
        *CANDIDATE_KEYS,
        "financialRipV3",
    ]

    analysis: Dict[str, Any] = {
        "financialRedundancy": redundancy_matrix(
            rows, financial_keys, bootstrap_draws=args.bootstrap_draws, seed=args.seed
        ),
        "collectorRedundancy": redundancy_matrix(
            rows, collector_keys, bootstrap_draws=args.bootstrap_draws, seed=args.seed
        ),
        "leaveOneComponentOut": leave_one_component_out(rows),
        "overallWeightSensitivity": {
            key: overall_weight_sensitivity(rows, key)
            for key in (PRIMARY_CANDIDATE_KEY, "CA7_legacy_bounded_bonus_50")
        },
    }

    # The core research questions, answered directly from the matrix so the
    # summary cannot drift from the numbers behind it.
    analysis["coreQuestions"] = _answer_core_questions(rows, analysis)
    return analysis


def _answer_core_questions(
    rows: Sequence[Mapping[str, Any]], analysis: Mapping[str, Any]
) -> Dict[str, Any]:
    """Section 9's six questions, each with the statistic that answers it."""

    def rho(a: str, b: str) -> Optional[float]:
        xs, ys = stats.paired(rows, a, b)
        value = stats.spearman(xs, ys)
        return round(value, 6) if value is not None else None

    primary = PRIMARY_CANDIDATE_KEY
    return {
        "doesHAddInformationBeyondD": {
            "spearmanHvsD": rho("h", "d"),
            "interpretation": "|rho| near 1 would mean H restates D.",
        },
        "doesHAddInformationBeyondP": {
            "spearmanHvsP": rho("h", "p"),
            "interpretation": "|rho| near 1 would mean the 0.60/0.40 blend measures one axis twice.",
        },
        "doesCandidateCollapseIntoD": {
            "spearmanCandidateVsD": rho(primary, "d"),
            "interpretation": "|rho| near 1 would mean the structural term changes nothing.",
        },
        "isCandidateAFinancialProxy": {
            "spearmanCandidateVsFinancialRipV3": rho(primary, "financialRipV3"),
            "interpretation": "A high value would mean the appeal pillar re-weights a financial signal.",
        },
        "isCandidateAChaseProxy": {
            "spearmanCandidateVsChaseAppeal": rho(primary, "chase_appeal_D_times_M"),
            "interpretation": "A high value would mean the candidate is a scarcity/price proxy.",
        },
        "doesCandidateAddVariance": {
            "spearmanCandidateVsLegacyCa7": rho(primary, "CA7_legacy_bounded_bonus_50"),
            "interpretation": "rho near 1 would mean the revision reorders nothing versus CA7.",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None, help="Price snapshot date (YYYY-MM-DD).")
    parser.add_argument("--set-id", action="append", default=None, help="Repeatable set id filter.")
    parser.add_argument("--all-supported", action="store_true", help="Use the full supported cohort.")
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    parser.add_argument("--uncertainty-draws", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when any cohort set lacks Financial RIP V3 data.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Run the analysis on whatever subset is ready, labelling it partial.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        targets, warnings = load_cohort(set_ids=args.set_id)
    except Exception as exc:  # noqa: BLE001 - a read failure is reported, never masked
        print(f"FAILED to load the RIP targets payload: {exc}", file=sys.stderr)
        return 2

    rows = build_rows(targets)
    readiness = assess_readiness(rows)
    manifest = build_manifest(args=args, rows=rows, readiness=readiness, warnings=warnings)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "manifest.json", manifest)
    write_csv(
        output_dir / "cohort.csv",
        rows,
        [
            "setId", "setName", "canonicalKey", "d", "h", "p", "m",
            "collectorAppealShipped", "legacyCa7", "chaseAppeal", "financialRipV3",
            "financialRipV3Status", *[f"v3_{k}" for k in FINANCIAL_RIP_V3_COMPONENT_ORDER],
            *CANDIDATE_KEYS, *COMPARISON_KEYS,
            "eligibleCardCount", "eligibleSubjectCount", "desirableSubjectCount",
            "coveredDemandShare", "slotGroupCount", "frequencyStatus",
            "pullModelAvailable", "availabilityReasons",
        ],
    )

    _print_readiness(readiness)

    missing_v3 = readiness["financialV3Missing"]
    if missing_v3 and not args.allow_partial:
        _print_rerun_instructions(missing_v3, rows)
        write_json(
            output_dir / "validation_results.json",
            {
                "status": "blocked_missing_financial_rip_v3",
                "manifest": manifest,
                "readiness": readiness,
                "analysis": None,
            },
        )
        print(
            f"\nWrote manifest.json and cohort.csv to {output_dir}. "
            "No analytical artifact was written: the empirical sections require "
            "Financial RIP V3 data."
        )
        if args.strict:
            print("\n--strict: exiting nonzero because Financial RIP V3 data is missing.")
            return 1
        return 0

    analysis = run_analysis(rows, args)
    write_json(
        output_dir / "validation_results.json",
        {
            "status": "partial" if missing_v3 else "complete",
            "manifest": manifest,
            "readiness": readiness,
            "analysis": analysis,
        },
    )
    _write_analysis_csvs(output_dir, analysis)
    print(f"\nWrote validation artifacts to {output_dir}")
    return 0


def _write_analysis_csvs(output_dir: Path, analysis: Mapping[str, Any]) -> None:
    """Machine-readable projections of the JSON, one file per research question."""
    for name, key in (
        ("pairwise_correlations.csv", "collectorRedundancy"),
        ("financial_component_correlations.csv", "financialRedundancy"),
    ):
        section = analysis.get(key) or {}
        write_csv(
            output_dir / name,
            section.get("pairs") or [],
            ["a", "b", "n", "spearman", "pearson", "ciLow", "ciHigh",
             "permutationP", "bhAdjustedP", "redundancyFlag", "smallSample"],
        )

    loo = analysis.get("leaveOneComponentOut") or {}
    loo_rows: List[Dict[str, Any]] = []
    for component, payload in (loo.get("components") or {}).items():
        for method in ("contributionRemoval", "dropAndRenormalize"):
            block = payload.get(method) or {}
            loo_rows.append(
                {
                    "component": component,
                    "weight": payload.get("weight"),
                    "method": method,
                    "spearman": block.get("spearman"),
                    "kendallTauB": block.get("kendallTauB"),
                    "meanAbsRankDelta": block.get("meanAbsRankDelta"),
                    "medianAbsRankDelta": block.get("medianAbsRankDelta"),
                    "maxAbsRankDelta": block.get("maxAbsRankDelta"),
                    "meanAbsScoreDelta": block.get("meanAbsScoreDelta"),
                    "top5Overlap": block.get("top5Overlap"),
                    "top10Overlap": block.get("top10Overlap"),
                    "pctMoving1Plus": block.get("pctMoving1Plus"),
                    "pctMoving3Plus": block.get("pctMoving3Plus"),
                    "pctMoving5Plus": block.get("pctMoving5Plus"),
                }
            )
    write_csv(
        output_dir / "financial_leave_one_out.csv",
        loo_rows,
        ["component", "weight", "method", "spearman", "kendallTauB",
         "meanAbsRankDelta", "medianAbsRankDelta", "maxAbsRankDelta",
         "meanAbsScoreDelta", "top5Overlap", "top10Overlap",
         "pctMoving1Plus", "pctMoving3Plus", "pctMoving5Plus"],
    )

    weight_rows: List[Dict[str, Any]] = []
    for candidate, payload in (analysis.get("overallWeightSensitivity") or {}).items():
        if not payload.get("available"):
            continue
        for label, block in (payload.get("weights") or {}).items():
            vs_financial = block.get("vsFinancialOnly") or {}
            adjacent = block.get("vsAdjacentWeight") or {}
            decomposition = block.get("varianceDecomposition") or {}
            weight_rows.append(
                {
                    "candidate": candidate,
                    "weight": block.get("weight"),
                    "spearmanVsFinancialOnly": vs_financial.get("spearman"),
                    "kendallVsFinancialOnly": vs_financial.get("kendallTauB"),
                    "meanAbsRankDelta": vs_financial.get("meanAbsRankDelta"),
                    "maxAbsRankDelta": vs_financial.get("maxAbsRankDelta"),
                    "top3Overlap": vs_financial.get("top3Overlap"),
                    "top5Overlap": vs_financial.get("top5Overlap"),
                    "top10Overlap": vs_financial.get("top10Overlap"),
                    "pctMoving3Plus": vs_financial.get("pctMoving3Plus"),
                    "pctMoving5Plus": vs_financial.get("pctMoving5Plus"),
                    "spearmanVsAdjacent": adjacent.get("spearman"),
                    "varFinancialTerm": decomposition.get("termFinancial"),
                    "varAppealTerm": decomposition.get("termAppeal"),
                    "varCrossTerm": decomposition.get("termCross"),
                    "dispersionShareAppeal": decomposition.get("dispersionShareAppeal"),
                    "appealContributionMean": decomposition.get("appealContributionMean"),
                    "correlationFinancialAppeal": decomposition.get("correlation"),
                }
            )
    write_csv(
        output_dir / "overall_weight_sensitivity.csv",
        weight_rows,
        ["candidate", "weight", "spearmanVsFinancialOnly", "kendallVsFinancialOnly",
         "meanAbsRankDelta", "maxAbsRankDelta", "top3Overlap", "top5Overlap",
         "top10Overlap", "pctMoving3Plus", "pctMoving5Plus", "spearmanVsAdjacent",
         "varFinancialTerm", "varAppealTerm", "varCrossTerm",
         "dispersionShareAppeal", "appealContributionMean",
         "correlationFinancialAppeal"],
    )


def _print_readiness(readiness: Mapping[str, Any]) -> None:
    print("=" * 100)
    print("DATA READINESS")
    print("=" * 100)
    print(f"Cohort size                     : {readiness['cohortSize']}")
    print(f"Financial RIP V3 ready          : {len(readiness['financialV3Ready'])}")
    print(f"Financial RIP V3 MISSING        : {len(readiness['financialV3Missing'])}")
    print(f"Collector Appeal inputs ready   : {len(readiness['collectorAppealReady'])}")
    print(f"Fully ready (both)              : {readiness['fullyReadyCount']}")
    if readiness["collectorAppealMissing"]:
        print("\nSets missing Collector Appeal inputs:")
        for name in readiness["collectorAppealMissing"]:
            reason = (readiness.get("missingReasons") or {}).get(name) or "unspecified"
            print(f"  - {name}: {reason}")


def _print_rerun_instructions(
    missing: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    keys = [
        row.get("canonicalKey")
        for row in rows
        if row["setName"] in set(missing) and row.get("canonicalKey")
    ]
    print()
    print("=" * 100)
    print("BLOCKED: Financial RIP V3 data is missing")
    print("=" * 100)
    print(
        "Financial RIP V3 is computed from the simulated per-pack outcome vector\n"
        "and is only persisted by simulation runs that happened AFTER migration\n"
        "060 was applied. It CANNOT be backfilled from stored percentiles: the\n"
        "Realistic and Jackpot Upside components need conditional means over exact\n"
        "empirical rank buckets, and no arithmetic over P50/P95/P99 recovers them.\n"
    )
    print(f"Sets missing Financial RIP V3 ({len(missing)}):")
    for name in missing:
        print(f"  - {name}")
    print("\nRun ONE of the following to populate it (each writes to")
    print("simulation_derived_metrics and is a production job - run deliberately):\n")
    print("  # whole cohort")
    print(f"  {REQUIRED_SIMULATION_COMMANDS[0]}\n")
    print("  # a single set")
    for key in sorted(set(k for k in keys if k))[:5]:
        print(f"  backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --set {key}")
    print("\n  # preview which sets would run, writing nothing")
    print("  backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --dry-run")
    print(
        "\nThis script did NOT launch any of them. Re-run this validation after the\n"
        "simulations complete."
    )


if __name__ == "__main__":
    raise SystemExit(main())
