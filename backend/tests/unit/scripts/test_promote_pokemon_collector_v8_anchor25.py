from datetime import date
from pathlib import Path

import pytest

from backend.scripts import promote_pokemon_collector_v8_anchor25 as subject


def _built():
    return {
        "manifest": {
            "formulaFingerprint": subject.V8_FROZEN_FORMULA_FINGERPRINT,
            "cardFingerprint": subject.EXPECTED_V8_CARD_FINGERPRINT,
            "setFingerprint": subject.EXPECTED_V8_SET_FINGERPRINT,
            "sourceRunIds": ["s1", "s2"],
            "calibrationAnalysis": {
                "controlReplayExact": True,
                "pokemonUnchanged": True,
                "trainerWithinDomainSpearman": 1.0,
            },
        },
        "cards": [],
        "sets": [],
    }


def _current():
    return {
        "model_run_id": subject.EXPECTED_V7_RUN_ID,
        "model_version": subject.V7_VERSION,
    }


def _model():
    return {
        "id": subject.EXPECTED_V7_RUN_ID,
        "status": "published",
        "validation_passed": True,
        "input_fingerprint": subject.EXPECTED_V7_MODEL_FINGERPRINT,
        "source_run_ids": ["s1", "s2"],
        "scoring_config_json": {
            "formulaFingerprint": subject.EXPECTED_V7_FORMULA_FINGERPRINT,
            "cardFingerprint": subject.EXPECTED_V7_CARD_FINGERPRINT,
            "setFingerprint": subject.EXPECTED_V7_SET_FINGERPRINT,
        },
    }


def test_exact_v7_control_gate_passes_only_frozen_authority():
    checks = subject.validate_exact_v7_control(_current(), _model(), _built())
    assert all(checks.values())


def test_control_gate_fails_if_current_v7_run_changed():
    current = _current()
    current["model_run_id"] = "different"
    with pytest.raises(RuntimeError, match="currentRun"):
        subject.validate_exact_v7_control(current, _model(), _built())


def test_control_gate_fails_if_source_lineage_changed():
    model = _model()
    model["source_run_ids"] = ["new1", "new2"]
    with pytest.raises(RuntimeError, match="sourceAuthority"):
        subject.validate_exact_v7_control(_current(), model, _built())


def test_cutover_default_is_read_only_and_commit_requires_ack(monkeypatch):
    monkeypatch.setattr(
        subject,
        "promotion_plan",
        lambda _client: (_built(), {"decision": "COLLECTOR_V8_CUTOVER_PREFLIGHT_PASS"}),
    )
    dry = subject.execute(
        object(),
        commit=False,
        acknowledged=False,
        history_as_of=date(2026, 9, 29),
    )
    assert dry["mode"] == "dry-run"
    assert dry["mutationsPerformed"] == 0

    with pytest.raises(RuntimeError, match="ACKNOWLEDGEMENT_REQUIRED"):
        subject.execute(
            object(),
            commit=True,
            acknowledged=False,
            history_as_of=date(2026, 9, 29),
        )


def test_cutover_source_has_no_overall_publication_path():
    source = Path("backend/scripts/promote_pokemon_collector_v8_anchor25.py").read_text(encoding="utf-8").lower()
    assert "--i-understand-this-promotes-collector-v8" in source
    assert "overallripmutation" in source
    for forbidden in (
        "promote_pokemon_overall",
        "publish_overall",
        "overall_rip_publication_rows",
        "overall_rip_publication_runs",
    ):
        assert forbidden not in source



def _current_v8():
    return {
        "model_run_id": "run-v8",
        "model_version": subject.V8_VERSION,
    }


def _model_v8():
    return {
        "id": "run-v8",
        "model_version": subject.V8_VERSION,
        "as_of_date": subject.MODEL_AS_OF_DATE.isoformat(),
        "status": "published",
        "validation_passed": True,
        "source_run_ids": ["s1", "s2"],
        "scoring_config_json": {
            "formulaFingerprint": subject.V8_FROZEN_FORMULA_FINGERPRINT,
            "cardFingerprint": subject.EXPECTED_V8_CARD_FINGERPRINT,
            "setFingerprint": subject.EXPECTED_V8_SET_FINGERPRINT,
        },
    }


def test_exact_v8_current_gate_supports_interruption_recovery_only_for_accepted_candidate():
    checks = subject.validate_exact_v8_current(_current_v8(), _model_v8(), _built())
    assert all(checks.values())

    bad = _model_v8()
    bad["scoring_config_json"] = {**bad["scoring_config_json"], "setFingerprint": "wrong"}
    with pytest.raises(RuntimeError, match="setFingerprint"):
        subject.validate_exact_v8_current(_current_v8(), bad, _built())


def test_already_promoted_exact_v8_recovery_appends_history_without_second_promotion(monkeypatch):
    monkeypatch.setattr(
        subject,
        "promotion_plan",
        lambda _client: (
            _built(),
            {
                "decision": "COLLECTOR_V8_CUTOVER_ALREADY_PROMOTED_EXACT",
                "cutoverState": "already_promoted_exact",
                "currentModelRunId": "run-v8",
            },
        ),
    )
    calls = []
    monkeypatch.setattr(
        subject,
        "_append_current_collector_history",
        lambda _client, **kwargs: calls.append(("history", kwargs)) or 128,
    )
    monkeypatch.setattr(
        subject,
        "_readback",
        lambda _client, run_id: calls.append(("readback", run_id)) or {"ok": True},
    )

    report = subject.execute(
        object(),
        commit=True,
        acknowledged=True,
        history_as_of=date(2026, 9, 29),
    )
    assert report["decision"] == "COLLECTOR_V8_CUTOVER_RECOVERED_EXACT_V8"
    assert report["historyRowsInserted"] == 128
    assert report["modelCreated"] is False
    assert [name for name, _ in calls] == ["history", "readback"]
