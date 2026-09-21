from types import SimpleNamespace
from unittest.mock import patch

from backend.scripts import publish_post_scrape_if_needed as publish


def _decision(*, allowed, reason_code):
    return SimpleNamespace(allowed=allowed, reason_code=reason_code)


def test_batch_gate_retries_authority_unavailable_with_fresh_client():
    from backend.db.services.publication_gate import (
        REASON_ALLOWED_COMPLETE,
        REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
    )
    clients = [object(), object(), object()]
    seen = []
    decisions = [
        _decision(allowed=False, reason_code=REASON_BLOCKED_AUTHORITY_UNAVAILABLE),
        _decision(allowed=False, reason_code=REASON_BLOCKED_AUTHORITY_UNAVAILABLE),
        _decision(allowed=True, reason_code=REASON_ALLOWED_COMPLETE),
    ]

    def evaluator(client, *, market_date):
        seen.append((client, market_date))
        return decisions[len(seen) - 1]

    factory_calls = {"n": 0}
    def factory():
        factory_calls["n"] += 1
        return clients[factory_calls["n"]]

    sleeps = []
    result = publish._batch_gate_decision(
        clients[0],
        "2026-09-20",
        evaluator=evaluator,
        client_factory=factory,
        sleep_fn=sleeps.append,
        max_attempts=3,
    )

    assert result.allowed is True
    assert [item[0] for item in seen] == clients
    assert sleeps == [5.0, 10.0]


def test_publish_if_needed_returns_nonzero_status_when_gate_authority_stays_unknown():
    from backend.db.services.publication_gate import REASON_BLOCKED_AUTHORITY_UNAVAILABLE
    gate = _decision(allowed=False, reason_code=REASON_BLOCKED_AUTHORITY_UNAVAILABLE)
    with patch.object(publish, "_batch_gate_decision", return_value=gate), patch.object(
        publish, "_already_current", side_effect=AssertionError("currency check must not run")
    ):
        result = publish.publish_if_needed("2026-09-20", client=object())
    assert result["status"] == publish.STATUS_GATE_AUTHORITY_UNAVAILABLE
    assert publish._status_to_exit_code(result["status"]) == 1


def test_publish_if_needed_keeps_genuine_incomplete_batch_as_noop():
    from backend.db.services.publication_gate import REASON_BLOCKED_INCOMPLETE
    gate = _decision(allowed=False, reason_code=REASON_BLOCKED_INCOMPLETE)
    with patch.object(publish, "_batch_gate_decision", return_value=gate), patch.object(
        publish, "_already_current", side_effect=AssertionError("currency check must not run")
    ):
        result = publish.publish_if_needed("2026-09-20", client=object())
    assert result["status"] == publish.STATUS_NOOP_NOT_COMPLETE
    assert publish._status_to_exit_code(result["status"]) == 0


def test_publish_if_needed_fails_closed_on_invalid_batch_contract():
    from backend.db.services.publication_gate import REASON_BLOCKED_INVALID_BATCH_CONTRACT
    gate = _decision(allowed=False, reason_code=REASON_BLOCKED_INVALID_BATCH_CONTRACT)
    with patch.object(publish, "_batch_gate_decision", return_value=gate):
        result = publish.publish_if_needed("2026-09-20", client=object())
    assert result["status"] == publish.STATUS_GATE_INVALID_CONTRACT
    assert publish._status_to_exit_code(result["status"]) == 1
