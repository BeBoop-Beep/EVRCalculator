"""Operator CLI for the V5/V14 candidate: dry-run default, read-only shadow, never in the daily path."""
import importlib
import inspect

import pytest

from backend.db.services import v5_shadow_runner as sr
from backend.scripts import run_financial_v5_candidate as cli


def test_commit_is_opt_in_and_defaults_to_a_dry_run():
    assert cli.build_parser().parse_args(["finalize-v5"]).commit is False
    assert cli.build_parser().parse_args(["finalize-v5", "--commit"]).commit is True


@pytest.mark.parametrize("command", ["shadow", "readiness"])
def test_read_only_commands_reject_commit(command):
    with pytest.raises(SystemExit, match="read-only"):
        cli.main([command, "--commit"])


def test_every_registered_command_has_a_handler():
    assert set(cli.COMMANDS) >= {"finalize-v5", "shadow", "build-v14", "ranking-v2", "best-open-v3", "readiness"}


def test_finalize_command_passes_dry_run_true_by_default(monkeypatch):
    seen = {}

    def fake_finalize(client, **kw):
        seen.update(kw)
        return {"status": "ok", "marketDate": "d", "dryRun": kw["dry_run"], "cohortRunCount": 0, "rowsConsidered": 0,
                "rowsReady": 0, "rowsUnavailable": 0, "unavailableReasons": {}, "rowsSkipped": 0, "artifactLoads": 0,
                "distributionBuilds": 0, "cohortComplete": False, "elapsedMs": 0, "results": []}
    import backend.db.services.sealed_product_financial_v5_finalization_service as svc
    monkeypatch.setattr(svc, "finalize_financial_rip_v5", fake_finalize)
    monkeypatch.setattr(cli, "_client", lambda: object())
    monkeypatch.setattr(cli, "resolve_cohort_date", lambda c, e: {"promotedDate": "d", "cohortDate": "d"})
    monkeypatch.setattr(cli, "_write_json", lambda *a, **k: None)
    assert cli.main(["finalize-v5"]) == 0
    assert seen["dry_run"] is True


def test_neither_the_cli_nor_the_shadow_runner_can_write():
    for mod in (sr, cli):
        src = inspect.getsource(mod)
        for forbidden in (".insert(", ".upsert(", ".update(", ".delete(", ".rpc("):
            assert forbidden not in src, (mod.__name__, forbidden)


def test_the_daily_publication_orchestrator_does_not_import_the_candidate_cli():
    src = inspect.getsource(importlib.import_module("backend.scripts.run_daily_opening_publication"))
    assert "run_financial_v5_candidate" not in src and "v5_shadow_runner" not in src


def test_compare_models_reports_rank_movement_and_top_overlap():
    old = {f"p{i}": 100.0 - i for i in range(30)}
    new = dict(old)
    new["p0"], new["p1"] = old["p1"], old["p0"]  # swap the top two
    r = sr.compare_models(old, new, label="t")
    assert r["n"] == 30 and r["topOverlap"]["5"] == 5 and r["rankMoveCounts"]["1-2"] == 2
    assert r["deltaMax"] > 0 > r["deltaMin"] and r["spearman"] > 0.99
