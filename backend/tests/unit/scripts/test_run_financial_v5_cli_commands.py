"""CLI: every command is implemented, dry-run by default, never activates, never builds ad hoc V5 on --commit."""
import inspect
import pytest

from backend.scripts import run_financial_v5_candidate as cli
from backend.db.services import budget_ranking_v2_orchestration as o2


def test_all_commands_are_registered_and_none_is_a_placeholder():
    assert set(cli.COMMANDS) == {"finalize-v5", "shadow", "build-v14", "ranking-v2", "best-open-v3", "readiness"}
    assert "later step" not in inspect.getsource(cli)


def test_commit_is_explicit_and_the_waiver_is_diagnostic_only():
    p = cli.build_parser()
    a = p.parse_args(["readiness"])
    assert a.commit is False and a.waive_best_open_v3 is False
    assert p.parse_args(["readiness", "--waive-best-open-v3"]).waive_best_open_v3 is True
    assert p.parse_args(["build-v14", "--commit"]).commit is True


def test_no_command_can_activate_or_move_a_pointer():
    src = inspect.getsource(cli)
    for forbidden in ("promote_pokemon_overall_rip_publication", "pokemon_overall_rip_current_publication", "activate_"):
        assert forbidden not in src


def test_commit_path_refuses_when_persisted_v5_is_not_ready(monkeypatch):
    monkeypatch.setattr(cli, "resolve_cohort_date", lambda c, d, **k: {"cohortDate": "2026-09-15"})
    monkeypatch.setattr(cli, "_persisted_v5_rows_or_report",
                        lambda c, d: (None, {"status": "not_ready", "reason": "financial_v5_schema_not_landed"}))
    for handler in (cli.cmd_build_v14, cli.cmd_ranking_v2):
        args = cli.build_parser().parse_args(["build-v14", "--commit"])
        out = handler(object(), args)
        assert out["status"] == "not_ready" and out["reason"] == "financial_v5_schema_not_landed"


def test_best_open_v3_reports_not_ready_without_a_ranking_v2_snapshot(capsys):
    class Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self):
            class R: data = []
            return R()

    class C:
        def table(self, name): return Q()
    args = cli.build_parser().parse_args(["best-open-v3"])
    out = cli.cmd_best_open_v3(C(), args)
    assert out["status"] == "not_ready" and out["reason"] == "no_live_ranking_v2_snapshot" and out["dryRun"] is True


def test_main_exits_nonzero_on_not_ready(monkeypatch):
    monkeypatch.setattr(cli, "_client", lambda: object())
    monkeypatch.setitem(cli.COMMANDS, "readiness", lambda c, a: {"status": "not_ready"})
    assert cli.main(["readiness"]) == 1


def test_o2_not_ready_carries_reason():
    with pytest.raises(o2.RankingV2NotReady) as e:
        o2.require_v5_source_rows([{"sealed_product_id": "x"}])
    assert e.value.reason == "financial_v5_source_rows_not_ready"
