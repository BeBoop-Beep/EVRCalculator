import pytest

from backend.scripts import audit_swsh_post_persistence_surface_verification as project11


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, table_rows):
        self._table_name = table_name
        self._table_rows = list(table_rows)
        self._filters = []
        self._order_by = None
        self._desc = False
        self._limit = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self._filters.append((str(column), value))
        return self

    def order(self, column, desc=False):
        self._order_by = str(column)
        self._desc = bool(desc)
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def execute(self):
        rows = list(self._table_rows)
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]

        if self._order_by:
            rows.sort(key=lambda row: row.get(self._order_by) or "", reverse=self._desc)

        if self._limit is not None:
            rows = rows[: self._limit]

        return _Response(rows)


class _FakeSupabase:
    def __init__(self, tables):
        self._tables = tables

    def table(self, table_name):
        return _Query(str(table_name), self._tables.get(str(table_name), []))


def _ids():
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


def _summary_row(run_id, row_id):
    return {
        "id": row_id,
        "calculation_run_id": run_id,
        "pack_cost": 4.0,
        "mean_value": 5.0,
        "median_value": 4.7,
        "roi": 0.25,
        "roi_percent": 25.0,
        "prob_profit": 0.52,
    }


def _derived_row(run_id):
    return {
        "id": f"derived-{run_id}",
        "calculation_run_id": run_id,
        "pack_score": 71.0,
        "p95_value_to_cost_ratio": 1.8,
        "mean_value_to_cost_ratio": 1.2,
        "derived_metric_version": "formula_roi_v2",
        "score_version": "pack_score_v2",
        "normalization_mode": "cross_set",
    }


def _build_good_tables():
    rows = {
        "calculation_runs": [
            {
                "id": "run-swsh6",
                "target_type": "set",
                "target_id": "swsh6",
                "calculation_config_id": "cfg-swsh6",
                "created_at": "2026-05-20T10:00:00Z",
            },
            {
                "id": "run-swsh7",
                "target_type": "set",
                "target_id": "swsh7",
                "calculation_config_id": "cfg-swsh7",
                "created_at": "2026-05-20T11:00:00Z",
            },
        ],
        "calculation_configs": [
            {"id": "cfg-swsh6"},
            {"id": "cfg-swsh7"},
        ],
        "simulation_run_summary": [
            _summary_row("run-swsh6", "summary-swsh6"),
            _summary_row("run-swsh7", "summary-swsh7"),
        ],
        "calculation_price_snapshots": [
            {"calculation_run_id": "run-swsh6"},
            {"calculation_run_id": "run-swsh6"},
            {"calculation_run_id": "run-swsh7"},
            {"calculation_run_id": "run-swsh7"},
        ],
        "simulation_input_cards": [
            *[{"calculation_run_id": "run-swsh6"} for _ in range(235)],
            *[{"calculation_run_id": "run-swsh7"} for _ in range(235)],
        ],
        "simulation_percentiles": [
            *[{"calculation_run_id": "run-swsh6", "percentile": p, "value": 1.0} for p in (1, 5, 25, 50, 75, 95, 99)],
            *[{"calculation_run_id": "run-swsh7", "percentile": p, "value": 1.0} for p in (1, 5, 25, 50, 75, 95, 99)],
        ],
        "simulation_pull_summary": [
            *[{"calculation_run_id": "run-swsh6", "rarity_bucket": f"r{i}"} for i in range(14)],
            *[{"calculation_run_id": "run-swsh7", "rarity_bucket": f"r{i}"} for i in range(14)],
        ],
        "simulation_state_counts": [
            {"calculation_run_id": "run-swsh6"},
            {"calculation_run_id": "run-swsh7"},
        ],
        "simulation_derived_metrics": [
            _derived_row("run-swsh6"),
            _derived_row("run-swsh7"),
        ],
        "simulation_value_distribution_bins": [
            *[{"calculation_run_id": "run-swsh6"} for _ in range(50)],
            *[{"calculation_run_id": "run-swsh7"} for _ in range(50)],
        ],
        "simulation_value_threshold_bins": [
            *[{"calculation_run_id": "run-swsh6"} for _ in range(18)],
            *[{"calculation_run_id": "run-swsh7"} for _ in range(18)],
        ],
        "explore_rip_statistics_latest": [
            {
                "set_id": "swsh6",
                "calculation_run_id": "run-swsh6",
                "pack_score": 71.0,
                "pack_cost": 4.0,
                "mean_value": 5.0,
                "median_value": 4.7,
                "roi_percent": 25.0,
                "prob_profit": 0.52,
                "p95_value_to_cost_ratio": 1.8,
                "mean_value_to_cost_ratio": 1.2,
            },
            {
                "set_id": "swsh7",
                "calculation_run_id": "run-swsh7",
                "pack_score": 72.0,
                "pack_cost": 4.0,
                "mean_value": 5.1,
                "median_value": 4.8,
                "roi_percent": 26.0,
                "prob_profit": 0.53,
                "p95_value_to_cost_ratio": 1.9,
                "mean_value_to_cost_ratio": 1.25,
            },
        ],
        "simulation_latest_by_target": [
            {"target_type": "set", "target_id": "swsh6", "calculation_run_id": "run-swsh6", "run_at": "2026-05-20T10:00:00Z"},
            {"target_type": "set", "target_id": "swsh7", "calculation_run_id": "run-swsh7", "run_at": "2026-05-20T11:00:00Z"},
        ],
        "set_pack_score_rankings_latest": [
            {"target_id": "swsh6", "calculation_run_id": "run-swsh6"},
            {"target_id": "swsh7", "calculation_run_id": "run-swsh7"},
        ],
    }
    return rows


