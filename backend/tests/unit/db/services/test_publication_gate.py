from backend.db.services.publication_gate import evaluate_publication_gate


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, *, raise_on_execute=False):
        self._rows = rows
        self._raise = raise_on_execute

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self._raise:
            raise RuntimeError("relation \"pokemon_scrape_batches\" does not exist")
        return _Result(self._rows)


class _Client:
    def __init__(self, rows, *, raise_on_execute=False):
        self._rows = rows
        self._raise = raise_on_execute

    def table(self, _name):
        return _Query(self._rows, raise_on_execute=self._raise)


def test_complete_batch_allows_promotion():
    client = _Client([
        {"id": 5, "market_date": "2026-07-25", "status": "complete", "promoted_at": "2026-07-25T09:00:00Z", "missing_set_count": 0}
    ])
    decision = evaluate_publication_gate(client)
    assert decision.allowed is True
    assert decision.gated is True
    assert decision.batch_status == "complete"
    assert decision.market_date == "2026-07-25"


def test_incomplete_batch_blocks_and_preserves_previous_good():
    client = _Client([
        {"id": 6, "market_date": "2026-07-25", "status": "incomplete", "promoted_at": None, "missing_set_count": 4}
    ])
    decision = evaluate_publication_gate(client)
    assert decision.allowed is False
    assert decision.gated is True
    assert decision.missing_set_count == 4
    assert "not complete" in decision.reason


def test_running_batch_blocks():
    client = _Client([
        {"id": 7, "market_date": "2026-07-25", "status": "running", "promoted_at": None, "missing_set_count": None}
    ])
    decision = evaluate_publication_gate(client)
    assert decision.allowed is False
    assert decision.batch_status == "running"


def test_no_batch_row_publishes_ungated():
    client = _Client([])
    decision = evaluate_publication_gate(client)
    assert decision.allowed is True
    assert decision.gated is False


def test_batch_authority_unavailable_publishes_ungated():
    client = _Client(None, raise_on_execute=True)
    decision = evaluate_publication_gate(client)
    assert decision.allowed is True
    assert decision.gated is False


def test_override_allows_without_touching_batch():
    # Even an incomplete batch is bypassed; override never queries the batch.
    client = _Client([
        {"id": 8, "market_date": "2026-07-25", "status": "incomplete", "promoted_at": None, "missing_set_count": 9}
    ])
    decision = evaluate_publication_gate(client, override=True)
    assert decision.allowed is True
    assert decision.override is True
    assert decision.gated is False
