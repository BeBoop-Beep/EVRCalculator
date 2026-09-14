"""Prompt 4: current-day final-provenance validation must never touch the
valuation-backed pokemon_market_public_rollout_root_sets_v1 view -- that view
prices the global root universe and measured ~7.86s in production, which left
no PostgREST budget for the (already cheap) candidate RPC itself.
"""
from __future__ import annotations

from types import SimpleNamespace

import backend.scripts.build_pokemon_market_index_history as index_history
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


class PoisonedRolloutViewClient:
    """Serves structural authority tables; explodes if the expensive view is read."""

    def __init__(self, *, history=None):
        self.poisoned_roots = [
            {"set_id": "root-1", "release_date": "2020-01-01", "activated_market_date": "2026-09-10"},
        ]
        self.era_rows = [{"era_id": ERA_A, "activated_market_date": "2026-09-10", "enabled": True}]
        self.set_rows = [
            {"id": "root-1", "era_id": ERA_A, "release_date": "2020-01-01",
             "parent_opening_set_id": None, "catalog_only": False, "ready_for_daily_scrape": True},
        ]
        self.history = history if history is not None else [
            {"set_id": "root-1", "value_scope": "standard", "snapshot_date": DAY,
             "source": "canonical_root_set_public_rollout_v1"},
            {"set_id": "root-1", "value_scope": "top10", "snapshot_date": DAY,
             "source": "canonical_root_top10_public_rollout_v1"},
        ]

    def table(self, name):
        if name == prep.ROLLOUT_VIEW:
            return Query(self.poisoned_roots, poison_name=name)
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


def test_candidate_preview_never_queries_expensive_rollout_view():
    client = PoisonedRolloutViewClient(history=[
        {"set_id": "root-1", "value_scope": "standard", "snapshot_date": DAY,
         "source": "canonical_root_set_public_rollout_candidate_v1"},
        {"set_id": "root-1", "value_scope": "top10", "snapshot_date": DAY,
         "source": "canonical_root_top10_public_rollout_candidate_v1"},
    ])
    result = index_history._rollout_source_materialization(client, DAY, allow_candidate=True)
    assert result["ready"] is True
    assert result["provenanceState"] == "candidate"
