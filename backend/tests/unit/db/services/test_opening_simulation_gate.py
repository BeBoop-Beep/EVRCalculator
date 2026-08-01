"""Contract tests for the opening-simulation freshness gate.

The gate exists because market snapshots and simulation history advance on
separate jobs: the snapshot builders republish whatever simulation rows already
exist, so a stopped simulation batch produces a *fresh-looking* market snapshot
carrying a frozen Opening Profit vs Cost series. Every test below pins a case
that must not be allowed to read as "published and current".

No live Supabase access: the fake client replays deterministic table rows.
"""

import pytest

from backend.db.services import opening_simulation_gate as gate
from backend.db.services.opening_simulation_gate import (
    STATUS_CURRENT,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_STALE,
    STATUS_UNRESOLVED,
    STATUS_UNSUPPORTED,
    evaluate_opening_simulation_freshness,
    sets_needing_simulation,
    supported_opening_set_keys,
)

MARKET_DATE = "2026-08-01"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return _Result(self._rows)


class _Client:
    """Replays per-table rows; ``raises`` marks a table as unreadable."""

    def __init__(self, tables, raises=None):
        self._tables = tables
        self._raises = raises or {}

    def table(self, name):
        return _Query(self._tables.get(name, []), raise_exc=self._raises.get(name))


def _client(*, sets_rows, history_rows, summary_rows, raises=None):
    return _Client(
        {
            "sets": sets_rows,
            "calculation_history_trend": history_rows,
            "simulation_run_summary": summary_rows,
        },
        raises=raises,
    )


def _set_row(key, set_id):
    return {"id": set_id, "name": key.title(), "canonical_key": key}


def _history_row(set_id, snapshot_date, run_id, *, mean=1.2, median=0.8):
    return {
        "target_id": set_id,
        "snapshot_date": snapshot_date,
        "calculation_run_id": run_id,
        "simulated_mean_pack_value_vs_pack_cost": mean,
        "simulated_median_pack_value_vs_pack_cost": median,
    }


def _evaluate(client, keys=("alpha", "beta"), **kwargs):
    return evaluate_opening_simulation_freshness(
        client, market_date=MARKET_DATE, canonical_keys=list(keys), **kwargs
    )


def test_supported_keys_are_exactly_the_monte_carlo_v2_sets():
    # The gate must never expect a set the simulation batch would not run, nor
    # ignore one it would.
    from backend.constants.tcg.pokemon.megaEvolutionEra.setMap import (
        SET_CONFIG_MAP as MEGA,
    )
    from backend.constants.tcg.pokemon.scarletAndVioletEra.setMap import (
        SET_CONFIG_MAP as SV,
    )

    expected = sorted(
        key for key, config_cls in {**SV, **MEGA}.items() if getattr(config_cls(), "USE_MONTE_CARLO_V2", False)
    )
    assert list(supported_opening_set_keys()) == expected
    assert expected, "the supported opening set list must not be empty"


def test_the_simulation_batch_selects_sets_by_the_same_rule():
    # Source-level pin rather than an import: run_all_v2_sets rebinds
    # sys.stdout/sys.stderr at module scope (UTF-8 for the scheduler's log
    # redirection), and the replacement wrapper closes pytest's capture buffer
    # when collected. Reading the file keeps the invariant without that damage.
    from pathlib import Path

    # parents[4] is the backend package root (…/backend/tests/unit/db/services).
    source = (
        Path(__file__).resolve().parents[4] / "scripts" / "run_all_v2_sets.py"
    ).read_text(encoding="utf-8")
    assert 'getattr(config, "USE_MONTE_CARLO_V2", False)' in source
    assert "SCARLET_VIOLET_SET_CONFIG_MAP" in source
    assert "MEGA_EVOLUTION_SET_CONFIG_MAP" in source


def test_all_sets_simulated_on_the_market_date_passes():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a"), _set_row("beta", "id-b")],
        history_rows=[
            _history_row("id-a", MARKET_DATE, "run-a"),
            _history_row("id-b", MARKET_DATE, "run-b"),
        ],
        summary_rows=[{"calculation_run_id": "run-a"}, {"calculation_run_id": "run-b"}],
    )
    report = _evaluate(client)
    assert report.ok is True
    assert report.current_count == 2
    assert report.failed_count == 0
    assert sets_needing_simulation(report) == []


def test_a_current_market_date_with_an_older_simulation_is_reported_stale():
    # The exact production shape: market advanced, simulations did not.
    client = _client(
        sets_rows=[_set_row("alpha", "id-a"), _set_row("beta", "id-b")],
        history_rows=[
            _history_row("id-a", "2026-07-27", "run-a"),
            _history_row("id-b", "2026-07-27", "run-b"),
        ],
        summary_rows=[{"calculation_run_id": "run-a"}, {"calculation_run_id": "run-b"}],
    )
    report = _evaluate(client)
    assert report.ok is False
    assert report.failed_count == 2
    assert {status.status for status in report.statuses} == {STATUS_STALE}
    assert all(status.latest_simulation_date == "2026-07-27" for status in report.statuses)
    assert "2026-07-27" in report.failures[0].reason
    assert sorted(sets_needing_simulation(report)) == ["alpha", "beta"]


