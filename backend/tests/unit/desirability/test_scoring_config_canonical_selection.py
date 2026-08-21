from backend.desirability import scoring_config as sc


def test_canonical_financial_rip_is_v4():
    assert sc.CANONICAL_FINANCIAL_RIP_VERSION == sc.FINANCIAL_RIP_V4_VERSION
    assert sc.canonical_financial_rip_is_v4() is True
    assert sc.canonical_financial_rip_is_v3() is False


def test_canonical_overall_rip_is_v10():
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V10_VERSION
    assert sc.CANONICAL_OVERALL_RIP_WEIGHTS == sc.OVERALL_RIP_V10_WEIGHTS
    assert sc.canonical_overall_rip_is_v10() is True
    assert sc.canonical_overall_rip_is_v9() is False


def test_canonical_public_rip_contract_is_v10():
    from backend.desirability.public_rip_contract_v10 import PUBLIC_RIP_CONTRACT_V10_VERSION
    assert sc.canonical_public_rip_contract_version() == PUBLIC_RIP_CONTRACT_V10_VERSION


def test_v3_v9_history_still_computable():
    """The old identifiers must remain valid, non-canonical, registered versions."""
    assert sc.FINANCIAL_RIP_V3_VERSION in sc.KNOWN_FINANCIAL_RIP_VERSIONS
    assert sc.OVERALL_RIP_V9_VERSION in sc.KNOWN_OVERALL_RIP_VERSIONS
