"""Current-day Market source validation around the root-authority cutover.

The validation path must never touch the valuation-backed
``pokemon_market_public_rollout_root_sets_v1`` view. Sep 10+ membership comes
from the frozen root-authority table; canonical-checklist values may fill exact
authority root/scope pairs that the rollout finalizer intentionally does not
promote, while arbitrary generic/member Price Storage rows remain rejected.
"""
from __future__ import annotations

from types import SimpleNamespace

import backend.scripts.build_pokemon_market_index_history as index_history
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


def _history_row(root, scope, source, *, day=DAY, value="10.00", count=10):
    return {
        "set_id": root,
        "value_scope": scope,
        "snapshot_date": day,
        "source": source,
        "set_value": value,
        "priced_card_count": count,
    }


def _final_rows(root="root-1", *, day=DAY):
    return [
        _history_row(root, "standard", "canonical_root_set_public_rollout_v1", day=day),
        _history_row(root, "top10", "canonical_root_top10_public_rollout_v1", day=day),
    ]


def _candidate_rows(root="root-1"):
    return [
        _history_row(root, "standard", "canonical_root_set_public_rollout_candidate_v1"),
        _history_row(root, "top10", "canonical_root_top10_public_rollout_candidate_v1"),
    ]


def _checklist_rows(root="root-1", *, day=DAY):
    return [
        _history_row(
            root,
            "standard",
            "card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist",
            day=day,
        ),
        _history_row(
            root,
            "top10",
            "card_variant_price_observations_near_mint_latest_as_of_day:top10:canonical_checklist",
            day=day,
        ),
    ]


class PoisonedRolloutViewClient:
    """Serves authority/history tables; explodes if the expensive view is read."""

    def __init__(self, *, history=None, authority_rows=None):
        self.poisoned_roots = [
            {"set_id": "root-1", "release_date": "2020-01-01", "activated_market_date": "2026-09-10"},
        ]
        self.authority_rows = authority_rows if authority_rows is not None else [
            {
                "set_id": "root-1",
                "activated_market_date": "2026-09-10",
                "deactivated_market_date": None,
                "enabled": True,
            },
        ]
        self.era_rows = [
            {"era_id": ERA_A, "activated_market_date": LEGACY_DAY, "enabled": True},
        ]
        self.set_rows = [
            {"id": "root-1", "era_id": ERA_A, "release_date": "2020-01-01",
             "parent_opening_set_id": None, "catalog_only": False, "ready_for_daily_scrape": True},
        ]
        self.history = list(history if history is not None else _final_rows())

    def table(self, name):
        if name == prep.ROLLOUT_VIEW:
            return Query(self.poisoned_roots, poison_name=name)
        if name == MARKET_ROOT_AUTHORITY_TABLE:
            return Query(self.authority_rows)
        if name == prep.ERA_ROLLOUT_VIEW:
            return Query(self.era_rows)
        if name == prep.SETS_TABLE:
            return Query(self.set_rows)
        return Query(self.history)


def test_final_provenance_validation_never_queries_expensive_rollout_view():
    client = PoisonedRolloutViewClient()
    result = index_history._rollout_source_materialization(client, DAY, allow_candidate=False)
    assert result["ready"] is True
    assert result["provenanceState"] == "final"
    assert result["finalProvenanceComplete"] is True


def test_candidate_preview_never_queries_expensive_rollout_view():
    client = PoisonedRolloutViewClient(history=_candidate_rows())
    result = index_history._rollout_source_materialization(client, DAY, allow_candidate=True)
    assert result["ready"] is True
    assert result["provenanceState"] == "candidate"


def test_candidate_rows_are_not_commit_ready_before_finalizer():
    client = PoisonedRolloutViewClient(history=_candidate_rows())
    result = index_history._rollout_source_materialization(client, DAY, allow_candidate=False)
    assert result["ready"] is False
    assert result["provenanceState"] == "candidate"
    assert ["root-1", "standard"] in result["missingRootScopePairs"]
    assert ["root-1", "top10"] in result["missingRootScopePairs"]


def test_postcutover_partial_final_plus_checklist_covers_full_authority():
    authority = [
        {"set_id": "root-1", "activated_market_date": "2026-09-10",
         "deactivated_market_date": None, "enabled": True},
        {"set_id": "root-2", "activated_market_date": "2026-09-10",
         "deactivated_market_date": None, "enabled": True},
    ]
    history = _final_rows("root-1") + _checklist_rows("root-2")
    result = index_history._rollout_source_materialization(
        PoisonedRolloutViewClient(history=history, authority_rows=authority),
        DAY,
        allow_candidate=False,
    )
    assert result["ready"] is True
    assert result["rootCount"] == 2
    assert result["materializedPairCount"] == 4
    assert result["provenanceState"] == "final"
    assert result["finalProvenanceComplete"] is False
    assert result["sourceContract"] == "canonical_market_root_authority_values_v1"


def test_postcutover_arbitrary_generic_member_source_is_rejected():
    history = [
        _history_row("root-1", "standard", "member_price_storage_v2_generic"),
        _history_row("root-1", "top10", "member_price_storage_v2_generic"),
    ]
    result = index_history._rollout_source_materialization(
        PoisonedRolloutViewClient(history=history), DAY, allow_candidate=False,
    )
    assert result["ready"] is False
    assert result["materializedPairCount"] == 0
    assert len(result["unsupportedSourcePairs"]) == 2


def test_postcutover_nonpositive_authority_value_fails_closed():
    history = _final_rows()
    history[1]["set_value"] = "0"
    result = index_history._rollout_source_materialization(
        PoisonedRolloutViewClient(history=history), DAY, allow_candidate=False,
    )
    assert result["ready"] is False
    assert ["root-1", "top10"] in result["missingRootScopePairs"]


def test_pre_cutover_canonical_checklist_does_not_relax_historical_provenance():
    client = PoisonedRolloutViewClient(history=_checklist_rows(day=LEGACY_DAY))
    result = index_history._rollout_source_materialization(
        client, LEGACY_DAY, allow_candidate=False,
    )
    assert result["ready"] is False
    assert result["provenanceState"] == "none"