def test_a_missing_summary_join_is_invalid_not_silently_accepted():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[_history_row("id-a", MARKET_DATE, "run-a")],
        summary_rows=[],  # the join target does not exist
    )
    report = _evaluate(client, keys=("alpha",))
    assert report.ok is False
    assert report.statuses[0].status == STATUS_INVALID
    assert "simulation_run_summary" in report.statuses[0].reason


def test_null_required_metrics_are_invalid():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[_history_row("id-a", MARKET_DATE, "run-a", mean=None)],
        summary_rows=[{"calculation_run_id": "run-a"}],
    )
    report = _evaluate(client, keys=("alpha",))
    assert report.ok is False
    assert report.statuses[0].status == STATUS_INVALID
    assert "simulated_mean_pack_value_vs_pack_cost" in report.statuses[0].reason


def test_a_set_with_no_history_at_all_is_missing():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[],
        summary_rows=[],
    )
    report = _evaluate(client, keys=("alpha",))
    assert report.statuses[0].status == STATUS_MISSING
    assert report.ok is False


def test_unsupported_sets_are_skipped_with_an_explicit_reason():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a"), _set_row("beta", "id-b")],
        history_rows=[_history_row("id-a", MARKET_DATE, "run-a")],
        summary_rows=[{"calculation_run_id": "run-a"}],
    )
    report = _evaluate(client, unsupported_keys=["beta"])
    assert report.ok is True
    assert report.skipped_count == 1
    skipped = next(status for status in report.statuses if status.status == STATUS_UNSUPPORTED)
    assert skipped.reason == "explicitly excepted from opening analytics"
    # An excepted set is never queued for simulation.
    assert sets_needing_simulation(report) == []


def test_a_partial_failure_fails_the_whole_report():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a"), _set_row("beta", "id-b")],
        history_rows=[
            _history_row("id-a", MARKET_DATE, "run-a"),
            _history_row("id-b", "2026-07-27", "run-b"),
        ],
        summary_rows=[{"calculation_run_id": "run-a"}, {"calculation_run_id": "run-b"}],
    )
    report = _evaluate(client)
    assert report.ok is False
    assert report.current_count == 1
    assert report.failed_count == 1
    assert sets_needing_simulation(report) == ["beta"]


def test_a_canonical_key_with_no_sets_row_is_unresolved_not_dropped():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[_history_row("id-a", MARKET_DATE, "run-a")],
        summary_rows=[{"calculation_run_id": "run-a"}],
    )
    report = _evaluate(client)
    assert report.ok is False
    unresolved = next(status for status in report.statuses if status.status == STATUS_UNRESOLVED)
    assert unresolved.canonical_key == "beta"


def test_an_unreadable_authority_fails_closed():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[],
        summary_rows=[],
        raises={"calculation_history_trend": RuntimeError("PGRST205 schema cache")},
    )
    report = _evaluate(client, keys=("alpha",))
    assert report.ok is False
    assert "simulation history read failed" in report.error


def test_a_missing_market_date_refuses_to_evaluate():
    client = _client(sets_rows=[], history_rows=[], summary_rows=[])
    report = evaluate_opening_simulation_freshness(client, market_date=None)
    assert report.ok is False
    assert "no promoted market date" in report.error


def test_reevaluating_the_same_date_is_stable_and_queues_nothing():
    # Idempotency: the daily view collapses reruns to one point per set/day, so
    # a second pass over an already-current date must add no work.
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[
            _history_row("id-a", MARKET_DATE, "run-old"),
            _history_row("id-a", MARKET_DATE, "run-a"),
        ],
        summary_rows=[{"calculation_run_id": "run-a"}, {"calculation_run_id": "run-old"}],
    )
    first = _evaluate(client, keys=("alpha",))
    second = _evaluate(client, keys=("alpha",))
    assert first.ok is second.ok is True
    assert sets_needing_simulation(first) == sets_needing_simulation(second) == []


def test_report_lines_are_structured_and_greppable():
    client = _client(
        sets_rows=[_set_row("alpha", "id-a")],
        history_rows=[_history_row("id-a", "2026-07-27", "run-a")],
        summary_rows=[{"calculation_run_id": "run-a"}],
    )
    lines = _evaluate(client, keys=("alpha",)).report_lines(entry_point="test")
    header = lines[0]
    assert "market_date=2026-08-01" in header
    assert "eligible=1" in header
    assert "current=0" in header
    assert "failed=1" in header
    assert "skipped=0" in header
    assert "ok=False" in header
    assert any("status=stale" in line and "latest_simulation_date=2026-07-27" in line for line in lines)


@pytest.mark.parametrize("status_value", [STATUS_STALE, STATUS_MISSING, STATUS_INVALID, STATUS_UNRESOLVED])
def test_every_failure_status_blocks_publication(status_value):
    status = gate.OpeningSetSimulationStatus(
        canonical_key="alpha", set_id="id-a", set_name="Alpha", status=status_value
    )
    assert status.ok is False


@pytest.mark.parametrize("status_value", [STATUS_CURRENT, STATUS_UNSUPPORTED])
def test_passing_statuses_do_not_block_publication(status_value):
    status = gate.OpeningSetSimulationStatus(
        canonical_key="alpha", set_id="id-a", set_name="Alpha", status=status_value
    )
    assert status.ok is True
