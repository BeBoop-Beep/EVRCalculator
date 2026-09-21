"""Tests for the 6:00 AM fallback / operator publish-if-needed command."""

from types import SimpleNamespace

import backend.scripts.publish_post_scrape_if_needed as mod
from backend.db.services.post_scrape_publication_trigger import PublicationCurrencyStatus


def _gate(*, allowed=True, reason_code="allowed_complete"):
    return SimpleNamespace(allowed=allowed, reason_code=reason_code)


def _set_lock(monkeypatch, held: bool) -> None:
    monkeypatch.setattr(
        "backend.db.services.post_scrape_publication_trigger._default_lock_is_held",
        lambda _path: held,
    )


def test_incomplete_batch_is_a_noop(monkeypatch):
    monkeypatch.setattr(
        mod, "_batch_gate_decision",
        lambda *_a, **_k: _gate(allowed=False, reason_code="blocked_incomplete"),
    )
    ran = []
    result = mod.publish_if_needed(
        "2026-09-01", client=object(), run_rebuild=lambda md: ran.append(md) or 0
    )
    assert result["status"] == mod.STATUS_NOOP_NOT_COMPLETE
    assert ran == []


def test_gate_authority_unavailable_is_not_mislabeled_incomplete(monkeypatch):
    monkeypatch.setattr(
        mod, "_batch_gate_decision",
        lambda *_a, **_k: _gate(
            allowed=False, reason_code="blocked_authority_unavailable"
        ),
    )
    result = mod.publish_if_needed("2026-09-01", client=object())
    assert result["status"] == mod.STATUS_GATE_AUTHORITY_UNAVAILABLE
    assert mod._status_to_exit_code(result["status"]) != 0


def test_complete_and_current_is_a_noop(monkeypatch):
    monkeypatch.setattr(mod, "_batch_gate_decision", lambda *_a, **_k: _gate())
    _set_lock(monkeypatch, False)
    monkeypatch.setattr(
        mod,
        "_already_current",
        lambda *_a, **_k: PublicationCurrencyStatus.CURRENT,
    )
    ran = []
    result = mod.publish_if_needed(
        "2026-09-01", client=object(), run_rebuild=lambda md: ran.append(md) or 0
    )
    assert result["status"] == mod.STATUS_NOOP_ALREADY_CURRENT
    assert ran == []


def test_lock_held_is_distinct_noop_and_never_claims_published(monkeypatch):
    monkeypatch.setattr(mod, "_batch_gate_decision", lambda *_a, **_k: _gate())
    _set_lock(monkeypatch, True)
    monkeypatch.setattr(
        mod,
        "_already_current",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("currency audit must not run while publisher owns lock")
        ),
    )
    ran = []
    result = mod.publish_if_needed(
        "2026-09-01", client=object(), run_rebuild=lambda md: ran.append(md) or 0
    )
    assert result["status"] == mod.STATUS_NOOP_ALREADY_RUNNING
    assert result["lock_path"].endswith("pokemon-post-scrape-publication.lock")
    assert mod._status_to_exit_code(result["status"]) == 0
    assert ran == []


def test_complete_and_stale_launches_rebuild_with_exact_date(monkeypatch):
    monkeypatch.setattr(mod, "_batch_gate_decision", lambda *_a, **_k: _gate())
    _set_lock(monkeypatch, False)
    monkeypatch.setattr(
        mod,
        "_already_current",
        lambda *_a, **_k: PublicationCurrencyStatus.STALE,
    )
    ran = []
    result = mod.publish_if_needed(
        "2026-09-01", client=object(), run_rebuild=lambda md: ran.append(md) or 0
    )
    assert result["status"] == mod.STATUS_PUBLISHED
    assert ran == ["2026-09-01"]


def test_rebuild_failure_is_reported(monkeypatch):
    monkeypatch.setattr(mod, "_batch_gate_decision", lambda *_a, **_k: _gate())
    _set_lock(monkeypatch, False)
    monkeypatch.setattr(
        mod,
        "_already_current",
        lambda *_a, **_k: PublicationCurrencyStatus.STALE,
    )
    result = mod.publish_if_needed(
        "2026-09-01", client=object(), run_rebuild=lambda _md: 1
    )
    assert result["status"] == mod.STATUS_PUBLISH_FAILED
    assert result["exit_code"] == 1


def test_currency_unknown_never_rebuilds(monkeypatch):
    monkeypatch.setattr(mod, "_batch_gate_decision", lambda *_a, **_k: _gate())
    _set_lock(monkeypatch, False)
    monkeypatch.setattr(
        mod,
        "_already_current",
        lambda *_a, **_k: PublicationCurrencyStatus.UNKNOWN,
    )
    ran = []
    result = mod.publish_if_needed(
        "2026-09-02", client=object(), run_rebuild=lambda md: ran.append(md) or 0
    )
    assert result["status"] == mod.STATUS_NOOP_CURRENCY_UNKNOWN
    assert ran == []
    assert mod._status_to_exit_code(result["status"]) != 0


def test_malformed_market_date_fails_before_publishing():
    result = mod.publish_if_needed("09/01/2026", client=object())
    assert result["status"] == mod.STATUS_INVALID_MARKET_DATE


def test_default_market_date_resolves_to_phoenix_today(monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.run_pokemon_set_scrape._market_date_iso",
        lambda: "2026-09-01",
    )
    assert mod._resolve_market_date(None) == "2026-09-01"


def test_explicit_market_date_is_never_overridden_by_wall_clock():
    assert mod._resolve_market_date("2026-08-15") == "2026-08-15"


def test_run_rebuild_script_never_passes_force_publish():
    args = [str(mod.REBUILD_SCRIPT), "2026-09-01"]
    assert "--force-publish" not in args
