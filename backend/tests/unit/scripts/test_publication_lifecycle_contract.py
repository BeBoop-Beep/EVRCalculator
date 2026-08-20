"""Publication lifecycle: honest exit codes, cache invalidation, daily advance.

Three defects and one lifecycle contract are covered here:

* Direct market publishers counted failed sets but still exited 0, so the
  orchestration script (which trusts child exit codes) reported a fully
  successful publication after silent per-set failures.
* Cache invalidation only ran from the stale-refresh workflow, so a direct
  rebuild could publish new snapshot rows while the frontend kept serving an
  older cached seed.
* The daily cycle must advance from one completed market date to the next
  without an operator running any snapshot command by hand, including a
  deterministic automatic retry after a deferred publication.
"""

import sys
import types

import pytest

from backend.db.services import set_publication_revalidation as revalidation
from backend.db.services.pokemon_set_market_service import PokemonSetMarketError
from backend.scripts import build_pokemon_market_dashboard_snapshots as market_cmd
from backend.scripts import build_pokemon_public_snapshots as orchestration
from backend.scripts import build_pokemon_set_cards_snapshots as cards_cmd
from backend.scripts import build_pokemon_set_page_snapshots as page_cmd
from backend.scripts import refresh_stale_public_snapshots as refresh


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _capture_revalidations(monkeypatch, module):
    """Record every publish-success revalidation the module performs."""
    calls = []

    def _fake(set_row, *, window=None, commit=True, seen=None):
        if not commit:
            return False
        identifiers = revalidation.resolve_set_revalidation_identifiers(set_row)
        if seen is not None:
            if identifiers[0] in seen:
                return False
            seen.add(identifiers[0])
        calls.append(
            {
                "identifiers": identifiers,
                "windows": revalidation.resolve_revalidation_windows(window),
            }
        )
        return True

    monkeypatch.setattr(module, "notify_set_publication", _fake)
    return calls


def _run_market(monkeypatch, *, build, sets, argv=None, gate_mode="disabled"):
    # Market artifacts are gated by Market Date Quality, whose local/test
    # disable is a SEPARATE variable so turning off the batch gate can never
    # silently turn off Market quality. These lifecycle cases exercise the
    # build loop, not gating, so both move in lockstep.
    if gate_mode is None:
        monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
        monkeypatch.delenv("MARKET_PUBLICATION_GATE_MODE", raising=False)
    else:
        monkeypatch.setenv("PUBLICATION_GATE_MODE", gate_mode)
        monkeypatch.setenv("MARKET_PUBLICATION_GATE_MODE", gate_mode)
    monkeypatch.setattr(market_cmd, "get_client", lambda: object())
    monkeypatch.setattr(market_cmd, "resolve_target_sets", lambda _c, _a: sets)
    monkeypatch.setattr(market_cmd, "build_coordinated_set_market_snapshot_rows", build)
    monkeypatch.setattr(market_cmd, "refresh_canonical_card_market_prices_for_set", lambda *_a, **_k: None)
    monkeypatch.setattr(
        sys,
        "argv",
        argv or ["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit", "--delay-seconds", "0"],
    )
    return market_cmd.main()


def _ok_rows(set_row, **_kwargs):
    return ({"set_id": set_row["id"]}, {"set_id": set_row["id"], "window_key": "365d"}, [])


_SETS = [
    {"id": "uuid-1", "canonical_key": "alpha", "pokemon_api_set_id": "sv1", "name": "Alpha"},
    {"id": "uuid-2", "canonical_key": "beta", "pokemon_api_set_id": "sv2", "name": "Beta"},
]


# --------------------------------------------------------------------------- #
# Defect 3 — honest CLI exit codes
# --------------------------------------------------------------------------- #
def test_market_cli_exits_zero_when_every_set_builds(monkeypatch, capsys):
    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: None)
    code = _run_market(monkeypatch, build=_ok_rows, sets=_SETS)
    assert code == 0
    assert "built=2 skipped=0 failed=0" in capsys.readouterr().out


def test_market_cli_exits_one_on_a_single_genuine_failure(monkeypatch, capsys):
    def build(set_row, **_kwargs):
        if set_row["id"] == "uuid-2":
            raise RuntimeError("movement parity exploded")
        return _ok_rows(set_row)

    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: None)
    code = _run_market(monkeypatch, build=build, sets=_SETS)
    # Mixed success and failure is still a FAILURE: one good set must not hide it.
    assert code == 1
    assert "built=1 skipped=0 failed=1" in capsys.readouterr().out


