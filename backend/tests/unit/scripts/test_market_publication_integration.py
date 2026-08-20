"""Blocker 4: exercise the REAL Market publication entry points.

Every case asserts on artifact upserts actually reaching the client, not on
service-helper return values.
"""

import pytest

import backend.scripts.build_pokemon_explore_set_value_snapshot as set_value
import backend.scripts.build_pokemon_market_index_history as index_history
from backend.db.services import market_publication_gate as gate
from backend.db.services.market_date_quality import (
    STATUS_DEGRADED, STATUS_INCOMPLETE, STATUS_READY,
)

MARKET_ARTIFACT_TABLES = {
    "pokemon_market_index_daily_history",
    "pokemon_market_dashboard_snapshots",
    "pokemon_explore_set_value_snapshot",
    "pokemon_set_value_daily_history",
}
QUALITY_TABLE = "pokemon_market_date_quality"


@pytest.fixture(autouse=True)
def _required_mode(monkeypatch):
    """Every case runs against the fail-closed default."""
    monkeypatch.delenv(gate.MARKET_GATE_MODE_ENV, raising=False)


class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, client, name):
        self._client, self._name = client, name

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def range(self, *_a, **_k):
        return self

    def upsert(self, rows, **_k):
        self._client.upserts.append((self._name, list(rows)))
        return self

    def execute(self):
        return _Result(list(self._client.rows.get(self._name, [])))


class _Client:
    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.upserts = []

    def table(self, name):
        return _Table(self, name)

    @property
    def artifact_upserts(self):
        return [entry for entry in self.upserts if entry[0] in MARKET_ARTIFACT_TABLES]

    @property
    def quality_upserts(self):
        return [entry for entry in self.upserts if entry[0] == QUALITY_TABLE]


def _force_status(monkeypatch, status, market_date="2026-08-19"):
    evaluation = {"marketDate": market_date, "status": status,
                  "contractVersion": "pokemon-market-date-quality-v1",
                  "cohortSetCount": 22,
                  "qualifyingSetCount": 22 if status == STATUS_READY else 13,
                  "missingSetIds": [] if status == STATUS_READY else ["set-x"],
                  "cohortFingerprint": "fp", "evidence": {}}
    monkeypatch.setattr(gate, "evaluate_market_date_quality", lambda *a, **k: evaluation)
    monkeypatch.setattr(gate, "resolve_latest_accepted_market_date",
                        lambda *a, **k: "2026-08-17")
    return evaluation


# ---------------------------------------------------------------- cases 1 & 2

@pytest.mark.parametrize("full_batch_status", ["complete", "incomplete"])
def test_ready_allows_market_writes_regardless_of_full_batch(monkeypatch, full_batch_status):
    """Case 1 and case 2.

    164/167 with 3 unrelated deterministic failures must NOT block a 22/22
    Market cohort. The full batch is not an additional requirement.
    """
    _force_status(monkeypatch, STATUS_READY)
    client = _Client({"pokemon_scrape_batches": [{
        "id": 7, "market_date": "2026-08-19", "status": full_batch_status,
        "promoted_at": None if full_batch_status == "incomplete" else "2026-08-19T12:00:00Z",
        "missing_set_count": 3 if full_batch_status == "incomplete" else 0,
        "expected_set_count": 167}]})

    result = gate.enforce_market_publication_gate(
        client, commit=True, market_date="2026-08-19",
        entry_point="Pokemon Market index history")

    assert result.proceed is True
    assert result.exit_code == 0
    assert result.decision.status == STATUS_READY


def test_aug19_production_shape_allows_market_publication(monkeypatch):
    """The exact production incident: batch 164/167 incomplete, Market 22/22."""
    _force_status(monkeypatch, STATUS_READY)
    client = _Client({"pokemon_scrape_batches": [{
        "id": 7, "market_date": "2026-08-19", "status": "incomplete",
        "promoted_at": None, "missing_set_count": 3, "expected_set_count": 167,
        "succeeded_set_count": 164, "failed_set_count": 3}]})

    result = gate.enforce_market_publication_gate(
        client, commit=True, market_date="2026-08-19")

    assert result.proceed is True
    assert result.decision.evaluation["qualifyingSetCount"] == 22
    assert result.decision.evaluation["cohortSetCount"] == 22


# ------------------------------------------------------------- cases 3, 4, 9

@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_status_writes_zero_market_artifacts(monkeypatch, status):
    """Cases 3 and 4, across the real entry points."""
    _force_status(monkeypatch, status)

    for module in (index_history, set_value):
        client = _Client()
        monkeypatch.setattr(module, "get_client", lambda client=client: client)
        monkeypatch.setattr(
            "sys.argv", ["prog", "--commit", "--market-date", "2026-08-19"])

        with pytest.raises(SystemExit) as excinfo:
            module.main()

        assert excinfo.value.code == 3, f"{module.__name__} must defer with exit 3"
        assert client.artifact_upserts == [], (
            f"{module.__name__} wrote Market artifacts on {status}")


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_blocked_status_still_persists_quality_state(monkeypatch, status):
    """Case 3: quality state is durable diagnostics, not publication."""
    _force_status(monkeypatch, status)
    client = _Client()
    gate.enforce_market_publication_gate(client, commit=True, market_date="2026-08-19")
    assert len(client.quality_upserts) == 1
    assert client.artifact_upserts == []


