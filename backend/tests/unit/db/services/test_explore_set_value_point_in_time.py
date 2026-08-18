"""Point-in-time regressions for the global Market Set Value snapshot build.

A promoted build for 2026-08-17 loaded canonical rows with no upper bound, so
once 2026-08-18 observations landed every set was rejected as stale
(canonicalDate=2026-08-18 vs dashboardDate=2026-08-17). A snapshot for D must
only consume canonical observations with snapshot_date <= D, while STILL
requiring an exact observation on D.
"""

import pytest

from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    build_global_set_value_row,
)
from backend.scripts.build_pokemon_explore_set_value_snapshot import _load_canonical_histories

TARGET = "2026-08-17"
FUTURE = "2026-08-18"
SET_ID = "set-1"


def _canonical(dates):
    return [
        {"set_id": SET_ID, "snapshot_date": day, "set_value": 100.0 + index}
        for index, day in enumerate(dates)
    ]


def _prepared(rows):
    return [{"date": row["snapshot_date"], "setValue": row["set_value"]} for row in rows]


def _pokemon_set():
    return {"id": SET_ID, "canonical_key": "alpha", "name": "Alpha", "logo_image_url": "logo"}


def _dashboard(prepared_rows, latest=TARGET):
    return [{
        "set_id": SET_ID, "window_key": "365d", "latest_market_date": latest,
        "set_value_histories_json": {"standard": prepared_rows},
    }]


def _row(canonical_rows, prepared_rows, *, target=TARGET, latest=TARGET):
    return build_global_set_value_row(
        [_pokemon_set()], _dashboard(prepared_rows, latest), {SET_ID: canonical_rows},
        target_market_date=target,
    )


# --- CASE A: a future canonical row must not poison a historical build ------ #
def test_case_a_future_canonical_row_does_not_poison_historical_build():
    canonical = _canonical(["2026-08-15", "2026-08-16", TARGET, FUTURE])
    through_target = [row for row in canonical if row["snapshot_date"] <= TARGET]
    result = _row(canonical, _prepared(through_target))

    published = result["payload_json"]["sets"][0]
    assert result["_diagnostics"]["staleSets"] == []
    assert published["setValueAsOf"] == TARGET
    assert published["currentSetValue"] == through_target[-1]["set_value"]
    assert published["historyEndDate"] == TARGET
    assert FUTURE not in [point[0] for point in published["trend"]]
    assert published["historyPointCount"] == 3


def test_case_a_future_row_does_not_change_the_generation_fingerprint():
    """A build for D must be identical whether or not D+1 data has landed yet."""
    through_target = _canonical(["2026-08-15", "2026-08-16", TARGET])
    with_future = through_target + _canonical([FUTURE])[:1]
    with_future[-1] = {"set_id": SET_ID, "snapshot_date": FUTURE, "set_value": 999.0}
    prepared_rows = _prepared(through_target)
    assert (_row(through_target, prepared_rows)["source_generation_fingerprint"]
            == _row(with_future, prepared_rows)["source_generation_fingerprint"])


# --- CASE B: the exact target date is still required ----------------------- #
def test_case_b_missing_target_date_still_blocks_and_never_substitutes_earlier():
    """08-16 + 08-18 present, 08-17 absent -> must NOT fall back to 08-16."""
    canonical = _canonical(["2026-08-16", FUTURE])
    prepared_rows = [{"date": TARGET, "setValue": 100.0}]
    with pytest.raises(ExploreSetValueUnavailable):
        _row(canonical, prepared_rows)


def test_case_b_diagnostics_report_the_clamped_date_not_the_future_one():
    canonical = _canonical(["2026-08-16", FUTURE])
    prepared_rows = [{"date": TARGET, "setValue": 100.0}]
    try:
        _row(canonical, prepared_rows)
    except ExploreSetValueUnavailable as exc:
        stale = exc.diagnostics.get("staleSets") or []
        assert stale and stale[0]["canonicalDate"] == "2026-08-16"


# --- CASE C: a current-date build is unaffected ---------------------------- #
def test_case_c_current_date_build_still_works():
    canonical = _canonical(["2026-08-16", TARGET, FUTURE])
    result = _row(canonical, _prepared(canonical), target=FUTURE, latest=FUTURE)
    published = result["payload_json"]["sets"][0]
    assert published["setValueAsOf"] == FUTURE
    assert published["historyEndDate"] == FUTURE
    assert result["market_date"] == FUTURE


# --------------------------------------------------------------------------- #
# CASE D/E: the loader bounds the query server-side and still pages correctly.
# --------------------------------------------------------------------------- #
class _RecordingQuery:
    def __init__(self, rows, recorder):
        self._rows = rows
        self._rec = recorder
        self._range = None

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def lte(self, column, value):
        self._rec.setdefault("lte", []).append((column, value))
        self._rows = [row for row in self._rows if str(row["snapshot_date"]) <= str(value)]
        return self

    def order(self, column, desc=False):
        self._rec.setdefault("order", []).append((column, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = sorted(self._rows, key=lambda row: (row["snapshot_date"], row["set_id"]))
        start, end = self._range
        self._rec.setdefault("pages", []).append((start, end))

        class _R:
            data = rows[start:end + 1]
        return _R()


class _RecordingClient:
    def __init__(self, rows):
        self.rows = rows
        self.recorder = {}

    def table(self, _name):
        return _RecordingQuery(list(self.rows), self.recorder)


def test_case_d_loader_applies_the_server_side_upper_bound():
    client = _RecordingClient(_canonical(["2026-08-16", TARGET, FUTURE]))
    grouped = _load_canonical_histories(client, [SET_ID], through_date=TARGET)

    assert ("snapshot_date", TARGET) in client.recorder["lte"]
    dates = [row["snapshot_date"] for row in grouped[SET_ID]]
    assert dates == ["2026-08-16", TARGET]
    assert FUTURE not in dates


def test_case_d_loader_preserves_scope_and_stable_ordering():
    client = _RecordingClient(_canonical([TARGET]))
    _load_canonical_histories(client, [SET_ID], through_date=TARGET)
    assert client.recorder["order"] == [("snapshot_date", False), ("set_id", False)]


def test_case_e_pagination_remains_stable_under_the_date_bound():
    days = [f"2026-{month:02d}-{day:02d}" for month in (1, 2, 3, 4) for day in range(1, 29)]
    rows = []
    for set_index in range(12):
        for day in days:
            rows.append({"set_id": f"set-{set_index}", "snapshot_date": day, "set_value": 1.0})
    rows.append({"set_id": "set-0", "snapshot_date": "2026-12-31", "set_value": 999.0})
    assert len(rows) > 1000

    client = _RecordingClient(rows)
    grouped = _load_canonical_histories(client, [f"set-{i}" for i in range(12)], through_date="2026-04-28")

    assert len(client.recorder["pages"]) > 1, "expected more than one page"
    assert sum(len(values) for values in grouped.values()) == len(days) * 12
    assert "2026-12-31" not in [row["snapshot_date"] for row in grouped["set-0"]]
