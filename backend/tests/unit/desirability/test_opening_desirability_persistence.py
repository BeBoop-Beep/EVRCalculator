import json
from types import SimpleNamespace

from backend.desirability.rip_desirability import SCORING_VERSION as RIP_DESIRABILITY_SCORING_VERSION
from backend.scripts.build_set_rip_desirability_prototype import (
    OPENING_DESIRABILITY_TABLE,
    RipDesirabilityPrototypeRepository,
    build_opening_desirability_persistence_row,
    maybe_persist_opening_desirability,
)


BUILT_AT = "2026-06-15T19:15:46+00:00"


def test_persistence_payload_maps_public_safe_opening_fields():
    payload = build_opening_desirability_persistence_row(
        _scored_row(),
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
        built_at=BUILT_AT,
    )

    assert payload["set_name"] == "Prismatic Evolutions"
    assert payload["set_canonical_key"] == "prismaticEvolutions"
    assert payload["opening_desirability_score"] == 79.5
    assert payload["opening_desirability_rank"] == 2
    assert payload["collector_appeal_score"] == 91.1
    assert payload["collector_appeal_rank"] == 1
    assert payload["chase_appeal_score"] == 52.6
    assert payload["chase_appeal_rank"] == 7
    assert payload["chase_appeal_data_quality"] == "usable"
    assert payload["opening_desirability_display_status"] == "scored"
    assert payload["source_v2_component_row_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["source_rip_calculation_run_id"] == "22222222-2222-2222-2222-222222222222"
    assert payload["scoring_version"] == RIP_DESIRABILITY_SCORING_VERSION
    assert payload["built_at"] == BUILT_AT


def test_persistence_payload_excludes_formula_weights_component_json_and_blend_copy():
    row = {
        **_scored_row(),
        "monetary_component_scores_json": {"formula": "secret", "weights": {"a": 1}},
        "rip_component_scores_json": {"formulae": {"rip_desirability_score_70_30": "secret"}},
    }

    payload = build_opening_desirability_persistence_row(
        row,
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
        built_at=BUILT_AT,
    )
    serialized = json.dumps(payload).lower()

    assert "formula" not in serialized
    assert "weights" not in serialized
    assert "monetary_component_scores_json" not in payload
    assert "rip_component_scores_json" not in payload
    assert "70/30" not in serialized


def test_missing_chase_appeal_persists_null_opening_desirability():
    payload = build_opening_desirability_persistence_row(
        {
            "set_id": "33333333-3333-3333-3333-333333333333",
            "set_name": "Collector Only Set",
            "set_canonical_key": "collectorOnly",
            "pure_desirability_score": 79.2,
            "pure_desirability_rank": 4,
            "monetary_chase_appeal_score": None,
            "monetary_chase_appeal_rank": None,
            "monetary_data_quality": "missing",
            "primary_rip_desirability_score": None,
            "rip_desirability_rank_70_30": None,
        },
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
        built_at=BUILT_AT,
    )

    assert payload["opening_desirability_score"] is None
    assert payload["opening_desirability_rank"] is None
    assert payload["collector_appeal_score"] == 79.2
    assert payload["collector_appeal_rank"] == 4
    assert payload["chase_appeal_score"] is None
    assert payload["chase_appeal_rank"] is None
    assert payload["chase_appeal_data_quality"] == "missing"
    assert payload["opening_desirability_display_status"] == "collector_only"


def test_default_path_is_read_only_and_does_not_call_writer():
    repository = RecordingRepository()

    result = maybe_persist_opening_desirability(
        report={"rows": [_scored_row()]},
        repository=repository,
        commit=False,
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
    )

    assert result["committed"] is False
    assert result["rows_to_write"] == 0
    assert result["rows_that_would_be_persisted"] == 1
    assert repository.calls == []


def test_commit_path_writes_public_safe_rows_to_repository():
    repository = RecordingRepository()

    result = maybe_persist_opening_desirability(
        report={"rows": [_scored_row()]},
        repository=repository,
        commit=True,
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
    )

    assert result["committed"] is True
    assert result["rows_to_write"] == 1
    assert result["written_rows_returned"] == 1
    assert repository.calls == [([_scored_row()], RIP_DESIRABILITY_SCORING_VERSION)]


def test_repository_writer_inserts_sanitized_payload_into_opening_table():
    client = RecordingClient()
    repository = RipDesirabilityPrototypeRepository(client=client)

    written = repository.insert_opening_desirability_rows(
        [_scored_row()],
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
    )

    assert client.table_name == OPENING_DESIRABILITY_TABLE
    assert len(client.inserted_rows) == 1
    assert written == client.inserted_rows
    assert client.inserted_rows[0]["opening_desirability_display_status"] == "scored"
    assert "monetary_component_scores_json" not in client.inserted_rows[0]


class RecordingRepository:
    def __init__(self):
        self.calls = []

    def insert_opening_desirability_rows(self, rows, *, scoring_version):
        self.calls.append((list(rows), scoring_version))
        return [{"id": "persisted"} for _ in rows]


class RecordingClient:
    table_name = None
    inserted_rows = None

    def table(self, table_name):
        self.table_name = table_name
        return self

    def insert(self, rows):
        self.inserted_rows = list(rows)
        return self

    def execute(self):
        return SimpleNamespace(data=self.inserted_rows)


def _scored_row():
    return {
        "set_id": "00000000-0000-0000-0000-000000000001",
        "set_name": "Prismatic Evolutions",
        "set_canonical_key": "prismaticEvolutions",
        "v2_component_row_id": "11111111-1111-1111-1111-111111111111",
        "calculation_run_id": "22222222-2222-2222-2222-222222222222",
        "primary_rip_desirability_score": 79.5,
        "rip_desirability_rank_70_30": 2,
        "pure_desirability_score": 91.1,
        "pure_desirability_rank": 1,
        "monetary_chase_appeal_score": 52.6,
        "monetary_chase_appeal_rank": 7,
        "monetary_data_quality": "usable",
        "rip_desirability_score_80_20": 83.4,
        "rip_desirability_score_70_30": 79.5,
        "rip_desirability_score_60_40": 75.7,
    }

