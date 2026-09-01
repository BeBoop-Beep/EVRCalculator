from backend.scripts import run_daily_opening_publication as publication


def test_transient_set_failure_retries_then_recovers(monkeypatch):
    exits = iter([75, 0])
    sleeps = []
    monkeypatch.setattr(publication, "_run_command", lambda *_args, **_kwargs: next(exits))
    result = publication.run_simulations_for_sets(
        ["journeyTogether"], market_date="2026-08-31", sleep=sleeps.append
    )[0]
    assert result.succeeded is True
    assert result.attempts == 2
    assert sleeps == [15.0]


def test_deterministic_set_failure_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(publication, "_run_command", lambda *args, **kwargs: calls.append(args) or 1)
    result = publication.run_simulations_for_sets(["destinedRivals"], sleep=lambda _delay: None)[0]
    assert result.succeeded is False
    assert result.transient is False
    assert result.attempts == 1
    assert len(calls) == 1


def test_transient_retry_exhaustion_remains_failed(monkeypatch):
    monkeypatch.setattr(publication, "_run_command", lambda *_args, **_kwargs: 75)
    result = publication.run_simulations_for_sets(
        ["journeyTogether"], sleep=lambda _delay: None, max_attempts=3
    )[0]
    assert result.succeeded is False
    assert result.transient is True
    assert result.attempts == 3

