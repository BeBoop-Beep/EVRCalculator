from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_market_rollout_preparation as prep

DAY = "2026-09-13"
ERA_A = "era-a"


class Query:
    def __init__(self, rows, *, poison_name=None):
        self.rows = list(rows)
        self.poison_name = poison_name

    def _touch(self):
        if self.poison_name:
            raise AssertionError(
                f"expensive valuation-backed view {self.poison_name!r} must not be queried"
            )

    def select(self, *_a):
        self._touch()
        return self

    def lte(self, key, value):
        self.rows = [r for r in self.rows if str(r.get(key)) <= value]
        return self

    def eq(self, key, value):
        self.rows = [r for r in self.rows if r.get(key) == value]
        return self

    def in_(self, key, values):
        self.rows = [r for r in self.rows if r.get(key) in values]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class Client:
    """Fake client serving structural rollout authority tables only.

    ``roots`` (the expensive ``pokemon_market_public_rollout_root_sets_v1``
    view) is retained solely to prove the current-day path never touches it:
    any ``.select(...)`` call against it raises via ``Query``'s poison guard.
    """

    def __init__(self, *, response=None, authority_response=None, materialized=False,
                 incomplete_after_rpc=False, era_rows=None, set_rows=None):
        self.roots = [{"set_id": "root", "release_date": "2020-01-01",
                       "activated_market_date": "2026-09-10"}]
        self.era_rows = era_rows if era_rows is not None else [
            {"era_id": ERA_A, "activated_market_date": "2026-09-10", "enabled": True},
        ]
        self.set_rows = set_rows if set_rows is not None else [
            {"id": "root", "era_id": ERA_A, "release_date": "2020-01-01",
             "parent_opening_set_id": None, "catalog_only": False,
             "ready_for_daily_scrape": True},
        ]
        self.history = []
        self.response = response or {
            "status": "complete", "marketDate": DAY, "candidateDate": DAY,
            "rolloutRootCount": 1, "standardRowsUpserted": 1, "top10RowsUpserted": 1,
        }
        self.authority_response = authority_response or {
            "status": "complete", "marketDate": DAY, "rowsActivated": 0,
            "structuralRootCount": 155, "activeAuthorityRootCount": 155,
            "missingStructuralRootCount": 0, "structuralFingerprint": "fp",
        }
        self.rpc_calls = []
        self.incomplete_after_rpc = incomplete_after_rpc
        if materialized:
            self._materialize()

    def _materialize(self):
        self.history = [
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "standard",
             "source": "canonical_root_set_public_rollout_candidate_v1"},
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "top10",
             "source": "canonical_root_top10_public_rollout_candidate_v1"},
        ]

    def table(self, name):
        if name == prep.ROLLOUT_VIEW:
            return Query(self.roots, poison_name=name)
        if name == prep.ERA_ROLLOUT_VIEW:
            return Query(self.era_rows)
        if name == prep.SETS_TABLE:
            return Query(self.set_rows)
        return Query(self.history)

    def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        client = self

        class RPC:
            def execute(self):
                if name == prep.AUTHORITY_SYNC_RPC:
                    return SimpleNamespace(data=client.authority_response)
                client._materialize()
                if client.incomplete_after_rpc:
                    client.history.pop()
                return SimpleNamespace(data=client.response)

        return RPC()


def test_commit_syncs_authority_then_prepares_and_validates_complete_candidate_pairs():
    client = Client()
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    assert client.rpc_calls == [
        (prep.AUTHORITY_SYNC_RPC, {"p_market_date": DAY}),
        (prep.CANDIDATE_PREPARATION_RPC, {"p_market_date": DAY}),
    ]
    assert result["authoritySync"]["structuralRootCount"] == 155
    assert result["materialization"]["ready"] is True
    assert result["materialization"]["provenanceState"] == "candidate"


def test_dry_run_is_read_only_and_reports_preparation_required():
    client = Client()
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=False)
    assert client.rpc_calls == []
    assert result["candidatePreparationRequired"] is True
    assert result["rpcInvoked"] is False


