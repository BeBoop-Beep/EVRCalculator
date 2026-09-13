from types import SimpleNamespace

import pytest

from backend.scripts import build_pokemon_market_index_history as script


def _args(*, commit=True):
    return SimpleNamespace(
        commit=commit, dry_run=not commit, market_date="2026-09-13",
        backfill=False, from_date=None, force_publish=False,
    )


def test_standalone_commit_prepares_before_quality_and_build(monkeypatch):
    order = []
    monkeypatch.setattr(script, "parser", lambda: SimpleNamespace(parse_args=lambda: _args()))
    monkeypatch.setattr(script, "get_client", lambda: object())
    monkeypatch.setattr(script, "resolve_market_publication_date", lambda *_a: "2026-09-13")
    monkeypatch.setattr(script, "prepare_market_rollout_candidate",
                        lambda *_a, **_k: order.append("prepare") or {"status": "complete"})
    decision = SimpleNamespace(market_date="2026-09-13", status="READY")
    monkeypatch.setattr(script, "enforce_market_publication_gate",
                        lambda *_a, **_k: order.append("quality") or SimpleNamespace(proceed=True, decision=decision))
    monkeypatch.setattr(script, "market_index_accepted_dates", lambda *_a, **_k: set())
    monkeypatch.setattr(script, "build", lambda *_a, **_k: order.append("build") or {})
    script.main()
    assert order == ["prepare", "quality", "build"]


def test_standalone_dry_run_never_invokes_candidate_rpc(monkeypatch):
    seen = []
    monkeypatch.setattr(script, "parser", lambda: SimpleNamespace(parse_args=lambda: _args(commit=False)))
    monkeypatch.setattr(script, "get_client", lambda: object())
    monkeypatch.setattr(script, "resolve_market_publication_date", lambda *_a: "2026-09-13")
    monkeypatch.setattr(script, "prepare_market_rollout_candidate",
                        lambda *_a, **kw: seen.append(kw["commit"]) or {"status": "dry_run"})
    decision = SimpleNamespace(market_date="2026-09-13", status="INCOMPLETE")
    monkeypatch.setattr(script, "enforce_market_publication_gate",
                        lambda *_a, **_k: SimpleNamespace(proceed=True, decision=decision))
    monkeypatch.setattr(script, "market_index_accepted_dates", lambda *_a, **_k: set())
    monkeypatch.setattr(script, "build", lambda *_a, **_k: {})
    script.main()
    assert seen == [False]


def test_standalone_preparation_failure_prevents_quality(monkeypatch):
    monkeypatch.setattr(script, "parser", lambda: SimpleNamespace(parse_args=lambda: _args()))
    monkeypatch.setattr(script, "get_client", lambda: object())
    monkeypatch.setattr(script, "resolve_market_publication_date", lambda *_a: "2026-09-13")
    monkeypatch.setattr(script, "prepare_market_rollout_candidate",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("wrong candidate date")))
    monkeypatch.setattr(script, "enforce_market_publication_gate",
                        lambda *_a, **_k: pytest.fail("Quality must not run"))
    with pytest.raises(SystemExit) as exc:
        script.main()
    assert exc.value.code == 3


def test_historical_backfill_does_not_use_current_candidate_preparation(monkeypatch):
    args = _args(); args.backfill = True
    monkeypatch.setattr(script, "parser", lambda: SimpleNamespace(parse_args=lambda: args))
    monkeypatch.setattr(script, "get_client", lambda: object())
    monkeypatch.setattr(script, "prepare_market_rollout_candidate",
                        lambda *_a, **_k: pytest.fail("historical backfill must not prepare current candidates"))
    decision = SimpleNamespace(market_date="2026-09-13", status="READY")
    monkeypatch.setattr(script, "enforce_market_publication_gate",
                        lambda *_a, **_k: SimpleNamespace(proceed=True, decision=decision))
    monkeypatch.setattr(script, "market_index_accepted_dates", lambda *_a, **_k: set())
    monkeypatch.setattr(script, "build", lambda *_a, **_k: {})
    script.main()