def test_market_cli_exits_zero_for_documented_graceful_skips(monkeypatch, capsys):
    def build(set_row, **_kwargs):
        if set_row["id"] == "uuid-2":
            raise PokemonSetMarketError(status_code=404, message="set not found", code="NOT_FOUND")
        return _ok_rows(set_row)

    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: None)
    code = _run_market(monkeypatch, build=build, sets=_SETS)
    assert code == 0
    assert "built=1 skipped=1 failed=0" in capsys.readouterr().out


def test_market_cli_defers_with_three_and_writes_nothing_when_gate_closed(monkeypatch):
    writes = []
    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: writes.append(1))
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: writes.append(1))
    calls = _capture_revalidations(monkeypatch, market_cmd)
    code = _run_market(
        monkeypatch,
        build=_ok_rows,
        sets=_SETS,
        argv=["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit"],
        gate_mode=None,  # real (required) gate + object() client => closed
    )
    assert code == 3
    assert writes == []
    assert calls == []


def test_cards_cli_exits_one_when_a_set_fails(monkeypatch, capsys):
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(cards_cmd, "get_client", lambda: object())
    monkeypatch.setattr(cards_cmd, "resolve_target_sets", lambda _c, _a: _SETS)
    monkeypatch.setattr(cards_cmd, "refresh_canonical_card_market_prices_for_set", lambda *_a, **_k: None)
    monkeypatch.setattr(cards_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(cards_cmd, "upsert_rows", lambda *_a, **_k: None)

    def build(set_row, **_kwargs):
        if set_row["id"] == "uuid-2":
            raise RuntimeError("boom")
        return _ok_rows(set_row)

    monkeypatch.setattr(cards_cmd, "build_coordinated_set_market_snapshot_rows", build)
    monkeypatch.setattr(
        sys, "argv", ["build_pokemon_set_cards_snapshots.py", "--all", "--commit", "--delay-seconds", "0"]
    )
    code = cards_cmd.main()
    assert code == 1
    assert "built=1 failed=1" in capsys.readouterr().out


def test_delegated_market_entry_point_propagates_the_exit_code():
    """build_pokemon_set_market_snapshots.py must not swallow main()'s result."""
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[4]
    source = (repo_root / "backend" / "scripts" / "build_pokemon_set_market_snapshots.py").read_text(
        encoding="utf-8"
    )
    assert "raise SystemExit(main())" in source


# --------------------------------------------------------------------------- #
# Defect 3 — orchestration must not report success over hidden child failures
# --------------------------------------------------------------------------- #
def _stub_orchestration_gate(monkeypatch, *, proceed=True, exit_code=0):
    enforcement = types.SimpleNamespace(
        decision=types.SimpleNamespace(reason_code="test", reason="test"),
        proceed=proceed,
        exit_code=exit_code,
    )
    monkeypatch.setattr(orchestration, "get_client", lambda: object())
    monkeypatch.setattr(orchestration, "enforce_cli_publication_gate", lambda *_a, **_k: enforcement)


@pytest.mark.parametrize("failing_step", ["coordinated set cards and market dashboards", "set pages"])
def test_orchestration_reports_failure_when_a_market_child_exits_one(monkeypatch, caplog, failing_step):
    _stub_orchestration_gate(monkeypatch)
    monkeypatch.setattr(orchestration, "_run_step", lambda label, args: 1 if label == failing_step else 0)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    with caplog.at_level("INFO"):
        with pytest.raises(SystemExit) as excinfo:
            orchestration.main()

    assert excinfo.value.code == 1
    assert "all 3 steps succeeded" not in caplog.text
    assert "failed step(s)" in caplog.text


def test_orchestration_reports_deferred_when_a_child_exits_three(monkeypatch, caplog):
    _stub_orchestration_gate(monkeypatch)
    monkeypatch.setattr(
        orchestration,
        "_run_step",
        lambda label, args: 3 if label == "coordinated set cards and market dashboards" else 0,
    )
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    with caplog.at_level("INFO"):
        with pytest.raises(SystemExit) as excinfo:
            orchestration.main()

    assert excinfo.value.code == 3
    assert "all 3 steps succeeded" not in caplog.text
    assert "DEFERRED" in caplog.text


# --------------------------------------------------------------------------- #
# Defect 2 — publish-success cache invalidation coverage
# --------------------------------------------------------------------------- #
def test_coordinated_commit_revalidates_once_after_all_writes_succeed(monkeypatch):
    order = []
    monkeypatch.setattr(
        market_cmd, "upsert_row", lambda _c, table, *_a, **_k: order.append(table)
    )
    monkeypatch.setattr(
        market_cmd, "upsert_rows", lambda _c, table, *_a, **_k: order.append(table)
    )
    calls = _capture_revalidations(monkeypatch, market_cmd)

    code = _run_market(monkeypatch, build=_ok_rows, sets=_SETS[:1])

    assert code == 0
    # Cards -> Top Chase daily history -> dashboard, and only THEN revalidation.
    assert order == [
        "pokemon_set_cards_snapshot_latest",
        "pokemon_set_top_chase_card_daily_history",
        "pokemon_set_market_dashboard_snapshot_latest",
    ]
    assert len(calls) == 1
    # Every identifier the frontend may address the set by.
    assert calls[0]["identifiers"] == ["alpha", "uuid-1", "sv1"]
    # The requested window plus the standard Overview windows.
    assert calls[0]["windows"][0] == "365d"
    assert set(revalidation.DEFAULT_OVERVIEW_WINDOWS).issubset(set(calls[0]["windows"]))


def test_dry_run_performs_no_revalidation_and_no_writes(monkeypatch):
    seen_commit = []
    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, commit=None, **_k: seen_commit.append(commit))
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, commit=None, **_k: seen_commit.append(commit))
    calls = _capture_revalidations(monkeypatch, market_cmd)

    code = _run_market(
        monkeypatch,
        build=_ok_rows,
        sets=_SETS,
        argv=["build_pokemon_market_dashboard_snapshots.py", "--all", "--dry-run", "--delay-seconds", "0"],
    )

    assert code == 0
    assert seen_commit and all(value is False for value in seen_commit)
    assert calls == []


