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
    COLLECTOR_APPEAL_V3_FORMULA_VERSION,
    COLLECTOR_APPEAL_V3_VERSION,
    DUAL_PATH_DEPTH_VERSION,
)
from backend.desirability.desirable_outcome_frequency import (
    DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION,
    DESIRABLE_OUTCOME_FREQUENCY_VERSION,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_PRODUCTION_GUARDRAILS,
    OVERALL_RIP_V7_WEIGHTS,
)
from backend.research import validation_stats as stats
from backend.research.collector_appeal_candidates import (
    CANDIDATE_KEYS,
    CANONICAL_PRODUCTION_KEY,
    COMPARISON_KEYS,
    LEGACY_CA7_KEY,
    OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID,
    PRIMARY_CANDIDATE_KEY,
    PURE_D_KEY,
    SUPERSEDED_V2_KEY,
    candidate_registry,
    canonical_overall_weight,
    collector_appeal_v3_contributions,
    collector_appeal_v3_weight,
    compute_all_candidates,
    compute_comparisons,
    compute_overall,
    compute_v3_without_input,
)
from backend.research.validation_uncertainty import scenario_registry

logger = logging.getLogger(__name__)

RESEARCH_VERSION = "rip_v3_collector_appeal_validation_v1"

# The output directory is CALLER-SUPPLIED and must be private. The default sits
# under `private_artifacts/`, which `.gitignore` excludes, so an artifact set
# containing per-set scores and full rank tables cannot reach the repository by
# forgetting a flag.
#
# There is deliberately no default under `docs/research/`. That path is tracked,
# and the previous default wrote there - so every run produced committable
# artifacts by default and the "keep validation output private" rule depended on
# whoever ran it remembering a flag.
DEFAULT_OUTPUT_DIR = Path("private_artifacts/collector_appeal_v3_validation")

# Directory prefixes considered private. A caller may point `--output-dir`
# anywhere outside the repository (an absolute path on a local disk); what is
# refused is a path INSIDE the repository that git would track.
PRIVATE_OUTPUT_PREFIXES = ("private_artifacts",)

# Reported in a dedicated section because they exercise different corners of the
# model. NOTHING is asserted about them and no direction is hardcoded; the
# report prints what the data says, including "moved down".
HIGHLIGHT_SETS = ("Perfect Order", "Journey Together", "Ascended Heroes", "Phantasmal Flames")

# Owner-defined PRODUCT decision rules, not statistical thresholds. Reported
# against, never used to auto-select or auto-reject a model.
#
# READ from `scoring_config.OVERALL_RIP_PRODUCTION_GUARDRAILS`, not restated. A
# guardrail that lives in a script is a guardrail a script can weaken; keeping
# the numbers in reviewed config is what makes "do not silently weaken the
# guardrail" enforceable rather than aspirational.
STABILITY_GUARDRAILS = {
    "minAdjacentSpearman": OVERALL_RIP_PRODUCTION_GUARDRAILS["min_spearman_vs_financial_only"],
    "minTop5Overlap": OVERALL_RIP_PRODUCTION_GUARDRAILS["min_top5_overlap"],
    "maxMeanAbsRankDelta": OVERALL_RIP_PRODUCTION_GUARDRAILS["max_mean_absolute_rank_movement"],
    "maxShareMoving5Plus": OVERALL_RIP_PRODUCTION_GUARDRAILS["max_share_moving_5_plus_ranks"],
}
GUARDRAIL_NOTE = (
    "These are owner-defined product decision rules, NOT statistical truths and "
    "NOT significance tests. A model is not selected because it clears them and "
    "not rejected because it misses one. They exist so the report states its "
    "stability expectations in advance rather than rationalising whatever the "
    "data turns out to show."
)
BASELINE_GUARDRAIL_NOTE = (
    "The PRODUCTION guardrails are evaluated against the FINANCIAL-ONLY ranking, "
    "not against the adjacent weight. Adjacent-weight comparisons answer 'are "
    "13% and 14% distinguishable?', which is a different question and a much "
    "easier bar: every adjacent pair looks stable while the cumulative movement "
    "away from the financial ranking grows without any single step failing."
)

REQUIRED_SIMULATION_COMMANDS = (
    "backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets",
    "backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --set <canonicalKey>",
)


# ---------------------------------------------------------------------------
# Cohort loading
# ---------------------------------------------------------------------------

def resolve_supported_set_keys() -> Tuple[str, ...]:
    """The canonical keys explicitly supported for opening simulation.

    Delegates to ``opening_simulation_gate.supported_opening_set_keys()``, which
    that module documents as THE single definition of "simulation-supported" -
    shared by the metadata sync, the migration/backfill generator, the
    publication gate and the publication audit. It resolves over the FULL set
    registry using ``pokemon_set_lifecycle_flags.supports_opening_simulation``,
    whose order is: explicit ``SUPPORTS_OPENING_SIMULATION`` declaration, else
    ``USE_MONTE_CARLO_V2``, else false, with ``catalog_only`` always false.

    Deliberately NOT reimplemented here, and deliberately NOT a list of set names
    in this file. A second definition of "supported" is how a set silently
    becomes invisible to one caller and visible to another.
    """
    from backend.db.services.opening_simulation_gate import supported_opening_set_keys

    return supported_opening_set_keys()


