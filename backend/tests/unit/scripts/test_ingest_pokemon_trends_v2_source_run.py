"""Unit tests for the Pokémon Trends V2 source-run persistence bridge.

Covers Phase 9 validation rules and Phase 8 idempotency identity from the
Collector Appeal V6 persistence-bridge task. No DB access -- all fixtures
are constructed in-memory / via tmp_path.
"""
from __future__ import annotations

import copy
import json
import math

import pytest

from backend.scripts.ingest_pokemon_trends_v2_source_run import (
    EXPECTED_SUBJECT_COUNT,
    LoadedCheckpoint,
    ValidationError,
    build_observation_row,
    capture_identity,
    load_checkpoint,
    validate_checkpoint,
)


def _valid_row(subject_id: int, **overrides) -> dict:
    row = {
        "subject_id": subject_id,
        "pokedex_number": subject_id,
        "pokemon_name": f"Subject{subject_id}",
        "assigned_anchor": "Torkoal",
        "escalated": False,
        "raw_target": 10.0,
        "raw_anchor": 20.0,
        "global_relative": 50.0,
        "classification": "SCORED",
        "retry_count": 0,
        "failure_detail": None,
        "manifest_version": "pokemon_trends_anchor_ladder_manifest_v1",
        "code_version": "capture_pokemon_trends_anchor_ladder_v2_r1",
        "query_settings": {"timeframe": "today 1-m", "geo": "US", "queryType": "search_term"},
        "timestamp": 1789005373.0,
    }
    row.update(overrides)
    return row


def _valid_header() -> dict:
    return {
        "manifest_fingerprint": "009418a05f6b9631",
        "code_version": "capture_pokemon_trends_anchor_ladder_v2_r1",
        "timeframe": "today 1-m",
        "geo": "US",
        "started_at": 1789005372.0,
    }


def _full_rows(n=EXPECTED_SUBJECT_COUNT) -> list[dict]:
    return [_valid_row(i) for i in range(1, n + 1)]


def test_validate_checkpoint_accepts_well_formed_full_capture():
    loaded = LoadedCheckpoint(header=_valid_header(), rows=_full_rows())
    report = validate_checkpoint(loaded)
    assert report["totalRows"] == EXPECTED_SUBJECT_COUNT
    assert report["uniqueSubjects"] == EXPECTED_SUBJECT_COUNT
    assert report["failedRows"] == 0


def test_validate_checkpoint_rejects_wrong_row_count():
    loaded = LoadedCheckpoint(header=_valid_header(), rows=_full_rows(10))
    with pytest.raises(ValidationError, match="expected 1025 rows"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_duplicate_subject():
    rows = _full_rows()
    rows.append(copy.deepcopy(rows[0]))  # now 1026 rows, duplicate subject_id=1
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_wrong_manifest_fingerprint():
    header = _valid_header()
    header["manifest_fingerprint"] = "deadbeef"
    loaded = LoadedCheckpoint(header=header, rows=_full_rows())
    with pytest.raises(ValidationError, match="manifest_fingerprint"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_mixed_code_versions():
    rows = _full_rows()
    rows[0]["code_version"] = "some_other_version"
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="code_version"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_unknown_anchor():
    rows = _full_rows()
    rows[0]["assigned_anchor"] = "Mewtwo"
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="anchor identity"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_malformed_calibrated_score():
    rows = _full_rows()
    rows[0]["global_relative"] = math.nan
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="non-finite"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_failed_coerced_to_numeric_zero():
    rows = _full_rows()
    rows[0]["classification"] = "failed"
    rows[0]["global_relative"] = 0.0  # attempted coercion of FAILED -> 0
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="must not carry a numeric"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_accepts_genuine_failed_row_without_score():
    rows = _full_rows()
    rows[0]["classification"] = "failed"
    rows[0]["global_relative"] = None
    rows[0]["raw_target"] = None
    rows[0]["raw_anchor"] = None
    rows[0]["failure_detail"] = "status=rate_limited error_type=rate_limited_429"
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    report = validate_checkpoint(loaded)
    assert report["failedRows"] == 1
    assert report["usableScoredRows"] == EXPECTED_SUBJECT_COUNT - 1


def test_validate_checkpoint_rejects_missing_pokemon_identity():
    rows = _full_rows()
    del rows[0]["pokemon_name"]
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="identity fields"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_price_contaminated_row():
    rows = _full_rows()
    rows[0]["price_usd"] = 12.5
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="price-contaminated"):
        validate_checkpoint(loaded)


def test_validate_checkpoint_rejects_unknown_classification():
    rows = _full_rows()
    rows[0]["classification"] = "totally_unsupported_state"
    loaded = LoadedCheckpoint(header=_valid_header(), rows=rows)
    with pytest.raises(ValidationError, match="unknown classification"):
        validate_checkpoint(loaded)


def test_capture_identity_is_deterministic_and_pins_query_contract():
    header_a = _valid_header()
    header_b = _valid_header()
    assert capture_identity(header_a) == capture_identity(header_b)

    header_c = _valid_header()
    header_c["timeframe"] = "today 12-m"
    assert capture_identity(header_c) != capture_identity(header_a)


def test_load_checkpoint_missing_files_fail_closed(tmp_path):
    with pytest.raises(ValidationError, match="rows file not found"):
        load_checkpoint(tmp_path / "missing_rows.jsonl", tmp_path / "missing_header.json")


def test_load_checkpoint_rejects_malformed_json_line(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    header_path = tmp_path / "header.json"
    header_path.write_text(json.dumps(_valid_header()), encoding="utf-8")
    rows_path.write_text('{"subject_id": 1}\nNOT JSON\n', encoding="utf-8")
    with pytest.raises(ValidationError, match="not valid JSON"):
        load_checkpoint(rows_path, header_path)


def test_build_observation_row_never_persists_score_for_failed_row():
    row = _valid_row(1, classification="failed", global_relative=None, raw_target=None, raw_anchor=None,
                      failure_detail="status=rate_limited error_type=rate_limited_429")
    observation = build_observation_row(source_run_id="run-1", entity_id="entity-1", row=row)
    assert observation["normalized_observation_score"] is None
    assert observation["raw_row_json"]["classification"] == "failed"
    assert observation["raw_row_json"]["failureDetail"] == "status=rate_limited error_type=rate_limited_429"
    # Full audit trail retained, not just pokemon_id + score:
    assert observation["raw_row_json"]["assignedAnchor"] == row["assigned_anchor"]
    assert observation["raw_row_json"]["manifestVersion"] == row["manifest_version"]
    assert observation["raw_row_json"]["captureCodeVersion"] == row["code_version"]


def test_build_observation_row_persists_calibrated_score_for_scored_row():
    row = _valid_row(2)
    observation = build_observation_row(source_run_id="run-1", entity_id="entity-2", row=row)
    assert observation["normalized_observation_score"] == pytest.approx(50.0)
    assert observation["dimension_key"] == "pokemon_search_interest_v2"
    assert observation["match_status"] == "matched"
    assert observation["source_run_id"] == "run-1"
    assert observation["collector_entity_id"] == "entity-2"
