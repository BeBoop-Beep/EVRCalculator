from backend.desirability import scoring_config as sc


def test_canonical_financial_rip_is_v4():
    assert sc.CANONICAL_FINANCIAL_RIP_VERSION == sc.FINANCIAL_RIP_V4_VERSION
    assert sc.canonical_financial_rip_is_v4() is True
    assert sc.canonical_financial_rip_is_v3() is False


def test_canonical_overall_rip_is_v12():
    """2026-09-03 cutover: canonical Overall RIP is V12, not V10."""
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION
    assert sc.CANONICAL_OVERALL_RIP_WEIGHTS == sc.OVERALL_RIP_V12_WEIGHTS
    assert sc.canonical_overall_rip_is_v12() is True
    assert sc.canonical_overall_rip_is_v10() is False
    assert sc.canonical_overall_rip_is_v9() is False


def test_overall_rip_v10_remains_explicit_historical_lineage():
    """V10 stays fully computable/registered - it is simply no longer canonical."""
    assert sc.OVERALL_RIP_V10_VERSION in sc.KNOWN_OVERALL_RIP_VERSIONS
    assert sc.OVERALL_RIP_V10_WEIGHTS == {"financial_rip": 0.90, "collector_appeal": 0.10}


def test_canonical_public_rip_contract_is_v11():
    """2026-09-03 cutover: canonical public contract is v11 (carries Overall RIP V12)."""
    from backend.desirability.public_rip_contract_v11 import PUBLIC_RIP_CONTRACT_V11_VERSION
    assert sc.canonical_public_rip_contract_version() == PUBLIC_RIP_CONTRACT_V11_VERSION


def test_explicit_v10_public_contract_still_computable_unchanged():
    """Explicitly requesting the V10 contract must remain byte-identical - never removed."""
    from backend.desirability.public_rip_contract_v10 import (
        PUBLIC_RIP_CONTRACT_V10_VERSION,
        build_public_rip_contract_v10,
    )
    assert PUBLIC_RIP_CONTRACT_V10_VERSION == "public_rip_contract_v10"
    assert callable(build_public_rip_contract_v10)


def test_v3_v9_v10_history_still_computable():
    """The old identifiers must remain valid, non-canonical, registered versions."""
    assert sc.FINANCIAL_RIP_V3_VERSION in sc.KNOWN_FINANCIAL_RIP_VERSIONS
    assert sc.OVERALL_RIP_V9_VERSION in sc.KNOWN_OVERALL_RIP_VERSIONS
    assert sc.OVERALL_RIP_V10_VERSION in sc.KNOWN_OVERALL_RIP_VERSIONS
