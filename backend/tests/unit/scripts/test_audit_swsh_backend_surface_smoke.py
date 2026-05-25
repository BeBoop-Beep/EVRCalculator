import json

import pytest

from backend.scripts import audit_swsh_backend_surface_smoke as project12


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)
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
        rows = list(self._rows)
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
        return _Query(self._tables.get(str(table_name), []))


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


def _good_summary(run_id):
    return {
        "calculation_run_id": run_id,
        "pack_cost": 4.0,
        "mean_value": 5.0,
        "median_value": 4.5,
        "roi": 0.25,
        "roi_percent": 25.0,
        "prob_profit": 0.5,
        "mean_value_to_cost_ratio": 1.25,
        "p95_value_to_cost_ratio": 1.8,
        "derived_metric_version": "formula_roi_v2",
        "score_version": "pack_score_v2",
        "normalization_mode": "cross_set",
    }


def _good_explore_payload():
    return {
        "summary": {
            "pack_cost": 4.0,
            "mean_value": 5.0,
            "median_value": 4.5,
            "roi": 0.25,
            "roi_percent": 25.0,
            "prob_profit": 0.5,
        },
        "rankings": [{"rarity_bucket": "rare", "pulled_count": 10}],
        "percentiles": [{"percentile": 95, "value": 9.0}],
        "distribution_bins": [{"bin_floor": 0.0, "bin_ceiling": 1.0}],
        "threshold_bins": [{"bucket_order": 1, "bucket_label": "loss"}],
        "meta": {
            "sources": {
                "simulation_pull_summary": "OK",
                "simulation_percentiles": "OK",
                "simulation_value_distribution_bins": "OK",
                "simulation_value_threshold_bins": "OK",
            }
        },
    }


def _good_targets_payload():
    return {
        "targets": [
            {"target_id": "swsh6", "target_type": "set"},
            {"target_id": "swsh7", "target_type": "set"},
        ]
    }


