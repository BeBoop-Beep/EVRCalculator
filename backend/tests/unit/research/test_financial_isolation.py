"""Financial RIP V3 must be a function of the outcome vector and pack cost ONLY.

The whole architecture rests on one boundary: Financial RIP V3 measures money,
Collector Appeal measures appeal, and neither may leak into the other. If
Collector Appeal could move Financial RIP V3, then Overall RIP would weight the
appeal signal twice - once explicitly at 20%, once invisibly inside the 80% -
and no amount of weight-sensitivity analysis would reveal it, because both terms
would move together by construction.

These tests are the mechanical guarantee of that boundary.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

from backend.calculations.evr import financial_rip_v3, financial_rip_v3_config
from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.desirability import desirable_outcome_frequency

PACK_COST = 5.0
REPO_ROOT = Path(__file__).resolve().parents[4]


def _outcomes(n: int = 12_000) -> list:
    """A deterministic, mildly heavy-tailed outcome vector.

    Fixed rather than random so a failure is reproducible: a flaky isolation
    test would be worse than none, because it would train the reader to rerun.
    """
    values = []
    for i in range(n):
        if i % 1000 == 0:
            values.append(180.0)
        elif i % 100 == 0:
            values.append(28.0)
        elif i % 10 == 0:
            values.append(7.5)
        else:
            values.append(1.1 + (i % 7) * 0.35)
    return values


# ---------------------------------------------------------------------------
# Import-level isolation
# ---------------------------------------------------------------------------

def test_financial_rip_v3_does_not_import_collector_appeal():
    """No appeal module may appear in the V3 engine's or config's import graph."""
    forbidden = (
        "collector_appeal",
        "desirable_outcome_frequency",
        "opening_appeal",
        "factorized_opening_appeal",
        "universal_set_desirability",
    )
    for module in (financial_rip_v3, financial_rip_v3_config):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            for banned in forbidden:
                assert banned not in name, (
                    f"{module.__name__} imports {name!r}, which would let a "
                    f"Collector Appeal input reach Financial RIP V3."
                )


def test_desirable_outcome_frequency_reads_no_price_or_value():
    """H is an appeal statistic and must never touch money.

    Guards the labelling failure the module's docstring warns about: an appeal
    frequency described (or computed) as a financial rate would let a collector
    read "60% of packs contain a card you want" as a promise about money.
    """
    source = inspect.getsource(desirable_outcome_frequency)
    tree = ast.parse(source)

    banned_identifiers = {
        "price", "market_price", "value", "set_value", "expected_value",
        "pack_cost", "ev", "profit", "revenue", "cost",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in banned_identifiers:
            pytest.fail(f"desirable_outcome_frequency reads attribute {node.attr!r}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # String keys are how this codebase reads payload fields, so a
            # monetary key would be a real read, not just a mention.
            if node.value in {"price", "market_price", "pack_cost", "set_value", "total_card_ev"}:
                pytest.fail(
                    f"desirable_outcome_frequency references payload key {node.value!r}"
                )


# ---------------------------------------------------------------------------
# Behavioural isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "d,h,p",
    [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), (0.93, 0.02, 0.44)],
)
def test_changing_d_h_or_p_cannot_move_financial_rip_v3(d, h, p):
    """The decisive test: appeal inputs vary wildly, V3 does not move at all.

    V3 is recomputed inside the loop rather than compared to a stored constant,
    so the test would catch a V3 that had acquired a hidden dependency on module
    state that the appeal computation mutates.
    """
    from backend.research.collector_appeal_candidates import compute_primary

    outcomes = _outcomes()
    baseline = build_financial_rip_v3(outcomes, PACK_COST)

    appeal = compute_primary(d, h, p)
    after = build_financial_rip_v3(outcomes, PACK_COST)

    assert appeal is not None
    assert after["score"] == baseline["score"]
    for component in financial_rip_v3_config.FINANCIAL_RIP_V3_COMPONENT_ORDER:
        assert (
            after["components"][component]["score"]
            == baseline["components"][component]["score"]
        )


def test_financial_rip_v3_is_a_pure_function_of_outcomes_and_cost():
    """Same vector + same cost => byte-identical payload, across separate calls."""
    outcomes = _outcomes()
    first = build_financial_rip_v3(outcomes, PACK_COST)
    second = build_financial_rip_v3(list(outcomes), float(PACK_COST))
    assert first["score"] == second["score"]

    # And a genuine change to the vector DOES move it - otherwise the equality
    # above would pass for a function that ignores its inputs entirely.
    shifted = [v * 1.5 for v in outcomes]
    assert build_financial_rip_v3(shifted, PACK_COST)["score"] != first["score"]


def test_true_win_frequency_and_desirable_outcome_frequency_are_different_quantities():
    """The two frequencies must never be conflated.

        True Win Frequency        = P(pack value >= pack cost)
        Desirable Outcome Frequency = P(pack has >= 1 desirable-subject card)

    A desirable outcome can be a financial loss. This test builds exactly that
    case: a pack that almost always contains a wanted card and almost never
    covers its cost.
    """
    from backend.desirability.desirable_outcome_frequency import (
        compute_desirable_outcome_frequency,
    )

    # Nearly every pack contains the desirable common; nearly none beats cost.
    # `appeal_excess` (demand above the baseline) is what `desirable_subjects`
    # selects on - `subject_demand` alone leaves a subject ineligible.
    subjects = [
        {
            "subject_key": "s1",
            "subject_name": "Pikachu",
            "subject_demand": 95.0,
            "appeal_excess": 45.0,
            "cards": [{"card_name": "Pikachu", "pull_probability": 0.95, "slot_group": "a"}],
        }
    ]
    frequency = compute_desirable_outcome_frequency(subjects)
    assert frequency["available"] is True
    assert frequency["rawValue"] > 0.9
    assert frequency["isFinancialMetric"] is False

    cheap_outcomes = [0.10] * 11_000 + [500.0] * 1_000
    financial = build_financial_rip_v3(cheap_outcomes, PACK_COST)
    true_win = financial["components"]["true_win_frequency"]["raw"]["trueWinProbability"]
    assert true_win < 0.15
    # High desirable-outcome frequency, low true win frequency: the two are
    # measuring different things and must be free to disagree completely.
    assert frequency["rawValue"] > true_win + 0.5


# ---------------------------------------------------------------------------
# Migration 060 immutability
# ---------------------------------------------------------------------------

MIGRATION_060 = REPO_ROOT / "backend" / "db" / "migrations" / "060_add_financial_rip_v3_metrics.sql"

# Pinned LITERAL, captured from the applied file at the start of this validation
# work. It must never be re-derived from the file at test time: a hash the test
# computes from its own subject can only ever agree with it, which would make
# this an assertion that the file equals itself.
EXPECTED_MIGRATION_060_SHA256 = (
    "a5be633c2f2698e772b5648fbc205da2b1ddb0cbc7b74e6f83a09e06fdc58084"
)


def test_migration_060_exists_and_is_not_modified_by_this_work():
    """Migration 060 is applied in production and is therefore immutable.

    Pinned by content hash. Editing an applied migration makes the file disagree
    with the database it supposedly describes, and nothing downstream can detect
    that divergence. A schema change needs migration 061.
    """
    assert MIGRATION_060.exists(), "migration 060 is missing"
    digest = hashlib.sha256(MIGRATION_060.read_bytes()).hexdigest()
    assert digest == EXPECTED_MIGRATION_060_SHA256, (
        "Migration 060 has changed. It is already applied in production and must "
        "be treated as immutable - add migration 061 instead of editing it. If "
        "this change is genuinely intended, update the pinned hash deliberately."
    )


def test_migration_060_adds_no_collector_appeal_column():
    """simulation_derived_metrics must carry no appeal field.

    Collector Appeal is a set-level property computed from desirability and the
    pack model; storing it on a per-simulation-run financial table would make it
    look like a simulation output and would create a second, divergent source of
    truth the moment desirability rebuilt without a simulation rerun.
    """
    sql = MIGRATION_060.read_text(encoding="utf-8").lower()
    for banned in (
        "collector_appeal",
        "desirable_outcome_frequency",
        "dual_path_depth",
        "chase_appeal",
        "roster_desirability",
    ):
        assert banned not in sql, f"migration 060 must not add a {banned!r} column"
