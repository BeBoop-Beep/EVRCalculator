from pathlib import Path

import pytest

from backend.scripts.build_pokemon_collector_appeal_v8_anchor25 import (
    ALPHA,
    ANCHOR_METHOD,
    MODEL_VERSION,
    calibrated_subject,
    tie_percentiles,
)


def test_v8_identity_and_alpha_are_frozen():
    assert MODEL_VERSION == "pokemon_collector_appeal_v8_anchor25_cross_domain_v1"
    assert ALPHA == 0.25
    assert ANCHOR_METHOD == "trainer_tie_midrank_percentile_to_pokemon_empirical_quantile_v1"


def test_calibration_changes_only_trainers():
    assert calibrated_subject(original=80.0, anchor=60.0, domain="trainer") == 75.0
    assert calibrated_subject(original=80.0, anchor=60.0, domain="pokemon") == 80.0
    assert calibrated_subject(original=80.0, anchor=60.0, domain="neutral_functional") == 80.0


def test_tie_midrank_percentiles_are_stable():
    pct = tie_percentiles({"a": 1.0, "b": 1.0, "c": 3.0})
    assert pct["a"] == pct["b"]
    assert pct["a"] < pct["c"]


def test_builder_does_not_promote_or_change_current_pointer():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8").lower()
    assert "promote_pokemon_collector" not in source
    assert "select_pokemon_collector_appeal_current" not in source
    assert "pokemon_collector_appeal_current" in source  # read-only baseline binding
    assert "--write-stage" in source


def test_default_execution_is_not_write_stage():
    source = Path("backend/scripts/build_pokemon_collector_appeal_v8_anchor25.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--write-stage", action="store_true")' in source
    assert "if args.write_stage:" in source
