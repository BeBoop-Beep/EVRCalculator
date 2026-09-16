from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_market_rollout_preparation as prep
from backend.db.services.pokemon_market_rollout_cohort import MARKET_ROOT_AUTHORITY_TABLE

DAY = "2026-09-13"
LEGACY_DAY = "2026-09-09"
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
    """Fake client for both the frozen root authority and legacy rollout path."""

    def __init__(
        self,
        *,
        response=None,
        materialized=False,
        incomplete_after_rpc=False,
        authority_rows=None,
        era_rows=None,
        set_rows=None,
        history=None,
    ):
        self.roots = [{
            "set_id": "root", "release_date": "2020-01-01",
            "activated_market_date": "2026-09-10",
        }]
        self.authority_rows = authority_rows if authority_rows is not None else [{
            "set_id": "root", "activated_market_date": "2026-09-10",
            "deactivated_market_date": None, "enabled": True,
        }]
        self.era_rows = era_rows if era_rows is not None else [
            {"era_id": ERA_A, "activated_market_date": "2026-09-09", "enabled": True},
        ]
        self.set_rows = set_rows if set_rows is not None else [
            {"id": "root", "era_id": ERA_A, "release_date": "2020-01-01",
             "parent_opening_set_id": None, "catalog_only": False,
             "ready_for_daily_scrape": True},
        ]
        self.history = list(history or [])
        self.response = response or {
            "status": "complete", "marketDate": DAY, "candidateDate": DAY,
            "rolloutRootCount": 1, "standardRowsUpserted": 1, "top10RowsUpserted": 1,
        }
        self.rpc_calls = []
        self.incomplete_after_rpc = incomplete_after_rpc
        if materialized:
            self._materialize()

    def _materialize(self):
        self.history = [row for row in self.history if row.get("set_id") != "root"] + [
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "standard",
             "source": "canonical_root_set_public_rollout_candidate_v1"},
            {"set_id": "root", "snapshot_date": DAY, "value_scope": "top10",
             "source": "canonical_root_top10_public_rollout_candidate_v1"},
        ]

    def table(self, name):
        if name == prep.ROLLOUT_VIEW:
            return Query(self.roots, poison_name=name)
        if name == MARKET_ROOT_AUTHORITY_TABLE:
            return Query(self.authority_rows)
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
                client._materialize()
                if client.incomplete_after_rpc:
                    client.history.pop()
                return SimpleNamespace(data=client.response)

        return RPC()


def _generic_pair(root):
    return [
        {"set_id": root, "snapshot_date": DAY, "value_scope": "standard",
         "source": "card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist"},
        {"set_id": root, "snapshot_date": DAY, "value_scope": "top10",
         "source": "card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist"},
    ]


def test_commit_prepares_and_reconciles_candidate_write_receipt():
    client = Client()
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    assert client.rpc_calls == [(prep.CANDIDATE_PREPARATION_RPC, {"p_market_date": DAY})]
    assert result["expectedRootCount"] == 1
    assert result["candidateWrites"]["standardCandidateCount"] == 1
    assert result["candidateWrites"]["top10CandidateCount"] == 1
    assert result["candidateWrites"]["top10SubsetOfStandard"] is True
    assert result["materialization"]["ready"] is True


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
    ({"top10RowsUpserted": 2}, "Top10 row count mismatch"),
])
def test_bad_candidate_response_fails_closed(change, match):
    response = dict(Client().response)
    response.update(change)
    with pytest.raises(RuntimeError, match=match):
        prep.prepare_market_rollout_candidate(Client(response=response), DAY, commit=True)


def test_partial_candidate_writes_are_allowed_across_larger_authority_cohort():
    authority = [
        {"set_id": "root", "activated_market_date": "2026-09-10",
         "deactivated_market_date": None, "enabled": True},
        {"set_id": "root-2", "activated_market_date": "2026-09-10",
         "deactivated_market_date": None, "enabled": True},
    ]
    client = Client(authority_rows=authority, history=_generic_pair("root-2"))
    result = prep.prepare_market_rollout_candidate(client, DAY, commit=True)

    assert result["rolloutRootCount"] == 1
    assert result["expectedRootCount"] == 2
    assert result["candidateWrites"]["standardCandidateCount"] == 1
    assert result["candidateWrites"]["top10CandidateCount"] == 1
    # Generic current-day rows are intentionally not accepted by the stricter
    # provenance diagnostic. The subsequent Market Date Quality gate owns full
    # authority-cohort valuation completeness and may accept those rows there.
    assert result["materialization"]["ready"] is False
    assert result["materialization"]["rootCount"] == 2


def test_candidate_top10_receipt_mismatch_fails_closed():
    with pytest.raises(RuntimeError, match="Top10 write receipt mismatch"):
        prep.prepare_market_rollout_candidate(
            Client(incomplete_after_rpc=True), DAY, commit=True,
        )


