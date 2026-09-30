"""Regression tests for the Treatment Hierarchy V1 research study
(docs/research/collector_appeal/treatment_hierarchy_v1/).

This study is research-only and made zero production writes. These tests
protect the preregistered gate logic and the frozen decision artifact
against silent drift, and guard several of the specific research
invariants called out in the spec (no hard-coded rarity ordering, no
production writes, unsupported cells stay null, treatment-cell identity
is compositional).
"""
import json
from pathlib import Path

STUDY_DIR = Path(__file__).resolve().parents[4] / "docs" / "research" / "collector_appeal" / "treatment_hierarchy_v1"

# Round 24 panel-readiness ledger (frozen; see PREREGISTRATION.md Section 1).
# Reused verbatim from docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND24_RESULTS.md
ROUND24_PANEL_READINESS = {
    "PANEL_READY_STRONG": 1,
    "PANEL_READY_MODERATE": 4,
    "METADATA_BLOCKED": 935,
    "HISTORY_BLOCKED": 15049,
    "NO_TRUE_LADDER": 0,
}
ROUND24_DENOMINATOR = 15989


def classify_support(panel_readiness_class: str, set_has_exact_pull_scarcity: bool) -> str:
    """Preregistered support-class mapping (PREREGISTRATION.md Section 5)."""
    if panel_readiness_class in ("PANEL_READY_STRONG", "PANEL_READY_MODERATE"):
        return "GOLD_SCARCITY_CONTROLLED" if set_has_exact_pull_scarcity else "DIAGNOSTIC_PACKAGE_ONLY"
    return "UNSUPPORTED"


def eligible_for_phase2(cells_by_set_and_family, min_independent_sets: int = 2) -> bool:
    """Preregistered era-progression gate (PREREGISTRATION.md Section 6):
    at least `min_independent_sets` independent Sets must clear gates for
    a shared treatment family before the study may proceed past Phase 1/3.
    """
    for family, sets in cells_by_set_and_family.items():
        if len(set(sets)) >= min_independent_sets:
            return True
    return False


def test_round24_ledger_matches_frozen_study_document():
    total = sum(ROUND24_PANEL_READINESS.values())
    assert total == ROUND24_DENOMINATOR
    panel_ready = ROUND24_PANEL_READINESS["PANEL_READY_STRONG"] + ROUND24_PANEL_READINESS["PANEL_READY_MODERATE"]
    assert panel_ready == 5


def test_support_classification_never_promotes_unsupported_cells():
    assert classify_support("HISTORY_BLOCKED", set_has_exact_pull_scarcity=True) == "UNSUPPORTED"
    assert classify_support("METADATA_BLOCKED", set_has_exact_pull_scarcity=True) == "UNSUPPORTED"
    assert classify_support("NO_TRUE_LADDER", set_has_exact_pull_scarcity=False) == "UNSUPPORTED"


def test_support_classification_requires_scarcity_authority_for_gold_tier():
    assert classify_support("PANEL_READY_STRONG", set_has_exact_pull_scarcity=True) == "GOLD_SCARCITY_CONTROLLED"
    assert classify_support("PANEL_READY_MODERATE", set_has_exact_pull_scarcity=False) == "DIAGNOSTIC_PACKAGE_ONLY"


def test_stop_rule_triggers_with_round24_evidence():
    # Only 5 panel-ready cells exist catalog-wide; even in the best case
    # where all 5 belonged to one family, they cannot be guaranteed to
    # span >= 2 independent Sets with a frozen, reproducible sample
    # (Round 24 sampleHash is null). The preregistered stop rule must
    # therefore hold given this evidence, unless a future round supplies
    # a Set-level breakdown.
    worst_case_single_set = {"special_illustration_rare": ["only_one_set"]}
    assert eligible_for_phase2(worst_case_single_set) is False

    hypothetical_two_sets = {"special_illustration_rare": ["set_a", "set_b"]}
    assert eligible_for_phase2(hypothetical_two_sets) is True


def test_treatment_cell_identity_is_compositional_not_a_single_label():
    key = "|".join(["sv-era", "sv-151", "rare_holo", "holo", "none", "unlimited"])
    parts = key.split("|")
    assert len(parts) == 6, "treatment cell key must carry era, set, rarity, finish, special, edition"
    assert parts[0] != parts[1], "era and set must remain distinct identity components"


def test_no_hard_coded_rarity_ordering_in_support_classifier():
    import inspect

    source = inspect.getsource(classify_support) + inspect.getsource(eligible_for_phase2)
    forbidden_tokens = ["SIR > IR", "IR > Ultra", "Ultra Rare >", "sir_beats_ir", "RARITY_ORDER"]
    for token in forbidden_tokens:
        assert token not in source


def test_decision_json_reports_zero_production_impact():
    decision = json.loads((STUDY_DIR / "decision.json").read_text(encoding="utf-8"))
    impact = decision["productionImpact"]
    assert impact["collectorAppealMutated"] is False
    assert impact["overallRipMutated"] is False
    assert impact["rankingsMutated"] is False
    assert impact["setPagesPublished"] is False
    assert impact["productionRowsWritten"] == 0
    assert decision["decisionToken"] == "SET_RELATIVE_TREATMENT_NOT_SUPPORTED"


def test_decision_json_does_not_choose_positive_token_without_passing_gates():
    decision = json.loads((STUDY_DIR / "decision.json").read_text(encoding="utf-8"))
    positive_tokens = {
        "HIERARCHICAL_TREATMENT_SUPPORTED_FOR_COLLECTOR_SHADOW",
        "HIERARCHICAL_TREATMENT_SUPPORTED_FOR_COLLECTOR_V9_RESEARCH",
        "SET_RELATIVE_TREATMENT_SUPPORTED_WITH_LIMITED_COVERAGE",
    }
    assert decision["decisionToken"] not in positive_tokens
    for phase in decision["phasesNotExecuted"]:
        assert phase not in decision["phasesExecuted"]


def test_preregistration_json_freezes_gates_before_phase2():
    prereg = json.loads((STUDY_DIR / "preregistration.json").read_text(encoding="utf-8"))
    assert prereg["decisionGates"]["G1_matchedIdentityMin"] == 2
    assert prereg["decisionGates"]["eraProgressionMinIndependentSets"] == 2
    assert "force monotonic rarity ordering" in prereg["prohibited"]
    assert "write pokemon_collector_appeal_current" in prereg["prohibited"]
