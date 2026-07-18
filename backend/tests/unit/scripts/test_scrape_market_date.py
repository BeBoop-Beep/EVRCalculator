"""The scrape market day is America/Phoenix, not the UTC calendar day (Phase 2)."""

from datetime import datetime, timezone

from backend.scripts.run_pokemon_set_scrape import _market_date_iso


def test_just_after_utc_midnight_is_still_the_previous_arizona_day():
    # 2026-07-18 02:00 UTC == 2026-07-17 19:00 America/Phoenix (UTC-7, no DST).
    instant = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    assert _market_date_iso("America/Phoenix", now=instant) == "2026-07-17"


def test_utc_midnight_boundary_matches_incident_5pm_arizona():
    # The incident batch was created at 2026-07-17 00:00 UTC == 17:00 AZ on 07-16.
    instant = datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc)
    assert _market_date_iso("America/Phoenix", now=instant) == "2026-07-16"


def test_arizona_morning_is_the_same_calendar_day():
    instant = datetime(2026, 7, 17, 17, 30, tzinfo=timezone.utc)  # 10:30 AZ
    assert _market_date_iso("America/Phoenix", now=instant) == "2026-07-17"
