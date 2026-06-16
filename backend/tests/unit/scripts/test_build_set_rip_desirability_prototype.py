from __future__ import annotations

from typing import Any, Dict, List, Sequence

import pytest

import backend.scripts.build_set_rip_desirability_prototype as prototype


class FakeRepository:
    def __init__(
        self,
        *,
        exact_v2_rows: Sequence[Dict[str, Any]],
        fallback_v2_rows: Sequence[Dict[str, Any]],
        rip_rows: Sequence[Dict[str, Any]],
        sets_rows: Sequence[Dict[str, Any]],
    ):
        self._exact_v2_rows = list(exact_v2_rows)
        self._fallback_v2_rows = list(fallback_v2_rows)
        self._rip_rows = list(rip_rows)
        self._sets_rows = list(sets_rows)
        self.persist_calls: List[Dict[str, Any]] = []

    def list_v2_rows(self, *, scoring_version: str, hit_policy_version: str, composite_scoring_version: str):
        _ = (scoring_version, hit_policy_version, composite_scoring_version)
        return list(self._exact_v2_rows)

    def list_v2_rows_any_version(self):
        return list(self._fallback_v2_rows)

    def list_latest_rip_rows(self):
        return list(self._rip_rows)

    def list_sets_metadata(self):
        return list(self._sets_rows)

    def list_top_simulation_cards_for_runs(self, run_ids):
        _ = run_ids
        return {}

    def insert_opening_desirability_rows(self, rows, *, scoring_version):
        self.persist_calls.append({"rows": list(rows), "scoring_version": scoring_version})
        return [{"id": f"row-{idx}"} for idx, _ in enumerate(rows, start=1)]


def test_global_run_includes_set_present_only_in_fallback_component_rows(monkeypatch):
    _patch_scoring(monkeypatch)
    repository = FakeRepository(
        exact_v2_rows=[],
        fallback_v2_rows=[
            _v2_row(
                set_id="set-chaos",
                set_name="Chaos Rising",
                set_canonical_key="chaosRising",
                set_desirability_score=55.0,
                built_at="2026-06-16T17:03:14+00:00",
            )
        ],
        rip_rows=[
            _rip_row(
                set_id="set-chaos",
                set_name="Chaos Rising",
                canonical_key="chaosRising",
                calculation_run_id="run-chaos",
                prob_big_hit=0.31,
                run_at="2026-06-16T17:51:35+00:00",
            )
        ],
        sets_rows=[
            _set_row(
                set_id="set-chaos",
                name="Chaos Rising",
                canonical_key="chaosRising",
            )
        ],
    )

    report = prototype.build_report(
        repository=repository,
        scoring_version="v2",
        hit_policy_version="new-hit-policy",
        composite_scoring_version="comp-v1",
    )

    keys = {row["set_canonical_key"] for row in report["rows"]}
    assert "chaosRising" in keys


def test_set_with_collector_but_missing_chase_is_kept_as_collector_only(monkeypatch):
    _patch_scoring(monkeypatch)
    repository = FakeRepository(
        exact_v2_rows=[
            _v2_row(
                set_id="set-collector-only",
                set_name="Collector Only",
                set_canonical_key="collectorOnly",
                set_desirability_score=64.2,
                built_at="2026-06-16T17:00:00+00:00",
            )
        ],
        fallback_v2_rows=[],
        rip_rows=[],
        sets_rows=[
            _set_row(
                set_id="set-collector-only",
                name="Collector Only",
                canonical_key="collectorOnly",
            )
        ],
    )

    report = prototype.build_report(
        repository=repository,
        scoring_version="v2",
        hit_policy_version="hp",
        composite_scoring_version="comp",
    )

    row = report["rows"][0]
    assert row["set_canonical_key"] == "collectorOnly"
    assert row["collector_appeal_score"] == 64.2
    assert row["chase_appeal_score"] is None
    assert row["opening_desirability_score"] is None
    assert row["opening_desirability_display_status"] == "collector_only"


def test_global_ranks_are_computed_against_all_rows_not_partial_subset(monkeypatch):
    _patch_scoring(monkeypatch)
    repository = FakeRepository(
        exact_v2_rows=[
            _v2_row(
                set_id="set-top",
                set_name="Top Set",
                set_canonical_key="topSet",
                set_desirability_score=92.0,
                built_at="2026-06-16T17:00:00+00:00",
            ),
            _v2_row(
                set_id="set-mid",
                set_name="Mid Set",
                set_canonical_key="midSet",
                set_desirability_score=70.0,
                built_at="2026-06-16T17:00:00+00:00",
            ),
        ],
        fallback_v2_rows=[],
        rip_rows=[
            _rip_row(
                set_id="set-top",
                set_name="Top Set",
                canonical_key="topSet",
                calculation_run_id="run-top",
                prob_big_hit=0.55,
                run_at="2026-06-16T17:51:35+00:00",
            ),
            _rip_row(
                set_id="set-mid",
                set_name="Mid Set",
                canonical_key="midSet",
                calculation_run_id="run-mid",
                prob_big_hit=0.20,
                run_at="2026-06-16T17:51:35+00:00",
            ),
        ],
        sets_rows=[
            _set_row(set_id="set-top", name="Top Set", canonical_key="topSet"),
            _set_row(set_id="set-mid", name="Mid Set", canonical_key="midSet"),
        ],
    )

    report = prototype.build_report(
        repository=repository,
        scoring_version="v2",
        hit_policy_version="hp",
        composite_scoring_version="comp",
    )

    by_key = {row["set_canonical_key"]: row for row in report["rows"]}
    assert by_key["topSet"]["opening_desirability_rank"] == 1
    assert by_key["midSet"]["opening_desirability_rank"] == 2
    assert by_key["midSet"]["opening_desirability_rank"] != 1


