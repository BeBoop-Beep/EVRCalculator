from backend.db.services.publication_gate import (
    MODE_REQUIRED,
    REASON_ALLOWED_COMPLETE,
    REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
    evaluate_publication_gate,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _Transient522(RuntimeError):
    code = "522"
    status_code = 522


class _DeterministicSqlstate(RuntimeError):
    code = "42501"
    status_code = 500


class _SequencedClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Result(outcome)


def _complete_batch():
    return [{
        "id": 60,
        "market_date": "2026-09-22",
        "status": "complete",
        "promoted_at": "2026-09-22T16:27:05Z",
        "missing_set_count": 0,
        "expected_set_count": 167,
        "succeeded_set_count": 166,
        "failed_set_count": 1,
    }]


def test_transient_522_authority_read_recovers_before_failing_closed():
    sleeps = []
    client = _SequencedClient([
        _Transient522("origin timed out"),
        _Transient522("origin timed out again"),
        _complete_batch(),
    ])

    decision = evaluate_publication_gate(
        client,
        market_date="2026-09-22",
        mode=MODE_REQUIRED,
        authority_sleep=sleeps.append,
    )

    assert decision.allowed is True
    assert decision.reason_code == REASON_ALLOWED_COMPLETE
    assert client.calls == 3
    assert sleeps == [1.0, 2.0]


def test_deterministic_sqlstate_is_not_retried():
    sleeps = []
    client = _SequencedClient([
        _DeterministicSqlstate("permission denied"),
    ])

    decision = evaluate_publication_gate(
        client,
        market_date="2026-09-22",
        mode=MODE_REQUIRED,
        authority_sleep=sleeps.append,
    )

    assert decision.allowed is False
    assert decision.reason_code == REASON_BLOCKED_AUTHORITY_UNAVAILABLE
    assert client.calls == 1
    assert sleeps == []
