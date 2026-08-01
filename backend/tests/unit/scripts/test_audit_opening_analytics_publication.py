"""Contract tests for the read-only opening-analytics publication audit.

The audit is the tripwire for the failure that ran undetected in production for
five days: a market snapshot whose ``latest_market_date`` advanced while its
Opening Profit vs Cost history stayed frozen. Every assertion below pins a case
that must be reported truthfully rather than passed over.
"""

import pytest

from backend.scripts.audit_opening_analytics_publication import (
    AuditReport,
    SetAuditRow,
    audit_set_row,
    latest_real_performance_date,
    run_audit,
)

MARKET_DATE = "2026-08-01"


def _window(key="30D"):
    return {
        "window": key,
        "startDate": "2026-07-03",
        "endDate": MARKET_DATE,
        "changeAmount": -81.21,
        "changePercent": -6.22,
        "cardVariantId": "variant-1",
        "conditionId": "condition-1",
    }


def _card(*, windows=("1D", "7D", "30D"), variant="variant-1"):
    card = {"name": "Mega Gengar ex", "cardVariantId": variant}
    if windows:
        card["marketDeltaWindows"] = {key: _window(key) for key in windows}
    return card


def _dashboard_row(*, perf_dates=(MARKET_DATE,), market_date=MARKET_DATE, cards=None, carried=()):
    history = [
        {"date": date, "isCarriedForward": date in carried, "mean_value_to_cost_ratio": 0.5}
        for date in perf_dates
    ]
    return {
        "latest_market_date": market_date,
        "performance_vs_cost_history_json": history,
        "top_chase_cards_json": list(cards if cards is not None else [_card() for _ in range(10)]),
    }


def _row(**overrides):
    kwargs = {
        "canonical_key": "ascendedHeroes",
        "set_id": "id-a",
        "set_name": "Ascended Heroes",
        "simulation_status": "current",
        "simulation_reason": None,
        "market_date": MARKET_DATE,
        "dashboard_row": _dashboard_row(),
    }
    kwargs.update(overrides)
    return audit_set_row(**kwargs)


def test_a_fully_current_set_passes():
    row = _row()
    assert row.passed is True
    assert row.failures == []
    assert row.dates_match is True
    assert row.top_chase_card_count == 10
    assert row.cards_with_1d_window == 10
    assert row.cards_with_7d_window == 10
    assert row.cards_with_30d_window == 10
    assert row.cards_falling_back_to_history == 0
    assert row.cards_missing_canonical_identity == 0


def test_the_production_failure_shape_is_reported():
    # Market date advanced to 2026-08-01; the OPvC history stopped on 07-27.
    row = _row(
        simulation_status="stale",
        simulation_reason="latest simulation is 2026-07-27",
        dashboard_row=_dashboard_row(perf_dates=("2026-07-26", "2026-07-27")),
    )
    assert row.passed is False
    assert row.performance_history_latest_real_date == "2026-07-27"
    assert row.market_snapshot_latest_date == MARKET_DATE
    assert row.dates_match is False
    assert any("simulation stale" in failure for failure in row.failures)
    assert any("performance history ends 2026-07-27" in failure for failure in row.failures)


def test_a_carried_forward_point_cannot_satisfy_the_date_check():
    # A display-only point carried up to the market date must never be accepted
    # as evidence that a simulation ran that day.
    row = _row(
        simulation_status="stale",
        dashboard_row=_dashboard_row(
            perf_dates=("2026-07-27", MARKET_DATE), carried=(MARKET_DATE,)
        ),
    )
    assert row.performance_history_latest_real_date == "2026-07-27"
    assert row.dates_match is False
    assert row.passed is False


def test_missing_canonical_30d_windows_fail_the_set():
    row = _row(dashboard_row=_dashboard_row(cards=[_card(windows=("1D", "7D")) for _ in range(10)]))
    assert row.cards_with_30d_window == 0
    assert row.cards_falling_back_to_history == 10
    assert row.passed is False
    assert any("lack the canonical 30D window" in failure for failure in row.failures)


def test_cards_missing_canonical_identity_are_counted():
    row = _row(dashboard_row=_dashboard_row(cards=[_card(variant=None), _card()]))
    assert row.cards_missing_canonical_identity == 1


def test_an_excepted_set_is_skipped_and_never_fails():
    row = _row(
        simulation_status="unsupported",
        skipped=True,
        dashboard_row=_dashboard_row(perf_dates=("2026-05-01",), cards=[]),
    )
    assert row.skipped is True
    assert row.passed is True
    assert row.failures == []


def test_a_set_with_no_dashboard_row_fails_rather_than_passing_vacuously():
    row = _row(dashboard_row=None)
    assert row.passed is False
    assert row.performance_history_latest_real_date is None
    assert any("ends nowhere" in failure for failure in row.failures)


def test_latest_real_performance_date_ignores_carried_forward_points():
    history = [
        {"date": "2026-07-26"},
        {"date": "2026-07-27"},
        {"date": "2026-07-28", "isCarriedForward": True},
        {"date": "2026-08-01", "is_carried_forward": True},
    ]
    assert latest_real_performance_date(history) == "2026-07-27"


def test_latest_real_performance_date_handles_empty_and_malformed_history():
    assert latest_real_performance_date(None) is None
    assert latest_real_performance_date([]) is None
    assert latest_real_performance_date(["nope", {"date": None}]) is None


def test_report_passes_only_when_every_row_passes():
    passing = SetAuditRow(canonical_key="a", set_id="1", set_name="A", simulation_status="current")
    failing = SetAuditRow(
        canonical_key="b", set_id="2", set_name="B", simulation_status="stale", failures=["stale"]
    )
    assert AuditReport(market_date=MARKET_DATE, rows=[passing]).passed is True
    assert AuditReport(market_date=MARKET_DATE, rows=[passing, failing]).passed is False


def test_an_empty_report_is_a_failure_not_a_pass():
    # "Nothing to check" must never read as "everything is fine".
    assert AuditReport(market_date=MARKET_DATE, rows=[]).passed is False


def test_an_errored_report_is_a_failure():
    assert AuditReport(market_date=MARKET_DATE, rows=[], error="unreadable").passed is False


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

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._rows)


class _Client:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(self._tables.get(name, []))


def test_run_audit_joins_freshness_and_snapshot_state():
    client = _Client(
        {
            "sets": [{"id": "id-a", "name": "Alpha", "canonical_key": "alpha"}],
            "calculation_history_trend": [
                {
                    "target_id": "id-a",
                    "snapshot_date": "2026-07-27",
                    "calculation_run_id": "run-a",
                    "simulated_mean_pack_value_vs_pack_cost": 0.5,
                    "simulated_median_pack_value_vs_pack_cost": 0.2,
                }
            ],
            "simulation_run_summary": [{"calculation_run_id": "run-a"}],
            "pokemon_set_market_dashboard_snapshot_latest": [
                dict(_dashboard_row(perf_dates=("2026-07-27",)), set_id="id-a", window_key="365d")
            ],
        }
    )
    report = run_audit(client, market_date=MARKET_DATE, unsupported_keys=[], canonical_keys=["alpha"])
    alpha = next((row for row in report.rows if row.canonical_key == "alpha"), None)
    assert alpha is not None
    assert alpha.simulation_status == "stale"
    assert alpha.performance_history_latest_real_date == "2026-07-27"
    assert alpha.passed is False
    assert report.passed is False