def test_partial_commit_is_rejected():
    with pytest.raises(ValueError, match="Refusing to commit Opening Desirability ranks from a partial set run"):
        prototype.maybe_persist_opening_desirability(
            report={
                "rows": [_report_row()],
                "parameters": {"limit": 1},
            },
            repository=FakeRepository(exact_v2_rows=[], fallback_v2_rows=[], rip_rows=[], sets_rows=[]),
            commit=True,
            scoring_version="opening-v1",
        )


def test_partial_non_commit_is_allowed():
    result = prototype.maybe_persist_opening_desirability(
        report={
            "rows": [_report_row()],
            "parameters": {"limit": 1},
        },
        repository=FakeRepository(exact_v2_rows=[], fallback_v2_rows=[], rip_rows=[], sets_rows=[]),
        commit=False,
        scoring_version="opening-v1",
    )

    assert result["committed"] is False
    assert result["rows_that_would_be_persisted"] == 1


def _patch_scoring(monkeypatch):
    def fake_monetary(inputs):
        prob_big_hit = inputs.get("prob_big_hit")
        if prob_big_hit is None:
            return {
                "monetary_chase_appeal_score": None,
                "monetary_data_quality": "missing",
                "component_scores_json": {},
            }
        score = round(float(prob_big_hit) * 100.0, 4)
        return {
            "monetary_chase_appeal_score": score,
            "monetary_data_quality": "usable",
            "component_scores_json": {},
        }

    def fake_rip(*, pure_desirability_score, monetary_chase_appeal_score):
        if pure_desirability_score is None or monetary_chase_appeal_score is None:
            primary = None
        else:
            primary = round((0.7 * float(pure_desirability_score)) + (0.3 * float(monetary_chase_appeal_score)), 4)
        return {
            "rip_desirability_score_80_20": primary,
            "rip_desirability_score_70_30": primary,
            "rip_desirability_score_60_40": primary,
            "primary_rip_desirability_score": primary,
            "component_scores_json": {},
        }

    monkeypatch.setattr(prototype, "compute_monetary_chase_appeal", fake_monetary)
    monkeypatch.setattr(prototype, "compute_rip_desirability", fake_rip)


def _set_row(*, set_id: str, name: str, canonical_key: str) -> Dict[str, Any]:
    return {
        "id": set_id,
        "name": name,
        "canonical_key": canonical_key,
        "pokemon_api_set_id": None,
        "release_date": "2026-01-01",
    }


def _v2_row(
    *,
    set_id: str,
    set_name: str,
    set_canonical_key: str,
    set_desirability_score: float,
    built_at: str,
) -> Dict[str, Any]:
    return {
        "id": f"v2-{set_id}",
        "set_id": set_id,
        "set_name": set_name,
        "set_canonical_key": set_canonical_key,
        "set_desirability_score": set_desirability_score,
        "chase_subject_strength": 50.0,
        "chase_subject_depth": 50.0,
        "accessible_favorite_hits": 50.0,
        "special_pack_chase_appeal": 50.0,
        "built_at": built_at,
    }


def _rip_row(
    *,
    set_id: str,
    set_name: str,
    canonical_key: str,
    calculation_run_id: str,
    prob_big_hit: float,
    run_at: str,
) -> Dict[str, Any]:
    return {
        "set_id": set_id,
        "set_name": set_name,
        "canonical_key": canonical_key,
        "calculation_run_id": calculation_run_id,
        "run_at": run_at,
        "prob_big_hit": prob_big_hit,
        "p95_value_to_cost_ratio": None,
        "p99_value_to_cost_ratio": None,
        "hit_ev_per_pack": None,
        "mean_value_to_cost_ratio": None,
        "effective_chase_count": None,
        "hhi_ev_concentration": None,
        "top1_ev_share": None,
        "top3_ev_share": None,
        "top5_ev_share": None,
        "current_market_pack_cost": None,
        "pack_cost": None,
    }


def _report_row() -> Dict[str, Any]:
    return {
        "set_id": "set-1",
        "set_name": "Any Set",
        "set_canonical_key": "anySet",
        "pure_desirability_score": 50.0,
        "pure_desirability_rank": 1,
        "monetary_chase_appeal_score": 25.0,
        "monetary_chase_appeal_rank": 1,
        "rip_desirability_score_80_20": 42.5,
        "rip_desirability_score_70_30": 42.5,
        "rip_desirability_score_60_40": 42.5,
        "rip_desirability_rank_70_30": 1,
    }
