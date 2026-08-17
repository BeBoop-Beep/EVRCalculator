"""Transient-failure retry contract for the simulation persistence path.

The failure these tests describe is a real one: an unattended
`prismaticEvolutions` run died 1.8 seconds in when a Cloudflare HTML
`502 Bad Gateway` surfaced as `APIError(code=502)` from a
`simulation_input_cards` insert. Nothing about the payload was wrong.

Two properties matter and both are asserted here:

  1. a transient HTTP/transport failure is retried, bounded, with backoff; and
  2. a retry can never duplicate a row or manufacture a completed run.

Every test drives a fake PostgREST client, so no network is involved, and the
backoff sleep is replaced with a recorder - the suite must stay fast.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from backend.db.repositories import calculation_runs_repository as repo
from backend.db.services import supabase_persistence_retry as retry_module
from backend.db.services.data_service_health import classify_data_service_error


class FakeAPIError(Exception):
    """Shaped like supabase-py's APIError: the status arrives inside `code`."""

    def __init__(self, message: str, code: Any):
        super().__init__(message)
        self.message = message
        self.code = str(code)


def cloudflare_502() -> FakeAPIError:
    return FakeAPIError("JSON could not be generated", 502)


class FakeQuery:
    def __init__(self, table: "FakeTable"):
        self._table = table
        self._filters: List[tuple] = []

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append((column, value))
        return self

    def is_(self, column: str, _null: str) -> "FakeQuery":
        self._filters.append((column, None))
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def execute(self) -> Any:
        self._table.raise_if_scripted("select")
        matches = [
            row
            for row in self._table.rows
            if all(row.get(column) == value for column, value in self._filters)
        ]
        return FakeResponse(matches[:1])


class FakeResponse:
    def __init__(self, data: Any):
        self.data = data


class FakeInsert:
    def __init__(self, table: "FakeTable", payload: Dict[str, Any]):
        self._table = table
        self._payload = payload

    def execute(self) -> FakeResponse:
        self._table.raise_if_scripted("insert")
        # The commit happens BEFORE the response is returned, which is exactly
        # the window the idempotency guard exists for.
        stored = dict(self._payload)
        stored.setdefault("id", f"row-{len(self._table.rows) + 1}")
        self._table.rows.append(stored)
        return FakeResponse([stored])


class FakeTable:
    def __init__(self, client: "FakeSupabase", name: str):
        self._client = client
        self.name = name
        self.rows = client.rows_by_table.setdefault(name, [])

    def insert(self, payload: Dict[str, Any]) -> FakeInsert:
        self._client.insert_calls.append((self.name, dict(payload)))
        return FakeInsert(self, payload)

    def select(self, _columns: str) -> FakeQuery:
        self._client.select_calls.append(self.name)
        return FakeQuery(self)

    def raise_if_scripted(self, verb: str) -> None:
        self._client.record(self.name, verb)
        error = self._client.next_error(self.name, verb)
        if error is not None:
            raise error


class FakeSupabase:
    """A PostgREST stand-in whose failures are scripted per (table, verb).

    ``commit_before_failing`` reproduces the dangerous case: Postgres accepted
    the row and the response was lost on the way back.
    """

    def __init__(
        self,
        *,
        insert_errors: Optional[List[Optional[Exception]]] = None,
        select_errors: Optional[List[Optional[Exception]]] = None,
        commit_before_failing: bool = False,
    ):
        self.rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
        self.insert_errors = list(insert_errors or [])
        self.select_errors = list(select_errors or [])
        self.commit_before_failing = commit_before_failing
        self.insert_calls: List[tuple] = []
        self.select_calls: List[str] = []
        self.verbs: List[str] = []

    def table(self, name: str) -> FakeTable:
        return FakeTable(self, name)

    def record(self, table_name: str, verb: str) -> None:
        self.verbs.append(f"{table_name}.{verb}")

    def next_error(self, table_name: str, verb: str) -> Optional[Exception]:
        queue = self.insert_errors if verb == "insert" else self.select_errors
        if not queue:
            return None
        error = queue.pop(0)
        if error is not None and verb == "insert" and self.commit_before_failing:
            payload = dict(self.insert_calls[-1][1])
            payload.setdefault("id", f"row-{len(self.rows_by_table[table_name]) + 1}")
            self.rows_by_table[table_name].append(payload)
        return error


INPUT_CARD_IDENTITY = [
    "calculation_run_id",
    "card_id",
    "card_variant_id",
    "condition_id",
]

INPUT_CARD_PAYLOAD = {
    "calculation_run_id": "run-1",
    "card_id": "10ac8163-a5e7-46de-9753-58b93cd4cafe",
    "card_variant_id": "variant-1",
    "condition_id": "condition-1",
    "price_used": 1.25,
}


@pytest.fixture
def no_sleep(monkeypatch):
    """Backoff sleeps become a recorded list; the suite never actually waits."""
    slept: List[float] = []

    class _Clock:
        @staticmethod
        def sleep(seconds: float) -> None:
            slept.append(seconds)

    monkeypatch.setattr(retry_module, "time", _Clock)
    monkeypatch.setattr(retry_module, "random", type("R", (), {"uniform": staticmethod(lambda a, b: 0.0)}))
    return slept


