from datetime import datetime, timezone

import backend.alerts.dispatcher as dispatcher


def test_parse_timestamp_accepts_postgres_five_digit_fractional_seconds():
    parsed = dispatcher._parse_timestamp("2026-09-14T21:02:39.75468+00:00")
    assert parsed == datetime(2026, 9, 14, 21, 2, 39, 754680, tzinfo=timezone.utc)


def test_formatter_accepts_postgres_five_digit_fractional_seconds():
    result = dispatcher.format_slack_message(
        {
            "severity": "critical",
            "alert_type": "pokemon_market_audit_failed",
            "title": "Post-scrape Market audit FAIL",
            "message": "publication surface read failed",
            "created_at": "2026-09-14T21:02:39.75468+00:00",
            "payload": {"market_date": "2026-09-14"},
        }
    )

    expected = datetime(2026, 9, 14, 21, 2, 39, 754680, tzinfo=timezone.utc)
    assert result["attachments"][0]["ts"] == int(expected.timestamp())


def test_formatter_falls_back_safely_for_malformed_timestamp():
    before = int(datetime.now(timezone.utc).timestamp())
    result = dispatcher.format_slack_message(
        {
            "severity": "error",
            "alert_type": "x",
            "title": "x",
            "message": "x",
            "created_at": "not-a-timestamp",
            "payload": {},
        }
    )
    after = int(datetime.now(timezone.utc).timestamp())

    assert before <= result["attachments"][0]["ts"] <= after