def test_candidate_standard_receipt_mismatch_fails_closed():
    response = dict(
        Client().response,
        rolloutRootCount=0,
        standardRowsUpserted=0,
        top10RowsUpserted=0,
    )
    with pytest.raises(RuntimeError, match="Standard write receipt mismatch"):
        prep.prepare_market_rollout_candidate(Client(response=response), DAY, commit=True)


def test_unprepared_historical_date_is_rejected_by_rpc_response():
    response = dict(Client().response, marketDate=DAY, candidateDate=DAY)
    with pytest.raises(RuntimeError, match="wrong marketDate"):
        prep.prepare_market_rollout_candidate(
            Client(response=response), "2026-09-12", commit=True,
        )


def test_candidate_preparation_retry_is_idempotent():
    client = Client()
    first = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    second = prep.prepare_market_rollout_candidate(client, DAY, commit=True)
    assert first["candidateWrites"]["standardCandidateCount"] == 1
    assert second["candidateWrites"]["standardCandidateCount"] == 1
    assert len(client.history) == 2
    assert len(client.rpc_calls) == 2


# --- authority / historical membership ------------------------------------


def _set_row(**overrides):
    row = {
        "id": "root", "era_id": ERA_A, "release_date": "2020-01-01",
        "parent_opening_set_id": None, "catalog_only": False,
        "ready_for_daily_scrape": True,
    }
    row.update(overrides)
    return row


def test_never_queries_expensive_rollout_view_on_commit_path():
    prep.prepare_market_rollout_candidate(Client(), DAY, commit=True)


def test_never_queries_expensive_rollout_view_on_dry_run_path():
    prep.prepare_market_rollout_candidate(Client(), DAY, commit=False)


def test_post_cutover_membership_comes_from_root_authority_not_era_rollout():
    client = Client(
        authority_rows=[
            {"set_id": "authority-root", "activated_market_date": "2026-09-10",
             "deactivated_market_date": None, "enabled": True},
        ],
        era_rows=[],
        set_rows=[],
    )
    assert prep.staged_rollout_root_ids(client, DAY) == ["authority-root"]


def test_post_cutover_future_authority_activation_is_excluded():
    client = Client(authority_rows=[
        {"set_id": "root", "activated_market_date": "2026-09-14",
         "deactivated_market_date": None, "enabled": True},
    ])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_post_cutover_deactivated_authority_member_is_excluded():
    client = Client(authority_rows=[
        {"set_id": "root", "activated_market_date": "2026-09-10",
         "deactivated_market_date": DAY, "enabled": True},
    ])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, DAY)


def test_post_cutover_duplicate_authority_rows_are_deduped():
    row = {"set_id": "root", "activated_market_date": "2026-09-10",
           "deactivated_market_date": None, "enabled": True}
    assert prep.staged_rollout_root_ids(Client(authority_rows=[row, dict(row)]), DAY) == ["root"]


def test_legacy_enabled_rollout_era_included():
    assert prep.staged_rollout_root_ids(Client(), LEGACY_DAY) == ["root"]


def test_legacy_disabled_rollout_era_excluded():
    client = Client(era_rows=[
        {"era_id": ERA_A, "activated_market_date": LEGACY_DAY, "enabled": False},
    ])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_future_activation_excluded():
    client = Client(era_rows=[
        {"era_id": ERA_A, "activated_market_date": "2026-09-10", "enabled": True},
    ])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_released_root_included():
    client = Client(set_rows=[_set_row(release_date=LEGACY_DAY)])
    assert prep.staged_rollout_root_ids(client, LEGACY_DAY) == ["root"]


def test_legacy_future_release_root_excluded():
    client = Client(set_rows=[_set_row(release_date="2026-09-10")])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_child_member_set_excluded():
    client = Client(set_rows=[_set_row(parent_opening_set_id="parent-set")])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_catalog_only_set_excluded():
    client = Client(set_rows=[_set_row(catalog_only=True)])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_not_ready_for_daily_scrape_excluded():
    client = Client(set_rows=[_set_row(ready_for_daily_scrape=False)])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_legacy_duplicate_input_eliminated():
    client = Client(
        era_rows=[
            {"era_id": ERA_A, "activated_market_date": "2026-09-08", "enabled": True},
            {"era_id": ERA_A, "activated_market_date": LEGACY_DAY, "enabled": True},
        ],
        set_rows=[_set_row(), _set_row()],
    )
    assert prep.staged_rollout_root_ids(client, LEGACY_DAY) == ["root"]


def test_empty_legacy_structural_cohort_fails_closed():
    client = Client(era_rows=[], set_rows=[])
    with pytest.raises(RuntimeError, match="empty"):
        prep.staged_rollout_root_ids(client, LEGACY_DAY)


def test_valuation_coverage_failure_does_not_shrink_expected_membership():
    client = Client()
    materialization = prep.rollout_candidate_materialization(client, DAY)
    assert materialization["ready"] is False
    assert materialization["rootCount"] == 1
    assert ["root", "standard"] in materialization["missingRootScopePairs"]
    assert ["root", "top10"] in materialization["missingRootScopePairs"]
