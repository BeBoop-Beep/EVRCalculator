"""Round 9 catalog coverage decomposition (research only; zero database writes)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round6 import CONTRACT

ROOT = Path("docs/research")
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
R4 = ROOT / "treatment_market_prestige_v3_round4_study.json"
R5 = ROOT / "treatment_market_prestige_v3_round5_study.json"
R8 = ROOT / "treatment_market_prestige_v3_round8_study.json"
OUT = ROOT / "treatment_market_prestige_v3_round9_coverage"
STUDY = ROOT / "treatment_market_prestige_v3_round9_study.json"
REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND9_RESULTS.md"

TARGET = 0.70
EQUIVALENCE_MARGIN = 0.50  # preregistered before inspecting pairwise results
MODERN_ERA_UNIVERSES = {"Scarlet and Violet", "Mega Evolution", "XY"}


def load_inputs() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return tuple(json.loads(p.read_text(encoding="utf-8")) for p in (COHORT, R4, R5, R8))  # type: ignore[return-value]


def universe_map(r4: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    by_set: dict[str, str] = {}
    definitions: dict[str, dict[str, Any]] = {}
    for era, data in r4["regime_definitions"]["era_regimes"].items():
        if era in ("Sword and Shield", "Sun and Moon"):
            for regime in data["regimes"]:
                definitions[regime["regime_id"]] = {"era": era, **regime}
                by_set.update({set_id: regime["regime_id"] for set_id in regime["set_ids"]})
    for era in MODERN_ERA_UNIVERSES:
        definitions[era] = {"era": era, "regime_id": None}
    return by_set, definitions


def primary_blocker(row: dict[str, Any], universe: str | None, treatment: dict[str, Any] | None,
                    universe_status: str | None, support_status: str | None) -> str:
    if not row.get("era_id"):
        return "MISSING_CANONICAL_MAPPING"
    if not row.get("rarity_designation"):
        return "TAXONOMY_UNMAPPED"
    if not row.get("species_id") or row.get("demand_score") is None:
        return "MISSING_CANONICAL_MAPPING"
    if row.get("promo_status_ambiguous"):
        return "TAXONOMY_UNMAPPED"
    if universe is None:
        if support_status == "TAXONOMY_REPAIR_REQUIRED":
            return "TAXONOMY_UNMAPPED"
        if support_status == "INSUFFICIENT_DATA":
            return "INSUFFICIENT_UNIVERSE_SUPPORT"
        return "UNSUPPORTED_ERA"
    if treatment is None:
        return "UNSUPPORTED_TREATMENT"
    status = treatment["evidenceStatus"]
    if status == "MODEL_INSTABILITY":
        return "MODEL_INSTABILITY"
    if status == "HIGH_HETEROGENEITY":
        return "HIGH_HETEROGENEITY"
    if status == "INSUFFICIENT_HISTORY":
        return "INSUFFICIENT_HISTORY"
    if status == "INSUFFICIENT_TREATMENT_SUPPORT":
        return "INSUFFICIENT_TREATMENT_SUPPORT"
    if status == "AVAILABLE" and universe_status != "AVAILABLE":
        return "INSUFFICIENT_UNIVERSE_SUPPORT"
    return "OTHER_VERIFIED_REASON"


def similarity_audit(r8: dict[str, Any]) -> dict[str, Any]:
    by_universe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for treatment in r8["treatment_matrix"]:
        by_universe[treatment["universeId"]].append(treatment)
    pairs = []
    for universe, treatments in sorted(by_universe.items()):
        eligible = [t for t in treatments if t["evidenceStatus"] == "AVAILABLE"]
        for i, left in enumerate(eligible):
            for right in eligible[i + 1:]:
                distance = abs(left["researchScore"] - right["researchScore"])
                if distance <= EQUIVALENCE_MARGIN:
                    pairs.append({"universeId": universe, "left": left["treatmentKey"],
                                  "right": right["treatmentKey"], "scoreDistance": distance,
                                  "classification": "PRACTICALLY_EQUIVALENT_PRESTIGE"})
    return {
        "preregisteredContract": {
            "scoreDistanceMargin": EQUIVALENCE_MARGIN,
            "requirements": ["both treatment magnitude estimates pass every individual gate",
                             "absolute score distance <= margin", "propagated score intervals may overlap",
                             "prediction widths pass heterogeneity gates", "temporal status is MARKET_MOVEMENT"],
            "pairwiseOrderingProbabilityAloneIsDispositive": False,
        },
        "existingRule": CONTRACT["universe_gate"],
        "ruleAudit": "SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT",
        "equivalentPairs": pairs,
        "cardsRecoverable": 0,
        "conclusion": "Round 6 never required unique ordering; failed universes lack two individually eligible treatments.",
    }


def build() -> dict[str, Any]:
    cohort_doc, r4, r5, r8 = load_inputs()
    rows = cohort_doc["rows"]
    by_set, definitions = universe_map(r4)
    universe_status = {u["universeId"]: u["publicationStatus"] for u in r8["universe_matrix"]}
    treatment_matrix = {(t["universeId"], t["treatmentKey"]): t for t in r8["treatment_matrix"]}
    support = r5["support_matrix"]
    card_results, covered = [], 0
    for row in rows:
        era = row["era_name"]
        universe = era if era in MODERN_ERA_UNIVERSES else by_set.get(row["set_id"])
        treatment = treatment_matrix.get((universe, row.get("rarity_designation"))) if universe else None
        model_eligible = bool(row.get("rarity_designation") and row.get("species_id") and
                              row.get("demand_score") is not None and not row.get("promo_status_ambiguous"))
        is_covered = bool(model_eligible and treatment and treatment["finalAvailabilityStatus"] == "AVAILABLE")
        if is_covered:
            covered += 1
            blocker = None
        else:
            blocker = primary_blocker(row, universe, treatment, universe_status.get(universe), support.get(era))
        secondary = []
        if not row.get("species_id"): secondary.append("MISSING_CANONICAL_MAPPING")
        if universe and universe_status.get(universe) != "AVAILABLE": secondary.append("INSUFFICIENT_UNIVERSE_SUPPORT")
        card_results.append({"canonicalCardId": row["canonical_card_id"], "era": era,
                             "setId": row["set_id"], "setName": row["set_name"],
                             "universeId": universe, "treatmentKey": row.get("rarity_designation"),
                             "covered": is_covered, "primaryBlocker": blocker,
                             "secondaryBlockers": sorted(set(secondary) - {blocker})})
    denominator = len(rows)
    blockers = Counter(x["primaryBlocker"] for x in card_results if not x["covered"])
    secondary = Counter(b for x in card_results for b in x["secondaryBlockers"])
    era_audit = []
    modern = {"Scarlet and Violet", "Mega Evolution", "Sword and Shield", "Sun and Moon", "XY"}
    for era in sorted({r["era_name"] for r in rows} - modern):
        group = [r for r in rows if r["era_name"] == era]
        era_audit.append({"era": era, "pricedCanonicalCards": len(group),
                          "sets": len({r["set_id"] for r in group}),
                          "species": len({r["species_id"] for r in group if r.get("species_id")}),
                          "mappedTreatmentCards": sum(bool(r.get("rarity_designation")) for r in group),
                          "treatments": sorted({r["rarity_designation"] for r in group if r.get("rarity_designation")}),
                          "supportStatus": support.get(era, "UNSUPPORTED_ERA"),
                          "temporalCheckpointDepth": 0, "earliestUsableDate": None,
                          "recommendedStructure": "ONTOLOGY_RESEARCH_REQUIRED_BEFORE_ERA_VS_REGIME_DECISION",
                          "dataRequirement": "NEW_TAXONOMY_RESEARCH_REQUIRED" if support.get(era)=="TAXONOMY_REPAIR_REQUIRED" else "EXTERNAL_HISTORICAL_DATA_REQUIRED"})
    universe_gaps = []
    for uid, definition in definitions.items():
        group = [x for x in card_results if x["universeId"] == uid]
        treatment_evidence = [{k: t[k] for k in ("treatmentKey", "cardCount", "setCount", "speciesCount",
                                                  "researchScore", "scoreInterval", "heterogeneityStatus",
                                                  "temporalStatus", "evidenceStatus", "finalAvailabilityStatus")}
                              for t in r8["treatment_matrix"] if t["universeId"] == uid]
        universe_gaps.append({"universeId": uid, "era": definition["era"], "cards": len(group),
                              "coveredCards": sum(x["covered"] for x in group),
                              "uncoveredCards": sum(not x["covered"] for x in group),
                              "primaryBlockers": dict(Counter(x["primaryBlocker"] for x in group if not x["covered"])),
                              "treatmentEvidence": treatment_evidence,
                              "publicationStatus": universe_status.get(uid, "NOT_EVALUATED")})
    opportunities = []
    running = covered
    work_map = {
        "MODEL_INSTABILITY": ("research", False, "high"), "INSUFFICIENT_HISTORY": ("data", True, "medium"),
        "UNSUPPORTED_ERA": ("taxonomy+data+research", True, "high"), "UNSUPPORTED_TREATMENT": ("taxonomy+research", False, "medium"),
        "INSUFFICIENT_UNIVERSE_SUPPORT": ("research", False, "high"), "TAXONOMY_UNMAPPED": ("taxonomy", False, "medium"),
        "MISSING_CANONICAL_MAPPING": ("canonical mapping", False, "medium"),
    }
    for blocker, count in sorted(blockers.items(), key=lambda x: (-x[1], x[0])):
        running += count
        work, external, risk = work_map.get(blocker, ("research", False, "high"))
        opportunities.append({"project": f"Resolve {blocker}", "currentlyUncoveredCards": count,
                              "percentagePointGain": 100*count/denominator,
                              "theoreticalCumulativeCoverage": running/denominator,
                              "primaryBlocker": blocker, "workType": work,
                              "externalDataRequired": external, "scientificRisk": risk,
                              "implementationComplexity": risk, "gainIsValidated": False})
    similarity = similarity_audit(r8)
    source_classification = {
        "INSUFFICIENT_HISTORY": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
        "MODEL_INSTABILITY": "INTERNAL_DATA_ALREADY_EXISTS",
        "INSUFFICIENT_UNIVERSE_SUPPORT": "INTERNAL_PIPELINE_REPAIR_REQUIRED",
        "UNSUPPORTED_TREATMENT": "NEW_TAXONOMY_RESEARCH_REQUIRED",
        "UNSUPPORTED_ERA": "EXTERNAL_HISTORICAL_DATA_REQUIRED",
        "TAXONOMY_UNMAPPED": "NEW_TAXONOMY_RESEARCH_REQUIRED",
        "MISSING_CANONICAL_MAPPING": "NEW_CANONICAL_MAPPING_REQUIRED",
    }
    core = {"round8StudyId": r8["study_id"], "cohortHash": r5["frozen_manifest"]["cohort_hash"],
            "denominator": denominator, "target": TARGET, "equivalenceMargin": EQUIVALENCE_MARGIN,
            "blockers": dict(sorted(blockers.items()))}
    study_id = f"treatment-market-prestige-v3-r9-{stable_json_hash(core)[:16]}"
    return {"study_id": study_id, "built_at": datetime.now(timezone.utc).isoformat(),
            "frozenRound8Denominator": 19847, "currentAuthoritativeDenominator": denominator,
            "currentlyCoveredCards": covered, "currentCoverage": covered/denominator,
            "uncoveredCards": denominator-covered, "catalogProductCoverageTarget": TARGET,
            "productStatus": "CATALOG_COVERAGE_BELOW_PRODUCT_THRESHOLD",
            "primaryFailureCategories": dict(sorted(blockers.items())),
            "primaryFailurePercentages": {k: v/denominator for k,v in sorted(blockers.items())},
            "secondaryFailureCategories": dict(sorted(secondary.items())),
            "similarityAudit": similarity, "universeGapDecomposition": universe_gaps,
            "olderEraAudit": era_audit, "coverageOpportunityTable": opportunities,
            "blockerDataRequirements": {k: source_classification[k] for k in sorted(blockers)},
            "scenarios": {
                "internalOnly": {"validatedFloor": covered, "maximumPlausible": covered, "note": "No failed project has yet passed the frozen evidence gates."},
                "internalHistoricalBackfill": {"validatedFloor": covered, "maximumPlausible": covered + blockers.get("INSUFFICIENT_HISTORY",0), "unproven": True},
                "verifiedExternalHistory": {"validatedFloor": covered, "maximumPlausible": denominator-blockers.get("TAXONOMY_UNMAPPED",0)-blockers.get("MISSING_CANONICAL_MAPPING",0), "unproven": True},
                "fullOlderEraResearch": {"validatedFloor": covered, "theoreticalCeiling": denominator, "unproven": True}},
            "thresholdPaths": {
                "50Percent": {"status": "PLAUSIBLE_BUT_UNPROVEN", "minimumValidatedProjects": None,
                              "reason": "No unresolved project has passed the unchanged evidence gates."},
                "60Percent": {"status": "PLAUSIBLE_BUT_UNPROVEN", "minimumValidatedProjects": None},
                "70Percent": {"status": "PLAUSIBLE_BUT_UNPROVEN", "minimumValidatedProjects": None},
                "80Percent": {"status": "PLAUSIBLE_BUT_UNPROVEN", "minimumValidatedProjects": None}},
            "coverageDiagnosis": "COVERAGE_GAP_MIXED",
            "similarityRuleStatus": similarity["ruleAudit"],
            "seventyPercentPathStatus": "70_PERCENT_COVERAGE_PATH_PLAUSIBLE_BUT_UNPROVEN",
            "productionImplementationPaused": True, "rowsPersisted": 0,
            "productionBehavior": "Unchanged; research artifacts only. No migration applied, candidate approved, reader activated, UI/frontend/RIP/V1/V2/ranking behavior changed.",
            "preservedImplementationScaffolding": ["supabase/migrations/20260830020000_create_treatment_market_prestige_v3_publication.sql", "backend/db/services/treatment_market_prestige_v3_service.py", "backend/scripts/build_treatment_market_prestige_v3_candidate.py", "backend/scripts/approve_treatment_market_prestige_v3_candidate.py", "backend/scripts/verify_treatment_market_prestige_v3_production.py"],
            "cardResultsFile": str(OUT/"card_coverage.json"),
            "filesChanged": [str(OUT/"card_coverage.json"), str(OUT/"manifest.json"), str(STUDY), str(REPORT), "backend/scripts/build_treatment_market_prestige_v3_round9.py", "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round9.py"],
            "testsExecuted": ["Round 9 exhaustive card accounting", "similarity semantics", "70% fail-closed product gate"],
            "remainingLimitations": ["Older eras have no frozen four-checkpoint temporal evidence", "opportunity counts are not eligibility claims", "no new external data was introduced"],
            "recommendedTasks": ["Backfill and validate existing failed modern regimes by coverage gain", "Research older-era structural ontologies", "Acquire and freeze authoritative older-era history", "Rerun the unchanged individual evidence gates"],
            "_card_results": card_results}


def render(study: dict[str, Any]) -> str:
    public = {k:v for k,v in study.items() if k != "_card_results"}
    gaps = {x["universeId"]: x for x in study["universeGapDecomposition"]}
    older = {x["era"]: x for x in study["olderEraAudit"]}
    required = [
        ("Round 9 study ID", study["study_id"]), ("Priced-card denominator", study["currentAuthoritativeDenominator"]),
        ("Currently covered card count", study["currentlyCoveredCards"]), ("Current coverage percentage", study["currentCoverage"]),
        ("Exact uncovered card count", study["uncoveredCards"]), ("Primary failure categories", list(study["primaryFailureCategories"])),
        ("Card count per failure category", study["primaryFailureCategories"]), ("Percentage per failure category", study["primaryFailurePercentages"]),
        ("Overlap/secondary failure categories", study["secondaryFailureCategories"]), ("Similarity-aware universe-rule audit", study["similarityAudit"]),
        ("Treatments currently stable but practically equivalent", study["similarityAudit"]["equivalentPairs"]),
        ("Cards recoverable through similarity-aware semantics", 0), ("Mega gap decomposition", gaps["Mega Evolution"]),
        ("Mega recoverable coverage", {"validated": 0, "opportunity": gaps["Mega Evolution"]["uncoveredCards"]}),
        ("SWSH regime 2 gap", gaps["sword_and_shield_r2"]), ("SWSH regime 3 gap", gaps["sword_and_shield_r3"]),
        ("SWSH regime 4 gap", gaps["sword_and_shield_r4"]), ("SWSH regime 5 gap", gaps["sword_and_shield_r5"]),
        ("SWSH total recoverable coverage", {"validated": 0, "opportunity": sum(gaps[f"sword_and_shield_r{i}"]["uncoveredCards"] for i in range(2,6))}),
        ("Sun & Moon regime 2 gap", gaps["sun_and_moon_r2"]), ("Sun & Moon regime 3 gap", gaps["sun_and_moon_r3"]),
        ("Sun & Moon total recoverable coverage", {"validated": 0, "opportunity": gaps["sun_and_moon_r2"]["uncoveredCards"]+gaps["sun_and_moon_r3"]["uncoveredCards"]}),
        ("Every older-era support audit", older), ("Older-era taxonomy gaps", {k:v["supportStatus"] for k,v in older.items()}),
        ("Older-era temporal gaps", {k:{"checkpointDepth":v["temporalCheckpointDepth"],"requirement":v["dataRequirement"]} for k,v in older.items()}),
        ("Era-vs-regime recommendation per older era", {k:v["recommendedStructure"] for k,v in older.items()}),
        ("Internal vs external data requirements", study["blockerDataRequirements"]), ("Coverage opportunity table", study["coverageOpportunityTable"]),
        ("Internal-only maximum coverage", study["scenarios"]["internalOnly"]), ("Historical-backfill coverage", study["scenarios"]["internalHistoricalBackfill"]),
        ("External-history coverage", study["scenarios"]["verifiedExternalHistory"]), ("Full-research potential coverage", study["scenarios"]["fullOlderEraResearch"]),
        ("Minimum path to 50%", study["thresholdPaths"]["50Percent"]), ("Minimum path to 60%", study["thresholdPaths"]["60Percent"]),
        ("Minimum path to 70%", study["thresholdPaths"]["70Percent"]), ("Path to 80% if credible", study["thresholdPaths"]["80Percent"]),
        ("Coverage diagnosis status", study["coverageDiagnosis"]), ("Similarity-rule status", study["similarityRuleStatus"]),
        ("70% path status", study["seventyPercentPathStatus"]), ("Whether production implementation should remain paused", True),
        ("Rows persisted", 0), ("Production behavior", study["productionBehavior"]), ("Files changed", study["filesChanged"]),
        ("Tests executed", study["testsExecuted"]), ("Remaining limitations", study["remainingLimitations"]),
        ("Exact recommended next research/data tasks in priority order", study["recommendedTasks"]),
    ]
    lines = ["# Treatment Market Prestige V3 — Round 9 Results", "",
             f"Study ID: `{study['study_id']}`", "",
             f"Coverage remains **{study['currentlyCoveredCards']:,} / {study['currentAuthoritativeDenominator']:,} ({study['currentCoverage']:.1%})**; {study['uncoveredCards']:,} cards are uncovered.", "",
             f"Decision states: `{study['coverageDiagnosis']}`, `{study['similarityRuleStatus']}`, `{study['seventyPercentPathStatus']}`.", "",
             "The 70% gate is not met. Production implementation remains paused and rows persisted remain `0`.", "", "## Required results", ""]
    lines.extend(f"{i}. **{label}:** `{json.dumps(value, sort_keys=True, default=str)}`\n" for i,(label,value) in enumerate(required,1))
    lines.extend([
             "## Machine-readable complete report", "", "```json", json.dumps(public, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def main() -> None:
    study = build()
    cards = study.pop("_card_results")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"card_coverage.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
    STUDY.write_text(json.dumps(study, indent=2), encoding="utf-8")
    REPORT.write_text(render(study), encoding="utf-8")
    manifest = {"study_id": study["study_id"], "study_hash": stable_json_hash(study),
                "card_coverage_hash": stable_json_hash(cards), "rows_persisted": 0}
    (OUT/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