def _insert_input_card(client, monkeypatch):
    monkeypatch.setattr(repo, "supabase", client)
    return repo._insert_required_payload(
        "simulation_input_cards",
        dict(INPUT_CARD_PAYLOAD),
        "Simulation input-card insert",
        identity_columns=INPUT_CARD_IDENTITY,
        operation_name="simulation_input_cards_insert",
    )


# ---------------------------------------------------------------------------
# Transient failures are retried
# ---------------------------------------------------------------------------


def test_a_single_502_is_retried_and_the_second_attempt_succeeds(no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[cloudflare_502()])

    row = _insert_input_card(client, monkeypatch)

    assert row["card_id"] == INPUT_CARD_PAYLOAD["card_id"]
    assert len(client.rows_by_table["simulation_input_cards"]) == 1
    assert no_sleep == [1.0]


def test_two_502s_are_retried_and_the_third_attempt_succeeds(no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[cloudflare_502(), cloudflare_502()])

    row = _insert_input_card(client, monkeypatch)

    assert row["card_id"] == INPUT_CARD_PAYLOAD["card_id"]
    assert len(client.rows_by_table["simulation_input_cards"]) == 1
    assert no_sleep == [1.0, 2.0]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_every_declared_transient_status_is_retried(status, no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[FakeAPIError("upstream said no", status)])

    row = _insert_input_card(client, monkeypatch)

    assert row["card_id"] == INPUT_CARD_PAYLOAD["card_id"]
    assert no_sleep == [1.0]


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionResetError("connection reset by peer"),
        TimeoutError("read timeout"),
        OSError("resource temporarily unavailable"),
    ],
)
def test_transport_failures_are_retried(exc, no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[exc])

    row = _insert_input_card(client, monkeypatch)

    assert row["card_id"] == INPUT_CARD_PAYLOAD["card_id"]


def test_exhausted_retries_fail_the_operation_with_the_original_cause(no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[cloudflare_502() for _ in range(5)])

    with pytest.raises(RuntimeError) as excinfo:
        _insert_input_card(client, monkeypatch)

    assert "simulation_input_cards" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, FakeAPIError)
    assert excinfo.value.__cause__.code == "502"
    # Five attempts means four sleeps: nothing sleeps after the final attempt.
    assert no_sleep == [1.0, 2.0, 4.0, 8.0]
    assert client.verbs.count("simulation_input_cards.insert") == 5


# ---------------------------------------------------------------------------
# Deterministic failures are NOT retried
# ---------------------------------------------------------------------------


def test_a_postgres_constraint_violation_is_not_retried(no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[FakeAPIError("duplicate key value", "23505")])

    with pytest.raises(RuntimeError):
        _insert_input_card(client, monkeypatch)

    assert client.verbs.count("simulation_input_cards.insert") == 1
    assert no_sleep == []


@pytest.mark.parametrize(
    "code,message",
    [
        ("22P02", "invalid input syntax for type uuid"),
        ("23503", "violates foreign key constraint"),
        ("42703", "column does not exist"),
        ("42501", "permission denied for table"),
        ("PGRST204", "could not find the column in the schema cache"),
    ],
)
def test_deterministic_database_errors_are_not_retried(code, message, no_sleep, monkeypatch):
    client = FakeSupabase(insert_errors=[FakeAPIError(message, code)])

    with pytest.raises(RuntimeError):
        _insert_input_card(client, monkeypatch)

    assert client.verbs.count("simulation_input_cards.insert") == 1
    assert no_sleep == []


def test_a_deterministic_sqlstate_wins_over_a_transient_http_status():
    """A 500 carrying a real SQLSTATE is a database rejection, not a blip."""

    class BothSignals(Exception):
        def __init__(self):
            super().__init__("violates check constraint")
            self.code = "23514"
            self.status_code = 500

    assert classify_data_service_error(BothSignals()).transient is False


def test_a_business_validation_error_never_reaches_the_database(no_sleep, monkeypatch):
    client = FakeSupabase()
    monkeypatch.setattr(repo, "supabase", client)

    with pytest.raises(ValueError):
        repo.map_simulation_input_cards_rows("run-1", [{"card_id": None}])

    assert client.insert_calls == []
    assert no_sleep == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_a_retry_after_a_committed_write_cannot_duplicate_an_input_card(no_sleep, monkeypatch):
    """The dangerous case: Postgres committed, then the response was lost."""
    client = FakeSupabase(insert_errors=[cloudflare_502()], commit_before_failing=True)

    row = _insert_input_card(client, monkeypatch)

    stored = client.rows_by_table["simulation_input_cards"]
    assert len(stored) == 1, "the retry duplicated a simulation_input_cards row"
    assert row["card_id"] == INPUT_CARD_PAYLOAD["card_id"]
    # Attempt 2 read the row back instead of inserting it again.
    assert client.verbs.count("simulation_input_cards.insert") == 1
    assert client.verbs.count("simulation_input_cards.select") == 1