def _target_key(target: Mapping[str, Any]) -> str:
    return str(target.get("canonical_key") or target.get("canonicalKey") or "")


def load_cohort(
    *,
    set_ids: Optional[Sequence[str]] = None,
    all_supported: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """The published RIP targets, read through the publication path.

    Reads ``get_rip_statistics_targets_payload`` rather than querying tables, so
    the study describes the objects that would actually be published - the same
    Collector Appeal bundle, the same Financial RIP V3 payload, the same ranks -
    instead of a parallel reconstruction that could disagree with production
    while looking authoritative.

    ``all_supported`` restricts the cohort to sets EXPLICITLY supported for
    opening simulation.

    SUPPORT IS DECLARED, NEVER INFERRED FROM DATA
    ---------------------------------------------
    Filtering is keyed on the declared support marker alone. It is emphatically
    NOT ``financialRipV3 is not None``: that would define the cohort as "sets
    that happen to have a score", so a supported set whose simulation genuinely
    failed would be silently dropped from the study instead of failing the
    readiness gate. The gate's entire purpose is to catch that case, and an
    availability-based filter would delete the evidence it exists.

    Returns ``(targets, warnings, support_record)``. The support record carries
    every excluded set with its status and reason, so the manifest can state what
    was left out rather than only what was kept.
    """
    warnings: List[str] = []
    from backend.db.services.explore_rip_statistics_service import (
        get_rip_statistics_targets_payload,
    )

    payload = get_rip_statistics_targets_payload()
    targets = list(payload.get("targets") or [])
    total_targets = len(targets)

    support_record: Dict[str, Any] = {
        "mode": "all_supported" if all_supported else ("set_ids" if set_ids else "all_targets"),
        "supportSource": (
            "backend.db.services.opening_simulation_gate.supported_opening_set_keys()"
        ),
        "supportCriterion": (
            "pokemon_set_lifecycle_flags.supports_opening_simulation: explicit "
            "SUPPORTS_OPENING_SIMULATION declaration, else USE_MONTE_CARLO_V2, "
            "else false; catalog_only is always false."
        ),
        "publishedTargetCount": total_targets,
        "excludedSets": [],
        "supportedKeysMissingFromTargets": [],
    }

    if all_supported:
        supported = set(resolve_supported_set_keys())
        support_record["supportedKeyCount"] = len(supported)

        kept: List[Dict[str, Any]] = []
        for target in targets:
            key = _target_key(target)
            if key in supported:
                kept.append(target)
                continue
            support_record["excludedSets"].append(
                {
                    "setName": target.get("name"),
                    "canonicalKey": key or None,
                    "targetId": str(target.get("target_id") or "") or None,
                    "supportsOpeningSimulation": False,
                    "reason": (
                        "not declared as supported for opening simulation "
                        "(no usable pull model), so no Financial RIP V3 is expected"
                    ),
                }
            )

        # A supported set absent from the published targets is a real defect and
        # must surface, not vanish because the intersection happened to be empty
        # for it. Recorded here and reported as missing by the readiness gate.
        present = {_target_key(t) for t in kept}
        for key in sorted(supported - present):
            support_record["supportedKeysMissingFromTargets"].append(key)
            warnings.append(
                f"set '{key}' is declared simulation-supported but is absent from "
                "the published RIP targets payload"
            )

        targets = kept

    if set_ids:
        wanted = {str(s) for s in set_ids}
        filtered = [t for t in targets if str(t.get("target_id")) in wanted]
        missing = wanted - {str(t.get("target_id")) for t in filtered}
        if missing:
            warnings.append(f"requested set ids not present in cohort: {sorted(missing)}")
        targets = filtered

    support_record["includedSetCount"] = len(targets)
    support_record["excludedSetCount"] = len(support_record["excludedSets"])
    return targets, warnings, support_record


def build_rows(targets: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten each target into the analysis row this study operates on.

    Every value is READ from the published payload. Nothing is recomputed here
    except the candidate grid itself, which is the object under study.
    """
    rows: List[Dict[str, Any]] = []
    for target in targets:
        opening = target.get("openingExperience") or {}
        appeal = opening.get("collectorAppeal") or {}
        # `factors` is the V3 shape; `inputs` is the superseded V2 shape. Both
        # are read so a payload built before the cutover still yields a D rather
        # than silently dropping every set out of the analysis.
        factors = appeal.get("factors") or appeal.get("inputs") or {}
        frequency = opening.get("desirableOutcomeFrequency") or {}
        dual_path = opening.get("dualPathDepth") or {}
        legacy = opening.get("legacyCollectorAppealCA7") or {}
        legacy_v2 = opening.get("legacyCollectorAppealV2") or {}
        chase = opening.get("chaseAppeal") or {}
        coverage = opening.get("coverage") or {}

        financial_v3 = target.get("financialRipV3") or {}
        components = financial_v3.get("components") or {}

        d = stats._finite(factors.get("rosterDesirability"))
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
            "collectorAppealShippedVersion": appeal.get("version"),
            "legacyCollectorAppealV2Published": stats._finite(legacy_v2.get("score")),
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
        comparisons = compute_comparisons(d=d, p=p, h=h, m=m)
        for key, value in comparisons.items():
            row[key] = None if value is None else value * 100.0

        # The two Collector Appeal V3 ablation families, both on 0-100. Computed
        # here, once, so every influence section reads the same numbers.
        for study_key in ("d", "h", "p"):
            row[f"v3_drop_{study_key}_raw"] = _scale(
                compute_v3_without_input(d, h, p, dropped=study_key, renormalize=False)
            )
            row[f"v3_drop_{study_key}_renorm"] = _scale(
                compute_v3_without_input(d, h, p, dropped=study_key, renormalize=True)
            )
        for study_key, contribution in collector_appeal_v3_contributions(d, h, p).items():
            row[f"v3_contribution_{study_key}"] = _scale(contribution)

        rows.append(row)
    return rows


def _scale(unit_value: Optional[float]) -> Optional[float]:
    """Unit scale -> 0-100. The single conversion, done once, in one place."""
    return None if unit_value is None else float(unit_value) * 100.0


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

    Reports each weight against the FINANCIAL-ONLY baseline and, separately,
    against its adjacent weight. Both, and never only the second: the adjacent
    comparison answers "are 13% and 14% practically distinguishable?", which is
    a much easier bar than "how far has the leaderboard moved from its financial
    ranking?" - every adjacent step can look stable while the cumulative
    movement grows past every guardrail.

    The PRODUCTION guardrails are therefore evaluated against the baseline. The
    adjacent-weight guardrail block is retained beside them, explicitly labelled,
    as a distinguishability diagnostic.
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

    canonical_weight = canonical_overall_weight()
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
        adjacent_guardrails = None
        if vs_adjacent is not None:
            adjacent_guardrails = {
                "adjacentWeight": previous,
                "isProductionGate": False,
                "note": (
                    "Distinguishability diagnostic only. The production gate is "
                    "`productionGuardrails`, which is measured against the "
                    "financial-only ranking."
                ),
                "spearmanOk": _at_least(vs_adjacent["spearman"], STABILITY_GUARDRAILS["minAdjacentSpearman"]),
                "top5OverlapOk": _at_least(vs_adjacent.get("top5Overlap"), STABILITY_GUARDRAILS["minTop5Overlap"]),
                "meanRankMovementOk": _at_most(vs_adjacent["meanAbsRankDelta"], STABILITY_GUARDRAILS["maxMeanAbsRankDelta"]),
                "share5PlusOk": _at_most(vs_adjacent.get("pctMoving5Plus"), STABILITY_GUARDRAILS["maxShareMoving5Plus"]),
            }

        weights_payload[f"{weight:.2f}"] = {
            "weight": weight,
            "isCanonicalProductionWeight": abs(weight - canonical_weight) < 1e-12,
            "scores": {names[k]: v for k, v in scores.items()},
            "ranks": {
                names[k]: v for k, v in stats.dense_ranks(scores).items()
            },
            "vsFinancialOnly": vs_financial,
            "vsAdjacentWeight": vs_adjacent,
            "varianceDecomposition": decomposition,
            # THE GATE. Measured against Financial-only, per the predeclared
            # production guardrails.
            "productionGuardrails": _evaluate_production_guardrails(vs_financial),
            "guardrails": adjacent_guardrails,
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

    canonical_cell = weights_payload.get(f"{canonical_weight:.2f}") or {}
    canonical_gate = canonical_cell.get("productionGuardrails") or {}
    return {
        "available": True,
        "appealKey": appeal_key,
        "isCanonicalAppealFormula": appeal_key == CANONICAL_PRODUCTION_KEY,
        "n": len(usable),
        "weightGrid": list(OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID),
        "canonicalProductionWeight": canonical_weight,
        "weights": weights_payload,
        # The single verdict a reviewer needs: does the SHIPPING configuration
        # pass the predeclared gate? Surfaced at the top level so it cannot be
        # missed among the sensitivity cells, and computed from the same numbers
        # the cells report.
        "canonicalConfigurationVerdict": {
            "appealKey": appeal_key,
            "weight": canonical_weight,
            "passed": canonical_gate.get("passed"),
            "failedChecks": canonical_gate.get("failedChecks"),
            "measured": canonical_gate.get("measured"),
            "policy": (
                "If the canonical configuration fails any guardrail the correct "
                "response is to leave the prior canonical configuration intact and "
                "report the failing metric. Weakening a guardrail or re-tuning "
                "weights to engineer a pass would make this a fitting exercise "
                "rather than a gate."
            ),
        },
        "guardrailNote": GUARDRAIL_NOTE,
        "baselineGuardrailNote": BASELINE_GUARDRAIL_NOTE,
        "highlightNote": (
            "Highlight sets are reported, never asserted. No direction of "
            "movement is expected or preferred for any of them."
        ),
    }


def _evaluate_production_guardrails(vs_financial: Mapping[str, Any]) -> Dict[str, Any]:
    """The four predeclared production guardrails, versus the financial-only rank.

    ``passed`` is None - not False - when a guardrail cannot be measured. An
    unmeasurable guardrail is missing evidence, and reporting missing evidence as
    a failure is as wrong as reporting it as a pass.
    """
    checks = {
        "spearmanOk": _at_least(
            vs_financial.get("spearman"), STABILITY_GUARDRAILS["minAdjacentSpearman"]
        ),
        "top5OverlapOk": _at_least(
            vs_financial.get("top5Overlap"), STABILITY_GUARDRAILS["minTop5Overlap"]
        ),
        "meanRankMovementOk": _at_most(
            vs_financial.get("meanAbsRankDelta"), STABILITY_GUARDRAILS["maxMeanAbsRankDelta"]
        ),
        "share5PlusOk": _at_most(
            vs_financial.get("pctMoving5Plus"), STABILITY_GUARDRAILS["maxShareMoving5Plus"]
        ),
    }
    unmeasured = [name for name, value in checks.items() if value is None]
    failed = [name for name, value in checks.items() if value is False]
    return {
        "isProductionGate": True,
        "comparedAgainst": "financial_only",
        "thresholds": dict(STABILITY_GUARDRAILS),
        "measured": {
            "spearman": vs_financial.get("spearman"),
            "kendallTauB": vs_financial.get("kendallTauB"),
            "top3Overlap": vs_financial.get("top3Overlap"),
            "top5Overlap": vs_financial.get("top5Overlap"),
            "top10Overlap": vs_financial.get("top10Overlap"),
            "meanAbsRankDelta": vs_financial.get("meanAbsRankDelta"),
            "medianAbsRankDelta": vs_financial.get("medianAbsRankDelta"),
            "maxAbsRankDelta": vs_financial.get("maxAbsRankDelta"),
            "pctMoving1Plus": vs_financial.get("pctMoving1Plus"),
            "pctMoving3Plus": vs_financial.get("pctMoving3Plus"),
            "pctMoving5Plus": vs_financial.get("pctMoving5Plus"),
        },
        **checks,
        "failedChecks": failed,
        "unmeasuredChecks": unmeasured,
        "passed": None if unmeasured else not failed,
    }


def _at_least(value: Optional[float], threshold: float) -> Optional[bool]:
    return None if value is None else bool(value >= threshold)


def _at_most(value: Optional[float], threshold: float) -> Optional[bool]:
    return None if value is None else bool(value <= threshold)


# ---------------------------------------------------------------------------
# Collector Appeal V3 input influence: what D, H and P ACTUALLY do
# ---------------------------------------------------------------------------

INFLUENCE_NOTE = (
    "Nominal coefficients (0.40 / 0.35 / 0.25) describe the FORMULA. Effective "
    "influence describes the COHORT, and the two routinely disagree: an input "
    "with a large coefficient and almost no spread across 22 sets moves nothing, "
    "while an input with a smaller coefficient and a wide spread can dominate "
    "the ordering. No claim of 'comparable effective influence' is made from the "
    "coefficients here; every number below is measured."
)


def collector_appeal_input_influence(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Six independent readings of how much D, H and P each move Collector Appeal.

    They are reported together because each one is answerable and misleading on
    its own:

      1. contribution removal WITHOUT renormalization - how much of the score
         this input supplies. Ranks only; the score leaves the 0-100 scale.
      2. drop-and-renormalize - the counterfactual metric built without this
         input, still on 0-100 and still comparable set to set.
      3. mean absolute score contribution - the size of the term in points.
      4. mean and maximum rank movement under (1) and (2).
      5. variance/covariance contribution - how much of the score's variance the
         term accounts for, INCLUDING its covariance with the others, which is
         where a "small" input can turn out to be carrying the ordering.
      6. share of Collector Appeal dispersion associated with each input.
    """
    usable = [
        row for row in rows if all(row.get(key) is not None for key in ("d", "h", "p"))
    ]
    if len(usable) < 3:
        return {
            "available": False,
            "reason": "fewer than 3 sets carry all three of D, H and P",
            "n": len(usable),
            "note": INFLUENCE_NOTE,
        }

    baseline = {row["setId"]: row[CANONICAL_PRODUCTION_KEY] for row in usable}
    baseline_values = [row[CANONICAL_PRODUCTION_KEY] for row in usable]
    baseline_variance = stats._population_variance(
        [value for value in baseline_values if value is not None]
    )

    per_input: Dict[str, Any] = {}
    for study_key in ("d", "h", "p"):
        weight = collector_appeal_v3_weight(study_key)
        raw_scores = {row["setId"]: row[f"v3_drop_{study_key}_raw"] for row in usable}
        renorm_scores = {row["setId"]: row[f"v3_drop_{study_key}_renorm"] for row in usable}
        contributions = [
            row[f"v3_contribution_{study_key}"]
            for row in usable
            if row.get(f"v3_contribution_{study_key}") is not None
        ]
        input_values = [row[study_key] for row in usable]
        term_values = [value * weight * 100.0 for value in input_values]

        removal = stats.rank_comparison(baseline, raw_scores)
        renormalized = stats.rank_comparison(baseline, renorm_scores)

        # Variance/covariance: Var(w*X) + 2*Cov(w*X, rest). The covariance term
        # is what stops this being a restatement of the weight - two inputs that
        # move together share credit, and the split shows it.
        rest_values = [
            (baseline_values[index] or 0.0) - term_values[index]
            for index in range(len(usable))
        ]
        own_variance = stats._population_variance(term_values)
        cross_covariance = stats._population_covariance(term_values, rest_values)
        variance_share = (
            (own_variance + cross_covariance) / baseline_variance
            if baseline_variance > 0
            else None
        )

        # Dispersion (mean absolute deviation of the weighted term) rather than
        # variance alone: variance squares the outliers, so a single extreme set
        # can make an input look decisive when it is not.
        term_mean = sum(term_values) / len(term_values)
        dispersion = sum(abs(value - term_mean) for value in term_values) / len(term_values)

        per_input[study_key] = {
            "nominalWeight": weight,
            "inputSpread": {
                "min": min(input_values),
                "max": max(input_values),
                "range": max(input_values) - min(input_values),
                "populationVariance": round(stats._population_variance(input_values), 8),
            },
            # (1) + (4)
            "removalWithoutRenormalization": {
                "spearmanVsFull": removal.get("spearman"),
                "kendallTauBVsFull": removal.get("kendallTauB"),
                "meanAbsRankDelta": removal.get("meanAbsRankDelta"),
                "maxAbsRankDelta": removal.get("maxAbsRankDelta"),
                "pctMoving1Plus": removal.get("pctMoving1Plus"),
                "pctMoving3Plus": removal.get("pctMoving3Plus"),
                "top5Overlap": removal.get("top5Overlap"),
                "note": (
                    "Scores are off the 0-100 scale by construction (the surviving "
                    "weights sum to less than 1). Only the RANKS are interpretable."
                ),
            },
            # (2) + (4)
            "dropAndRenormalize": {
                "spearmanVsFull": renormalized.get("spearman"),
                "kendallTauBVsFull": renormalized.get("kendallTauB"),
                "meanAbsRankDelta": renormalized.get("meanAbsRankDelta"),
                "maxAbsRankDelta": renormalized.get("maxAbsRankDelta"),
                "meanAbsScoreDelta": renormalized.get("meanAbsScoreDelta"),
                "pctMoving1Plus": renormalized.get("pctMoving1Plus"),
                "pctMoving3Plus": renormalized.get("pctMoving3Plus"),
                "top5Overlap": renormalized.get("top5Overlap"),
            },
            # (3)
            "meanAbsoluteScoreContribution": (
                round(sum(abs(value) for value in contributions) / len(contributions), 6)
                if contributions
                else None
            ),
            # (5)
            "varianceContribution": {
                "ownVariance": round(own_variance, 8),
                "covarianceWithOtherTerms": round(cross_covariance, 8),
                "shareOfScoreVariance": (
                    round(variance_share, 6) if variance_share is not None else None
                ),
                "note": (
                    "Own variance plus covariance with the remaining terms, over the "
                    "score's total variance. The three shares sum to 1 by "
                    "construction; a NEGATIVE share means the term moves against the "
                    "rest of the score and damps its spread."
                ),
            },
            # (6)
            "dispersion": {
                "meanAbsoluteDeviationOfTerm": round(dispersion, 6),
            },
        }

    total_dispersion = sum(
        entry["dispersion"]["meanAbsoluteDeviationOfTerm"] for entry in per_input.values()
    )
    for entry in per_input.values():
        entry["dispersion"]["shareOfAppealDispersion"] = (
            round(entry["dispersion"]["meanAbsoluteDeviationOfTerm"] / total_dispersion, 6)
            if total_dispersion > 0
            else None
        )

    return {
        "available": True,
        "n": len(usable),
        "appealKey": CANONICAL_PRODUCTION_KEY,
        "collectorAppealVersion": COLLECTOR_APPEAL_V3_VERSION,
        "byInput": per_input,
        "note": INFLUENCE_NOTE,
        "methodsReported": [
            "contribution_removal_without_renormalization",
            "drop_and_renormalize",
            "mean_absolute_score_contribution",
            "mean_and_max_rank_movement",
            "variance_covariance_contribution",
            "share_of_appeal_dispersion",
        ],
    }


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
    support_record: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Everything needed to reproduce this run exactly.

    A result that cannot be traced to its inputs is an anecdote. This records
    the commit, the cohort, the seeds, the draw counts, every formula version
    and the literal command line.

    ``support_record`` makes the EXCLUSIONS auditable. A cohort statement that
    lists only what was included cannot be checked: a reader cannot tell a
    deliberately unsupported set from one that was dropped by accident. Every
    excluded set is therefore named with its support status and reason.
    """
    support = dict(support_record or {})
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
                "Sets explicitly supported for opening simulation, intersected "
                "with the targets published by explore_rip_statistics_service."
                if args.all_supported
                else "Targets published by explore_rip_statistics_service - the "
                "simulated, RIP-eligible cohort."
            ),
            "requestedSetIds": list(args.set_id or []),
            "allSupported": bool(args.all_supported),
            "supportSource": support.get("supportSource"),
            "supportCriterion": support.get("supportCriterion"),
            "publishedTargetCount": support.get("publishedTargetCount"),
            "supportedKeyCount": support.get("supportedKeyCount"),
            "includedSets": [row["setName"] for row in rows],
            "size": len(rows),
            # Named, with a status and a reason each - not a bare count.
            "excludedSets": support.get("excludedSets", []),
            "excludedSetCount": support.get("excludedSetCount", 0),
            "supportedKeysMissingFromTargets": support.get(
                "supportedKeysMissingFromTargets", []
            ),
            # Kept distinct from support-based exclusion: a set can be IN the
            # cohort and still lack Collector Appeal inputs, which is a data gap
            # rather than a scope decision.
            "inCohortMissingCollectorAppealInputs": readiness.get("collectorAppealMissing"),
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
            "collectorAppealShipped": COLLECTOR_APPEAL_V3_VERSION,
            "collectorAppealShippedFormulaVersion": COLLECTOR_APPEAL_V3_FORMULA_VERSION,
            "supersededCollectorAppealV2": COLLECTOR_APPEAL_V2_VERSION,
            "supersededCollectorAppealV2Formula": COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
            "legacyCa7": COLLECTOR_APPEAL_CA7_VERSION,
            "desirableOutcomeFrequency": DESIRABLE_OUTCOME_FREQUENCY_VERSION,
            "desirableOutcomeFrequencyCoveragePolicy": (
                DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION
            ),
            "dualPathDepth": DUAL_PATH_DEPTH_VERSION,
            "canonicalOverallRip": CANONICAL_OVERALL_RIP_VERSION,
            "canonicalOverallRipWeights": dict(OVERALL_RIP_V7_WEIGHTS),
            # The V3 weights are deliberately NOT recorded here. This manifest is
            # written to a caller-supplied directory that may be shared, and the
            # weights are internal to the model - see public_rip_contract_v7's
            # header. The version identifier is sufficient to reproduce a run,
            # because the version and the weights move together.
            "collectorAppealWeightsDisclosed": False,
        },
        "candidateRegistry": candidate_registry(),
        "uncertaintyScenarios": scenario_registry(),
        "stabilityGuardrails": {
            **STABILITY_GUARDRAILS,
            "note": GUARDRAIL_NOTE,
            "baselineNote": BASELINE_GUARDRAIL_NOTE,
            "source": "backend.desirability.scoring_config.OVERALL_RIP_PRODUCTION_GUARDRAILS",
        },
        "readiness": readiness,
        "warnings": list(warnings),
        "writePolicy": (
            "READ-ONLY. This run wrote no database row, published no snapshot, "
            "applied no SQL, launched no simulation and changed no canonical "
            "version."
        ),
    }


def assert_private_output_dir(output_dir: Path) -> None:
    """Refuse to write analytical artifacts into a tracked repository path.

    The artifacts contain per-set scores, full rank tables and every candidate
    formula's output. Writing them somewhere git tracks turns "keep validation
    output private" into a rule enforced by whoever remembers a flag.

    A path OUTSIDE the repository is allowed without restriction: pointing at a
    local scratch disk is a legitimate caller choice, and this function's job is
    to stop an accidental commit, not to dictate where a researcher keeps files.
    """
    repo_root = Path(__file__).resolve().parents[2]
    resolved = Path(output_dir).expanduser().resolve()
    try:
        relative = resolved.relative_to(repo_root)
    except ValueError:
        return  # outside the repository: nothing git could track
    head = relative.parts[0] if relative.parts else ""
    if head not in PRIVATE_OUTPUT_PREFIXES:
        raise SystemExit(
            f"Refusing to write validation artifacts to {relative.as_posix()!r}: paths "
            f"inside the repository must live under one of {PRIVATE_OUTPUT_PREFIXES} "
            "(git-ignored). Pass --output-dir with a private or out-of-repo path."
        )


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
    # Every formula the brief requires the study to compare: pure D, legacy CA7,
    # the superseded V2 bounded-headroom formula, the canonical V3 balanced
    # formula, and Financial RIP V3.
    collector_keys = [
        "d", "h", "p",
        PURE_D_KEY,
        "CA6_dual_path_utility",
        LEGACY_CA7_KEY,
        SUPERSEDED_V2_KEY,
        CANONICAL_PRODUCTION_KEY,
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
        # The canonical formula FIRST, then the formulas it replaced. Each one
        # gets the full weight grid so a reviewer can see whether a guardrail
        # outcome is a property of the weight or of the appeal formula.
        "overallWeightSensitivity": {
            key: overall_weight_sensitivity(rows, key)
            for key in (
                CANONICAL_PRODUCTION_KEY,
                SUPERSEDED_V2_KEY,
                LEGACY_CA7_KEY,
                PURE_D_KEY,
                PRIMARY_CANDIDATE_KEY,
            )
        },
        "collectorAppealInputInfluence": collector_appeal_input_influence(rows),
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

    canonical = CANONICAL_PRODUCTION_KEY
    return {
        "doesHAddInformationBeyondD": {
            "spearmanHvsD": rho("h", "d"),
            "interpretation": "|rho| near 1 would mean H restates D.",
        },
        "doesHAddInformationBeyondP": {
            "spearmanHvsP": rho("h", "p"),
            "interpretation": "|rho| near 1 would mean H and P measure one axis twice.",
        },
        "doesCanonicalCollapseIntoD": {
            "spearmanCanonicalVsD": rho(canonical, "d"),
            "spearmanSupersededV2VsD": rho(SUPERSEDED_V2_KEY, "d"),
            "interpretation": (
                "|rho| near 1 would mean the structural terms change nothing. The V2 "
                "figure is reported beside it because collapsing into D at ~0.99 is "
                "the finding that motivated the balanced formula; the comparison is "
                "the point, not the absolute value."
            ),
        },
        "isCanonicalAFinancialProxy": {
            "spearmanCanonicalVsFinancialRipV3": rho(canonical, "financialRipV3"),
            "interpretation": "A high value would mean the appeal pillar re-weights a financial signal.",
        },
        "isCanonicalAChaseProxy": {
            "spearmanCanonicalVsChaseAppeal": rho(canonical, "chase_appeal_D_times_M"),
            "interpretation": "A high value would mean the formula is a scarcity/price proxy.",
        },
        "doesCanonicalReorderVersusItsPredecessors": {
            "spearmanCanonicalVsLegacyCa7": rho(canonical, LEGACY_CA7_KEY),
            "spearmanCanonicalVsSupersededV2": rho(canonical, SUPERSEDED_V2_KEY),
            "spearmanSupersededV2VsLegacyCa7": rho(SUPERSEDED_V2_KEY, LEGACY_CA7_KEY),
            "interpretation": (
                "rho near 1 would mean the revision reorders nothing. The "
                "V2-vs-CA7 figure is the baseline it has to beat."
            ),
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None, help="Price snapshot date (YYYY-MM-DD).")
    parser.add_argument("--set-id", action="append", default=None, help="Repeatable set id filter.")
    parser.add_argument(
        "--all-supported",
        action="store_true",
        help=(
            "Restrict the cohort to sets explicitly supported for opening "
            "simulation, per opening_simulation_gate.supported_opening_set_keys()."
        ),
    )
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    parser.add_argument("--uncertainty-draws", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Where to write the artifacts. Must be outside the repository or under "
            f"{'/'.join(PRIVATE_OUTPUT_PREFIXES)}/ (git-ignored). Defaults to "
            f"{DEFAULT_OUTPUT_DIR.as_posix()}."
        ),
    )
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

    # Mutually exclusive: one names a cohort by policy, the other by hand. Silently
    # intersecting them would let `--all-supported` appear to have been honoured
    # while an explicit id list did the real filtering - and a cohort that is not
    # what the flag says it is invalidates every readiness count derived from it.
    if args.all_supported and args.set_id:
        parser.error(
            "--all-supported and --set-id are mutually exclusive: the first selects "
            "the declared simulation-supported cohort, the second selects sets by "
            "hand. Pass one or the other."
        )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Checked BEFORE any read or computation, so a misdirected --output-dir costs
    # a message rather than a full run whose artifacts then have to be deleted
    # from a tracked path.
    assert_private_output_dir(args.output_dir)

    try:
        targets, warnings, support_record = load_cohort(
            set_ids=args.set_id, all_supported=args.all_supported
        )
    except Exception as exc:  # noqa: BLE001 - a read failure is reported, never masked
        print(f"FAILED to load the RIP targets payload: {exc}", file=sys.stderr)
        return 2

    rows = build_rows(targets)
    readiness = assess_readiness(rows)
    manifest = build_manifest(
        args=args,
        rows=rows,
        readiness=readiness,
        warnings=warnings,
        support_record=support_record,
    )
    _print_cohort_scope(support_record)

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

    # A set declared simulation-supported but absent from the published targets
    # never reaches `financialV3Missing` - it has no row to be missing a score on.
    # Under --strict that silence would read as success, so it fails here.
    orphans = list((support_record or {}).get("supportedKeysMissingFromTargets") or [])
    if orphans and args.strict:
        print(
            "\n--strict: exiting nonzero because these declared simulation-supported "
            "sets are absent from the published RIP targets payload: "
            + ", ".join(orphans)
        )
        return 1
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
            gate = block.get("productionGuardrails") or {}
            weight_rows.append(
                {
                    "candidate": candidate,
                    "weight": block.get("weight"),
                    "isCanonicalProductionWeight": block.get("isCanonicalProductionWeight"),
                    "spearmanVsFinancialOnly": vs_financial.get("spearman"),
                    "kendallVsFinancialOnly": vs_financial.get("kendallTauB"),
                    "meanAbsRankDelta": vs_financial.get("meanAbsRankDelta"),
                    "medianAbsRankDelta": vs_financial.get("medianAbsRankDelta"),
                    "maxAbsRankDelta": vs_financial.get("maxAbsRankDelta"),
                    "top3Overlap": vs_financial.get("top3Overlap"),
                    "top5Overlap": vs_financial.get("top5Overlap"),
                    "top10Overlap": vs_financial.get("top10Overlap"),
                    "pctMoving1Plus": vs_financial.get("pctMoving1Plus"),
                    "pctMoving3Plus": vs_financial.get("pctMoving3Plus"),
                    "pctMoving5Plus": vs_financial.get("pctMoving5Plus"),
                    "productionGuardrailsPassed": gate.get("passed"),
                    "productionGuardrailsFailed": ";".join(gate.get("failedChecks") or []),
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
        ["candidate", "weight", "isCanonicalProductionWeight",
         "spearmanVsFinancialOnly", "kendallVsFinancialOnly",
         "meanAbsRankDelta", "medianAbsRankDelta", "maxAbsRankDelta",
         "top3Overlap", "top5Overlap", "top10Overlap",
         "pctMoving1Plus", "pctMoving3Plus", "pctMoving5Plus",
         "productionGuardrailsPassed", "productionGuardrailsFailed",
         "spearmanVsAdjacent", "varFinancialTerm", "varAppealTerm", "varCrossTerm",
         "dispersionShareAppeal", "appealContributionMean",
         "correlationFinancialAppeal"],
    )

    # The D/H/P influence table: one row per input per method, so a reader can
    # sort by observed influence instead of reading the nominal coefficients.
    influence = analysis.get("collectorAppealInputInfluence") or {}
    influence_rows: List[Dict[str, Any]] = []
    for study_key, payload in (influence.get("byInput") or {}).items():
        for method, block in (
            ("removal_without_renormalization", payload.get("removalWithoutRenormalization") or {}),
            ("drop_and_renormalize", payload.get("dropAndRenormalize") or {}),
        ):
            influence_rows.append(
                {
                    "input": study_key,
                    "nominalWeight": payload.get("nominalWeight"),
                    "method": method,
                    "spearmanVsFull": block.get("spearmanVsFull"),
                    "kendallTauBVsFull": block.get("kendallTauBVsFull"),
                    "meanAbsRankDelta": block.get("meanAbsRankDelta"),
                    "maxAbsRankDelta": block.get("maxAbsRankDelta"),
                    "top5Overlap": block.get("top5Overlap"),
                    "meanAbsoluteScoreContribution": payload.get("meanAbsoluteScoreContribution"),
                    "shareOfScoreVariance": (
                        (payload.get("varianceContribution") or {}).get("shareOfScoreVariance")
                    ),
                    "shareOfAppealDispersion": (
                        (payload.get("dispersion") or {}).get("shareOfAppealDispersion")
                    ),
                    "inputRange": (payload.get("inputSpread") or {}).get("range"),
                }
            )
    write_csv(
        output_dir / "collector_appeal_input_influence.csv",
        influence_rows,
        ["input", "nominalWeight", "method", "spearmanVsFull", "kendallTauBVsFull",
         "meanAbsRankDelta", "maxAbsRankDelta", "top5Overlap",
         "meanAbsoluteScoreContribution", "shareOfScoreVariance",
         "shareOfAppealDispersion", "inputRange"],
    )


def _print_cohort_scope(support_record: Mapping[str, Any]) -> None:
    """State what the cohort is and what it deliberately left out."""
    mode = support_record.get("mode")
    print("=" * 100)
    print("COHORT SCOPE")
    print("=" * 100)
    print(f"Mode                            : {mode}")
    print(f"Published targets               : {support_record.get('publishedTargetCount')}")
    if mode == "all_supported":
        print(f"Declared simulation-supported   : {support_record.get('supportedKeyCount')}")
        print(f"Support source                  : {support_record.get('supportSource')}")
    print(f"Included in cohort              : {support_record.get('includedSetCount')}")
    excluded = list(support_record.get("excludedSets") or [])
    print(f"Excluded (unsupported)          : {len(excluded)}")
    for entry in excluded:
        print(f"  - {entry.get('setName')} [{entry.get('canonicalKey')}]: {entry.get('reason')}")
    orphans = list(support_record.get("supportedKeysMissingFromTargets") or [])
    if orphans:
        print(f"\nDECLARED SUPPORTED BUT ABSENT FROM TARGETS ({len(orphans)}):")
        for key in orphans:
            print(f"  - {key}")
    print()


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
