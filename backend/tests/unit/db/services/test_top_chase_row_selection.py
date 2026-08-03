"""Top Chase stored-row selection: freshness first, then structural quality.

A row can carry cards and prices while carrying no usable history at all. That
row renders as a full grid of "Awaiting trend" charts, so counting cards is not a
measure of quality — counting cards that can actually draw a line is.
"""

from __future__ import annotations

from backend.db.services.pokemon_public_snapshot_service import (
    _pick_fresher_top_chase_row,
    _score_top_chase_row_quality,
)

DATE = "2026-08-03"
PRIOR = "2026-08-02"


def _row(window, latest_date, *, renderable=True, priced=1):
    cards = []
    histories = {}
    for index in range(priced):
        key = f"v{index}"
        cards.append({"cardVariantId": key, "marketPrice": 10.0})
        histories[key] = (
            [{"date": PRIOR, "marketPrice": 9.0}, {"date": latest_date, "marketPrice": 10.0}]
            if renderable
            else []
        )
    return {
        "window_key": window,
        "latest_market_date": latest_date,
        "top_chase_cards_json": cards,
        "top_chase_card_histories_json": histories,
    }


# --- quality scoring ---------------------------------------------------------
def test_complete_row_scores_as_complete():
    quality = _score_top_chase_row_quality(_row("365d", DATE, priced=3))
    assert quality == {"priced_cards": 3, "renderable_cards": 3, "complete": 1}


def test_row_with_prices_but_no_histories_is_not_complete():
    quality = _score_top_chase_row_quality(_row("30d", DATE, renderable=False, priced=3))
    assert quality["priced_cards"] == 3
    assert quality["renderable_cards"] == 0
    assert quality["complete"] == 0


def test_single_point_history_cannot_draw_a_line():
    row = _row("365d", DATE)
    row["top_chase_card_histories_json"]["v0"] = [{"date": DATE, "marketPrice": 10.0}]
    assert _score_top_chase_row_quality(row)["renderable_cards"] == 0


def test_unpriced_cards_are_not_counted():
    row = _row("365d", DATE)
    row["top_chase_cards_json"][0]["marketPrice"] = 0
    assert _score_top_chase_row_quality(row)["priced_cards"] == 0


# --- selection ---------------------------------------------------------------
def test_fresher_canonical_row_wins():
    chosen, used_fallback, reason = _pick_fresher_top_chase_row(
        _row("30d", PRIOR), _row("365d", DATE)
    )
    assert chosen["window_key"] == "365d"
    assert used_fallback is True
    assert reason == "requested_window_row_stale"


def test_fresher_requested_row_wins_over_stale_canonical():
    chosen, used_fallback, _ = _pick_fresher_top_chase_row(
        _row("30d", DATE), _row("365d", PRIOR)
    )
    assert chosen["window_key"] == "30d"
    assert used_fallback is False


def test_same_date_complete_row_beats_same_date_incomplete_row():
    """The core fix: equal freshness must be broken on structural quality."""
    incomplete_requested = _row("30d", DATE, renderable=False, priced=5)
    complete_canonical = _row("365d", DATE, renderable=True, priced=5)

    chosen, used_fallback, reason = _pick_fresher_top_chase_row(
        incomplete_requested, complete_canonical
    )

    assert chosen["window_key"] == "365d"
    assert used_fallback is True
    assert reason == "requested_window_row_incomplete"


def test_same_date_equally_complete_rows_keep_the_requested_window():
    chosen, used_fallback, reason = _pick_fresher_top_chase_row(
        _row("30d", DATE), _row("365d", DATE)
    )
    assert chosen["window_key"] == "30d"
    assert used_fallback is False
    assert reason is None


def test_complete_requested_row_is_not_replaced_by_incomplete_canonical():
    chosen, used_fallback, _ = _pick_fresher_top_chase_row(
        _row("30d", DATE, renderable=True), _row("365d", DATE, renderable=False)
    )
    assert chosen["window_key"] == "30d"
    assert used_fallback is False


def test_missing_requested_row_falls_back_to_canonical():
    chosen, used_fallback, reason = _pick_fresher_top_chase_row(None, _row("365d", DATE))
    assert chosen["window_key"] == "365d"
    assert used_fallback is True
    assert reason == "missing_requested_window_row"


def test_both_rows_missing_returns_nothing():
    assert _pick_fresher_top_chase_row(None, None) == (None, False, None)
