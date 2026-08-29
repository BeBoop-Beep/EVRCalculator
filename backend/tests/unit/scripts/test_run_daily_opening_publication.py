"""Contract tests for the coordinated daily opening-analytics publication.

These pin the ordering guarantee the pipeline previously lacked: simulations run
and are VERIFIED before the run may describe Opening Profit vs Cost as current.
No subprocess is ever launched — the command runners are injected.
"""

import copy

import pytest

from backend.scripts import run_daily_opening_publication as orchestrator
from backend.scripts.run_daily_opening_publication import (
    EXIT_CANNOT_START,
    EXIT_FAILED,
    EXIT_OK,
    PublicationSummary,
    orchestrate,
)
from backend.db.services.publication_gate import GATE_DEFERRED_EXIT_CODE
from backend.db.services.public_rip_publication_contract import (
    DIAGNOSTICS_COHORT_FINGERPRINT_KEY,
    DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY,
    DIAGNOSTICS_CONTRACT_VERSION_KEY,
    canonical_publication_identity,
    supported_cohort_fingerprint,
)

MARKET_DATE = "2026-08-01"
PRIOR_DATE = "2026-07-31"
STALE_DATE = "2026-07-27"

SET_ID = "id-a"
SET_KEY = "alpha"
RUN_ID = "run-a"


# ===========================================================================
# The query fake.
#
# It used to accept only select/eq/in_/order/limit and IGNORE every filter, so
# `_load_value_histories`'s real `.gte(...)` raised AttributeError and the whole
# market-publication audit collapsed into `publication surface read failed`
# before a single assertion ran. Five orchestrator tests "passed through" that
# hole for months.
#
# Two rules keep the replacement honest:
#
#   * NO `__getattr__`. Every fluent method is written out. A production query
#     that starts using a method this fake does not implement must fail loudly
#     with AttributeError, exactly as it did — silently absorbing unknown
#     methods is how the hole would come back.
#   * Filters, ordering, limits and projections are REALLY APPLIED against the
#     fixtures, and an unknown column raises the way PostgREST rejects one.
#     A fake that returns every row regardless of `.eq(...)` cannot distinguish
#     an audit that filtered correctly from one that did not.
# ===========================================================================
class UnknownColumn(Exception):
    """PostgREST rejects a SELECT naming a column the relation does not have."""


# The columns each fixture relation actually exposes. Declared rather than
# inferred from the fixture rows so that a column which is real-but-null still
# selects, and a column that does not exist still fails.
TABLE_COLUMNS = {
    "sets": {
        "id", "name", "canonical_key", "catalog_only", "supports_opening_simulation",
        # era_id backs the public-analytics eligibility rule the market
        # publication audit uses to derive the global Set Value cohort.
        "era_id", "has_sealed_details_url", "ready_for_daily_scrape",
    },
    "calculation_history_trend": {
        "target_type", "target_id", "snapshot_date", "calculation_run_id",
        "simulated_mean_pack_value_vs_pack_cost",
        "simulated_median_pack_value_vs_pack_cost",
    },
    "simulation_run_summary": {"calculation_run_id"},
    "pokemon_scrape_batches": {
        "id", "market_date", "promoted_at", "status",
        "missing_set_count", "expected_set_count",
        "succeeded_set_count", "failed_set_count",
    },
    "pokemon_set_market_dashboard_snapshot_latest": {
        "set_id", "window_key", "latest_market_date", "top_chase_cards_json",
        "top_chase_card_histories_json", "performance_vs_cost_history_json",
    },
    "pokemon_set_sealed_market_snapshot_latest": {"set_id", "market_date", "product_count"},
    "pokemon_set_cards_snapshot_latest": {
        "set_id", "payload_json", "cards_json", "card_count", "updated_at",
    },
    "pokemon_set_page_snapshot_latest": {
        "set_id", "payload_json", "title_card_json", "market_summary_json", "as_of", "updated_at",
    },
    "pokemon_set_value_daily_history": {"set_id", "snapshot_date", "set_value", "value_scope"},
    "sealed_products": {"id", "set_id", "name"},
    "sealed_product_price_observations": {"sealed_product_id", "captured_at"},
    "pokemon_explore_rankings_snapshot_latest": {
        "tcg", "scope", "ranking_payload_json", "updated_at",
    },
    "pokemon_explore_set_value_snapshot_latest": {
        "tcg", "scope", "payload_json", "market_date", "set_count",
        "payload_size_bytes", "updated_at",
    },
    "pokemon_public_rip_leaderboard_snapshots": {
        "id", "market_date", "built_at", "published_at", "publication_status",
        "eligible_cohort_count", "cohort_version", "cohort_fingerprint",
        "overall_rip_version", "financial_rip_version", "ca7_version", "diagnostics_json",
    },
    "pokemon_public_rip_leaderboard_rows": {
        "snapshot_id", "set_id", "set_canonical_key", "overall_rip_score", "overall_rip_rank",
        "financial_rip_score", "financial_rip_rank", "overall_ranked_cohort_count",
        "simulation_calculation_run_id",
    },
    # Deliberately WITHOUT `set_canonical_key`: the live view exposes
    # `canonical_key`, and requesting `set_canonical_key` made PostgREST reject
    # the whole SELECT so the public RIP audit could not run at all. This fake
    # reproduces that rejection.
    "explore_rip_statistics_latest": {
        "set_id", "calculation_run_id", "financial_rip_v3_score_version", "canonical_key", "run_at",
    },
}


class _Result:
    def __init__(self, data):
        self.data = data


class _Not:
    """The `.not_` namespace. Only the operators production uses exist."""

    def __init__(self, query):
        self._query = query

    def is_(self, column, value):
        self._query._require_column(column)
        self._query._ops.append(("not.is", column, value))
        if str(value).lower() == "null":
            self._query._predicates.append(lambda row: row.get(column) is not None)
        else:  # pragma: no cover - production only ever asks for null
            raise AssertionError(f"unsupported not.is value {value!r}")
        return self._query


