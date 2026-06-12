from __future__ import annotations

from backend.desirability.composite import (
    COMPOSITE_SCORING_VERSION,
    build_composite_report,
    build_composite_scores,
)
from backend.desirability.normalization import SCORING_VERSION as FAN_SCORING_VERSION
from backend.desirability.trends_normalization import RECENT_TREND_SCORE, TREND_SCORING_VERSION


REFERENCES = [
    {"id": 1, "pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur"},
    {"id": 4, "pokedex_number": 4, "canonical_name": "charmander", "display_name": "Charmander"},
    {"id": 25, "pokedex_number": 25, "canonical_name": "pikachu", "display_name": "Pikachu"},
]


def test_composite_formula_and_missing_trend_fallback():
    rows, summary = build_composite_scores(
        references=REFERENCES,
        fan_scores=[
            _fan_score(1, "Bulbasaur", 80.0, 2),
            _fan_score(4, "Charmander", 40.0, 3),
        ],
        fan_snapshot_id=2,
        current_trend_scores=[
            _trend_score(1, 20.0, 2),
        ],
        current_trend_snapshot_id=1,
    )

    by_ref = {row["pokemon_reference_id"]: row for row in rows}
    assert by_ref[1]["desirability_score"] == 65.0
    assert by_ref[1]["score_components_json"]["trend_missing_fallback"] is False
    assert by_ref[4]["desirability_score"] == 40.0
    assert by_ref[4]["current_trend_score"] is None
    assert by_ref[4]["score_components_json"]["trend_missing_fallback"] is True
    assert summary["missing_trend_count"] == 1


def test_composite_ranking_uses_desirability_score():
    rows, _summary = build_composite_scores(
        references=REFERENCES,
        fan_scores=[
            _fan_score(1, "Bulbasaur", 50.0, 2),
            _fan_score(4, "Charmander", 70.0, 1),
            _fan_score(25, "Pikachu", 40.0, 3),
        ],
        fan_snapshot_id=2,
        current_trend_scores=[
            _trend_score(1, 100.0, 1),
            _trend_score(4, 10.0, 3),
            _trend_score(25, 80.0, 2),
        ],
        current_trend_snapshot_id=1,
    )

    assert [row["pokemon_reference_id"] for row in rows] == [1, 4, 25]
    assert [row["desirability_rank"] for row in rows] == [1, 2, 3]
    assert rows[0]["desirability_score"] == 62.5


def test_composite_dry_run_writes_no_rows_and_reports_diagnostics():
    repository = CompositeRepository()

    report = build_composite_report(
        repository=repository,
        dry_run=True,
        min_coverage=0.5,
        expected_reference_count=3,
    )

    assert report["status"] == "dry_run"
    assert report["diagnostics"]["total_pokemon_processed"] == 3
    assert report["diagnostics"]["fan_scores_found"] == 3
    assert report["diagnostics"]["trend_scores_found"] == 2
    assert report["diagnostics"]["missing_trend_count"] == 1
    assert report["diagnostics"]["trend_rows_by_snapshot_id"] == {"1": 1, "3": 1}
    assert report["diagnostics"]["valid_current_trend_snapshot_ids_considered"] == [3, 1]
    assert report["scoring_version"] == COMPOSITE_SCORING_VERSION
    assert repository.inserted_composite_rows == []


def test_composite_uses_latest_valid_trend_row_per_pokemon():
    repository = CompositeRepository()

    report = build_composite_report(
        repository=repository,
        dry_run=False,
        min_coverage=0.5,
        expected_reference_count=3,
    )

    by_ref = {row["pokemon_reference_id"]: row for row in repository.inserted_composite_rows}
    assert report["status"] == "committed"
    assert by_ref[1]["current_trend_snapshot_id"] == 3
    assert by_ref[1]["current_trend_score"] > 0
    assert by_ref[25]["current_trend_snapshot_id"] == 1
    assert by_ref[4]["current_trend_snapshot_id"] is None
    assert by_ref[4]["score_components_json"]["trend_missing_fallback"] is True


class CompositeRepository:
    def __init__(self):
        self.inserted_composite_rows = []

    def list_pokemon_references(self):
        return REFERENCES

    def list_latest_desirability_source_snapshots(self, *, source_name, limit=10):
        assert source_name == "favoritepokemon"
        return [{"id": 2, "source_name": source_name, "status": "captured", "captured_at": "2026-06-10"}]

    def list_desirability_scores_for_snapshot(self, snapshot_id, *, scoring_version=None):
        assert snapshot_id == 2
        assert scoring_version == FAN_SCORING_VERSION
        return [
            _fan_score(1, "Bulbasaur", 80.0, 2),
            _fan_score(4, "Charmander", 60.0, 3),
            _fan_score(25, "Pikachu", 100.0, 1),
        ]

    def list_valid_current_trend_source_snapshots(
        self,
        *,
        source_name,
        provider_name,
        geo,
        timeframe,
        window_role,
        query_type,
        status,
        limit=50,
    ):
        assert timeframe == "today 1-m"
        assert provider_name == "pytrends"
        assert window_role == "recent"
        assert query_type == "search_term"
        assert status == "captured_relative_search_interest"
        return [
            {"id": 3, "source_name": source_name, "geo": geo, "timeframe": timeframe, "status": status},
            {"id": 1, "source_name": source_name, "geo": geo, "timeframe": timeframe, "status": status},
        ][:limit]

    def list_trend_source_rows_for_snapshot(self, snapshot_id):
        rows_by_snapshot = {
            3: [
                _trend_source_row(1, "Bulbasaur", snapshot_id=3, relative_to_anchor=0.5, raw_interest_value=3.125),
            ],
            1: [
                _trend_source_row(1, "Bulbasaur", snapshot_id=1, relative_to_anchor=0.0, raw_interest_value=0.0),
                _trend_source_row(25, "Pikachu", snapshot_id=1, relative_to_anchor=1.0, raw_interest_value=75.0),
            ],
        }
        return rows_by_snapshot.get(snapshot_id, [])

    def insert_desirability_composite_scores(self, rows):
        self.inserted_composite_rows = list(rows)
        return self.inserted_composite_rows


def _fan_score(reference_id, name, score, rank):
    return {
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
        "pokemon_name": name,
        "source_name": "favoritepokemon",
        "snapshot_id": 2,
        "normalized_score": score,
        "normalized_rank": rank,
        "scoring_version": FAN_SCORING_VERSION,
    }


def _trend_score(reference_id, score, rank):
    return {
        "pokemon_reference_id": reference_id,
        "source_name": "google_trends_search_interest",
        "score_name": RECENT_TREND_SCORE,
        "relative_search_interest_score": score,
        "normalized_rank": rank,
        "primary_snapshot_id": 1,
        "scoring_version": TREND_SCORING_VERSION,
    }


def _trend_source_row(reference_id, name, *, snapshot_id, relative_to_anchor, raw_interest_value):
    return {
        "snapshot_id": snapshot_id,
        "source_name": "google_trends_search_interest",
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
        "pokemon_name": name,
        "query_term": name,
        "geo": "US",
        "timeframe": "today 1-m",
        "window_role": "recent",
        "query_type": "search_term",
        "raw_interest_value": raw_interest_value,
        "anchor_interest_value": 75.0,
        "relative_to_anchor": relative_to_anchor,
        "extraction_confidence": "high",
    }
