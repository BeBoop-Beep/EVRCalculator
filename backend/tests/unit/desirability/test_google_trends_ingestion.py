from __future__ import annotations

from backend.desirability.google_trends import (
    QUERY_TYPE_SEARCH_TERM,
    SOURCE_NAME,
    TrendProviderResponse,
    TrendTimeframe,
    build_anchor_batches,
    fetch_timeframe_rows,
    is_ambiguous_query_term,
)
from backend.desirability.trends_normalization import (
    SEARCH_POPULARITY_SCORE,
    TREND_MOMENTUM_SCORE,
    TREND_SCORING_VERSION,
    calculate_derived_trend_scores,
    normalize_timeframe_rows,
)
from backend.scripts.ingest_pokemon_trends import derive_from_existing_snapshots, run_ingestion


REFERENCES = [
    {"id": 1, "pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur", "generation": 1},
    {"id": 4, "pokedex_number": 4, "canonical_name": "charmander", "display_name": "Charmander", "generation": 1},
    {"id": 25, "pokedex_number": 25, "canonical_name": "pikachu", "display_name": "Pikachu", "generation": 1},
    {"id": 95, "pokedex_number": 95, "canonical_name": "onix", "display_name": "Onix", "generation": 1},
    {"id": 150, "pokedex_number": 150, "canonical_name": "mewtwo", "display_name": "Mewtwo", "generation": 1},
]

EXTENDED_REFERENCES = [
    {
        "id": number,
        "pokedex_number": number,
        "canonical_name": f"pokemon-{number}",
        "display_name": f"Pokemon {number}",
        "generation": 1,
    }
    for number in range(1, 14)
]


class StaticProvider:
    provider_name = "static_test"

    def fetch_interest(self, *, terms, timeframe, geo, query_type):
        values = {"Pikachu": 50.0, "Bulbasaur": 10.0, "Charmander": 20.0, "Onix": 0.0, "Mewtwo": 40.0}
        return TrendProviderResponse(
            status="captured",
            interest_by_term={term: values[term] for term in terms},
            raw_payload={"terms": list(terms), "timeframe": timeframe},
        )


class FlexibleStaticProvider:
    provider_name = "flexible_static_test"

    def fetch_interest(self, *, terms, timeframe, geo, query_type):
        values = {term: float(index + 10) for index, term in enumerate(terms)}
        values["Pikachu"] = 50.0
        return TrendProviderResponse(
            status="captured",
            interest_by_term=values,
            raw_payload={"terms": list(terms), "timeframe": timeframe},
        )


class RateLimitProvider:
    provider_name = "rate_limit_test"

    def __init__(self, captured_batches_before_429=0):
        self.calls = 0
        self.captured_batches_before_429 = captured_batches_before_429

    def fetch_interest(self, *, terms, timeframe, geo, query_type):
        self.calls += 1
        if self.calls <= self.captured_batches_before_429:
            values = {term: 10.0 for term in terms}
            values["Pikachu"] = 50.0
            return TrendProviderResponse(status="captured", interest_by_term=values, raw_payload={"terms": list(terms)})
        return TrendProviderResponse(
            status="rate_limited",
            error="TooManyRequestsError: 429",
            retryable=False,
            error_type="rate_limited_429",
        )