@pytest.mark.parametrize("change,match", [
    ({"status": "blocked"}, "did not complete"),
    ({"marketDate": "2026-09-12"}, "wrong marketDate"),
    ({"structuralRootCount": 0}, "empty structural cohort"),
    ({"missingStructuralRootCount": 1}, "left structural roots missing"),
    ({"activeAuthorityRootCount": 154}, "active count is below structural count"),
])
def test_bad_authority_sync_response_fails_closed(change, match):
    response = dict(Client().authority_response)
    response.update(change)
    with pytest.raises(RuntimeError, match=match):
        prep.prepare_market_rollout_candidate(
            Client(authority_response=response), DAY, commit=True,
        )


@pytest.mark.parametrize("change,match", [
    ({"marketDate": "2026-09-12"}, "wrong marketDate"),
    ({"candidateDate": "2026-09-12"}, "wrong candidateDate"),
    ({"rolloutRootCount": 2}, "root count mismatch"),
    ({"standardRowsUpserted": 0}, "Standard row count mismatch"),
    ({"top10RowsUpserted": 0}, "Top10 row count mismatch"),
])
def test_bad_candidate_response_fails_closed(change, match):
    response = dict(Client().response)
    response.update(change)
    with pytest.raises(RuntimeError, match=match):
        prep.prepare_market_rollout_candidate(Client(response=response), DAY, commit=True)


def test_unprepared_historical_date_is_rejected_by_authority_sync_response():
    authority = dict(Client().authority_response, marketDate=DAY)
    with pytest.raises(RuntimeError, match="wrong marketDate"):
        prep.prepare_market_rollout_candidate(
            Client(authority_response=authority), "2026-09-12", commit=True,
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
    assert len(client.rpc_calls) == 4


# --- structural membership -------------------------------------------------


def _set_row(**overrides):
    row = {
        "id": "root", "era_id": ERA_A, "release_date": "2020-01-01",
        "parent_opening_set_id": None, "catalog_only": False,
        "ready_for_daily_scrape": True,
    }
    row.update(overrides)
    return row


def test_never_queries_expensive_rollout_view_on_commit_path():
    client = Client()
    prep.prepare_market_rollout_candidate(client, DAY, commit=True)


def test_never_queries_expensive_rollout_view_on_dry_run_path():
    client = Client()
    prep.prepare_market_rollout_candidate(client, DAY, commit=False)


def test_enabled_rollout_era_included():
    client = Client()
    assert prep.staged_rollout_root_ids(client, DAY) == ["root"]


def test_disabled_rollout_era_excluded():
    client = Client(era_rows=[{"era_id": ERA_A, "activated_market_date": "2026-09-10", "enabled": False}])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_future_activation_excluded():
    client = Client(era_rows=[{"era_id": ERA_A, "activated_market_date": "2026-09-14", "enabled": True}])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_released_root_included():
    client = Client(set_rows=[_set_row(release_date="2026-09-13")])
    assert prep.staged_rollout_root_ids(client, DAY) == ["root"]


def test_future_release_root_excluded():
    client = Client(set_rows=[_set_row(release_date="2026-09-14")])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_child_member_set_excluded():
    client = Client(set_rows=[_set_row(parent_opening_set_id="parent-set")])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_catalog_only_set_excluded():
    client = Client(set_rows=[_set_row(catalog_only=True)])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_not_ready_for_daily_scrape_excluded():
    client = Client(set_rows=[_set_row(ready_for_daily_scrape=False)])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_duplicate_input_eliminated():
    client = Client(
        era_rows=[
            {"era_id": ERA_A, "activated_market_date": "2026-09-10", "enabled": True},
            {"era_id": ERA_A, "activated_market_date": "2026-09-11", "enabled": True},
        ],
        set_rows=[_set_row(), _set_row()],
    )
    assert prep.staged_rollout_root_ids(client, DAY) == ["root"]


def test_empty_structural_cohort_fails_closed():
    client = Client(era_rows=[], set_rows=[])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_valuation_coverage_failure_does_not_shrink_expected_membership():
    # No history rows at all -- the root is still structurally expected, so
    # materialization must report it missing rather than silently excluding
    # it from the expected cohort.
    client = Client()
    materialization = prep.rollout_candidate_materialization(client, DAY)
    assert materialization["ready"] is False
    assert materialization["rootCount"] == 1
    assert ["root", "standard"] in materialization["missingRootScopePairs"]
    assert ["root", "top10"] in materialization["missingRootScopePairs"]
