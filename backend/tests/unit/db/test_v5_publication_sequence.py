import importlib
import inspect

from backend.db.services import v5_publication_sequence as seq


def test_sequence_is_well_formed_and_ordered_as_specified():
    assert seq.validate_sequence() == []
    keys = [s.key for s in seq.V5_CANDIDATE_SEQUENCE]
    assert keys[:3] == ["resolve_market_date", "verify_or_run_simulations", "verify_exact_run_map"]
    assert keys.index("rebuild_chase_accessibility") < keys.index("finalize_financial_v5") < keys.index("build_overall_v14_candidate")
    assert keys.index("publish_ranking_v2") < keys.index("publish_best_open_v3") < keys.index("activate_pointer")
    assert keys[-1] == "activate_pointer"


def test_activation_needs_explicit_authorization_and_is_never_in_the_default_prefix():
    assert seq.V5_CANDIDATE_SEQUENCE[-1].requires_explicit_authorization is True
    assert "activate_pointer" not in [s.key for s in seq.authorized_prefix(False)]
    assert "activate_pointer" in [s.key for s in seq.authorized_prefix(True)]
    assert seq.authorized_prefix(False, upto="finalize_financial_v5")[-1].key == "finalize_financial_v5"


def test_broken_sequences_are_detected():
    steps = list(seq.V5_CANDIDATE_SEQUENCE)
    swapped = steps[:]
    swapped[4], swapped[5] = swapped[5], swapped[4]
    assert seq.validate_sequence(swapped)
    unauthorized = [s if s.key != "activate_pointer" else seq.SequenceStep(s.order, s.key, s.description, s.implemented_by, True) for s in steps]
    assert seq.validate_sequence(unauthorized)


def test_the_current_daily_publication_orchestrator_does_not_use_the_v5_sequence():
    src = inspect.getsource(importlib.import_module("backend.scripts.run_daily_opening_publication"))
    assert "v5_publication_sequence" not in src and "budget_ranking_v2_orchestration" not in src
    assert "overall_v14_candidate_publication" not in src