class RecordingRepository:
    def __init__(self, references=None):
        self.created_snapshots = 0
        self.inserted_rows = 0
        self.inserted_scores = 0
        self.updated_statuses = []
        self.references = references or REFERENCES
        self.snapshots = {}
        self.rows_by_snapshot = {}
        self.existing_score_keys = set()
        self.inserted_score_rows = []

    def list_pokemon_references(self):
        return self.references

    def create_trend_snapshot(self, **kwargs):
        self.created_snapshots += 1
        snapshot = {"id": self.created_snapshots, **kwargs}
        self.snapshots[self.created_snapshots] = snapshot
        return snapshot

    def get_trend_snapshot(self, snapshot_id):
        return self.snapshots.get(snapshot_id)

    def update_trend_snapshot_status(self, snapshot_id, status, notes=None):
        self.updated_statuses.append({"snapshot_id": snapshot_id, "status": status, "notes": notes})
        if snapshot_id in self.snapshots:
            self.snapshots[snapshot_id]["status"] = status

    def list_trend_source_rows_for_snapshot(self, snapshot_id):
        return list(self.rows_by_snapshot.get(snapshot_id, []))

    def insert_trend_source_rows(self, rows):
        rows = [dict(row) for row in rows]
        self.inserted_rows += len(rows)
        for row in rows:
            self.rows_by_snapshot.setdefault(row["snapshot_id"], []).append(row)
        return rows

    def insert_trend_scores(self, rows):
        rows = [dict(row) for row in rows]
        self.inserted_scores += len(rows)
        self.inserted_score_rows.extend(rows)
        return rows

    def list_latest_usable_trend_snapshots(self, *, source_name, provider_name, geo, timeframes):
        return {
            snapshot["timeframe"]: snapshot
            for snapshot in self.snapshots.values()
            if snapshot.get("source_name") == source_name
            and snapshot.get("geo") == geo
            and snapshot.get("timeframe") in set(timeframes)
        }

    def list_trend_score_keys(self, *, scoring_version):
        return set(self.existing_score_keys)


def test_build_anchor_batches_uses_anchor_plus_up_to_four_pokemon_terms():
    batches = build_anchor_batches(REFERENCES, anchor_term="Pikachu", batch_size=5)

    assert len(batches) == 1
    assert batches[0].terms == ["Pikachu", "Bulbasaur", "Charmander", "Onix", "Mewtwo"]
    assert all(term != "Pikachu" for term in [pokemon.query_term for pokemon in batches[0].pokemon])


def test_fetch_timeframe_rows_calculates_relative_to_anchor_and_zero_confidence():
    result = fetch_timeframe_rows(
        provider=StaticProvider(),
        references=REFERENCES,
        timeframe=TrendTimeframe("today 12-m", "current", "Search Popularity Score component"),
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
    )

    by_name = {row["pokemon_name"]: row for row in result["rows"]}
    assert by_name["Bulbasaur"]["relative_to_anchor"] == 0.2
    assert by_name["Mewtwo"]["relative_to_anchor"] == 0.8
    assert by_name["Onix"]["raw_interest_value"] == 0.0
    assert by_name["Onix"]["extraction_confidence"] == "low"


def test_normalize_timeframe_rows_scales_relative_interest_to_0_100():
    rows = [
        {"pokemon_reference_id": 1, "pokemon_name": "A", "relative_to_anchor": 1.0, "extraction_confidence": "high"},
        {"pokemon_reference_id": 2, "pokemon_name": "B", "relative_to_anchor": 0.0, "extraction_confidence": "low"},
    ]

    normalized, summary = normalize_timeframe_rows(rows)

    assert normalized[0]["normalized_relative_search_interest_score"] == 100.0
    assert normalized[1]["normalized_relative_search_interest_score"] == 0.0
    assert normalized[1]["confidence"] == "low"
    assert summary["measurement_note"].endswith("not absolute search volume.")


def test_ambiguous_name_flagging_includes_noisy_terms():
    assert is_ambiguous_query_term("Persian") is True
    assert is_ambiguous_query_term("Type: Null") is True
    assert is_ambiguous_query_term("Porygon-Z") is True
    assert is_ambiguous_query_term("Bulbasaur") is False


def test_calculate_derived_scores_keeps_search_popularity_and_momentum_separate():
    normalized_by_timeframe = {
        "today 1-m": [_score(1, "A", "today 1-m", 1.0, 100.0), _score(2, "B", "today 1-m", 0.2, 40.0)],
        "today 12-m": [_score(1, "A", "today 12-m", 0.5, 80.0), _score(2, "B", "today 12-m", 0.2, 40.0)],
        "today 5-y": [_score(1, "A", "today 5-y", 0.25, 60.0), _score(2, "B", "today 5-y", 0.5, 100.0)],
    }

    derived, summary = calculate_derived_trend_scores(normalized_by_timeframe)

    assert summary["search_popularity_scores"] == 2
    assert summary["trend_momentum_scores"] == 2
    assert {row["score_name"] for row in derived} >= {SEARCH_POPULARITY_SCORE, TREND_MOMENTUM_SCORE}
    momentum = [row for row in derived if row["score_name"] == TREND_MOMENTUM_SCORE]
    assert momentum[0]["pokemon_name"] == "A"
    assert momentum[0]["score_components"]["baseline_timeframe"] == "today 5-y"