class _Query:
    """A fluent PostgREST query that really filters, orders, limits and projects."""

    def __init__(self, table, rows, ops_log):
        self._table = table
        self._rows = rows
        self._ops = ops_log
        self._predicates = []
        self._columns = None
        self._order = []
        self._limit = None

    # -- column contract ---------------------------------------------------
    def _require_column(self, column):
        known = TABLE_COLUMNS.get(self._table)
        if known is not None and column not in known:
            raise UnknownColumn(
                f'column "{column}" does not exist on relation "{self._table}"'
            )

    # -- fluent surface (explicit; no __getattr__) --------------------------
    def select(self, columns="*", **_k):
        self._ops.append(("select", self._table, columns))
        if columns and columns != "*":
            requested = [c.strip() for c in str(columns).split(",") if c.strip()]
            for column in requested:
                self._require_column(column)
            self._columns = requested
        return self

    def eq(self, column, value):
        self._require_column(column)
        self._ops.append(("eq", column, value))
        self._predicates.append(lambda row, c=column, v=value: row.get(c) == v)
        return self

    def in_(self, column, values):
        self._require_column(column)
        wanted = list(values)
        self._ops.append(("in", column, wanted))
        self._predicates.append(lambda row, c=column, w=wanted: row.get(c) in w)
        return self

    def gte(self, column, value):
        """Present because `_load_value_histories` and
        `_load_sealed_source_latest_dates` both use it. Its absence is what made
        the whole market audit unreachable."""
        self._require_column(column)
        self._ops.append(("gte", column, value))
        self._predicates.append(
            lambda row, c=column, v=value: row.get(c) is not None and str(row.get(c)) >= str(v)
        )
        return self

    def order(self, column, desc=False, **_k):
        self._require_column(column)
        self._ops.append(("order", column, desc))
        self._order.append((column, bool(desc)))
        return self

    def limit(self, count, **_k):
        self._ops.append(("limit", count))
        self._limit = int(count)
        return self

    @property
    def not_(self):
        return _Not(self)

    # -- execution ---------------------------------------------------------
    def execute(self):
        rows = [row for row in self._rows if all(p(row) for p in self._predicates)]
        # Applied last-key-first so the first `.order(...)` wins, as PostgREST does.
        for column, desc in reversed(self._order):
            rows = sorted(rows, key=lambda row: (row.get(column) is None, row.get(column)), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._columns is not None:
            rows = [{c: row.get(c) for c in self._columns} for row in rows]
        else:
            rows = [dict(row) for row in rows]
        self._ops.append(("execute", self._table, len(rows)))
        return _Result(copy.deepcopy(rows))


# ---------------------------------------------------------------------------
# Production-shaped fixtures for one publication-required set on MARKET_DATE.
# Every value below is the value the corresponding audit section actually reads.
# ---------------------------------------------------------------------------
SET_VALUE = 123.45

SET_ROW = {
    "id": SET_ID,
    "name": "Alpha",
    "canonical_key": SET_KEY,
    "catalog_only": False,
    "supports_opening_simulation": True,
    "has_sealed_details_url": True,
    "ready_for_daily_scrape": True,
}


def _history(date, run_id=RUN_ID, set_id=SET_ID):
    return [
        {
            "target_type": "set",
            "target_id": set_id,
            "snapshot_date": date,
            "calculation_run_id": run_id,
            "simulated_mean_pack_value_vs_pack_cost": 0.51,
            "simulated_median_pack_value_vs_pack_cost": 0.14,
        }
    ]


def _market_fixtures(market_date=MARKET_DATE):
    """Every market surface CURRENT for ``market_date`` — the passing baseline."""
    cohort = supported_cohort_fingerprint([SET_KEY])
    identity = canonical_publication_identity()
    return {
        "pokemon_scrape_batches": [
            {
                "id": 1,
                "market_date": market_date,
                "promoted_at": f"{market_date}T12:00:00+00:00",
                # The real promotion contract: only these satisfy the
                # canonical publication gate. The old fixture used a
                # status ("promoted") that the gate does not recognise.
                "status": "complete",
                "missing_set_count": 0,
                "expected_set_count": 1,
                "succeeded_set_count": 1,
                "failed_set_count": 0,
            }
        ],
        "pokemon_set_market_dashboard_snapshot_latest": [
            {
                "set_id": SET_ID,
                "window_key": "365d",
                "latest_market_date": market_date,
                "top_chase_cards_json": [
                    {"cardVariantId": "cv-a", "setId": SET_ID, "marketPrice": 12.0}
                ],
                "top_chase_card_histories_json": {
                    "cv-a": [
                        {"date": PRIOR_DATE, "marketPrice": 11.0},
                        {"date": market_date, "marketPrice": 12.0},
                    ]
                },
                "performance_vs_cost_history_json": [
                    {"date": PRIOR_DATE, "simulatedMeanPackValueVsPackCost": 0.49},
                    {"date": market_date, "simulatedMeanPackValueVsPackCost": 0.51},
                ],
            }
        ],
        "pokemon_set_sealed_market_snapshot_latest": [
            {"set_id": SET_ID, "market_date": market_date, "product_count": 1}
        ],
        "pokemon_set_cards_snapshot_latest": [
            {
                "set_id": SET_ID,
                "payload_json": {"meta": {"pricingContract": {"latestMarketDate": market_date}}},
                "cards_json": [{"id": "card-1", "marketPrice": 3.5}],
                "card_count": 1,
                "updated_at": f"{market_date}T12:00:00+00:00",
            }
        ],
        "pokemon_set_page_snapshot_latest": [
            {
                "set_id": SET_ID,
                "payload_json": {"meta": {"snapshot": {"marketAsOfDate": market_date}}},
                "title_card_json": {},
                "market_summary_json": {"setValue": SET_VALUE},
                "as_of": market_date,
                "updated_at": f"{market_date}T12:00:00+00:00",
            }
        ],
        "pokemon_set_value_daily_history": [
            {"set_id": SET_ID, "snapshot_date": PRIOR_DATE, "set_value": 120.0, "value_scope": "standard"},
            {"set_id": SET_ID, "snapshot_date": market_date, "set_value": SET_VALUE, "value_scope": "standard"},
            # A different scope, and an out-of-window date, both of which the
            # real query filters out. If the fake ignored .eq/.gte these would
            # corrupt the canonical set value and the section would fail.
            {"set_id": SET_ID, "snapshot_date": market_date, "set_value": 999.0, "value_scope": "hits"},
        ],
        "sealed_products": [{"id": "sp-1", "set_id": SET_ID, "name": "Alpha Booster Box"}],
        "sealed_product_price_observations": [
            {"sealed_product_id": "sp-1", "captured_at": f"{market_date}T09:00:00+00:00"},
            {"sealed_product_id": "sp-1", "captured_at": f"{STALE_DATE}T09:00:00+00:00"},
        ],
        "pokemon_explore_rankings_snapshot_latest": [
            {
                "tcg": "pokemon",
                "scope": "rip-statistics",
                "ranking_payload_json": {
                    "meta": {"snapshot": {"marketDate": market_date}},
                    "targets": [
                        {
                            "set_id": SET_ID,
                            "canonical_key": SET_KEY,
                            "checklistSetValue": SET_VALUE,
                            "checklistSetValueAsOf": market_date,
                        }
                    ],
                },
                "updated_at": f"{market_date}T12:00:00+00:00",
            }
        ],
        # The compact global artifact /Market's Set Value ladder renders. It is a
        # DIFFERENT public surface from the RIP rankings snapshot above, and the
        # audit requires it independently.
        "pokemon_explore_set_value_snapshot_latest": [
            {
                "tcg": "pokemon",
                "scope": "market",
                "payload_json": {
                    "meta": {"snapshot": {"marketDate": market_date}},
                    "sets": [
                        {
                            "setId": SET_ID,
                            "canonicalKey": SET_KEY,
                            "name": "Alpha",
                            "currentSetValue": SET_VALUE,
                            "setValueAsOf": market_date,
                            "windows": {
                                key: {"amount": 1.0, "percent": 1.0}
                                for key in ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
                            },
                        }
                    ],
                },
                "market_date": market_date,
                "set_count": 1,
                "payload_size_bytes": 512,
                "updated_at": f"{market_date}T12:00:00+00:00",
            }
        ],
        "pokemon_public_rip_leaderboard_snapshots": [
            {
                "id": "snap-1",
                "market_date": market_date,
                "built_at": f"{market_date}T12:00:00+00:00",
                "published_at": f"{market_date}T12:05:00+00:00",
                "publication_status": "complete",
                "eligible_cohort_count": 1,
                "cohort_version": cohort["version"],
                "cohort_fingerprint": cohort["fingerprint"],
                "overall_rip_version": identity["overallRipVersion"],
                "financial_rip_version": identity["financialRipVersion"],
                "ca7_version": identity["collectorAppealVersion"],
                "diagnostics_json": {
                    DIAGNOSTICS_CONTRACT_VERSION_KEY: identity["publicRipContractVersion"],
                    DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY: identity["collectorAppealVersion"],
                    DIAGNOSTICS_COHORT_FINGERPRINT_KEY: cohort["fingerprint"],
                },
            }
        ],
        "pokemon_public_rip_leaderboard_rows": [
            {
                "snapshot_id": "snap-1",
                "set_id": SET_ID,
                "set_canonical_key": SET_KEY,
                "overall_rip_score": 71.2,
                "overall_rip_rank": 1,
                "financial_rip_score": 68.4,
                "financial_rip_rank": 1,
                "overall_ranked_cohort_count": 1,
                "simulation_calculation_run_id": RUN_ID,
            }
        ],
        "explore_rip_statistics_latest": [
            {
                "set_id": SET_ID,
                "canonical_key": SET_KEY,
                "calculation_run_id": RUN_ID,
                "financial_rip_v3_score_version": identity["financialRipVersion"],
                "run_at": f"{market_date}T11:00:00+00:00",
            }
        ],
    }


class _Client:
    """Replays table rows; ``history_pages`` lets a run change between reads.

    ``tables`` carries the market/leaderboard fixtures the two later audits read;
    it defaults to the fully-current baseline so a test only states the surface
    it is actually about. ``raise_on`` makes one relation unreadable.
    """

    def __init__(self, *, sets_rows, history_pages, summary_rows, tables=None, raise_on=None):
        self._sets = sets_rows
        self._history_pages = list(history_pages)
        self._summary = summary_rows
        self._tables = _market_fixtures() if tables is None else dict(tables)
        self._raise_on = dict(raise_on or {})
        self.history_reads = 0
        self.ops = []

    @property
    def tables_read(self):
        return [table for op in self.ops if op[0] == "execute" for table in (op[1],)]

    def table(self, name):
        if name in self._raise_on:
            raise self._raise_on[name]
        if name == "sets":
            return _Query(name, self._sets, self.ops)
        if name == "simulation_run_summary":
            return _Query(name, self._summary, self.ops)
        if name == "calculation_history_trend":
            index = min(self.history_reads, len(self._history_pages) - 1)
            self.history_reads += 1
            return _Query(name, self._history_pages[index], self.ops)
        return _Query(name, self._tables.get(name, []), self.ops)


@pytest.fixture
def patched(monkeypatch):
    """Record the ordered sequence of orchestration steps."""
    calls = []

    def fake_resolve(_client, explicit):
        return (explicit or MARKET_DATE), None

    def fake_run_sims(set_keys, **_kwargs):
        calls.append(("simulate", list(set_keys)))
        return [
            orchestrator.SimulationOutcome(canonical_key=key, succeeded=True)
            for key in set_keys
        ]

    def fake_refresh(**_kwargs):
        calls.append(("refresh", []))
        return 0

    def fake_chase_refresh(**_kwargs):
        calls.append(("chase", []))
        return 0

    import backend.scripts.audit_opening_analytics_publication as audit_module

    def fake_audit(_client, **_kwargs):
        calls.append(("audit", []))
        return audit_module.AuditReport(
            market_date=MARKET_DATE,
            rows=[
                audit_module.SetAuditRow(
                    canonical_key="alpha",
                    set_id="id-a",
                    set_name="Alpha",
                    simulation_status="current",
                )
            ],
        )

    monkeypatch.setattr(audit_module, "resolve_market_date", fake_resolve)
    monkeypatch.setattr(audit_module, "run_audit", fake_audit)
    monkeypatch.setattr(orchestrator, "run_simulations_for_sets", fake_run_sims)
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", fake_refresh)
    monkeypatch.setattr(orchestrator, "refresh_chase_economics_snapshots", fake_chase_refresh)
    return calls


def _client(history_pages, **kwargs):
    return _Client(
        sets_rows=[dict(SET_ROW)],
        history_pages=history_pages,
        summary_rows=[{"calculation_run_id": RUN_ID}],
        **kwargs,
    )


def _orchestrate(client, **kwargs):
    # canonical_keys is threaded through the gate; restrict to the fake set.
    import backend.db.services.opening_simulation_gate as gate

    original = gate.supported_opening_set_keys
    gate.supported_opening_set_keys = lambda: ("alpha",)
    try:
        return orchestrate(
            client,
            simulation_execution_date=kwargs.pop("simulation_execution_date", MARKET_DATE),
            **kwargs,
        )
    finally:
        gate.supported_opening_set_keys = original


def test_simulations_run_before_snapshots_are_built(patched):
    # Stale first read, current after the simulation.
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert [step for step, _ in patched] == ["simulate", "refresh", "chase", "audit"], (
        "simulate and coordinated refresh must precede Chase, then the audit reads the publication"
    )
    assert patched[0][1] == ["alpha"]
    assert summary.exit_code == EXIT_OK
    assert summary.verification_passed is True
    assert summary.snapshot_publication_status == "published"


def test_previous_day_rollover_defers_without_launching_simulation(monkeypatch, patched):
    persisted = []
    monkeypatch.setattr(orchestrator, "_persist_rankings_deferral", lambda _client, report: persisted.append(report))
    client = _client([_history(STALE_DATE)])

    summary = _orchestrate(client, simulation_execution_date="2026-08-02")

    assert not [call for call in patched if call[0] == "simulate"]
    assert summary.exit_code == GATE_DEFERRED_EXIT_CODE
    assert summary.rankings_readiness_reason_code == "DEFERRED_SIMULATION_DATE_ROLLOVER"
    assert summary.simulation_execution_date == "2026-08-02"
    assert "cannot be backdated" in summary.error
    assert persisted and persisted[0].reason_code == "DEFERRED_SIMULATION_DATE_ROLLOVER"


def test_rollover_dry_run_never_persists_attempt(monkeypatch, patched):
    monkeypatch.setattr(
        orchestrator,
        "_persist_rankings_deferral",
        lambda *_a, **_k: pytest.fail("dry-run must not persist a publication attempt"),
    )
    summary = _orchestrate(
        _client([_history(STALE_DATE)]),
        simulation_execution_date="2026-08-02",
        dry_run=True,
    )
    assert summary.exit_code == GATE_DEFERRED_EXIT_CODE


def test_mixed_current_day_cohort_runs_only_stale_sets(monkeypatch, patched):
    from backend.db.services.opening_simulation_gate import (
        OpeningSetSimulationStatus,
        OpeningSimulationFreshnessReport,
        STATUS_CURRENT,
        STATUS_STALE,
    )

    keys = [f"set-{index:02d}" for index in range(22)]
    before = OpeningSimulationFreshnessReport(
        market_date=MARKET_DATE,
        statuses=[
            OpeningSetSimulationStatus(
                canonical_key=key, set_id=key, set_name=key,
                status=STATUS_CURRENT if index == 0 else STATUS_STALE,
                latest_simulation_date=MARKET_DATE if index == 0 else PRIOR_DATE,
                calculation_run_id=f"run-{index}" if index == 0 else None,
            )
            for index, key in enumerate(keys)
        ],
    )
    after = OpeningSimulationFreshnessReport(
        market_date=MARKET_DATE,
        statuses=[
            OpeningSetSimulationStatus(
                canonical_key=key, set_id=key, set_name=key, status=STATUS_CURRENT,
                latest_simulation_date=MARKET_DATE, calculation_run_id=f"run-{index}",
            )
            for index, key in enumerate(keys)
        ],
    )
    reports = iter((before, after))
    monkeypatch.setattr(orchestrator, "evaluate_opening_simulation_freshness", lambda *_a, **_k: next(reports))

    summary = _orchestrate(_client([_history(MARKET_DATE)]))

    simulations = [sets for step, sets in patched if step == "simulate"]
    assert simulations == [keys[1:]]
    assert any(entry["set"] == keys[0] and "already current" in entry["reason"] for entry in summary.skipped)
    assert summary.verification_passed is True


def test_tier_a_exists_before_same_run_snapshot_projection(monkeypatch, patched):
    """Regression: daily research must be available to this day's projection."""
    from backend.db.services.ev_representativeness_public_service import (
        project_opening_outcome_profile_v1,
        project_public_v1,
    )

    research = {}

    def build_before_snapshot(_client, freshness, *, dry_run):
        patched.append(("tier_a", []))
        run_id = next(item.calculation_run_id for item in freshness.statuses if item.status == "current")
        research[run_id] = {
            "calculation_run_id": run_id,
            "research_method_version": "ev_representativeness_v1",
            "market_date": MARKET_DATE,
            "source_artifact_sha256": "a" * 64,
            "typical_capture": .5,
            "top1_outcome_ev_share": .2,
            "ev": 5,
            "p50": 2.5,
            "return_ratio_buckets_json": {
                "cost": 10, "sampleSize": 8,
                "buckets": [
                    {"ratioFloor": floor, "ratioCeiling": ceiling,
                     "occurrenceCount": 1, "probability": .125}
                    for floor, ceiling in ((0,.25),(.25,.5),(.5,.75),(.75,1),(1,1.5),(1.5,2),(2,5),(5,None))
                ],
            },
        }
        return "research_complete eligible=1 existing=0 built=1 failed=0"

    def project_during_refresh(**_kwargs):
        patched.append(("refresh", []))
        row = research[RUN_ID]  # proves the builder ran before projection
        ev = project_public_v1(row, [], expected_calculation_run_id=RUN_ID)
        outcome = project_opening_outcome_profile_v1(row, expected_calculation_run_id=RUN_ID)
        assert ev["calculationRunId"] == RUN_ID
        assert outcome["calculationRunId"] == RUN_ID
        return 0

    monkeypatch.setattr(orchestrator, "_build_ev_representativeness_tier_a", build_before_snapshot)
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", project_during_refresh)
    summary = _orchestrate(_client([_history(MARKET_DATE)]))

    order = [step for step, _ in patched]
    assert order.index("tier_a") < order.index("refresh")
    assert summary.exit_code == EXIT_OK


def test_one_tier_a_failure_is_recorded_but_does_not_block_other_sets(monkeypatch, patched):
    from backend.db.services import ev_representativeness_service as service
    from backend.db.services.ev_representativeness_public_service import project_opening_outcome_profile_v1
    from backend.db.services.opening_simulation_gate import OpeningSetSimulationStatus, OpeningSimulationFreshnessReport

    attempts = []
    research_rows = {}
    def fake_build(_client, run_id):
        attempts.append(run_id)
        if run_id == "run-bad":
            raise RuntimeError("artifact read failed")
        research_rows[run_id] = {
            "calculation_run_id": run_id, "research_method_version": "ev_representativeness_v1",
            "market_date": MARKET_DATE, "source_artifact_sha256": "b" * 64, "ev": 5, "p50": 2,
            "return_ratio_buckets_json": {"cost": 10, "sampleSize": 8, "buckets": [
                {"ratioFloor": floor, "ratioCeiling": ceiling, "occurrenceCount": 1, "probability": .125}
                for floor, ceiling in ((0,.25),(.25,.5),(.5,.75),(.75,1),(1,1.5),(1.5,2),(2,5),(5,None))
            ]},
        }
        return {"status": "research_built", "calculationRunId": run_id}

    monkeypatch.setattr(service, "build_tier_a_for_run", fake_build)
    freshness = OpeningSimulationFreshnessReport(market_date=MARKET_DATE, statuses=[
        OpeningSetSimulationStatus("good", "set-good", "Good", "current", calculation_run_id="run-good"),
        OpeningSetSimulationStatus("bad", "set-bad", "Bad", "current", calculation_run_id="run-bad"),
    ])
    status = orchestrator._build_ev_representativeness_tier_a(object(), freshness, dry_run=False)
    assert attempts == ["run-good", "run-bad"]
    assert status == "research_partial eligible=2 existing=0 built=1 failed=1"
    assert project_opening_outcome_profile_v1(
        research_rows["run-good"], expected_calculation_run_id="run-good"
    )["calculationRunId"] == "run-good"
    assert research_rows.get("run-bad") is None  # affected target has no optional projection source

    # The orchestration treats that status as observability, never as a gate.
    calls = []
    monkeypatch.setattr(orchestrator, "_build_ev_representativeness_tier_a", lambda *_a, **_k: status)
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", lambda **_k: calls.append("refresh") or 0)
    monkeypatch.setattr(orchestrator, "refresh_chase_economics_snapshots", lambda **_k: 0)
    summary = _orchestrate(_client([_history(MARKET_DATE)]))
    assert calls == ["refresh"]
    assert summary.exit_code == EXIT_OK
    assert summary.ev_representativeness_status == status


def test_chase_refresh_targets_current_authorities_and_same_market_date(monkeypatch):
    captured = []
    monkeypatch.setattr(orchestrator, "_run_command", lambda command, **_k: captured.append(command) or 0)
    assert orchestrator.refresh_chase_economics_snapshots(
        python_executable="python", market_date=MARKET_DATE
    ) == 0
    command = captured[0]
    assert "--current-authorities" in command
    assert command[command.index("--market-date") + 1] == MARKET_DATE


def test_a_set_already_current_is_skipped_so_reruns_do_no_work(patched):
    client = _client([_history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert patched[0] == ("simulate", []), "a current set must not be re-simulated"
    assert summary.exit_code == EXIT_OK
    assert any(entry["set"] == "alpha" and "already current" in entry["reason"] for entry in summary.skipped)


def test_rerunning_the_same_market_date_is_idempotent(patched):
    client = _client([_history(MARKET_DATE)])
    first = _orchestrate(client)
    second = _orchestrate(client)

    assert first.exit_code == second.exit_code == EXIT_OK
    assert all(step_sets == [] for step, step_sets in patched if step == "simulate")


def test_a_simulation_failure_prevents_claiming_full_freshness(monkeypatch, patched):
    def failing_sims(set_keys, **_kwargs):
        patched.append(("simulate", list(set_keys)))
        return [
            orchestrator.SimulationOutcome(canonical_key=key, succeeded=False, reason="boom")
            for key in set_keys
        ]

    monkeypatch.setattr(orchestrator, "run_simulations_for_sets", failing_sims)
    # Still stale on the verification read — the simulation did not land.
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.simulation_failed == 1
    assert summary.verification_passed is False
    assert "NOT current" in summary.error


def test_verification_failure_alone_fails_even_when_simulations_reported_success(patched):
    # The runner exited 0 but no row landed for the market date. Trusting the
    # exit code alone is exactly how a frozen series looks healthy.
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client)

    assert summary.simulation_failed == 0
    assert summary.verification_passed is False
    assert summary.exit_code == EXIT_FAILED
    assert summary.latest_simulation_date_by_set["alpha"] == STALE_DATE


def test_a_missing_summary_join_blocks_publication(patched):
    client = _Client(
        sets_rows=[dict(SET_ROW)],
        history_pages=[_history(MARKET_DATE), _history(MARKET_DATE)],
        summary_rows=[],  # the join target is absent
    )
    summary = _orchestrate(client)
    assert summary.verification_passed is False
    assert summary.exit_code == EXIT_FAILED


def test_unsupported_sets_are_skipped_with_a_reason(patched):
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client, unsupported_keys=["alpha"])

    assert summary.exit_code == EXIT_OK
    assert summary.verification_passed is True
    assert summary.skipped == [
        {"set": "alpha", "reason": "explicitly excepted from opening analytics"}
    ]
    assert patched[0] == ("simulate", [])


def test_an_unresolvable_market_date_cannot_start(monkeypatch):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    monkeypatch.setattr(
        audit_module, "resolve_market_date", lambda *_a, **_k: (None, "no promoted batch")
    )
    summary = _orchestrate(_client([_history(MARKET_DATE)]))
    assert summary.exit_code == EXIT_CANNOT_START
    assert "no promoted batch" in summary.error


def test_a_deferred_cohort_propagates_exit_3(monkeypatch, patched):
    monkeypatch.setattr(
        orchestrator, "refresh_public_snapshots", lambda **_k: GATE_DEFERRED_EXIT_CODE
    )
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == GATE_DEFERRED_EXIT_CODE
    assert summary.snapshot_publication_status == "deferred_cohort_not_ready"


def test_a_snapshot_build_failure_fails_the_run(monkeypatch, patched):
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", lambda **_k: 7)
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.snapshot_publication_status == "failed_exit_7"


def test_summary_reports_every_required_field(patched):
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    text = "\n".join(_orchestrate(client).lines())

    for expected in (
        f"market_date={MARKET_DATE}",
        "eligible_sets=",
        "simulations_succeeded=",
        "simulations_failed=",
        "skipped_sets=",
        "latest_simulation_date_by_set:",
        "snapshot_publication_status=",
        "verification_passed=",
        "exit_code=",
    ):
        assert expected in text, f"summary is missing {expected!r}"


def test_the_market_date_is_never_taken_from_wall_clock():
    from pathlib import Path

    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    assert "datetime.now()" not in source
    assert "date.today()" not in source


def test_snapshot_builders_are_not_asked_to_run_simulations():
    # The separation of responsibilities this incident depended on: publication
    # republishes, it never computes.
    from pathlib import Path

    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    assert "refresh_stale_public_snapshots.py" in source
    assert "run_all_v2_sets.py" in source
    # The refresh command must not be handed a simulation flag.
    assert "--simulate" not in source


def test_default_summary_is_a_failure_until_proven_otherwise():
    assert PublicationSummary().exit_code == EXIT_CANNOT_START
    assert PublicationSummary().verification_passed is False


# ---------------------------------------------------------------------------
# The publication verdict must consume the read-only audit.
#
# Current simulations are necessary but not sufficient: the market-dashboard
# snapshot is what Overview reads, and it can lag the simulation it was built
# from. Exit 0 must mean "what got published reached the market date", not
# "the commands ran".
# ---------------------------------------------------------------------------


def _failing_audit_report(reason="performance history ends 2026-07-31, market date is 2026-08-01"):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    return audit_module.AuditReport(
        market_date=MARKET_DATE,
        rows=[
            audit_module.SetAuditRow(
                canonical_key="alpha",
                set_id="id-a",
                set_name="Alpha",
                simulation_status="current",
                failures=[reason],
            )
        ],
    )


def test_current_simulations_do_not_excuse_a_lagging_dashboard(monkeypatch, patched):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    monkeypatch.setattr(audit_module, "run_audit", lambda _client, **_kwargs: _failing_audit_report())
    client = _client([_history(MARKET_DATE)])

    summary = _orchestrate(client)

    assert summary.verification_passed is True, "simulations themselves are current"
    assert summary.exit_code == EXIT_FAILED, "a lagging published dashboard must not exit 0"
    assert summary.publication_audit_status == "failed"
    assert summary.publication_audit_failed_sets == ["alpha"]
    assert "did not reach" in (summary.error or "")


def test_a_passing_audit_allows_exit_zero(patched):
    client = _client([_history(MARKET_DATE)])

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_OK
    assert summary.publication_audit_status == "passed"
    assert summary.publication_audit_failed_sets == []
    # Exit 0 requires ALL THREE audits, not just the opening one. Asserting the
    # opening audit alone is what let the market audit sit unreachable behind a
    # missing `.gte(...)` while this test still read as green.
    assert summary.market_audit_status == "passed"
    assert summary.rip_contract_audit_status == "passed"


def test_dual_rankings_page_clocks_must_both_match_promoted_date(monkeypatch, patched):
    monkeypatch.setattr(orchestrator, "_rip_stats_capability_expected", lambda _client: True)
    def publish_stats(_client, summary, *, market_date, dry_run):
        summary.rip_stats_market_date = market_date
        return "published"
    monkeypatch.setattr(orchestrator, "_publish_rip_stats", publish_stats)
    monkeypatch.setattr(orchestrator, "_audit_rip_stats", lambda *_a, **_k: "passed")
    def stale_rankings(_client, summary, **_kwargs):
        summary.rankings_market_date = PRIOR_DATE
        return "passed"
    monkeypatch.setattr(orchestrator, "_run_rip_contract_audit", stale_rankings)

    summary = _orchestrate(_client([_history(MARKET_DATE)]))

    assert summary.exit_code == EXIT_FAILED
    assert summary.rip_stats_market_date == MARKET_DATE
    assert summary.rankings_market_date == PRIOR_DATE
    assert "publication clocks disagree" in summary.error


def test_dual_rankings_page_clocks_allow_same_date_success(monkeypatch, patched):
    monkeypatch.setattr(orchestrator, "_rip_stats_capability_expected", lambda _client: True)
    def publish_stats(_client, summary, *, market_date, dry_run):
        summary.rip_stats_market_date = market_date
        return "published"
    monkeypatch.setattr(orchestrator, "_publish_rip_stats", publish_stats)
    monkeypatch.setattr(orchestrator, "_audit_rip_stats", lambda *_a, **_k: "passed")

    summary = _orchestrate(_client([_history(MARKET_DATE)]))

    assert summary.exit_code == EXIT_OK
    assert summary.rip_stats_market_date == summary.rankings_market_date == MARKET_DATE


def test_an_unreadable_audit_is_not_reported_as_success(monkeypatch, patched):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    def raise_audit(_client, **_kwargs):
        raise RuntimeError("dashboard read failed")

    monkeypatch.setattr(audit_module, "run_audit", raise_audit)
    client = _client([_history(MARKET_DATE)])

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.publication_audit_status.startswith("error:")


def test_audit_is_skipped_when_nothing_was_published(patched):
    client = _client([_history(MARKET_DATE)])

    summary = _orchestrate(client, skip_snapshots=True)

    assert summary.publication_audit_status == "skipped"
    assert summary.exit_code == EXIT_OK
    assert "audit" not in [step for step, _ in patched]


def test_skip_snapshots_never_attempts_rip_stats_publication(monkeypatch, patched):
    monkeypatch.setattr(orchestrator, "_rip_stats_capability_expected", lambda _client: True)
    monkeypatch.setattr(orchestrator, "_publish_rip_stats", lambda *_a, **_k: pytest.fail("RIP Stats must not publish"))
    client = _client([_history(MARKET_DATE)])
    summary = _orchestrate(client, skip_snapshots=True)
    assert summary.exit_code == EXIT_OK
    assert summary.rip_stats_publication_status == "skipped_skip_snapshots"
    assert summary.rip_stats_audit_status == "skipped"


def test_summary_reports_the_publication_audit_verdict(monkeypatch, patched):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    monkeypatch.setattr(audit_module, "run_audit", lambda _client, **_kwargs: _failing_audit_report())
    client = _client([_history(MARKET_DATE)])

    text = "\n".join(_orchestrate(client).lines())

    assert "publication_audit_status=failed" in text
    assert "publication_audit_failed_sets=alpha" in text


# ===========================================================================
# The market-publication audit and the public RIP contract audit must ACTUALLY
# EXECUTE — and each must independently be able to stop exit 0.
#
# Before the fake implemented `.gte(...)`, `_load_value_histories` raised
# AttributeError, `run_market_publication_audit` caught it as
# "publication surface read failed", and the run failed for a reason that had
# nothing to do with the data. Nothing below can pass unless the real query
# path runs end to end.
# ===========================================================================


def _fixtures_with(table, rows):
    tables = _market_fixtures()
    tables[table] = rows
    return tables


def test_the_orchestrator_reaches_all_three_audits_before_exiting_zero(patched):
    client = _client([_history(MARKET_DATE)])

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_OK
    assert (summary.publication_audit_status, summary.market_audit_status,
            summary.rip_contract_audit_status) == ("passed", "passed", "passed")

    read = client.tables_read
    # The market audit's own sources.
    for table in (
        "pokemon_set_market_dashboard_snapshot_latest",
        "pokemon_set_sealed_market_snapshot_latest",
        "pokemon_set_cards_snapshot_latest",
        "pokemon_set_page_snapshot_latest",
        "pokemon_set_value_daily_history",
        "sealed_products",
        "sealed_product_price_observations",
        "pokemon_explore_rankings_snapshot_latest",
    ):
        assert table in read, f"market audit never read {table}"
    # The public RIP contract audit's own sources.
    for table in (
        "pokemon_public_rip_leaderboard_snapshots",
        "pokemon_public_rip_leaderboard_rows",
        "explore_rip_statistics_latest",
    ):
        assert table in read, f"RIP contract audit never read {table}"


def test_the_market_audit_really_issues_a_gte_filtered_history_read(patched):
    client = _client([_history(MARKET_DATE)])

    _orchestrate(client)

    gte_ops = [op for op in client.ops if op[0] == "gte"]
    assert ("gte", "snapshot_date", MARKET_DATE) in gte_ops, (
        "the value-history read must be bounded by the promoted market date"
    )
    assert any(op[1] == "captured_at" for op in gte_ops), (
        "the sealed source read must be bounded by the promoted market date"
    )
    # And the filters really applied: the out-of-scope `hits` row (set_value
    # 999.0) never reached the audit, so the Explore/page comparison agreed.
    assert ("eq", "value_scope", "standard") in client.ops


def test_a_market_audit_failure_prevents_success(patched):
    """A dashboard whose OPvC never reached the promoted date must fail the run."""
    stale = _market_fixtures()
    stale["pokemon_set_market_dashboard_snapshot_latest"][0][
        "performance_vs_cost_history_json"
    ] = [{"date": STALE_DATE, "simulatedMeanPackValueVsPackCost": 0.4}]
    client = _client([_history(MARKET_DATE)], tables=stale)

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.market_audit_status == "failed"
    assert summary.market_audit_failed_sets == [SET_KEY]
    assert summary.rip_contract_audit_status == "not_attempted", (
        "a failed market audit must short-circuit before claiming success"
    )


def test_a_stale_explore_set_value_prevents_success(patched):
    """The Explore surface is audited independently of the set page."""
    stale = _market_fixtures()
    stale["pokemon_explore_rankings_snapshot_latest"][0]["ranking_payload_json"]["targets"][0][
        "checklistSetValue"
    ] = 999.99
    client = _client([_history(MARKET_DATE)], tables=stale)

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.market_audit_status == "failed"


def test_a_public_rip_audit_failure_prevents_success(patched):
    """An obsolete published scoring version moves no timestamp — and must still fail."""
    stale = _market_fixtures()
    stale["pokemon_public_rip_leaderboard_snapshots"][0][
        "financial_rip_version"
    ] = "financial_rip_v2_60_25_15"
    client = _client([_history(MARKET_DATE)], tables=stale)

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.market_audit_status == "passed", "the market surfaces are genuinely current"
    assert summary.rip_contract_audit_status == "failed"
    assert any("financial_rip_is_v3" in failure for failure in summary.rip_contract_audit_failures)
    assert "canonical scoring contract" in (summary.error or "")


def test_a_superseded_source_run_prevents_success(patched):
    """A re-run after a fix must reach the public page, or the run fails."""
    stale = _market_fixtures()
    stale["explore_rip_statistics_latest"][0]["calculation_run_id"] = "run-b"
    client = _client([_history(MARKET_DATE)], tables=stale)

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.rip_contract_audit_status == "failed"
    assert any(
        "every_row_from_latest_eligible_run" in failure
        for failure in summary.rip_contract_audit_failures
    )


def test_a_query_exception_during_the_market_audit_prevents_success(patched):
    client = _client(
        [_history(MARKET_DATE)],
        raise_on={"pokemon_set_cards_snapshot_latest": RuntimeError("connection reset")},
    )

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.market_audit_status.startswith("error:")
    assert "publication surface read failed" in summary.market_audit_status
    assert summary.rip_contract_audit_status == "not_attempted"


def test_a_service_role_timeout_during_the_market_audit_prevents_success(patched):
    """A timeout is a failure. It is never a pass, a fresh result, or a skip."""

    class ReadTimeout(Exception):
        pass

    client = _client(
        [_history(MARKET_DATE)],
        raise_on={"pokemon_set_value_daily_history": ReadTimeout("timed out")},
    )

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.market_audit_status.startswith("error:")
    assert summary.market_audit_status != "skipped"
    assert summary.rip_contract_audit_status == "not_attempted"


def test_a_service_role_timeout_during_the_rip_audit_prevents_success(patched):
    class ReadTimeout(Exception):
        pass

    client = _client(
        [_history(MARKET_DATE)],
        raise_on={"pokemon_public_rip_leaderboard_snapshots": ReadTimeout("timed out")},
    )

    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.rip_contract_audit_status.startswith("error:")


def test_every_audit_failure_exits_the_process_nonzero(monkeypatch, patched):
    """main() propagates the verdict as the process exit code."""
    stale = _market_fixtures()
    stale["pokemon_public_rip_leaderboard_snapshots"][0]["publication_status"] = "failed"
    client = _client([_history(MARKET_DATE)], tables=stale)

    monkeypatch.setattr(
        "backend.scripts.pokemon_snapshot_builders.get_client", lambda: client
    )
    import backend.db.services.opening_simulation_gate as gate

    original = gate.supported_opening_set_keys
    gate.supported_opening_set_keys = lambda: (SET_KEY,)
    try:
        code = orchestrator.main([])
    finally:
        gate.supported_opening_set_keys = original

    assert code != EXIT_OK
    assert code == EXIT_FAILED


# ---------------------------------------------------------------------------
# The fake must stay honest.
# ---------------------------------------------------------------------------
def test_the_fake_rejects_an_unimplemented_query_method():
    """No __getattr__: a production query using a new method must fail loudly."""
    query = _Query("sets", [dict(SET_ROW)], [])
    with pytest.raises(AttributeError):
        query.lte("id", "z")
    with pytest.raises(AttributeError):
        query.range(0, 99)


def test_the_fake_rejects_an_unknown_column_the_way_postgrest_does():
    query = _Query("sets", [dict(SET_ROW)], [])
    with pytest.raises(UnknownColumn):
        query.select("id,not_a_real_column")


def test_the_rip_view_still_refuses_set_canonical_key():
    """`explore_rip_statistics_latest` exposes `canonical_key`, never
    `set_canonical_key`. Requesting the latter made PostgREST reject the whole
    SELECT, so the public RIP audit could not run at all."""
    query = _Query("explore_rip_statistics_latest", [], [])
    with pytest.raises(UnknownColumn):
        query.select("set_id,set_canonical_key")


def test_the_public_rip_audit_selects_exactly_the_three_contract_columns(patched):
    client = _client([_history(MARKET_DATE)])

    _orchestrate(client)

    selects = [op[2] for op in client.ops if op[0] == "select" and op[1] == "explore_rip_statistics_latest"]
    assert selects == ["set_id,calculation_run_id,financial_rip_v3_score_version"]
