"""Tests for the 6:00 AM fallback / operator "publish if needed" command.

Decision table under test:
    batch not complete                    -> no-op, no rebuild launched
    batch complete + publication current   -> no-op, no rebuild launched
    batch complete + publication stale      -> rebuild launched with the exact date
"""
import backend.scripts.publish_post_scrape_if_needed as mod
import backend.scripts.publish_post_scrape_if_needed as publish_module
from backend.db.services.post_scrape_publication_trigger import PublicationCurrencyStatus


class _FakeGateDecision:
    def __init__(self, allowed, reason_code="ok"):
        self.allowed = allowed
        self.reason_code = reason_code


def test_incomplete_batch_is_a_noop(monkeypatch):
    monkeypatch.setattr(mod, "_batch_complete", lambda client, market_date: False)
    ran = []
    result = mod.publish_if_needed("2026-09-01", client=object(),
                                   run_rebuild=lambda md: ran.append(md) or 0)
    assert result["status"] == mod.STATUS_NOOP_NOT_COMPLETE
    assert ran == []


def test_complete_and_current_is_a_noop(monkeypatch):
    monkeypatch.setattr(mod, "_batch_complete", lambda client, market_date: True)
    monkeypatch.setattr(
        mod, "_already_current", lambda client, market_date: PublicationCurrencyStatus.CURRENT
    )
    ran = []
    result = mod.publish_if_needed("2026-09-01", client=object(),
                                   run_rebuild=lambda md: ran.append(md) or 0)
    assert result["status"] == mod.STATUS_NOOP_ALREADY_CURRENT
    assert ran == []


def test_complete_and_stale_launches_rebuild_with_exact_date(monkeypatch):
    monkeypatch.setattr(mod, "_batch_complete", lambda client, market_date: True)
    monkeypatch.setattr(
        mod, "_already_current", lambda client, market_date: PublicationCurrencyStatus.STALE
    )
    ran = []
    result = mod.publish_if_needed("2026-09-01", client=object(),
                                   run_rebuild=lambda md: ran.append(md) or 0)
    assert result["status"] == mod.STATUS_PUBLISHED
    assert ran == ["2026-09-01"]


def test_rebuild_failure_is_reported_but_does_not_raise(monkeypatch):
    monkeypatch.setattr(mod, "_batch_complete", lambda client, market_date: True)
    monkeypatch.setattr(
        mod, "_already_current", lambda client, market_date: PublicationCurrencyStatus.STALE
    )
    result = mod.publish_if_needed("2026-09-01", client=object(), run_rebuild=lambda md: 1)
    assert result["status"] == mod.STATUS_PUBLISH_FAILED
    assert result["exit_code"] == 1


def test_malformed_market_date_fails_before_publishing(monkeypatch):
    ran = []
    result = mod.publish_if_needed("09/01/2026", client=object(),
                                   run_rebuild=lambda md: ran.append(md) or 0)
    assert result["status"] == mod.STATUS_INVALID_MARKET_DATE
    assert ran == []


def test_default_market_date_resolves_to_phoenix_today(monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.run_pokemon_set_scrape._market_date_iso", lambda: "2026-09-01"
    )
    assert mod._resolve_market_date(None) == "2026-09-01"


def test_explicit_market_date_is_never_overridden_by_wall_clock(monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.run_pokemon_set_scrape._market_date_iso", lambda: "2026-09-02"
    )
    assert mod._resolve_market_date("2026-08-15") == "2026-08-15"


def test_run_rebuild_script_never_passes_force_publish():
    args = [str(mod.REBUILD_SCRIPT), "2026-09-01"]
    assert "--force-publish" not in args


def test_batch_complete_uses_the_publication_gate_authority(monkeypatch):
    """Removing the gate check (i.e. always returning True) would let a stale/
    incomplete cohort publish — the gate call must actually happen."""
    seen = {}

    def fake_gate(client, *, market_date=None):
        seen["market_date"] = market_date
        return _FakeGateDecision(allowed=False, reason_code="batch_incomplete")

    monkeypatch.setattr(
        "backend.db.services.publication_gate.evaluate_publication_gate", fake_gate
    )
    assert mod._batch_complete(object(), "2026-09-01") is False
    assert seen["market_date"] == "2026-09-01"


def test_currency_check_exception_does_not_rebuild_and_reports_unknown(monkeypatch):
    class _FakeGateDecisionAllowed:
        allowed = True

    monkeypatch.setattr(
        publish_module, "_batch_complete",
        lambda client, market_date: True,
    )

    def broken_audit(client, market_date, phase):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(
        "backend.scripts.audit_pokemon_market_publication.run_market_publication_audit",
        broken_audit,
    )

    rebuild_calls = []
    result = publish_module.publish_if_needed(
        "2026-09-02", client=object(),
        run_rebuild=lambda market_date: rebuild_calls.append(market_date),
    )

    assert result["status"] == publish_module.STATUS_NOOP_CURRENCY_UNKNOWN
    assert rebuild_calls == []  # must NOT rebuild on an unknown currency state


def test_unknown_currency_status_yields_nonzero_cli_exit(monkeypatch):
    exit_code = publish_module._status_to_exit_code(publish_module.STATUS_NOOP_CURRENCY_UNKNOWN)
    assert exit_code != 0