def test_partial_coordinated_write_failure_performs_no_success_revalidation(monkeypatch):
    """A dashboard write failure must not leave a 'revalidated' claim behind."""
    written = []

    def upsert_row(_client, table, *_a, **_k):
        if table == "pokemon_set_market_dashboard_snapshot_latest":
            raise RuntimeError("dashboard write failed")
        written.append(table)

    monkeypatch.setattr(market_cmd, "upsert_row", upsert_row)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda _c, table, *_a, **_k: written.append(table))
    calls = _capture_revalidations(monkeypatch, market_cmd)

    code = _run_market(monkeypatch, build=_ok_rows, sets=_SETS[:1])

    assert code == 1  # the run FAILS
    assert "pokemon_set_cards_snapshot_latest" in written  # cards did write
    assert calls == []  # but nothing claimed a successful publication


def test_build_failure_performs_no_revalidation(monkeypatch):
    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: None)
    calls = _capture_revalidations(monkeypatch, market_cmd)

    def build(_set_row, **_kwargs):
        raise RuntimeError("builder exploded")

    code = _run_market(monkeypatch, build=build, sets=_SETS)
    assert code == 1
    assert calls == []


def test_set_page_commit_revalidates_after_success_only(monkeypatch):
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(page_cmd, "get_client", lambda: object())
    monkeypatch.setattr(page_cmd, "should_commit", lambda _a: True)
    monkeypatch.setattr(page_cmd, "resolve_target_sets", lambda _c, _a: _SETS)
    monkeypatch.setattr(page_cmd, "upsert_row", lambda *_a, **_k: None)
    calls = _capture_revalidations(monkeypatch, page_cmd)

    def build(set_row, client=None):
        if set_row["id"] == "uuid-2":
            raise RuntimeError("set page build failed")
        return {"set_id": set_row["id"]}

    monkeypatch.setattr(page_cmd, "build_set_page_snapshot_row", build)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])

    code = page_cmd.main()

    assert code == 1
    # Only the set that actually published is invalidated.
    assert [call["identifiers"][0] for call in calls] == ["alpha"]


