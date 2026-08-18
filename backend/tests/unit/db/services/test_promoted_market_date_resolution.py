"""Promoted-market-date resolution regressions for the 2026-08-18 incident.

``resolve_market_date`` consumed ``decision.market_date`` from a BLOCKED gate
decision, so an incomplete 2026-08-18 batch was treated as the promoted date and
RIP Stats published against it. Resolution must instead come from the latest
genuinely promoted batch, and a newer incomplete batch must not hide it.
"""

import pytest

from backend.db.services.publication_gate import (
    GATE_DEFERRED_EXIT_CODE,
    resolve_latest_promoted_market_date,
)
from backend.scripts.audit_opening_analytics_publication import resolve_market_date

INCOMPLETE_DAY = "2026-08-18"
PROMOTED_DAY = "2026-08-17"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Mimics the PostgREST builder, honouring .eq() filters like the real one."""

    def __init__(self, rows, *, raise_exc=None):
        self._rows = list(rows)
        self._raise = raise_exc

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._rows = [row for row in self._rows if str(row.get(column)) == str(value)]
        return self

    def order(self, column, desc=False):
        self._rows = sorted(self._rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        return self

    def limit(self, count):
        self._rows = self._rows[:count]
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return _Result(self._rows)


class _Client:
    def __init__(self, rows, *, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc

    def table(self, _name):
        return _Query(self._rows, raise_exc=self._raise)


def _batch(market_date, **overrides):
    row = {
        "id": int(market_date.replace("-", "")[-2:]),
        "market_date": market_date,
        "status": "complete",
        "promoted_at": f"{market_date}T10:54:05Z",
        "missing_set_count": 0,
        "expected_set_count": 167,
    }
    row.update(overrides)
    return row


_INCOMPLETE_TODAY = _batch(INCOMPLETE_DAY, id=24, status="incomplete", promoted_at=None,
                           missing_set_count=12, expected_set_count=167)
_PROMOTED_YESTERDAY = _batch(PROMOTED_DAY, id=23)


# --- CASE A: a newer incomplete batch must not hide the promoted one ------- #
def test_case_a_incomplete_newer_batch_resolves_previous_promoted_date():
    client = _Client([_INCOMPLETE_TODAY, _PROMOTED_YESTERDAY])
    assert resolve_latest_promoted_market_date(client) == (PROMOTED_DAY, None)
    assert resolve_market_date(client, None) == (PROMOTED_DAY, None)


# --- CASE B: newest batch complete and promoted wins ----------------------- #
def test_case_b_latest_complete_promoted_batch_is_used():
    client = _Client([_batch(INCOMPLETE_DAY, id=24), _PROMOTED_YESTERDAY])
    assert resolve_latest_promoted_market_date(client) == (INCOMPLETE_DAY, None)
    assert resolve_market_date(client, None) == (INCOMPLETE_DAY, None)


# --- CASE C: nothing promoted at all fails closed -------------------------- #
def test_case_c_no_complete_batch_fails_closed():
    client = _Client([_INCOMPLETE_TODAY])
    resolved, error = resolve_latest_promoted_market_date(client)
    assert resolved is None and error
    resolved, error = resolve_market_date(client, None)
    assert resolved is None and error


# --- CASE D: a contradictory newest COMPLETE row must NOT fall back -------- #
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"promoted_at": None}, id="promoted_at_null"),
        pytest.param({"missing_set_count": 4}, id="missing_sets"),
        pytest.param({"expected_set_count": 0}, id="expected_zero"),
    ],
)
def test_case_d_contradictory_newest_complete_batch_fails_closed(overrides):
    """Never silently publish an older date because the newest authority is corrupt."""
    client = _Client([_batch(INCOMPLETE_DAY, id=24, **overrides), _PROMOTED_YESTERDAY])
    resolved, error = resolve_latest_promoted_market_date(client)
    assert resolved is None
    assert INCOMPLETE_DAY in error
    assert resolve_market_date(client, None)[0] is None


def test_authority_read_failure_fails_closed():
    client = _Client([_PROMOTED_YESTERDAY], raise_exc=RuntimeError("network down"))
    resolved, error = resolve_latest_promoted_market_date(client)
    assert resolved is None and "network down" in error


# --- CASE E: explicit dates stay available for read-only audits ------------ #
def test_case_e_explicit_unpromoted_date_remains_auditable():
    client = _Client([_INCOMPLETE_TODAY, _PROMOTED_YESTERDAY])
    assert resolve_market_date(client, INCOMPLETE_DAY) == (INCOMPLETE_DAY, None)


# --------------------------------------------------------------------------- #
# Orchestrator: the commit-capable path must gate the EXACT resolved date.
# --------------------------------------------------------------------------- #
def _orchestrate(client, monkeypatch, **kwargs):
    from backend.scripts import run_daily_opening_publication as daily

    def _fail(*_a, **_k):
        raise AssertionError("phase-2 work ran despite a closed publication gate")

    monkeypatch.setattr(daily, "run_simulations_for_sets", _fail)
    monkeypatch.setattr(daily, "_publish_rip_stats", _fail)
    monkeypatch.setattr(daily, "_finalize_sealed_products", _fail)
    return daily.orchestrate(client, **kwargs)


# --- CASE F: explicit unpromoted date is deferred before any mutation ------ #
def test_case_f_explicit_incomplete_date_defers_before_any_phase2_work(monkeypatch):
    client = _Client([_INCOMPLETE_TODAY, _PROMOTED_YESTERDAY])
    summary = _orchestrate(client, monkeypatch, market_date=INCOMPLETE_DAY)
    assert summary.exit_code == GATE_DEFERRED_EXIT_CODE
    assert INCOMPLETE_DAY in summary.error
    assert summary.rip_stats_publication_status == "not_attempted"
    assert summary.snapshot_publication_status == "not_attempted"
    assert summary.simulation_succeeded == 0


# --- CASE G/H: a promoted date proceeds past the gate ---------------------- #
@pytest.mark.parametrize(
    "explicit,expected",
    [
        pytest.param(PROMOTED_DAY, PROMOTED_DAY, id="G_explicit_promoted"),
        pytest.param(None, PROMOTED_DAY, id="H_no_explicit_uses_promoted"),
    ],
)
def test_cases_g_and_h_promoted_date_passes_the_authority_gate(monkeypatch, explicit, expected):
    from backend.scripts import run_daily_opening_publication as daily

    client = _Client([_INCOMPLETE_TODAY, _PROMOTED_YESTERDAY])
    reached = {}

    def _stop_after_gate(_client, *, market_date, **_k):
        reached["market_date"] = market_date
        raise RuntimeError("reached phase 2")

    monkeypatch.setattr(daily, "evaluate_opening_simulation_freshness", _stop_after_gate)
    with pytest.raises(RuntimeError, match="reached phase 2"):
        daily.orchestrate(client, market_date=explicit)
    assert reached["market_date"] == expected
