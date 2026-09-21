from __future__ import annotations

from types import SimpleNamespace

from backend.db.services import post_scrape_publication_trigger as trigger
from backend.scripts import publish_post_scrape_if_needed as fallback


class _Response:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args):
        return self

    def execute(self):
        return _Response(self.rows)


class _Client:
    def __init__(self, coverage_rows):
        self.coverage_rows = list(coverage_rows)

    def table(self, name):
        assert name == trigger.MARKET_EXPLORER_V2_COVERAGE_TABLE
        return _Query(self.coverage_rows)


def _audit(*, passed=True, market_date="2026-09-20"):
    return SimpleNamespace(passed=passed, market_date=market_date)


def test_currency_current_requires_every_tracked_set_through_target(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.pokemon_market_explorer_query_service.resolve_tracked_set_ids",
        lambda _client: ["set-a", "set-b"],
    )
    client = _Client([
        {"set_id": "set-a", "computed_through": "2026-09-20"},
        {"set_id": "set-b", "computed_through": "2026-09-20"},
    ])

    status = trigger.evaluate_post_scrape_publication_currency(
        client,
        "2026-09-20",
        audit_runner=lambda *_a, **_k: _audit(),
    )

    assert status is trigger.PublicationCurrencyStatus.CURRENT


def test_canonical_current_but_missing_v2_set_is_stale(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.pokemon_market_explorer_query_service.resolve_tracked_set_ids",
        lambda _client: ["set-a", "set-b"],
    )
    client = _Client([
        {"set_id": "set-a", "computed_through": "2026-09-20"},
    ])

    status = trigger.evaluate_post_scrape_publication_currency(
        client,
        "2026-09-20",
        audit_runner=lambda *_a, **_k: _audit(),
    )

    assert status is trigger.PublicationCurrencyStatus.STALE


def test_canonical_current_but_v2_date_lag_is_stale(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.pokemon_market_explorer_query_service.resolve_tracked_set_ids",
        lambda _client: ["set-a", "set-b"],
    )
    client = _Client([
        {"set_id": "set-a", "computed_through": "2026-09-20"},
        {"set_id": "set-b", "computed_through": "2026-09-15"},
    ])

    status = trigger.evaluate_post_scrape_publication_currency(
        client,
        "2026-09-20",
        audit_runner=lambda *_a, **_k: _audit(),
    )

    assert status is trigger.PublicationCurrencyStatus.STALE


def test_canonical_stale_short_circuits_v2(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.pokemon_market_explorer_query_service.resolve_tracked_set_ids",
        lambda _client: (_ for _ in ()).throw(AssertionError("V2 must not be read")),
    )

    status = trigger.evaluate_post_scrape_publication_currency(
        object(),
        "2026-09-20",
        audit_runner=lambda *_a, **_k: _audit(passed=False),
    )

    assert status is trigger.PublicationCurrencyStatus.STALE


def test_v2_authority_error_is_unknown(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.pokemon_market_explorer_query_service.resolve_tracked_set_ids",
        lambda _client: (_ for _ in ()).throw(RuntimeError("authority unavailable")),
    )

    status = trigger.evaluate_post_scrape_publication_currency(
        object(),
        "2026-09-20",
        audit_runner=lambda *_a, **_k: _audit(),
    )

    assert status is trigger.PublicationCurrencyStatus.UNKNOWN


def test_fallback_reuses_shared_currency_contract(monkeypatch):
    seen = []

    def evaluate(client, market_date):
        seen.append((client, market_date))
        return trigger.PublicationCurrencyStatus.STALE

    monkeypatch.setattr(trigger, "evaluate_post_scrape_publication_currency", evaluate)
    client = object()

    assert fallback._already_current(client, "2026-09-20") is trigger.PublicationCurrencyStatus.STALE
    assert seen == [(client, "2026-09-20")]
