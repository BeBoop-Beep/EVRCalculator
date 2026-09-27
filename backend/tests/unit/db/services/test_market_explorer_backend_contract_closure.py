from types import SimpleNamespace

import pytest

from backend.db.services.market_explorer_prepared_directory import (
    PREPARED_SCREEN_KEYS,
    PreparedSurfaceValidationError,
    read_prepared_comparison_bundle,
    read_prepared_screen,
)
from backend.db.services.market_explorer_surface_v2 import (
    GenerationMismatch,
    normalize_directory_row,
    read_v2_comparison_bundle,
)


class Result:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class V1Client:
    def __init__(self, markets=None, history=None, screens=None):
        self.markets = markets or []
        self.history = history or []
        self.screens = screens or []

    def rpc(self, name, params):
        if "comparison" in name:
            return Result(self.markets)
        if "history" in name:
            return Result(self.history)
        if "screen" in name:
            return Result(self.screens)
        raise AssertionError(name)


class AliasTable:
    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class V2Client:
    def __init__(self, history):
        self.history = history

    def table(self, _):
        return AliasTable()

    def rpc(self, name, _):
        if "history" in name:
            return Result(self.history)
        raise AssertionError(name)


def v1_market(key, as_of="2026-09-25", generation="g1"):
    return {"market_key": key, "comparison_as_of": as_of, "generation_id": generation, "metadata": {}}


def v2_row(key, *, asset="sealed", scope="quick", as_of="2026-09-25", generation="g1"):
    return normalize_directory_row({
        "market_key": key, "label": key, "asset": asset, "scope_kind": scope,
        "generation_id": generation, "comparison_as_of": as_of,
        "source_as_of": as_of, "history_end_date": as_of,
        "availability": "available", "metadata": {"family": "test"},
    })


def test_v1_comparison_publishes_surface_and_rejects_mixed_watermarks_and_future_history():
    ok = read_prepared_comparison_bundle(
        V1Client([v1_market("a"), v1_market("b")], [{"market_key": "a", "market_date": "2026-09-25"}]),
        ["a", "b"],
    )
    assert ok["surface"] == {"version": "v1", "generationId": "g1", "comparisonAsOf": "2026-09-25"}
    with pytest.raises(PreparedSurfaceValidationError, match="PREPARED_COMPARISON_WATERMARK_MISMATCH"):
        read_prepared_comparison_bundle(V1Client([v1_market("a"), v1_market("b", "2026-09-24")]), ["a", "b"])
    with pytest.raises(PreparedSurfaceValidationError, match="PREPARED_COMPARISON_HISTORY_AFTER_WATERMARK"):
        read_prepared_comparison_bundle(
            V1Client([v1_market("a")], [{"market_key": "a", "market_date": "2026-09-26"}]), ["a"],
        )


def test_v2_quick_rows_are_generic_and_keep_asset_taxonomy_metadata_and_history():
    directory = [v2_row("sealed-quick:obtainable"), v2_row("sealed-quick:global-top10")]
    history = [
        {"generation_id": "g1", "market_key": row["market_key"], "market_date": "2026-09-25", "index_value": 100}
        for row in directory
    ]
    bundle = read_v2_comparison_bundle(V2Client(history), directory, [row["market_key"] for row in directory])
    assert [row["market_key"] for row in bundle["markets"]] == ["sealed-quick:obtainable", "sealed-quick:global-top10"]
    assert all(row["asset"] == "sealed" and row["scope_kind"] == "quick" for row in bundle["markets"])
    assert bundle["surface"]["comparisonAsOf"] == "2026-09-25"


def test_v2_rejects_mixed_watermarks_mixed_generation_and_history_after_watermark():
    with pytest.raises(PreparedSurfaceValidationError, match="PREPARED_COMPARISON_WATERMARK_MISMATCH"):
        read_v2_comparison_bundle(
            V2Client([]), [v2_row("a"), v2_row("b", as_of="2026-09-24")], ["a", "b"],
        )
    with pytest.raises(GenerationMismatch):
        read_v2_comparison_bundle(
            V2Client([]), [v2_row("a"), v2_row("b", generation="g2")], ["a", "b"],
        )
    with pytest.raises(PreparedSurfaceValidationError, match="PREPARED_COMPARISON_HISTORY_AFTER_WATERMARK"):
        read_v2_comparison_bundle(
            V2Client([{"generation_id": "g1", "market_key": "a", "market_date": "2026-09-26", "index_value": 101}]),
            [v2_row("a")], ["a"],
        )


def test_screen_registry_and_normalization_cover_existing_top_and_worst_keys():
    assert PREPARED_SCREEN_KEYS == {
        "rarity-leaders", "sealed-format-leaders", "momentum-leaders", "largest-drawdowns",
        "top-performers", "worst-performers",
    }
    rows = [{
        "rank": 1, "market_key": "set:fossil", "label": "Fossil", "asset": "cards",
        "market_type": "set", "metric_value": 3.5, "comparison_as_of": "2026-09-25",
        "generation_id": "g1", "generated_at": "2026-09-26T00:00:00Z",
        "relative_era_pct": 1.2, "private_rank_score": 999,
    }]
    for screen in PREPARED_SCREEN_KEYS:
        assert read_prepared_screen(V1Client(screens=rows), screen, None, 25)[0]["market_key"] == "set:fossil"
    assert "private_rank_score" not in read_prepared_screen(V1Client(screens=rows), "top-performers", "cards", 10)[0]
    with pytest.raises(ValueError):
        read_prepared_screen(V1Client(), "not-a-screen", None, 10)
    with pytest.raises(ValueError):
        read_prepared_screen(V1Client(), "top-performers", "graded", 10)
    with pytest.raises(ValueError):
        read_prepared_screen(V1Client(), "top-performers", None, 26)


@pytest.mark.parametrize("field,code", [
    ("generation_id", "PREPARED_SCREEN_GENERATION_MISMATCH"),
    ("comparison_as_of", "PREPARED_SCREEN_WATERMARK_MISMATCH"),
])
def test_screen_rows_fail_closed_when_authority_is_mixed(field, code):
    rows = [
        {"rank": 1, "market_key": "a", "generation_id": "g1", "comparison_as_of": "2026-09-25"},
        {"rank": 2, "market_key": "b", "generation_id": "g1", "comparison_as_of": "2026-09-25"},
    ]
    rows[1][field] = "different"
    with pytest.raises(PreparedSurfaceValidationError, match=code):
        read_prepared_screen(V1Client(screens=rows), "worst-performers", "sealed", 25)