def test_dry_run_ingestion_does_not_write_database_rows():
    repository = RecordingRepository()

    report = run_ingestion(
        repository=repository,
        provider=StaticProvider(),
        dry_run=True,
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        limit=5,
        timeframes=[
            TrendTimeframe("today 1-m", "recent", "Recent Trend Score component"),
            TrendTimeframe("today 12-m", "current", "Search Popularity Score component"),
            TrendTimeframe("today 5-y", "baseline", "Long-term baseline component"),
        ],
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
    )

    assert report["dry_run"] is True
    assert report["derived_summary"]["search_popularity_scores"] == 5
    assert repository.created_snapshots == 0
    assert repository.inserted_rows == 0
    assert repository.inserted_scores == 0


def test_ingestion_applies_pokedex_range_selection():
    repository = RecordingRepository(references=EXTENDED_REFERENCES)

    report = run_ingestion(
        repository=repository,
        provider=FlexibleStaticProvider(),
        dry_run=True,
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        pokedex_start=4,
        pokedex_end=7,
        timeframes=[TrendTimeframe("today 12-m", "current", "Search Popularity Score component")],
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
    )

    assert report["pokemon_processed"] == 4
    assert report["selection"]["pokedex_start"] == 4
    assert report["selection"]["pokedex_end"] == 7


def test_ingestion_applies_offset_and_limit_after_pokedex_ordering():
    repository = RecordingRepository(references=EXTENDED_REFERENCES)

    report = run_ingestion(
        repository=repository,
        provider=FlexibleStaticProvider(),
        dry_run=True,
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        offset=2,
        limit=4,
        timeframes=[TrendTimeframe("today 12-m", "current", "Search Popularity Score component")],
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
    )

    assert report["pokemon_reference_rows_available"] == 13
    assert report["pokemon_processed"] == 4
    assert report["selection"]["offset"] == 2
    assert report["selection"]["limit"] == 4
    assert report["timeframe_results"][0]["source_rows"] == 4


def test_append_mode_skips_existing_rows_and_inserts_only_missing_rows():
    repository = RecordingRepository(references=EXTENDED_REFERENCES[:5])
    repository.snapshots[10] = {
        "id": 10,
        "source_name": SOURCE_NAME,
        "provider_name": "pytrends",
        "geo": "US",
        "timeframe": "today 1-m",
        "window_role": "recent",
        "query_type": QUERY_TYPE_SEARCH_TERM,
        "anchor_term": "Pikachu",
        "status": "captured_partial",
    }
    repository.rows_by_snapshot[10] = [
        _source_row(1, 1, "Pokemon 1", "today 1-m", snapshot_id=10),
        _source_row(2, 2, "Pokemon 2", "today 1-m", snapshot_id=10),
        _source_row(3, 3, "Pokemon 3", "today 1-m", snapshot_id=10),
    ]

    report = run_ingestion(
        repository=repository,
        provider=FlexibleStaticProvider(),
        dry_run=False,
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        append_to_snapshot_id=10,
        timeframes=[TrendTimeframe("today 1-m", "recent", "Recent Trend Score component")],
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
    )

    assert report["mode"] == "append_to_snapshot"
    assert report["diagnostics"]["existing_rows_skipped"] == 3
    assert report["diagnostics"]["missing_rows_attempted"] == 2
    assert repository.created_snapshots == 0
    assert repository.inserted_rows == 2
    assert {row["pokemon_reference_id"] for row in repository.rows_by_snapshot[10]} == {1, 2, 3, 4, 5}


