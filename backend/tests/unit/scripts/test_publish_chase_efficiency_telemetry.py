from backend.scripts import publish_chase_efficiency as publisher


def test_timeout_report_contains_safe_bounded_telemetry(monkeypatch):
    candidate = {
        "snapshot": {"market_date": "2026-08-27", "eligible_cohort_count": 1},
        "rows": [{"card_variant_id": "v1"}],
        "excluded": [],
    }
    monkeypatch.setattr(publisher, "load_candidate", lambda client, market_date, telemetry: candidate)
    monkeypatch.setattr(publisher, "validate_candidate", lambda value: [])

    class DatabaseTimeout(Exception):
        code = "57014"

    monkeypatch.setattr(publisher, "publish_candidate", lambda client, value, telemetry: (_ for _ in ()).throw(DatabaseTimeout("statement timeout")))
    code, report = publisher.run(market_date="2026-08-27", commit=True, client=object())

    assert code == 1
    assert report["publicationError"]["databaseCode"] == "57014"
    assert report["publicationError"]["candidateRowCount"] == 1
    assert report["publicationError"]["payloadBytes"] > 0
    assert "p_rows" not in report["publicationError"]
    assert report["telemetry"]["totalSeconds"] >= report["telemetry"]["rpcPublicationSeconds"]
