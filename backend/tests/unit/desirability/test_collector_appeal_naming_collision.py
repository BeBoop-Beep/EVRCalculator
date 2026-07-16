"""Two different metrics, one product name. These tests keep them apart.

THE COLLISION
-------------
``collector_appeal_score`` already ships. It is fed from
``pure_desirability_score`` (see ``opening_desirability_presenter``), so the
public "Collector Appeal" IS Pure/Universal Desirability - a roster-quality
measure with no structural component at all.

CA7 is a different construct: ``D + 0.5 * P * (1 - D)``, where P is Dual-Path
Depth. It answers a different question and produces different numbers.

If CA7 were persisted under a generic ``collector_appeal`` key, the same product
name would mean two things depending on which field you read - and there would be
no way to tell from the data which definition any given consumer had picked up.
The ambiguity becomes permanent at the moment anything reads it.

So: CA7 is namespaced ``collector_appeal_ca7``, declares itself an internal
candidate, and touches nothing public. These tests fail if that boundary erodes.
See docs/research/collector_appeal_product_naming_transition.md.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_METRIC_NAME,
    COLLECTOR_APPEAL_PRODUCT_STATUS,
    COLLECTOR_APPEAL_VERSION,
)

REPO = Path(__file__).resolve().parents[4]

# The public surface this task is forbidden to touch.
PUBLIC_SCORE_FIELD = "collector_appeal_score"
PUBLIC_RANK_FIELD = "collector_appeal_rank"
PUBLIC_API_FIELD = "collectorAppealScore"


# ---------------------------------------------------------------------------
# The new metric's identity
# ---------------------------------------------------------------------------

def test_the_new_metric_is_namespaced_and_not_generic():
    assert COLLECTOR_APPEAL_DIAGNOSTICS_KEY == "collector_appeal_ca7"
    assert COLLECTOR_APPEAL_DIAGNOSTICS_KEY != "collector_appeal"
    assert COLLECTOR_APPEAL_METRIC_NAME == "collector_appeal_ca7"


def test_the_new_metric_declares_itself_an_internal_candidate():
    """Nothing may read this as a shipped product by accident."""
    assert COLLECTOR_APPEAL_PRODUCT_STATUS == "internal_candidate"


def test_the_new_metric_version_is_a_production_candidate_not_a_study():
    assert COLLECTOR_APPEAL_VERSION == "collector_appeal_ca7_v1"
    assert "research" not in COLLECTOR_APPEAL_VERSION


def test_the_stored_block_states_metric_formula_and_status_together():
    from backend.desirability.collector_appeal_fingerprint import build_collector_appeal_identity

    identity = build_collector_appeal_identity()
    assert identity["metric_name"] == "collector_appeal_ca7"
    assert identity["product_status"] == "internal_candidate"
    assert identity["formula"] == "CA7"


# ---------------------------------------------------------------------------
# The public metric is untouched
# ---------------------------------------------------------------------------

def test_the_rollout_never_names_the_public_score_field():
    """No write, no read, no rename of the shipping field."""
    import backend.desirability.collector_appeal_rollout as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value != PUBLIC_SCORE_FIELD, "rollout references the public score field"
            assert node.value != PUBLIC_RANK_FIELD
            assert node.value != PUBLIC_API_FIELD


def test_the_public_score_field_still_reads_from_pure_desirability():
    """Pins the collision as a FACT, so a silent redefinition breaks a test.

    If someone later points collector_appeal_score at CA7 without a migration,
    this fails - which is the intended alarm, not an inconvenience.
    """
    presenter = (REPO / "backend" / "desirability" / "opening_desirability_presenter.py").read_text(
        encoding="utf-8"
    )
    assert '_first_present(row, "collector_appeal_score", "pure_desirability_score")' in presenter


def test_the_public_metric_and_ca7_are_different_constructs():
    """Not a naming quibble: they compute different numbers from the same set.

    Pure/Universal Desirability is D. CA7 is D + 0.5*P*(1-D). They agree only
    where P = 0, so any set with dual-path structure is scored differently by the
    two definitions - under one product name.
    """
    from backend.desirability.collector_appeal import compute_collector_appeal

    d = 0.60
    assert compute_collector_appeal(d, 0.0) == pytest.approx(d)          # agree only at P=0
    assert compute_collector_appeal(d, 1.0) == pytest.approx(0.80)       # diverge otherwise
    assert compute_collector_appeal(d, 0.5) != pytest.approx(d)


# ---------------------------------------------------------------------------
# Nothing public, nothing frontend, no migration
# ---------------------------------------------------------------------------

def test_only_diagnostics_json_is_writable():
    from backend.desirability.collector_appeal_rollout import WRITABLE_COLUMNS

    assert tuple(WRITABLE_COLUMNS) == ("diagnostics_json",)


def test_the_rollout_issues_no_ddl():
    import backend.desirability.collector_appeal_rollout as module

    source = inspect.getsource(module).upper()
    for statement in ("ALTER TABLE", "CREATE TABLE", "DROP TABLE", "ADD COLUMN"):
        assert statement not in source


def test_the_dry_run_script_has_no_commit_flag():
    """`--commit` must be unreachable by construction, not by discipline."""
    script = (REPO / "backend" / "scripts" / "collector_appeal_production_dry_run.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(script)

    added_flags = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]
    assert "--commit" not in added_flags


def test_the_dry_run_script_never_passes_commit_true():
    script = (REPO / "backend" / "scripts" / "collector_appeal_production_dry_run.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(script)

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "execute_plan"):
            commit = next((kw for kw in node.keywords if kw.arg == "commit"), None)
            assert commit is not None, "execute_plan called without an explicit commit flag"
            assert commit.value.value is False, "the dry run must never pass commit=True"


def test_the_research_grid_and_the_production_function_are_documented_apart():
    """The module docstring must not let a reader mistake a candidate for a product."""
    import backend.desirability.collector_appeal as module

    # Whitespace-normalized: the docstring is line-wrapped, so a raw substring
    # search would fail on a phrase that merely spans two lines.
    docstring = " ".join(module.__doc__.lower().split())
    assert "research candidate grid" in docstring
    assert "selected production candidate" in docstring
    assert "collector_appeal_ca7_v1" in docstring
    assert "pure/universal desirability" in docstring
