"""Overall RIP V10, the V10 public contract, and the V4 integration surfaces.

Claims under test:

  * Overall RIP V10 is 90% Financial RIP V4 + 10% Collector Appeal V5,
  * Overall RIP V9 is unchanged and still computable (historical support),
  * Collector Appeal V5 is unchanged,
  * the version registries can identify every model, canonical or not,
  * V4/V10 are implemented but deliberately NOT canonical,
  * the V10 public contract keeps the public shape and names,
  * sealed-product scoring produces V4/V10 without persisting them,
  * raw cross-format sealed-product comparison remains disabled,
  * nothing in this path writes to a database, publishes a snapshot, or
    runs a simulation.
"""

from __future__ import annotations

import inspect

import pytest

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
)
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_VERSION,
    FINANCIAL_RIP_V4_WEIGHTS,
)
from backend.desirability import weighted_rip
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_V4_VERSION,
    COLLECTOR_APPEAL_V5_FORMULA_VERSION,
    COLLECTOR_APPEAL_V5_VERSION,
)
from backend.desirability.public_rip_contract_v9 import (
    PUBLIC_RIP_CONTRACT_V9_VERSION,
    build_public_rip_contract_v9,
)
from backend.desirability.public_rip_contract_v10 import (
    PUBLIC_RIP_CONTRACT_V10_KEY,
    PUBLIC_RIP_CONTRACT_V10_VERSION,
    build_public_rip_contract_v10,
)
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    KNOWN_FINANCIAL_RIP_VERSIONS,
    KNOWN_OVERALL_RIP_VERSIONS,
    OVERALL_RIP_V9_VERSION,
    OVERALL_RIP_V10_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V10_WEIGHTS,
    canonical_collector_appeal_version,
    canonical_financial_rip_is_v3,
    canonical_financial_rip_is_v4,
    canonical_overall_rip_is_v9,
    canonical_overall_rip_is_v10,
    canonical_scoring_selection,
    is_known_financial_rip_version,
    is_known_overall_rip_version,
)
from backend.desirability.weighted_rip import (
    compute_overall_rip_v9,
    compute_overall_rip_v10,
)
from backend.domain.pokemon import sealed_product_comparison_scope as scope

FINANCIAL = 71.0
APPEAL = 63.5


# ---------------------------------------------------------------------------
# Overall RIP V10
# ---------------------------------------------------------------------------

def test_v10_is_ninety_ten_over_financial_v4_and_collector_appeal_v5():
    result = compute_overall_rip_v10(FINANCIAL, APPEAL)
    assert result["status"] == "ready"
    assert result["version"] == OVERALL_RIP_V10_VERSION
    assert result["weights"] == {"financial_rip": 0.90, "collector_appeal": 0.10}
    assert result["score"] == pytest.approx(0.90 * FINANCIAL + 0.10 * APPEAL, abs=1e-9)
    assert result["formula"] == "0.90 * financial_rip_v4 + 0.10 * collector_appeal_v5"


def test_v10_version_string_names_its_actual_inputs():
    assert "financial_v4" in OVERALL_RIP_V10_VERSION
    assert "collector_appeal_v5" in OVERALL_RIP_V10_VERSION
    assert OVERALL_RIP_V10_VERSION != OVERALL_RIP_V9_VERSION


def test_v10_components_name_the_financial_model_they_hold():
    components = compute_overall_rip_v10(FINANCIAL, APPEAL)["components"]
    assert "financialRipV4" in components
    assert components["financialRipV4"]["weight"] == 0.90
    assert components["collectorAppeal"]["weight"] == 0.10