def test_revalidation_failure_never_turns_a_publication_into_a_failure(monkeypatch, caplog):
    monkeypatch.setenv("SET_REVALIDATION_URL", "https://example.test/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "s3cret")

    def boom(*_a, **_k):
        raise ConnectionError("frontend unreachable")

    monkeypatch.setattr(revalidation.urllib.request, "urlopen", boom)

    with caplog.at_level("WARNING"):
        ok = revalidation.notify_set_publication({"canonical_key": "alpha", "id": "uuid-1"})

    assert ok is False  # reported, not raised
    assert "cache invalidation FAILED" in caplog.text


def test_revalidation_identifier_and_window_resolution():
    assert revalidation.resolve_set_revalidation_identifiers(
        {"canonical_key": "alpha", "id": "uuid-1", "pokemon_api_set_id": "sv1"}
    ) == ["alpha", "uuid-1", "sv1"]
    # Duplicates and blanks are dropped; a bare identifier still works.
    assert revalidation.resolve_set_revalidation_identifiers(
        {"canonical_key": "alpha", "id": "alpha", "pokemon_api_set_id": None}
    ) == ["alpha"]
    assert revalidation.resolve_set_revalidation_identifiers("alpha") == ["alpha"]
    # The requested window is always present, exactly once.
    windows = revalidation.resolve_revalidation_windows("365d")
    assert windows.count("365d") == 1
    assert set(revalidation.DEFAULT_OVERVIEW_WINDOWS).issubset(set(windows))
    assert revalidation.resolve_revalidation_windows(None) == list(
        revalidation.DEFAULT_OVERVIEW_WINDOWS
    )


def test_dry_run_helper_is_a_hard_no_op(monkeypatch):
    monkeypatch.setenv("SET_REVALIDATION_URL", "https://example.test/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "s3cret")
    called = []
    monkeypatch.setattr(revalidation.urllib.request, "urlopen", lambda *_a, **_k: called.append(1))

    assert revalidation.notify_set_publication({"canonical_key": "alpha"}, commit=False) is False
    assert called == []


def test_full_orchestration_covers_every_published_set(monkeypatch):
    """Each child publishes its own family, so each invalidates its own sets."""
    market_calls = _capture_revalidations(monkeypatch, market_cmd)
    page_calls = _capture_revalidations(monkeypatch, page_cmd)

    monkeypatch.setattr(market_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(market_cmd, "upsert_rows", lambda *_a, **_k: None)
    assert _run_market(monkeypatch, build=_ok_rows, sets=_SETS) == 0

    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(page_cmd, "get_client", lambda: object())
    monkeypatch.setattr(page_cmd, "should_commit", lambda _a: True)
    monkeypatch.setattr(page_cmd, "resolve_target_sets", lambda _c, _a: _SETS)
    monkeypatch.setattr(page_cmd, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(page_cmd, "build_set_page_snapshot_row", lambda set_row, client=None: {"set_id": set_row["id"]})
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])
    assert page_cmd.main() == 0

    assert [call["identifiers"][0] for call in market_calls] == ["alpha", "beta"]
    assert [call["identifiers"][0] for call in page_calls] == ["alpha", "beta"]


# --------------------------------------------------------------------------- #
# Daily advancement: deterministic automatic retry after a deferred publication
# --------------------------------------------------------------------------- #
def _gate(allowed, *, reason_code="test"):
    return types.SimpleNamespace(
        allowed=allowed, reason_code=reason_code, reason="test", override=False
    )


def test_closed_gate_is_re_evaluated_a_bounded_number_of_times(monkeypatch, capsys):
    """batch incomplete -> requeued -> complete -> publication retried, automatically."""
    verdicts = [_gate(False), _gate(False), _gate(True)]
    seen = []
    slept = []

    def evaluate(_client, *, market_date=None, override=False):
        return verdicts[min(len(seen), len(verdicts) - 1)] if seen.append(1) is None else None

    monkeypatch.setattr(refresh, "evaluate_publication_gate", lambda _c, **_k: verdicts.pop(0))

    gate = refresh._await_open_publication_gate(
        object(),
        market_date="2026-07-26",
        override=False,
        attempts=6,
        delay_seconds=600,
        sleep=slept.append,
    )

    assert gate.allowed is True
    assert len(slept) == 2  # only as many waits as were needed
    assert "publication gate OPENED after 2 automatic re-evaluation(s)" in capsys.readouterr().out


def test_gate_retry_is_bounded_and_still_defers_when_the_cohort_never_completes(monkeypatch):
    slept = []
    monkeypatch.setattr(refresh, "evaluate_publication_gate", lambda _c, **_k: _gate(False))

    gate = refresh._await_open_publication_gate(
        object(),
        market_date="2026-07-26",
        override=False,
        attempts=3,
        delay_seconds=600,
        sleep=slept.append,
    )

    assert gate.allowed is False
    assert len(slept) == 3  # bounded: never an uncontrolled polling loop


def test_an_open_gate_never_waits(monkeypatch):
    slept = []
    monkeypatch.setattr(refresh, "evaluate_publication_gate", lambda _c, **_k: _gate(True))
    gate = refresh._await_open_publication_gate(
        object(), market_date=None, override=False, attempts=6, delay_seconds=600, sleep=slept.append
    )
    assert gate.allowed is True
    assert slept == []


def test_scheduler_wires_the_bounded_retry_into_the_daily_run():
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[4]
    script = (repo_root / "infra" / "local" / "run_simulations.sh").read_text(encoding="utf-8")
    assert "--gate-wait-attempts 6" in script
    assert "--gate-wait-seconds 600" in script
    # The bounded retry is now passed through the daily orchestrator, which owns
    # the simulate -> verify -> publish order; the knob stays operator-visible
    # in the wrapper rather than being buried in a default.
    assert "run_daily_opening_publication.py" in script
    # Deferral and hard failure remain distinct events.
    assert "PUBLICATION_EXIT\" -eq 3" in script
