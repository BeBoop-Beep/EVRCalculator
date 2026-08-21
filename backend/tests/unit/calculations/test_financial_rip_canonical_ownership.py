import ast
from pathlib import Path


def test_v3_v4_and_scoring_config_import_cleanly():
    import backend.calculations.evr.financial_rip_v3_config  # noqa: F401
    import backend.calculations.evr.financial_rip_v4_config  # noqa: F401
    import backend.desirability.scoring_config as scoring_config

    from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION

    assert scoring_config.CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V4_VERSION


def test_financial_rip_v3_config_does_not_import_v4_config():
    """Structural: the V3 config module must not depend on the V4 one — that
    direction is what caused the circular import this test guards against."""
    source = Path("backend/calculations/evr/financial_rip_v3_config.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "financial_rip_v4_config" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "financial_rip_v4_config" not in alias.name


def test_financial_rip_v3_config_no_longer_defines_canonical_switch():
    """Single-owner invariant: only scoring_config may define this symbol."""
    import backend.calculations.evr.financial_rip_v3_config as v3_config
    assert not hasattr(v3_config, "CANONICAL_FINANCIAL_RIP_VERSION")
