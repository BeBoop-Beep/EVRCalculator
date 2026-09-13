from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_market_rollout_preparation as prep

DAY = "2026-09-13"


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_a): return self
    def lte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) <= value]; return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def in_(self, key, values): self.rows = [r for r in self.rows if r.get(key) in values]; return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self, *, response=None, materialized=False, incomplete_after_rpc=False):
        self.roots = [{"set_id": "root", "release_date": "2020-01-01",
                       "activated_market_date": "2026-09-10"}]
        self.history = []
        self.response = response or {
            "status": "complete", "marketDate": DAY, "candidateDate": DAY,
            "rolloutRootCount": 1, "standardRowsUpserted": 1, "top10RowsUpserted": 1,
        }
        self.rpc_calls = []
        self.incomplete_after_rpc = incomplete_after_rpc
        if materialized: self._materialize()

    def _materialize(self):
        self.history = [
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "standard",
             "source": "canonical_root_set_public_rollout_candidate_v1"},
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "top10",
             "source": "canonical_root_top10_public_rollout_candidate_v1"},
        ]

    def table(self, name):
        return Query(self.roots if name == prep.ROLLOUT_VIEW else self.history)

    def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        client = self
        class RPC:
            def execute(self):
                client._materialize()
                if client.incomplete_after_rpc:
                    client.history.pop()
                return SimpleNamespace(data=client.response)
        return RPC()


def test_commit_prepares_and_validates_complete_candidate_pairs():
    client = Client()
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    assert client.rpc_calls == [(prep.CANDIDATE_PREPARATION_RPC, {"p_market_date": DAY})]
    assert result["materialization"]["ready"] is True
    assert result["materialization"]["provenanceState"] == "candidate"


def test_dry_run_is_read_only_and_reports_preparation_required():
    client = Client()
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=False)
    assert client.rpc_calls == []
    assert result["candidatePreparationRequired"] is True
    assert result["rpcInvoked"] is False


@pytest.mark.parametrize("change,match", [
    ({"marketDate": "2026-09-12"}, "wrong marketDate"),
    ({"candidateDate": "2026-09-12"}, "wrong candidateDate"),
    ({"rolloutRootCount": 2}, "root count mismatch"),
    ({"standardRowsUpserted": 0}, "Standard row count mismatch"),
    ({"top10RowsUpserted": 0}, "Top10 row count mismatch"),
])
def test_bad_candidate_response_fails_closed(change, match):
    response = dict(Client().response); response.update(change)
    with pytest.raises(RuntimeError, match=match):
        prep.prepare_market_rollout_candidate(Client(response=response), DAY, commit=True)


def test_unprepared_historical_date_is_rejected_by_rpc_response():
    response = dict(Client().response, marketDate=DAY, candidateDate=DAY)
    with pytest.raises(RuntimeError, match="wrong marketDate"):
        prep.prepare_market_rollout_candidate(
            Client(response=response), "2026-09-12", commit=True,
        )


def test_success_response_with_incomplete_materialization_fails_closed():
    with pytest.raises(RuntimeError, match="incomplete public-rollout materialization"):
        prep.prepare_market_rollout_candidate(
            Client(incomplete_after_rpc=True), DAY, commit=True,
        )


def test_candidate_preparation_retry_is_idempotent():
    client = Client()
    first = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    second = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    assert first["materialization"]["ready"] is True
    assert second["materialization"]["ready"] is True
    assert len(client.history) == 2
    assert len(client.rpc_calls) == 2
