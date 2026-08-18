import pytest

from backend.db.services.pokemon_market_index_service import build_index_rows


SETS = [
    {"id": "a", "canonical_key": "a", "release_date": "2026-01-01"},
    {"id": "b", "canonical_key": "b", "release_date": "2026-01-01"},
    {"id": "c", "canonical_key": "c", "release_date": "2026-01-02"},
]


def source(day, set_id, scope, value, count):
    return {"snapshot_date": day, "set_id": set_id, "value_scope": scope, "set_value": value,
            "priced_card_count": count, "source": "canonical", "updated_at": day}


def test_release_gate_completeness_and_independent_top10_authority():
    rows = []
    for scope, values, count in (("standard", {"a": 100, "b": 100}, 20), ("top10", {"a": 60, "b": 60}, 10)):
        rows += [source("2026-01-01", key, scope, value, count) for key, value in values.items()]
    # C enters on day two. Standard is complete, but top10 intentionally lacks C,
    # so only raw may publish that date.
    for scope, values, count in (("standard", {"a": 110, "b": 110, "c": 500}, 20), ("top10", {"a": 66, "b": 66}, 10)):
        rows += [source("2026-01-02", key, scope, value, count) for key, value in values.items()]
    built = build_index_rows(SETS, rows)
    raw = [row for row in built if row["index_key"] == "raw"]
    chase = [row for row in built if row["index_key"] == "top10"]
    assert [row["market_date"] for row in raw] == ["2026-01-01", "2026-01-02"]
    assert raw[-1]["normalized_index_value"] == pytest.approx(110)
    assert raw[-1]["basket_value"] == 720
    assert [row["market_date"] for row in chase] == ["2026-01-01"]


def test_input_order_does_not_change_source_fingerprints():
    rows = [source("2026-01-01", "a", "standard", 100, 20), source("2026-01-01", "b", "standard", 100, 20),
            source("2026-01-01", "a", "top10", 60, 10), source("2026-01-01", "b", "top10", 60, 10)]
    forward = build_index_rows(SETS[:2], rows)
    reverse = build_index_rows(list(reversed(SETS[:2])), list(reversed(rows)))
    assert [(r["index_key"], r["source_generation_fingerprint"]) for r in forward] == [(r["index_key"], r["source_generation_fingerprint"]) for r in reverse]