def _good_tables():
    return {
        "explore_rip_statistics_latest": [
            {
                "set_id": "swsh6",
                "calculation_run_id": "run-swsh6",
                "pack_score": 71.0,
                "pack_cost": 4.0,
                "mean_value": 5.0,
                "median_value": 4.5,
                "roi_percent": 25.0,
                "prob_profit": 0.5,
                "mean_value_to_cost_ratio": 1.25,
                "p95_value_to_cost_ratio": 1.8,
            },
            {
                "set_id": "swsh7",
                "calculation_run_id": "run-swsh7",
                "pack_score": 72.0,
                "pack_cost": 4.0,
                "mean_value": 5.2,
                "median_value": 4.6,
                "roi_percent": 30.0,
                "prob_profit": 0.52,
                "mean_value_to_cost_ratio": 1.30,
                "p95_value_to_cost_ratio": 1.9,
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


def _patch_clients(monkeypatch, tables):
    fake = _FakeSupabase(tables)
    monkeypatch.setattr(project12.supabase_client, "public_read_client", fake)
    monkeypatch.setattr(project12.supabase_client, "supabase", fake)


def _patch_services(monkeypatch, *, bad_json=False, raise_explore=False):
    if raise_explore:
        def _boom_explore(*_args, **_kwargs):
            raise RuntimeError("explore failed")
        monkeypatch.setattr(project12, "get_explore_page_payload", _boom_explore)
    else:
        monkeypatch.setattr(project12, "get_explore_page_payload", lambda **_kwargs: _good_explore_payload())

    if bad_json:
        monkeypatch.setattr(project12, "get_latest_evr_run_snapshot", lambda **_kwargs: {"summary": {"bad": {1, 2, 3}}})
    else:
        monkeypatch.setattr(project12, "get_latest_evr_run_snapshot", lambda **kwargs: {"summary": _good_summary(kwargs["target_id"].replace("swsh", "run-swsh")), "calculation_run_id": kwargs["target_id"].replace("swsh", "run-swsh")})

    monkeypatch.setattr(project12, "get_rip_statistics_targets_payload", lambda **_kwargs: _good_targets_payload())


def test_fails_if_latest_explore_row_missing(tmp_path, monkeypatch):
    tables = _good_tables()
    tables["explore_rip_statistics_latest"] = [row for row in tables["explore_rip_statistics_latest"] if row["set_id"] != "swsh7"]
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch)

    with pytest.raises(AssertionError, match="latest explore_rip_statistics_latest row missing"):
        project12.run_backend_surface_smoke(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_latest_run_id_mismatch(tmp_path, monkeypatch):
    tables = _good_tables()
    for row in tables["simulation_latest_by_target"]:
        if row["target_id"] == "swsh7":
            row["calculation_run_id"] = "wrong-run"
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch)

    with pytest.raises(AssertionError, match="latest run id mismatch"):
        project12.run_backend_surface_smoke(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_critical_pack_fields_null(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)

    monkeypatch.setattr(project12, "get_explore_page_payload", lambda **_kwargs: _good_explore_payload())
    monkeypatch.setattr(project12, "get_rip_statistics_targets_payload", lambda **_kwargs: _good_targets_payload())

    def _bad_snapshot(**kwargs):
        run_id = kwargs["target_id"].replace("swsh", "run-swsh")
        summary = _good_summary(run_id)
        summary["pack_cost"] = None
        return {"summary": summary, "calculation_run_id": run_id}

    monkeypatch.setattr(project12, "get_latest_evr_run_snapshot", _bad_snapshot)

    with pytest.raises(AssertionError, match="critical fields are null/missing"):
        project12.run_backend_surface_smoke(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_payload_not_json_serializable(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch, bad_json=True)

    with pytest.raises(AssertionError, match="payload not JSON serializable"):
        project12.run_backend_surface_smoke(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_fails_if_service_read_path_errors(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch, raise_explore=True)

    with pytest.raises(AssertionError, match="explore page service"):
        project12.run_backend_surface_smoke(
            json_output_path=tmp_path / "out.json",
            markdown_output_path=tmp_path / "out.md",
            identifiers_by_set=_ids(),
            fail_on_blockers=True,
        )


def test_closes_verified_when_all_surfaces_pass(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch)

    payload = project12.run_backend_surface_smoke(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=True,
    )

    assert payload["final_decision"] == "closed_backend_surface_smoke_verified"
    assert payload["blockers"] == []
    assert payload["read_path_gap_blockers"] == []
    assert payload["payloads_json_serializable"] is True

    saved = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert saved["final_decision"] == "closed_backend_surface_smoke_verified"


def test_blocks_when_latest_snapshot_service_returns_wrong_run(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)

    monkeypatch.setattr(project12, "get_explore_page_payload", lambda **_kwargs: _good_explore_payload())
    monkeypatch.setattr(project12, "get_rip_statistics_targets_payload", lambda **_kwargs: _good_targets_payload())

    def _wrong_snapshot(**kwargs):
        run_id = kwargs["target_id"].replace("swsh", "run-swsh")
        summary = _good_summary(run_id)
        return {
            "calculation_run_id": f"wrong-{run_id}",
            "summary": summary,
        }

    monkeypatch.setattr(project12, "get_latest_evr_run_snapshot", _wrong_snapshot)

    payload = project12.run_backend_surface_smoke(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=False,
    )

    assert payload["final_decision"] == "closed_backend_surface_smoke_blocked_on_read_path_gap"
    assert any("latest snapshot service" in item for item in payload["read_path_gap_blockers"])


def test_confirms_read_only_flags_false(tmp_path, monkeypatch):
    tables = _good_tables()
    _patch_clients(monkeypatch, tables)
    _patch_services(monkeypatch)

    payload = project12.run_backend_surface_smoke(
        json_output_path=tmp_path / "out.json",
        markdown_output_path=tmp_path / "out.md",
        identifiers_by_set=_ids(),
        fail_on_blockers=True,
    )

    assert payload["db_mutation_performed"] is False
    assert payload["execute_rerun_performed"] is False