def test_derive_from_existing_produces_three_score_types_and_skips_duplicates():
    repository = _repository_with_existing_snapshots()
    existing_duplicate = (1, "search_popularity_score", TREND_SCORING_VERSION, (102, 103))
    repository.existing_score_keys.add(existing_duplicate)

    report = derive_from_existing_snapshots(
        repository=repository,
        dry_run=False,
        source_name=SOURCE_NAME,
        provider_name="pytrends",
        geo="US",
    )

    assert report["counts_by_score_name"] == {
        "search_popularity_score": 3,
        "recent_trend_score": 3,
        "trend_momentum_score": 3,
    }
    assert report["duplicates_skipped"] == 1
    assert report["inserted_trend_scores"] == 8


def test_repeated_429_stops_gracefully():
    repository = RecordingRepository(references=EXTENDED_REFERENCES)
    provider = RateLimitProvider()

    report = run_ingestion(
        repository=repository,
        provider=provider,
        dry_run=True,
        geo="US",
        query_type=QUERY_TYPE_SEARCH_TERM,
        anchor_term="Pikachu",
        batch_size=5,
        timeframes=[TrendTimeframe("today 12-m", "current", "Search Popularity Score component")],
        delay_seconds=0,
        max_retries=0,
        retry_backoff_seconds=0,
        stop_after_consecutive_429s=2,
        cooldown_after_429_seconds=0,
    )

    timeframe_result = report["timeframe_results"][0]
    assert report["status"] == "rate_limited_gracefully"
    assert report["rate_limited_batches"] == 2
    assert timeframe_result["stopped_early"] is True
    assert timeframe_result["batches_attempted"] == 2
    assert timeframe_result["batches_planned"] > timeframe_result["batches_attempted"]
    assert provider.calls == 2


def _repository_with_existing_snapshots():
    repository = RecordingRepository(references=EXTENDED_REFERENCES[:3])
    snapshots = {
        101: ("today 1-m", "recent"),
        102: ("today 12-m", "current"),
        103: ("today 5-y", "baseline"),
    }
    for snapshot_id, (timeframe, role) in snapshots.items():
        repository.snapshots[snapshot_id] = {
            "id": snapshot_id,
            "source_name": SOURCE_NAME,
            "provider_name": "pytrends",
            "geo": "US",
            "timeframe": timeframe,
            "window_role": role,
            "query_type": QUERY_TYPE_SEARCH_TERM,
            "anchor_term": "Pikachu",
            "status": "captured_relative_search_interest",
        }
        repository.rows_by_snapshot[snapshot_id] = [
            _source_row(1, 1, "Pokemon 1", timeframe, snapshot_id=snapshot_id, relative=0.5),
            _source_row(2, 2, "Pokemon 2", timeframe, snapshot_id=snapshot_id, relative=0.25),
            _source_row(3, 3, "Pokemon 3", timeframe, snapshot_id=snapshot_id, relative=0.1),
        ]
    return repository


def _score(reference_id, name, timeframe, relative_to_anchor, normalized_score):
    return {
        "pokemon_reference_id": reference_id,
        "pokemon_name": name,
        "query_term": name,
        "source_name": SOURCE_NAME,
        "snapshot_id": 1,
        "timeframe": timeframe,
        "relative_to_anchor": relative_to_anchor,
        "normalized_relative_search_interest_score": normalized_score,
        "confidence": "high",
    }


def _source_row(reference_id, pokedex_number, name, timeframe, *, snapshot_id=1, relative=0.5):
    return {
        "snapshot_id": snapshot_id,
        "source_name": SOURCE_NAME,
        "pokemon_reference_id": reference_id,
        "pokedex_number": pokedex_number,
        "pokemon_name": name,
        "query_term": name,
        "geo": "US",
        "timeframe": timeframe,
        "window_role": "recent" if timeframe == "today 1-m" else "current",
        "query_type": QUERY_TYPE_SEARCH_TERM,
        "anchor_term": "Pikachu",
        "batch_key": "batch",
        "raw_interest_value": relative * 50.0,
        "anchor_interest_value": 50.0,
        "relative_to_anchor": relative,
        "is_ambiguous": False,
        "extraction_confidence": "high",
        "raw_row_json": {},
    }
