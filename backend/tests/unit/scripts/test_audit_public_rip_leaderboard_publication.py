"""Contract tests for the READ-ONLY published RIP leaderboard audit.

The defect these pin: the audit selected `set_canonical_key` from
`explore_rip_statistics_latest`, a column that view does not expose (it exposes
`canonical_key`). PostgREST rejects the whole SELECT, so the strict audit could
not run at all — the failure mode is "the audit is unavailable", which must
never read as a pass.
"""

from backend.scripts import audit_public_rip_leaderboard_publication as audit
from backend.db.services.public_rip_publication_contract import (
    canonical_publication_identity,
    supported_cohort_fingerprint,
)


# --- a fake PostgREST that enforces the REAL view shape ---------------------

# Exactly the columns the live view exposes for this audit's purposes. Note
# `canonical_key`, NOT `set_canonical_key`.
EXPLORE_RIP_STATISTICS_LATEST_COLUMNS = frozenset(
    {"set_id", "canonical_key", "calculation_run_id", "financial_rip_v3_score_version", "run_at"}
)
LEADERBOARD_ROW_COLUMNS = frozenset(
    {
        "set_id", "set_canonical_key", "overall_rip_score", "overall_rip_rank",
        "financial_rip_score", "financial_rip_rank", "overall_ranked_cohort_count",
        "financial_ranked_cohort_count", "simulation_calculation_run_id",
        "source_market_date", "pack_price", "snapshot_id",
    }
)
SNAPSHOT_COLUMNS = frozenset(
    {
        "id", "market_date", "built_at", "published_at", "publication_status",
        "eligible_cohort_count", "cohort_version", "cohort_fingerprint",
        "overall_rip_version", "financial_rip_version", "ca7_version",
        "payload_json", "diagnostics_json",
    }
)
KNOWN_COLUMNS = {
    "explore_rip_statistics_latest": EXPLORE_RIP_STATISTICS_LATEST_COLUMNS,
    "pokemon_public_rip_leaderboard_rows": LEADERBOARD_ROW_COLUMNS,
    "pokemon_public_rip_leaderboard_snapshots": SNAPSHOT_COLUMNS,
}


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, recorder, table, rows, columns, raise_on_execute=None):
        self._recorder = recorder
        self._table = table
        self._rows = rows
        self._columns = columns
        self._raise = raise_on_execute

    def select(self, columns):
        self._recorder.setdefault(self._table, []).append(columns)
        requested = [column.strip() for column in columns.split(",") if column.strip()]
        unknown = [column for column in requested if column not in self._columns]
        if unknown:
            # What PostgREST does with an unknown column: rejects the request.
            raise RuntimeError(
                f'column {self._table}.{unknown[0]} does not exist (PGRST204)'
            )
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return _Result(self._rows)


class _FakeClient:
    def __init__(self, tables, *, raise_on=None):
        self.tables = tables
        self.selects = {}
        self.raise_on = raise_on or {}

    def table(self, name):
        return _Query(
            self.selects,
            name,
            self.tables.get(name, []),
            KNOWN_COLUMNS.get(name, frozenset()),
            raise_on_execute=self.raise_on.get(name),
        )


# --- a realistic, fully-canonical publication ------------------------------


def _canonical_client(**overrides):
    canonical = canonical_publication_identity()
    supported = supported_cohort_fingerprint()
    keys = list(supported["keys"])
    run_id_for = lambda key: f"run-{key}"

    snapshot = {
        "id": "snapshot-1",
        "market_date": "2026-08-04",
        "built_at": "2026-08-04T08:00:00Z",
        "published_at": "2026-08-04T08:01:00Z",
        "publication_status": "complete",
        "eligible_cohort_count": supported["count"],
        "cohort_version": supported["fingerprint"],
        "cohort_fingerprint": supported["fingerprint"],
        "overall_rip_version": canonical["overallRipVersion"],
        "financial_rip_version": canonical["financialRipVersion"],
        "ca7_version": canonical["collectorAppealVersion"],
        "diagnostics_json": {
            "public_rip_contract_version": canonical["publicRipContractVersion"],
            "supported_cohort_fingerprint": supported["fingerprint"],
        },
    }
    snapshot.update(overrides.get("snapshot", {}))

    rows = [
        {
            "set_id": f"set-{index}",
            "set_canonical_key": key,
            "overall_rip_score": 100.0 - index,
            "overall_rip_rank": index,
            "financial_rip_score": 90.0 - index,
            "financial_rip_rank": index,
            "overall_ranked_cohort_count": len(keys),
            "simulation_calculation_run_id": run_id_for(key),
        }
        for index, key in enumerate(keys, start=1)
    ]
    latest = [
        {
            "set_id": f"set-{index}",
            "canonical_key": key,
            "calculation_run_id": run_id_for(key),
            "financial_rip_v3_score_version": canonical["financialRipVersion"],
        }
        for index, key in enumerate(keys, start=1)
    ]
    latest = overrides.get("latest", latest)

    return _FakeClient(
        {
            "pokemon_public_rip_leaderboard_snapshots": [snapshot],
            "pokemon_public_rip_leaderboard_rows": rows,
            "explore_rip_statistics_latest": latest,
        },
        raise_on=overrides.get("raise_on"),
    )


def test_audit_never_requests_set_canonical_key_from_the_rip_statistics_view():
    """THE regression. `set_canonical_key` does not exist on this view."""
    client = _canonical_client()
    audit.run_audit(client)

    selects = client.selects["explore_rip_statistics_latest"]
    assert selects, "the audit must read explore_rip_statistics_latest"
    for select in selects:
        columns = {column.strip() for column in select.split(",")}
        assert "set_canonical_key" not in columns
        assert columns <= EXPLORE_RIP_STATISTICS_LATEST_COLUMNS


def test_audit_completes_against_the_production_view_shape():
    """With the real view shape the audit runs to completion and passes."""
    report = audit.run_audit(_canonical_client())

    assert report.error is None
    assert report.passed is True, [a.line() for a in report.failures]
    assert report.ranked_row_count == report.expected_cohort_count


def test_latest_run_and_financial_rip_v3_assertions_still_evaluate():
    """The two assertions that consume this view still detect real defects."""
    canonical = canonical_publication_identity()
    supported = supported_cohort_fingerprint()
    keys = list(supported["keys"])
    stale_latest = [
        {
            "set_id": f"set-{index}",
            "canonical_key": key,
            # A newer run exists that the leaderboard was NOT built from.
            "calculation_run_id": f"run-{key}-rerun",
            "financial_rip_v3_score_version": "financial_rip_v2_60_25_15",
        }
        for index, key in enumerate(keys, start=1)
    ]
    report = audit.run_audit(_canonical_client(latest=stale_latest))

    failed = {assertion.name for assertion in report.failures}
    assert "every_row_from_latest_eligible_run" in failed
    assert "every_source_run_computed_financial_rip_v3" in failed
    assert report.passed is False


def test_a_query_error_fails_closed_and_never_reports_success():
    client = _canonical_client(
        raise_on={"explore_rip_statistics_latest": RuntimeError("PGRST204 column missing")}
    )
    report = audit.run_audit(client)

    assert report.error is not None
    assert "leaderboard row read failed" in report.error
    assert report.passed is False


def test_an_unreadable_snapshot_authority_fails_closed():
    client = _canonical_client(
        raise_on={"pokemon_public_rip_leaderboard_snapshots": RuntimeError("timeout")}
    )
    report = audit.run_audit(client)

    assert report.error is not None
    assert report.passed is False
    # No assertion may have been recorded from an unreadable authority.
    assert report.assertions == []
