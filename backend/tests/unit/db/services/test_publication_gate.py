"""Publication-gate contract tests.

The gate is FAIL-CLOSED in required mode (the production default): only a valid
batch row satisfying the complete promotion contract permits publication. Every
failure class — timeout, auth failure, missing table, missing row, malformed
response, contradictory row, or an incomplete batch — must block.
"""

import pytest

from backend.db.services import publication_gate
from backend.db.services.publication_gate import (
    GATE_DEFERRED_EXIT_CODE,
    MODE_DISABLED,
    MODE_REQUIRED,
    REASON_ALLOWED_COMPLETE,
    REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
    REASON_BLOCKED_INCOMPLETE,
    REASON_BLOCKED_INVALID_BATCH_CONTRACT,
    REASON_BLOCKED_NO_BATCH,
    REASON_DISABLED_EXPLICITLY,
    REASON_MANUAL_OVERRIDE,
    enforce_cli_publication_gate,
    evaluate_publication_gate,
    resolve_gate_mode,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, *, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
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
    def __init__(self, rows, *, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc

    def table(self, _name):
        return _Query(self._rows, raise_exc=self._raise)


def _complete_batch(**overrides):
    row = {
        "id": 5,
        "market_date": "2026-07-25",
        "status": "complete",
        "promoted_at": "2026-07-25T09:00:00Z",
        "missing_set_count": 0,
        "expected_set_count": 166,
    }
    row.update(overrides)
    return row


def _required(client, **kwargs):
    # Force required mode so ambient PUBLICATION_GATE_MODE never leaks in.
    return evaluate_publication_gate(client, mode=MODE_REQUIRED, **kwargs)


# --------------------------------------------------------------------------- #
# 1. A valid complete batch allows publication.
# --------------------------------------------------------------------------- #
def test_1_complete_batch_allows_promotion():
    decision = _required(_Client([_complete_batch()]))
    assert decision.allowed is True
    assert decision.gated is True
    assert decision.reason_code == REASON_ALLOWED_COMPLETE
    assert decision.batch_status == "complete"
    assert decision.market_date == "2026-07-25"
    assert decision.expected_set_count == 166


# 2. status=complete with promoted_at=None blocks.
def test_2_complete_without_promoted_at_blocks():
    decision = _required(_Client([_complete_batch(promoted_at=None)]))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT
    assert "promoted_at" in decision.reason


# 3. status=complete with missing_set_count > 0 blocks.
def test_3_complete_with_missing_sets_blocks():
    decision = _required(_Client([_complete_batch(missing_set_count=4)]))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT
    assert "missing_set_count" in decision.reason


# 4. status=complete with expected_set_count == 0 blocks.
def test_4_complete_with_zero_expected_blocks():
    decision = _required(_Client([_complete_batch(expected_set_count=0)]))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT
    assert "expected_set_count" in decision.reason


# 5-8. Pending / running / incomplete / failed all block as incomplete.
@pytest.mark.parametrize("status", ["pending", "running", "incomplete", "failed"])
def test_5to8_non_complete_status_blocks(status):
    decision = _required(
        _Client([{"id": 6, "market_date": "2026-07-25", "status": status,
                  "promoted_at": None, "missing_set_count": 3, "expected_set_count": 166}])
    )
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INCOMPLETE
    assert decision.batch_status == status


# 9. Missing batch row blocks in required mode.
def test_9_missing_batch_row_blocks_in_required_mode():
    decision = _required(_Client([]))
    assert decision.allowed is False
    assert decision.gated is True
    assert decision.reason_code == REASON_BLOCKED_NO_BATCH


# 10. Missing batch table blocks in required mode.
def test_10_missing_batch_table_blocks_in_required_mode():
    exc = RuntimeError('relation "pokemon_scrape_batches" does not exist')
    decision = _required(_Client(None, raise_exc=exc))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE


# 11. Database timeout blocks in required mode.
def test_11_database_timeout_blocks_in_required_mode():
    exc = TimeoutError("canceling statement due to statement timeout (57014)")
    decision = _required(_Client(None, raise_exc=exc))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE


# 12. Authentication / permission failure blocks in required mode.
def test_12_auth_permission_failure_blocks_in_required_mode():
    exc = PermissionError("permission denied for table pokemon_scrape_batches (42501)")
    decision = _required(_Client(None, raise_exc=exc))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE


# 13. Explicit disabled mode allows ungated local/test execution.
def test_13_disabled_mode_allows_ungated():
    # Even an exception-raising client is never touched in disabled mode.
    client = _Client(None, raise_exc=RuntimeError("should never be queried"))
    decision = evaluate_publication_gate(client, mode=MODE_DISABLED)
    assert decision.allowed is True
    assert decision.gated is False
    assert decision.reason_code == REASON_DISABLED_EXPLICITLY
    assert decision.mode == MODE_DISABLED


# 14. Manual override allows publication and records the override.
def test_14_manual_override_allows_and_records():
    # Override never queries the batch — even an incomplete batch is bypassed.
    client = _Client([_complete_batch(status="incomplete", promoted_at=None, missing_set_count=9)])
    decision = evaluate_publication_gate(client, mode=MODE_REQUIRED, override=True)
    assert decision.allowed is True
    assert decision.override is True
    assert decision.gated is False
    assert decision.reason_code == REASON_MANUAL_OVERRIDE


# 15. Invalid gate mode cannot silently disable safety.
def test_15_invalid_mode_defaults_to_required_and_blocks(monkeypatch):
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    # An invalid explicit mode resolves to required (fail-closed): no batch blocks.
    decision = evaluate_publication_gate(_Client([]), mode="bananas")
    assert decision.allowed is False
    assert decision.mode == MODE_REQUIRED
    assert decision.reason_code == REASON_BLOCKED_NO_BATCH


def test_15b_missing_env_mode_resolves_required(monkeypatch):
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    assert resolve_gate_mode() == MODE_REQUIRED
    # And a failed query in that default-required mode blocks (never disables).
    decision = evaluate_publication_gate(_Client(None, raise_exc=RuntimeError("boom")))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE


# 16. Requested market date must match the returned batch row.
def test_16_requested_market_date_must_match():
    # A returned row for a different date is a contract violation, not an allow.
    client = _Client([_complete_batch(market_date="2026-07-24")])
    decision = _required(client, market_date="2026-07-25")
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT
    assert "does not match" in decision.reason


def test_16b_requested_market_date_match_allows():
    client = _Client([_complete_batch(market_date="2026-07-25")])
    decision = _required(client, market_date="2026-07-25")
    assert decision.allowed is True
    assert decision.reason_code == REASON_ALLOWED_COMPLETE


# --------------------------------------------------------------------------- #
# Extra structural-contract coverage (distinct classification, not one generic).
# --------------------------------------------------------------------------- #
def test_complete_with_non_numeric_counts_blocks_invalid_contract():
    decision = _required(_Client([_complete_batch(missing_set_count="oops")]))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT


def test_batch_without_id_blocks_invalid_contract():
    decision = _required(_Client([_complete_batch(id=None)]))
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT


def test_unknown_status_blocks_invalid_contract():
    decision = _required(
        _Client([{"id": 1, "market_date": "2026-07-25", "status": "banana",
                  "promoted_at": None, "missing_set_count": 0, "expected_set_count": 5}])
    )
    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_INVALID_BATCH_CONTRACT


# --------------------------------------------------------------------------- #
# Shared CLI enforcement helper.
# --------------------------------------------------------------------------- #
def test_enforce_open_gate_commit_proceeds():
    enforcement = enforce_cli_publication_gate(
        _Client([_complete_batch()]), commit=True, mode=MODE_REQUIRED, entry_point="unit"
    )
    assert enforcement.proceed is True
    assert enforcement.exit_code == 0
    assert enforcement.decision.reason_code == REASON_ALLOWED_COMPLETE


def test_enforce_closed_gate_commit_defers_with_exit_3(capsys):
    enforcement = enforce_cli_publication_gate(
        _Client([]), commit=True, mode=MODE_REQUIRED, entry_point="unit"
    )
    assert enforcement.proceed is False
    assert enforcement.exit_code == GATE_DEFERRED_EXIT_CODE
    out = capsys.readouterr().out
    assert "publication gate CLOSED" in out
    assert "PUBLICATION_DEFERRED" in out


def test_enforce_dry_run_always_proceeds_and_reports(capsys):
    # A closed gate in dry-run still proceeds (read-only) but reports the decision.
    enforcement = enforce_cli_publication_gate(
        _Client([]), commit=False, mode=MODE_REQUIRED, entry_point="unit"
    )
    assert enforcement.proceed is True
    assert enforcement.exit_code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert REASON_BLOCKED_NO_BATCH in out


def test_enforce_override_commit_announces_and_proceeds(capsys):
    enforcement = enforce_cli_publication_gate(
        _Client([]), commit=True, override=True, mode=MODE_REQUIRED, entry_point="unit"
    )
    assert enforcement.proceed is True
    assert enforcement.exit_code == 0
    assert "OVERRIDDEN" in capsys.readouterr().out


def test_deferral_report_includes_machine_line():
    decision = _required(
        _Client([{"id": 6, "market_date": "2026-07-25", "status": "incomplete",
                  "promoted_at": None, "missing_set_count": 4, "expected_set_count": 166}])
    )
    lines = publication_gate.gate_decision_report(decision, entry_point="stale refresh")
    joined = "\n".join(lines)
    assert "publication gate CLOSED" in joined
    assert "PUBLICATION_DEFERRED" in joined
    assert "missing_set_count=4" in joined
    assert "batch_status=incomplete" in joined
