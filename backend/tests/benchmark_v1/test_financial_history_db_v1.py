from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from backend.scripts import run_rip_benchmark_publisher_v1 as publisher


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "supabase" / "migrations" / "20260927234500_financial_rip_history_db_v1.sql"
FINANCIAL = "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = []
        self.membership = []
        self.mode = "select"
        self.payload = None

    def insert(self, payload):
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def select(self, *_args):
        self.mode = "select"
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def in_(self, column, values):
        self.membership.append((column, set(values)))
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.mode == "insert":
            rows.append(dict(self.payload))
            return Result([dict(self.payload)])
        matched = [
            row for row in rows
            if all(row.get(column) == value for column, value in self.filters)
            and all(row.get(column) in values for column, values in self.membership)
        ]
        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
            return Result([dict(row) for row in matched])
        return Result([dict(row) for row in matched])


class Client:
    def __init__(self, tables=None):
        self.tables = {name: [dict(row) for row in rows] for name, rows in (tables or {}).items()}

    def table(self, name):
        return Query(self, name)


def financial_rows(reference="30.22370909090909090909090909", day="2026-09-27"):
    rows = []
    for rank in range(1, 23):
        rows.append({
            "entity_type": "set",
            "metric_key": "financial",
            "raw_model_value": str(50 - rank),
            "benchmark_raw_value": reference,
            "source_model_version": FINANCIAL,
            "source_market_date": day,
            "rank": rank,
            "cohort_size": 22,
            "publication_id": "pub-1",
        })
    for rank in range(1, 3):
        rows.append({
            "entity_type": "era",
            "metric_key": "financial",
            "raw_model_value": str(35 - rank),
            "benchmark_raw_value": reference,
            "source_model_version": FINANCIAL,
            "source_market_date": day,
            "rank": rank,
            "cohort_size": 2,
            "publication_id": "pub-1",
        })
    return rows


def candidate(reference="30.22370909090909090909090909", day="2026-09-27"):
    return {
        "market_date": day,
        "references": {"financial": reference},
        "publish_rpc_request": {"arguments": {"p_header": {"financial_model_version": FINANCIAL}}},
    }


def test_attempt_receipt_is_durable_and_stateful():
    client = Client()
    attempt_id = publisher._start_attempt(client, "2026-09-27")
    UUID(attempt_id)
    row = client.tables[publisher._ATTEMPT_TABLE][0]
    assert row["status"] == "evaluating"
    assert row["reason_code"] == "ASSEMBLING"
    publisher._update_attempt(
        client,
        attempt_id,
        status="failed",
        reason_code="ASSEMBLY_FAILED",
        completed_at="2026-09-27T23:59:00+00:00",
    )
    assert row["status"] == "failed"
    assert row["reason_code"] == "ASSEMBLY_FAILED"


def test_assembly_failure_is_recorded_without_a_publication(monkeypatch):
    client = Client()
    monkeypatch.setattr(
        "backend.db.clients.supabase_client.create_short_timeout_service_client",
        lambda: client,
    )
    monkeypatch.setattr(
        publisher,
        "assemble_dry_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("incomplete cohort")),
    )
    with pytest.raises(RuntimeError, match="incomplete cohort"):
        publisher.main(["--publish", "--market-date", "2026-09-27"])
    row = client.tables[publisher._ATTEMPT_TABLE][0]
    assert row["status"] == "failed"
    assert row["reason_code"] == "ASSEMBLY_FAILED"
    assert row["resulting_publication_id"] if "resulting_publication_id" in row else True
    assert "incomplete cohort" in row["reason_detail"]


def test_post_publish_parity_accepts_exact_22_set_2_era_authority():
    client = Client({"pokemon_rip_benchmark_rows_v1": financial_rows()})
    result = publisher._post_publish_parity(client, candidate(), "pub-1")
    assert result == {
        "financial_row_count": 24,
        "set_financial_row_count": 22,
        "era_financial_row_count": 2,
        "overall_financial_rip_reference": "30.22370909090909090909090909",
    }


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda rows: rows.__setitem__(0, {**rows[0], "benchmark_raw_value": "99"}), "parity failed"),
        (lambda rows: rows.__setitem__(0, {**rows[0], "source_market_date": "2026-09-26"}), "lineage parity failed"),
        (lambda rows: rows.pop(), "parity failed"),
    ],
)
def test_post_publish_parity_fails_closed(mutation, match):
    rows = financial_rows()
    mutation(rows)
    client = Client({"pokemon_rip_benchmark_rows_v1": rows})
    with pytest.raises(RuntimeError, match=match):
        publisher._post_publish_parity(client, candidate(), "pub-1")


def test_database_contract_contains_atomic_cutover_and_bounded_history_guards():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "before update of publication_status" in sql
    assert "old.publication_status = 'staged' and new.publication_status = 'published'" in sql
    assert "RIP Benchmark Rankings authority changed or is not coherent with the candidate" in sql
    assert "v_set_reference is distinct from v_set_mean" in sql
    assert "equal_weight_mean_of_canonical_member_set_raw_scores" in sql
    assert "era_rip_aggregation_v1_equal_set_mean" in sql
    assert "create index if not exists rip_benchmark_financial_history_v1" in sql
    assert "where metric_key = 'financial' and entity_type in ('set','era')" in sql
    assert "p_limit integer default 10000" in sql
    assert "limit p_limit + 1" in sql
    assert "security invoker" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5" in sql
    assert "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5" in sql
