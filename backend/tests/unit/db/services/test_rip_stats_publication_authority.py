"""RIP Stats publication-authority regressions for the 2026-08-18 incident.

A direct service call published RIP Stats for an UNPROMOTED market date while
the promoted public cohort was still 2026-08-17. The CLI gate was correct but
was never on that code path, so the defense must live in the service and in the
RPC, not only in the CLI.
"""

from pathlib import Path

import pytest

from backend.db.services import pokemon_rip_stats_service
from backend.db.services.pokemon_rip_stats_service import (
    PokemonRipStatsUnavailable,
    publish_pokemon_rip_stats_snapshot,
)

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "db" / "migrations"
    / "20260818181500_harden_rip_stats_publication_batch_gate.sql"
)
INCIDENT_DATE = "2026-08-18"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._rows)


class _Client:
    """Batch-authority reads plus a recording RPC that must never fire."""

    def __init__(self, batch_rows):
        self._rows = batch_rows
        self.rpc_calls = []

    def table(self, _name):
        return _Query(self._rows)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _Query("00000000-0000-0000-0000-000000000001")


def _batch(**overrides):
    row = {
        "id": 24,
        "market_date": INCIDENT_DATE,
        "status": "complete",
        "promoted_at": "2026-08-18T17:00:00Z",
        "missing_set_count": 0,
        "expected_set_count": 22,
    }
    row.update(overrides)
    return row


def _built(market_date=INCIDENT_DATE):
    return {
        "snapshot": {"market_date": market_date, "eligible_cohort_count": 22},
        "constituents": [{"set_id": str(index)} for index in range(22)],
    }


# --- CASE B: direct service publish on an incomplete batch is blocked ------- #
def test_case_b_direct_service_publish_on_incomplete_batch_is_blocked():
    """The exact production bypass: incomplete batch 24, promoted_at null."""
    client = _Client([_batch(status="incomplete", promoted_at=None)])
    with pytest.raises(PokemonRipStatsUnavailable) as excinfo:
        publish_pokemon_rip_stats_snapshot(client, _built())
    assert INCIDENT_DATE in str(excinfo.value)
    assert client.rpc_calls == []


# --- CASE D: a complete, promoted batch is allowed through ----------------- #
def test_case_d_complete_promoted_batch_publishes():
    client = _Client([_batch()])
    assert publish_pokemon_rip_stats_snapshot(client, _built())
    assert [name for name, _ in client.rpc_calls] == [
        pokemon_rip_stats_service.PUBLICATION_RPC
    ]


# --- CASES E/F/G: complete-but-contradictory rows all fail closed ---------- #
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"promoted_at": None}, id="E_promoted_at_null"),
        pytest.param({"missing_set_count": 3}, id="F_missing_sets"),
        pytest.param({"expected_set_count": 0}, id="G_expected_zero"),
    ],
)
def test_cases_e_to_g_complete_but_contradictory_batch_is_blocked(overrides):
    client = _Client([_batch(**overrides)])
    with pytest.raises(PokemonRipStatsUnavailable):
        publish_pokemon_rip_stats_snapshot(client, _built())
    assert client.rpc_calls == []


# --- CASE H: snapshot date must match the batch it is authorized against --- #
def test_case_h_snapshot_date_mismatching_batch_is_blocked():
    """A promoted 08-17 batch must not authorize an 08-18 snapshot."""
    client = _Client([_batch(market_date="2026-08-17")])
    with pytest.raises(PokemonRipStatsUnavailable):
        publish_pokemon_rip_stats_snapshot(client, _built(INCIDENT_DATE))
    assert client.rpc_calls == []


def test_missing_batch_row_is_blocked():
    client = _Client([])
    with pytest.raises(PokemonRipStatsUnavailable):
        publish_pokemon_rip_stats_snapshot(client, _built())
    assert client.rpc_calls == []


def test_snapshot_without_market_date_cannot_authorize():
    client = _Client([_batch()])
    with pytest.raises(PokemonRipStatsUnavailable):
        publish_pokemon_rip_stats_snapshot(client, {"snapshot": {}, "constituents": []})
    assert client.rpc_calls == []


# --- CASE I: PUBLICATION_GATE_MODE=disabled cannot weaken this invariant ---- #
def test_case_i_gate_mode_disabled_does_not_bypass_service_authority(monkeypatch):
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    client = _Client([_batch(status="incomplete", promoted_at=None)])
    with pytest.raises(PokemonRipStatsUnavailable):
        publish_pokemon_rip_stats_snapshot(client, _built())
    assert client.rpc_calls == []


# --- CASE C: the RPC itself enforces the batch gate ------------------------ #
def test_case_c_migration_rpc_enforces_batch_gate_before_mutating():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create or replace function public.publish_pokemon_rip_stats_snapshot" in sql
    assert "security invoker" in sql
    assert "set search_path = public" in sql
    assert "from public.pokemon_scrape_batches" in sql
    assert "'complete'" in sql
    assert "promoted_at is null" in sql
    assert "missing_set_count" in sql
    assert "expected_set_count" in sql
    assert "grant execute on function public.publish_pokemon_rip_stats_snapshot(jsonb,jsonb) to service_role" in sql
    assert "revoke all on function public.publish_pokemon_rip_stats_snapshot(jsonb,jsonb) from public, anon, authenticated" in sql


def test_case_c_authority_block_precedes_every_write_statement():
    """The gate must raise before the first INSERT/UPDATE/DELETE in the body."""
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    gate = sql.index("from public.pokemon_scrape_batches")
    for token in ("insert into public.pokemon_rip_stats_snapshots",
                  "delete from public.pokemon_rip_stats_snapshot_sets",
                  "insert into public.pokemon_rip_stats_snapshot_latest"):
        assert gate < sql.index(token), f"{token} precedes the authority gate"


def test_case_i_migration_has_no_force_publish_escape_hatch():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "force" not in sql
    assert "override" not in sql


# --- CASE A: the CLI's own build(commit=True) helper is now gated too ------- #
def test_case_a_cli_build_commit_on_incomplete_batch_is_blocked(monkeypatch):
    """build(..., commit=True) bypasses main()'s gate; the service must stop it."""
    from backend.scripts import build_pokemon_rip_stats_snapshot as cli

    monkeypatch.setattr(
        cli, "build_pokemon_rip_stats_snapshot", lambda _client, *, market_date: _built(market_date)
    )
    client = _Client([_batch(status="incomplete", promoted_at=None)])
    with pytest.raises(PokemonRipStatsUnavailable):
        cli.build(client, market_date=INCIDENT_DATE, commit=True)
    assert client.rpc_calls == []