@pytest.mark.parametrize("status", [STATUS_INCOMPLETE, STATUS_DEGRADED])
def test_force_publish_does_not_publish(monkeypatch, status):
    """Case 9: explicit rejection, and definitely no writes."""
    _force_status(monkeypatch, status)
    client = _Client()
    monkeypatch.setattr(index_history, "get_client", lambda: client)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--commit", "--market-date", "2026-08-19", "--force-publish"])

    with pytest.raises(SystemExit) as excinfo:
        index_history.main()

    assert excinfo.value.code == 2
    assert client.artifact_upserts == []


def test_force_publish_is_rejected_on_a_ready_date_too(monkeypatch, capsys):
    _force_status(monkeypatch, STATUS_READY)
    client = _Client()
    monkeypatch.setattr(index_history, "get_client", lambda: client)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--commit", "--market-date", "2026-08-19", "--force-publish"])

    with pytest.raises(SystemExit) as excinfo:
        index_history.main()

    assert excinfo.value.code == 2
    assert gate.MARKET_FORCE_PUBLISH_REJECTION in capsys.readouterr().out
    assert client.artifact_upserts == []


def test_dry_run_on_blocked_date_writes_nothing(monkeypatch):
    _force_status(monkeypatch, STATUS_INCOMPLETE)
    client = _Client()
    gate.enforce_market_publication_gate(client, commit=False, market_date="2026-08-19")
    assert client.upserts == []


# ------------------------------------------------------------------- case 5

def test_existing_degraded_rows_are_never_deleted(monkeypatch):
    """Case 5: Aug 18 evidence stays in storage; it is excluded, not erased."""
    from backend.db.services.pokemon_market_index_service import build_index_rows

    _force_status(monkeypatch, STATUS_READY)
    stored = [{"market_date": "2026-08-18", "index_key": "raw"}]
    client = _Client({"pokemon_market_index_daily_history": list(stored)})

    gate.enforce_market_publication_gate(client, commit=True, market_date="2026-08-19")

    assert client.rows["pokemon_market_index_daily_history"] == stored
    assert not any(entry[0] == "pokemon_market_index_daily_history"
                   for entry in client.upserts), "no delete or rewrite of Aug 18"

    sets = [{"id": "set-a", "canonical_key": "a", "release_date": "2020-01-01"}]
    source = [{"set_id": "set-a", "snapshot_date": day, "set_value": 100.0,
               "priced_card_count": 5, "value_scope": scope, "source": "t",
               "updated_at": f"{day}T00:00:00Z"}
              for day in ("2026-08-17", "2026-08-18", "2026-08-19")
              for scope in ("standard", "top10")]
    rows = build_index_rows(sets, source, accepted_dates={"2026-08-17", "2026-08-19"})
    assert "2026-08-18" not in {row["market_date"] for row in rows}


# ------------------------------------------------------------------- case 10

def test_general_publication_authority_is_unweakened():
    """Case 10: the 167-set gate is untouched for non-Market surfaces."""
    from backend.db.services import publication_gate

    client = _Client({"pokemon_scrape_batches": [{
        "id": 7, "market_date": "2026-08-19", "status": "incomplete",
        "promoted_at": None, "missing_set_count": 3, "expected_set_count": 167}]})

    decision = publication_gate.evaluate_publication_gate(
        client, market_date="2026-08-19", mode=publication_gate.MODE_REQUIRED)

    assert decision.allowed is False
    assert decision.reason_code == publication_gate.REASON_BLOCKED_INCOMPLETE


def test_general_gate_still_honours_its_own_override():
    """The legacy --force-publish path for non-Market surfaces is untouched."""
    from backend.db.services import publication_gate

    decision = publication_gate.evaluate_publication_gate(
        _Client(), market_date="2026-08-19", override=True)

    assert decision.allowed is True
    assert decision.reason_code == publication_gate.REASON_MANUAL_OVERRIDE


def test_positive_control_ready_actually_reaches_artifact_persistence(monkeypatch):
    """Guard the guards.

    The zero-upsert assertions above are only meaningful if a READY run really
    does write. This proves the same entry point persists index rows when the
    gate allows it.
    """
    _force_status(monkeypatch, STATUS_READY)
    client = _Client()
    persisted = []

    monkeypatch.setattr(index_history, "get_client", lambda: client)
    monkeypatch.setattr(index_history, "accepted_market_dates",
                        lambda *a, **k: {"2026-08-17", "2026-08-19"})
    monkeypatch.setattr(index_history, "build_market_index_history",
                        lambda *a, **k: [{"market_date": "2026-08-19",
                                          "index_key": "raw",
                                          "source_generation_fingerprint": "fp"}])
    monkeypatch.setattr(index_history, "resolve_eligible_sets", lambda _c: [{"id": "s"}])
    monkeypatch.setattr(index_history, "persist_index_rows",
                        lambda _c, rows: persisted.extend(rows) or len(rows))
    monkeypatch.setattr("sys.argv", ["prog", "--commit", "--market-date", "2026-08-19"])

    index_history.main()

    assert len(persisted) == 1, "a READY date must actually publish"
    assert persisted[0]["market_date"] == "2026-08-19"


def test_blocked_date_never_reaches_artifact_persistence(monkeypatch):
    """The same seam as the positive control, but DEGRADED: never called."""
    _force_status(monkeypatch, STATUS_DEGRADED)
    called = []

    monkeypatch.setattr(index_history, "get_client", lambda: _Client())
    monkeypatch.setattr(index_history, "persist_index_rows",
                        lambda *a, **k: called.append(1))
    monkeypatch.setattr(index_history, "build_market_index_history",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not build on a DEGRADED date")))
    monkeypatch.setattr("sys.argv", ["prog", "--commit", "--market-date", "2026-08-18"])

    with pytest.raises(SystemExit) as excinfo:
        index_history.main()

    assert excinfo.value.code == 3
    assert called == []