def test_a_table_without_an_identity_is_never_retried(no_sleep, monkeypatch):
    """No identity means no way to tell a lost response from a lost write."""
    client = FakeSupabase(insert_errors=[cloudflare_502()])
    monkeypatch.setattr(repo, "supabase", client)

    with pytest.raises(RuntimeError):
        repo._insert_required_payload("some_table", {"a": 1}, "Unidentified insert")

    assert client.verbs.count("some_table.insert") == 1


def test_the_parent_run_carries_a_client_chosen_id_so_a_retry_cannot_fork_the_run(
    no_sleep, monkeypatch
):
    client = FakeSupabase(insert_errors=[cloudflare_502()], commit_before_failing=True)
    monkeypatch.setattr(repo, "supabase", client)

    run = repo.create_parent_calculation_run(
        "config-1", "set", "set-1", "combined", "notes", "monte_carlo_v2"
    )

    stored = client.rows_by_table["calculation_runs"]
    assert len(stored) == 1, "the retry created a second parent calculation_runs row"
    assert run["id"] == stored[0]["id"]


# ---------------------------------------------------------------------------
# The exact pack-outcome artifact
# ---------------------------------------------------------------------------


def test_a_retried_artifact_write_cannot_create_a_second_artifact(no_sleep):
    from backend.db.services import pack_outcome_artifact_service as artifact_service

    client = FakeSupabase(insert_errors=[cloudflare_502()], commit_before_failing=True)
    values = [1.0, 2.0, 3.0]

    result = retry_module.run_with_transient_retry(
        lambda _attempt: artifact_service.persist_pack_outcomes(client, "run-1", values),
        operation_name="simulation_pack_outcome_artifacts_persist",
    )

    rows = client.rows_by_table[artifact_service.TABLE]
    assert len(rows) == 1
    # The second attempt recognised its own committed row by checksum.
    assert result["status"] == "matched"
    assert result["outcome_count"] == 3


def test_artifact_retry_exhaustion_fails_the_run_rather_than_returning_a_result(no_sleep):
    from backend.db.services import pack_outcome_artifact_service as artifact_service

    client = FakeSupabase(insert_errors=[cloudflare_502() for _ in range(5)])

    with pytest.raises(FakeAPIError):
        retry_module.run_with_transient_retry(
            lambda _attempt: artifact_service.persist_pack_outcomes(client, "run-1", [1.0, 2.0]),
            operation_name="simulation_pack_outcome_artifacts_persist",
        )

    assert client.rows_by_table[artifact_service.TABLE] == []


def test_a_corrupt_artifact_conflict_is_never_retried(no_sleep):
    """A mismatched existing artifact is a data fault, not an outage."""
    from backend.db.services import pack_outcome_artifact_service as artifact_service

    client = FakeSupabase()
    client.rows_by_table[artifact_service.TABLE] = [
        {
            "calculation_run_id": "run-1",
            "raw_sha256": "0" * 64,
            "outcome_count": 99,
        }
    ]

    with pytest.raises(artifact_service.PackOutcomeArtifactCorrupt):
        retry_module.run_with_transient_retry(
            lambda _attempt: artifact_service.persist_pack_outcomes(client, "run-1", [1.0, 2.0]),
            operation_name="simulation_pack_outcome_artifacts_persist",
        )

    assert no_sleep == []


# ---------------------------------------------------------------------------
# Retry exhaustion cannot produce a completed / publishable run
# ---------------------------------------------------------------------------


def test_exhausted_input_card_retries_abort_before_any_output_is_persisted(no_sleep, monkeypatch):
    """The run must not reach summary, derived metrics or the artifact."""
    from backend.db.services import calculation_run_persistence_service as persistence

    client = FakeSupabase(insert_errors=[cloudflare_502() for _ in range(5)])
    monkeypatch.setattr(repo, "supabase", client)
    input_rows = [
        {
            "card_id": INPUT_CARD_PAYLOAD["card_id"],
            "card_variant_id": "variant-1",
            "condition_id": "condition-1",
            "card_name": "Test Card",
            "rarity_bucket": "hit",
            "price_source": "market",
            "price_used": 1.25,
            "captured_at": "2026-08-17",
            "effective_pull_rate": 0.01,
            "ev_contribution": 0.0125,
        }
    ]
    monkeypatch.setattr(
        persistence,
        "_resolve_simulation_input_snapshot",
        lambda calculation_input, config: input_rows,
    )

    with pytest.raises(RuntimeError):
        persistence.persist_simulation_inputs(
            run_id="run-1", calculation_input=input_rows, config=None
        )

    assert "simulation_run_summary" not in client.rows_by_table
    assert "simulation_derived_metrics" not in client.rows_by_table
    assert "simulation_pack_outcome_artifacts" not in client.rows_by_table


def test_backoff_is_bounded_and_capped():
    delays = [retry_module.compute_backoff_delay_seconds(attempt) for attempt in range(1, 7)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]
