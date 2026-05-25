import pytest

from backend.scripts import repair_swsh_controlled_persistence_execute_closure as repair


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, table_rows):
        self._table_name = table_name
        self._table_rows = table_rows
        self._id_filter = None
        self._limit = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        if str(column) == "id":
            self._id_filter = str(value)
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def execute(self):
        rows = list(self._table_rows)
        if self._id_filter is not None:
            rows = [row for row in rows if str(row.get("id")) == self._id_filter]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Response(rows)


class _FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, table_name):
        return _Query(str(table_name), self._tables.get(str(table_name), []))


def _good_identifiers():
    return {
        "swsh6": {
            "parent_run_id": "run-swsh6",
            "simulation_summary_id": "summary-swsh6",
        },
        "swsh7": {
            "parent_run_id": "run-swsh7",
            "simulation_summary_id": "summary-swsh7",
        },
    }


def _good_tables():
    return {
        "calculation_runs": [
            {"id": "run-swsh6"},
            {"id": "run-swsh7"},
        ],
        "simulation_run_summary": [
            {"id": "summary-swsh6", "calculation_run_id": "run-swsh6"},
            {"id": "summary-swsh7", "calculation_run_id": "run-swsh7"},
        ],
    }


def test_repair_refuses_when_required_run_id_missing(tmp_path, monkeypatch):
    ids = _good_identifiers()
    ids["swsh7"]["parent_run_id"] = ""

    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(_good_tables()))

    with pytest.raises(AssertionError, match="swsh7: parent_run_id is required"):
        repair.run_repair(
            json_output_path=tmp_path / "repair.json",
            markdown_output_path=tmp_path / "repair.md",
            identifiers_by_set=ids,
            fail_on_blockers=True,
        )


def test_repair_refuses_when_calculation_runs_row_missing(tmp_path, monkeypatch):
    tables = _good_tables()
    tables["calculation_runs"] = [{"id": "run-swsh6"}]

    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(tables))

    with pytest.raises(AssertionError, match="swsh7: calculation_runs row not found"):
        repair.run_repair(
            json_output_path=tmp_path / "repair.json",
            markdown_output_path=tmp_path / "repair.md",
            identifiers_by_set=_good_identifiers(),
            fail_on_blockers=True,
        )


def test_repair_refuses_when_simulation_run_summary_row_missing(tmp_path, monkeypatch):
    tables = _good_tables()
    tables["simulation_run_summary"] = [{"id": "summary-swsh6", "calculation_run_id": "run-swsh6"}]

    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(tables))

    with pytest.raises(AssertionError, match="swsh7: simulation_run_summary row not found"):
        repair.run_repair(
            json_output_path=tmp_path / "repair.json",
            markdown_output_path=tmp_path / "repair.md",
            identifiers_by_set=_good_identifiers(),
            fail_on_blockers=True,
        )


def test_repair_refuses_when_summary_not_owned_by_expected_run_id(tmp_path, monkeypatch):
    tables = _good_tables()
    tables["simulation_run_summary"] = [
        {"id": "summary-swsh6", "calculation_run_id": "run-swsh6"},
        {"id": "summary-swsh7", "calculation_run_id": "wrong-run"},
    ]

    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(tables))

    with pytest.raises(AssertionError, match="swsh7: simulation_run_summary summary-swsh7 does not belong to run_id=run-swsh7"):
        repair.run_repair(
            json_output_path=tmp_path / "repair.json",
            markdown_output_path=tmp_path / "repair.md",
            identifiers_by_set=_good_identifiers(),
            fail_on_blockers=True,
        )


def test_repair_marks_db_mutation_false(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(_good_tables()))

    closure = repair.run_repair(
        json_output_path=tmp_path / "repair.json",
        markdown_output_path=tmp_path / "repair.md",
        identifiers_by_set=_good_identifiers(),
        fail_on_blockers=True,
    )

    assert closure["db_mutation_performed"] is False


def test_repair_marks_execute_rerun_false(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(_good_tables()))

    closure = repair.run_repair(
        json_output_path=tmp_path / "repair.json",
        markdown_output_path=tmp_path / "repair.md",
        identifiers_by_set=_good_identifiers(),
        fail_on_blockers=True,
    )

    assert closure["execute_rerun_performed"] is False


def test_repair_closes_when_all_read_only_checks_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.supabase_client, "supabase", _FakeSupabase(_good_tables()))

    closure = repair.run_repair(
        json_output_path=tmp_path / "repair.json",
        markdown_output_path=tmp_path / "repair.md",
        identifiers_by_set=_good_identifiers(),
        fail_on_blockers=True,
    )

    assert closure["final_decision"] == "closed_controlled_persistence_executed_and_verified"
    assert closure["read_only_db_verification"]["passed"] is True
    assert closure["safety_passed"] is True