def _patch_clients(monkeypatch, tables):
    fake = _FakeSupabase(tables)
    monkeypatch.setattr(project11.supabase_client, "supabase", fake)
    monkeypatch.setattr(project11.supabase_client, "public_read_client", fake)


def test_fails_if_parent_run_row_missing(tmp_path, monkeypatch):
    tables = _build_good_tables()
    tables["calculation_runs"] = [row for row in tables["calculation_runs"] if row["id"] != "run-swsh7"]
    _patch_clients(monkeypatch, tables)

    with pytest.raises(AssertionError, match="swsh7: calculation_runs row missing"):
        project11.run_post_persistence_surface_verification(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_summary_row_missing(tmp_path, monkeypatch):
    tables = _build_good_tables()
    tables["simulation_run_summary"] = [row for row in tables["simulation_run_summary"] if row["id"] != "summary-swsh7"]
    _patch_clients(monkeypatch, tables)

    with pytest.raises(AssertionError, match="swsh7: simulation_run_summary row missing"):
        project11.run_post_persistence_surface_verification(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_summary_belongs_to_wrong_run(tmp_path, monkeypatch):
    tables = _build_good_tables()
    for row in tables["simulation_run_summary"]:
        if row["id"] == "summary-swsh7":
            row["calculation_run_id"] = "wrong-run"
    _patch_clients(monkeypatch, tables)

    with pytest.raises(AssertionError, match="swsh7: simulation_run_summary summary-swsh7 does not belong to run_id=run-swsh7"):
        project11.run_post_persistence_surface_verification(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_expected_table_count_is_zero(tmp_path, monkeypatch):
    tables = _build_good_tables()
    tables["simulation_percentiles"] = [
        row for row in tables["simulation_percentiles"] if row["calculation_run_id"] != "run-swsh7"
    ]
    _patch_clients(monkeypatch, tables)

    with pytest.raises(AssertionError, match="swsh7: simulation_percentiles expected=7 actual=0"):
        project11.run_post_persistence_surface_verification(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_reports_valid_but_not_latest_when_read_surface_points_elsewhere(tmp_path, monkeypatch):
    tables = _build_good_tables()
    for row in tables["explore_rip_statistics_latest"]:
        if row["set_id"] == "swsh7":
            row["calculation_run_id"] = "older-swsh7"
    _patch_clients(monkeypatch, tables)

    payload = project11.run_post_persistence_surface_verification(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=False,
    )

    assert payload["final_decision"] == "closed_persistence_valid_but_not_latest_surface_visible"
    assert payload["db_mutation_performed"] is False
    assert payload["execute_rerun_performed"] is False


def test_closes_verified_when_rows_counts_and_read_surfaces_pass(tmp_path, monkeypatch):
    tables = _build_good_tables()
    _patch_clients(monkeypatch, tables)

    payload = project11.run_post_persistence_surface_verification(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=True,
    )

    assert payload["final_decision"] == "closed_post_persistence_surface_verified"
    assert payload["newly_persisted_runs_selected_as_latest"] is True
    assert payload["downstream_readiness_status"] == "ready"


def test_confirms_read_only_flags_false(tmp_path, monkeypatch):
    tables = _build_good_tables()
    _patch_clients(monkeypatch, tables)

    payload = project11.run_post_persistence_surface_verification(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=True,
    )

    assert payload["db_mutation_performed"] is False
    assert payload["execute_rerun_performed"] is False