def test_v10_effective_weights_expand_the_v4_component_table():
    for component, weight in FINANCIAL_RIP_V4_WEIGHTS.items():
        assert OVERALL_RIP_V10_EFFECTIVE_WEIGHTS[component] == pytest.approx(
            0.90 * weight, abs=1e-12
        )
    assert OVERALL_RIP_V10_EFFECTIVE_WEIGHTS["collector_appeal"] == 0.10
    assert sum(OVERALL_RIP_V10_EFFECTIVE_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(
    "financial, appeal, missing",
    [
        (None, APPEAL, ["financial_rip_v4"]),
        (FINANCIAL, None, ["collector_appeal_v5"]),
        (None, None, ["financial_rip_v4", "collector_appeal_v5"]),
    ],
)
def test_v10_never_substitutes_a_missing_input(financial, appeal, missing):
    result = compute_overall_rip_v10(financial, appeal)
    assert result["score"] is None
    assert result["rankable"] is False
    assert result["missingInputs"] == missing
    assert result["version"] == OVERALL_RIP_V10_VERSION


def test_a_missing_collector_appeal_is_not_treated_as_zero():
    assert compute_overall_rip_v10(FINANCIAL, None)["score"] is None
    assert compute_overall_rip_v10(FINANCIAL, 0.0)["score"] == pytest.approx(
        0.90 * FINANCIAL, abs=1e-9
    )


# ---------------------------------------------------------------------------
# V9 historical support
# ---------------------------------------------------------------------------

def test_v9_is_unchanged_and_still_computable():
    result = compute_overall_rip_v9(FINANCIAL, APPEAL)
    assert result["version"] == OVERALL_RIP_V9_VERSION
    assert result["formula"] == "0.90 * financial_rip_v3 + 0.10 * collector_appeal_v5"
    assert result["components"]["financialRipV3"]["score"] == FINANCIAL


def test_v9_and_v10_are_distinguishable_despite_identical_arithmetic():
    """The scores agree; the identifiers must not, or a row loses its meaning."""
    v9 = compute_overall_rip_v9(FINANCIAL, APPEAL)
    v10 = compute_overall_rip_v10(FINANCIAL, APPEAL)
    assert v9["score"] == v10["score"]
    assert v9["version"] != v10["version"]
    assert v9["formula"] != v10["formula"]


def test_every_historical_overall_version_remains_importable():
    for name in (
        "compute_overall_rip_v5",
        "compute_overall_rip_v6",
        "compute_overall_rip_v7",
        "compute_overall_rip_v8",
        "compute_overall_rip_v9",
        "compute_overall_rip_v10",
    ):
        assert callable(getattr(weighted_rip, name))


# ---------------------------------------------------------------------------
# Collector Appeal V5 is unchanged
# ---------------------------------------------------------------------------

def test_collector_appeal_v5_is_untouched():
    assert COLLECTOR_APPEAL_V5_VERSION == (
        "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
    )
    assert canonical_collector_appeal_version() == COLLECTOR_APPEAL_V5_VERSION
    assert COLLECTOR_APPEAL_V5_VERSION != COLLECTOR_APPEAL_V4_VERSION
    assert COLLECTOR_APPEAL_V5_FORMULA_VERSION


def test_v10_consumes_the_same_appeal_score_v9_consumes():
    v9 = compute_overall_rip_v9(FINANCIAL, APPEAL)
    v10 = compute_overall_rip_v10(FINANCIAL, APPEAL)
    assert v9["components"]["collectorAppeal"] == v10["components"]["collectorAppeal"]


# ---------------------------------------------------------------------------
# Registries and the cutover switch
# ---------------------------------------------------------------------------

def test_both_financial_versions_are_registered_and_identifiable():
    assert is_known_financial_rip_version(FINANCIAL_RIP_V3_VERSION)
    assert is_known_financial_rip_version(FINANCIAL_RIP_V4_VERSION)
    assert not is_known_financial_rip_version("financial_rip_v9_invented")
    assert len(set(KNOWN_FINANCIAL_RIP_VERSIONS)) == len(KNOWN_FINANCIAL_RIP_VERSIONS)


def test_both_overall_versions_are_registered_and_identifiable():
    assert is_known_overall_rip_version(OVERALL_RIP_V9_VERSION)
    assert is_known_overall_rip_version(OVERALL_RIP_V10_VERSION)
    assert not is_known_overall_rip_version("overall_rip_v99_invented")
    assert len(set(KNOWN_OVERALL_RIP_VERSIONS)) == len(KNOWN_OVERALL_RIP_VERSIONS)


def test_v3_and_v9_remain_computable_as_history():
    """Financial RIP V4 / Overall RIP V10 are now canonical (the promotion cutover
    has happened). V3/V9 must remain registered and computable so historical rows
    stay readable and identifiable — they are simply no longer selected."""
    assert CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V4_VERSION
    assert CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION
    assert canonical_financial_rip_is_v4() is True
    assert canonical_financial_rip_is_v3() is False
    assert canonical_overall_rip_is_v10() is True
    assert canonical_overall_rip_is_v9() is False
    assert is_known_financial_rip_version(FINANCIAL_RIP_V3_VERSION)
    assert is_known_overall_rip_version(OVERALL_RIP_V9_VERSION)


def test_the_selection_payload_discloses_the_promoted_versions():
    selection = canonical_scoring_selection()
    assert selection["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V4_VERSION
    assert selection["canonicalOverallRipVersion"] == OVERALL_RIP_V10_VERSION
    assert FINANCIAL_RIP_V4_VERSION in selection["availableFinancialRipVersions"]
    assert OVERALL_RIP_V10_VERSION in selection["availableOverallRipVersions"]
    assert FINANCIAL_RIP_V3_VERSION in selection["availableFinancialRipVersions"]
    assert OVERALL_RIP_V9_VERSION in selection["availableOverallRipVersions"]


def test_v4_weights_are_numerically_equal_to_v3_but_separately_owned():
    assert FINANCIAL_RIP_V4_WEIGHTS == FINANCIAL_RIP_V3_WEIGHTS
    assert FINANCIAL_RIP_V4_WEIGHTS is not FINANCIAL_RIP_V3_WEIGHTS


# ---------------------------------------------------------------------------
# The V10 public contract
# ---------------------------------------------------------------------------

def _target():
    return {
        "overallRipV10": compute_overall_rip_v10(FINANCIAL, APPEAL),
        "overallRipV9": compute_overall_rip_v9(FINANCIAL, APPEAL),
        "financialRipV4": {
            "scoreVersion": FINANCIAL_RIP_V4_VERSION,
            "score": FINANCIAL,
            "components": {},
        },
        "cohortFingerprint": "cohort-abc",
    }


def test_v10_contract_declares_its_own_versions():
    contract = build_public_rip_contract_v10(_target())
    assert contract["contractVersion"] == PUBLIC_RIP_CONTRACT_V10_VERSION
    assert contract["canonicalOverallRipVersion"] == OVERALL_RIP_V10_VERSION
    assert contract["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V4_VERSION
    assert contract["canonicalCollectorAppealVersion"] == COLLECTOR_APPEAL_V5_VERSION
    assert PUBLIC_RIP_CONTRACT_V10_KEY == "publicRipContractV10"


def test_v10_contract_keeps_the_public_shape_and_metric_names():
    """A consumer parsing V9 must only need to learn the new top-level key."""
    v10 = build_public_rip_contract_v10(_target())
    v9 = build_public_rip_contract_v9(_target())
    assert set(v9) <= set(v10)
    for key in ("overallRip", "financialRip", "collectorAppeal"):
        assert key in v10


def test_v10_contract_publishes_the_financial_component_under_both_names():
    components = build_public_rip_contract_v10(_target())["overallRip"]["components"]
    # Backward compatible: the existing slot still resolves.
    assert components["financialRipV3"]["score"] == FINANCIAL
    # Truthful: the model that actually produced it is named too.
    assert components["financialRipV4"]["score"] == FINANCIAL


def test_v10_contract_reports_which_financial_model_it_carries():
    contract = build_public_rip_contract_v10(_target())
    assert contract["overallRip"]["financialInputVersion"] == FINANCIAL_RIP_V4_VERSION
    assert contract["financialRip"]["version"] == FINANCIAL_RIP_V4_VERSION


def test_v9_contract_is_unchanged_by_the_v10_addition():
    """`public_rip_contract_v9` is structurally frozen at the Financial RIP V3 era:
    both `canonicalOverallRipVersion` (V9) and `canonicalFinancialRipVersion` (V3)
    are pinned historical literals, not the live `CANONICAL_FINANCIAL_RIP_VERSION`
    switch. Following the live constant would make this contract falsely declare a
    Financial RIP V4 identity while its `financialRip` payload still carries V3
    numbers, so it must stay unchanged by the V4/V10 cutover."""
    contract = build_public_rip_contract_v9(_target())
    assert contract["contractVersion"] == PUBLIC_RIP_CONTRACT_V9_VERSION
    assert contract["canonicalOverallRipVersion"] == OVERALL_RIP_V9_VERSION
    assert contract["canonicalFinancialRipVersion"] == FINANCIAL_RIP_V3_VERSION


def test_building_the_v10_contract_does_not_mutate_the_source_target():
    target = _target()
    before = dict(target)
    build_public_rip_contract_v10(target)
    assert target == before


# ---------------------------------------------------------------------------
# Cross-format comparison remains disabled
# ---------------------------------------------------------------------------

def test_raw_cross_format_comparison_is_still_disabled():
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    assert scope.sealed_product_comparison_scope_contract()["crossFormatComparable"] is False
    assert scope.SEALED_PRODUCT_COMPARISON_SCOPE == "within_product_family_only"


def test_v4_does_not_unlock_a_cross_family_comparison():
    families = sorted(scope.COMPARABLE_FAMILIES)
    assert len(families) >= 2
    assert scope.may_compare_products(families[0], families[0]) is True
    assert scope.may_compare_products(families[0], families[1]) is False


def test_the_scope_reason_states_that_v4_does_not_change_it():
    reason = scope.SEALED_PRODUCT_COMPARISON_SCOPE_REASON
    assert "V4" in reason
    assert "equal-committed-capital" in reason


# ---------------------------------------------------------------------------
# No writes, no publication, no simulation
# ---------------------------------------------------------------------------

_SOURCES = (
    "backend/calculations/evr/financial_rip_v4.py",
    "backend/calculations/evr/financial_rip_v4_config.py",
    "backend/desirability/public_rip_contract_v10.py",
)

_FORBIDDEN = (
    ".insert(",
    ".upsert(",
    ".update(",
    ".delete(",
    "execute_sql",
    "run_simulation",
    "publish_",
)


@pytest.mark.parametrize("path", _SOURCES)
def test_the_new_modules_perform_no_writes_publication_or_simulation(path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    source = (root / path).read_text(encoding="utf-8")
    for token in _FORBIDDEN:
        assert token not in source, f"{path} contains a forbidden operation: {token}"


def test_the_new_modules_import_no_database_client():
    import backend.calculations.evr.financial_rip_v4 as v4_module
    import backend.desirability.public_rip_contract_v10 as contract_module

    for module in (v4_module, contract_module):
        source = inspect.getsource(module)
        assert "supabase" not in source.lower()
        assert "psycopg" not in source.lower()


def test_the_parity_verifier_declares_zero_mutations():
    from backend.scripts import research_financial_rip_v4_parity as verifier

    source = inspect.getsource(verifier)
    assert '"databaseMutations": "NONE"' in source
    assert '"publicationMutations": "NONE"' in source
    assert '"simulationRuns": "NONE"' in source
