import pytest

from backend.db.services import market_publication_gate as gate
from backend.db.services.market_date_quality import (
    STATUS_DEGRADED, STATUS_INCOMPLETE, STATUS_READY,
)


class _Recorder:
    """Captures every write so tests can assert ZERO artifact upserts."""

    def __init__(self):
        self.upserts = []

    def table(self, name):
        recorder = self

        class _T:
            def upsert(self, rows, **_k):
                recorder.upserts.append((name, rows))
                return self

            def execute(self):
                class _R:
                    data = []
                return _R()
        return _T()


def _stub(monkeypatch, status, market_date="2026-08-19"):
    evaluation = {"marketDate": market_date, "status": status,
                  "contractVersion": "pokemon-market-date-quality-v1",
                  "cohortSetCount": 22,
                  "qualifyingSetCount": 22 if status == STATUS_READY else 13,
                  "missingSetIds": [], "cohortFingerprint": "fp", "evidence": {}}
    monkeypatch.setattr(gate, "evaluate_market_date_quality",
                        lambda *a, **k: evaluation)
    monkeypatch.setattr(gate, "persist_market_date_quality", lambda *a, **k: 1)
    monkeypatch.setattr(gate, "resolve_latest_accepted_market_date",
                        lambda *a, **k: "2026-08-17")
    return evaluation


def test_ready_allows_commit(monkeypatch):
    _stub(monkeypatch, STATUS_READY)
    result = gate.enforce_market_publication_gate(
        _Recorder(), commit=True, market_date="2026-08-19")
    assert result.proceed is True
    assert result.exit_code == 0
    assert result.decision.status == STATUS_READY


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_statuses_defer_with_exit_code_three(monkeypatch, status):
    _stub(monkeypatch, status)
    result = gate.enforce_market_publication_gate(
        _Recorder(), commit=True, market_date="2026-08-19")
    assert result.proceed is False
    assert result.exit_code == gate.MARKET_GATE_DEFERRED_EXIT_CODE == 3
    assert result.decision.allowed is False


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_force_publish_is_explicitly_rejected(monkeypatch, status):
    _stub(monkeypatch, status)
    with pytest.raises(gate.MarketForcePublishRejected) as excinfo:
        gate.enforce_market_publication_gate(
            _Recorder(), commit=True, market_date="2026-08-19", force_publish=True)
    assert gate.MARKET_FORCE_PUBLISH_REJECTION in str(excinfo.value)


def test_force_publish_is_rejected_even_when_ready(monkeypatch):
    # The flag is meaningless for Market publication; never silently ignore it.
    _stub(monkeypatch, STATUS_READY)
    with pytest.raises(gate.MarketForcePublishRejected):
        gate.enforce_market_publication_gate(
            _Recorder(), commit=True, market_date="2026-08-19", force_publish=True)


def test_force_publish_is_rejected_before_any_evaluation(monkeypatch):
    # Rejection must not depend on reaching the database.
    def _boom(*_a, **_k):
        raise AssertionError("must not evaluate when --force-publish is present")

    monkeypatch.setattr(gate, "evaluate_market_date_quality", _boom)
    client = _Recorder()
    with pytest.raises(gate.MarketForcePublishRejected):
        gate.enforce_market_publication_gate(
            client, commit=True, market_date="2026-08-19", force_publish=True)
    assert client.upserts == []


def test_dry_run_reports_without_writing(monkeypatch, capsys):
    _stub(monkeypatch, STATUS_INCOMPLETE)
    client = _Recorder()
    result = gate.enforce_market_publication_gate(
        client, commit=False, market_date="2026-08-19")
    assert result.proceed is True
    assert client.upserts == [], "dry-run must not write artifacts"
    assert STATUS_INCOMPLETE in capsys.readouterr().out


def test_blocked_commit_persists_quality_state_but_no_artifacts(monkeypatch):
    evaluation = _stub(monkeypatch, STATUS_INCOMPLETE)
    persisted = []
    monkeypatch.setattr(gate, "persist_market_date_quality",
                        lambda client, ev: persisted.append(ev) or 1)
    client = _Recorder()
    gate.enforce_market_publication_gate(
        client, commit=True, market_date="2026-08-19")
    assert persisted == [evaluation], "quality state is diagnostic, not publication"
    assert client.upserts == [], "zero Market artifact upserts"


def test_blocked_commit_emits_the_deferral_marker(monkeypatch, capsys):
    _stub(monkeypatch, STATUS_DEGRADED)
    gate.enforce_market_publication_gate(
        _Recorder(), commit=True, market_date="2026-08-18",
        entry_point="Pokemon Market index history")
    out = capsys.readouterr().out
    assert gate.DEFERRAL_MARKER in out
    assert "market_quality_status=DEGRADED" in out
    assert "preserving previous good public Market authority" in out


def test_gate_never_reads_the_full_batch_authority(monkeypatch):
    """READY must not be re-gated on the 167-set cohort."""
    _stub(monkeypatch, STATUS_READY)

    class _Strict(_Recorder):
        def table(self, name):
            assert name != "pokemon_scrape_batches", (
                "Market gate must not consult the full-batch authority")
            return super().table(name)

    result = gate.enforce_market_publication_gate(
        _Strict(), commit=True, market_date="2026-08-19")
    assert result.proceed is True
