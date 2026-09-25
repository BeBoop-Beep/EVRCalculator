from backend.db.services import canonical_market_overview as overview


def _patch_common(monkeypatch, captured):
    monkeypatch.setattr(overview, "read_global_sealed_source_snapshots", lambda *_a, **_k: [])
    monkeypatch.setattr(overview, "build_global_sealed_market", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(overview, "build_global_sealed_segments", lambda *_a, **_k: {"segments": {}})

    def fake_build_market_overview(history, *, market_date, sealed_market, sealed_segments, card_segments):
        captured["card_segments"] = card_segments
        return {
            "raw": {"basketValue": 123.45},
            "cardSegments": card_segments,
            "marketDate": market_date,
        }

    monkeypatch.setattr(overview, "build_market_overview", fake_build_market_overview)


def test_critical_overview_can_defer_expensive_card_segments(monkeypatch):
    captured = {}
    _patch_common(monkeypatch, captured)

    def forbidden(*_a, **_k):
        raise AssertionError("expensive global card constituent history must not run")

    monkeypatch.setattr(overview, "expand_raw_card_member_set_ids", forbidden)
    monkeypatch.setattr(overview, "read_canonical_card_rarities", forbidden)
    monkeypatch.setattr(overview, "load_global_card_constituent_rows", forbidden)
    monkeypatch.setattr(overview, "build_global_card_segments", forbidden)

    result = overview.build_canonical_market_overview(
        object(),
        market_date="2026-09-24",
        history=[{"market_date": "2026-09-24", "index_key": "raw"}],
        set_ids=["set-1"],
        include_card_segments=False,
    )

    raw = captured["card_segments"]["raw"]
    assert raw["available"] is False
    assert raw["unavailableReason"] == "no card constituent history"
    assert raw["reconciliation"]["parentBasketValue"] == 123.45
    assert result["marketDate"] == "2026-09-24"


def test_full_overview_mode_still_builds_card_segments(monkeypatch):
    captured = {}
    _patch_common(monkeypatch, captured)
    calls = []

    monkeypatch.setattr(overview, "expand_raw_card_member_set_ids", lambda *_a, **_k: ["child-1"])
    monkeypatch.setattr(overview, "read_canonical_card_rarities", lambda *_a, **_k: {"card-1": {}})

    def load_rows(*_a, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(overview, "load_global_card_constituent_rows", load_rows)
    monkeypatch.setattr(
        overview,
        "build_global_card_segments",
        lambda *_a, **_k: {
            "segments": {},
            "definitions": {},
            "available": True,
            "reconciliation": {},
        },
    )

    overview.build_canonical_market_overview(
        object(),
        market_date="2026-09-24",
        history=[{"market_date": "2026-09-01", "index_key": "raw"}],
        set_ids=["set-1"],
    )

    assert calls == [{"start_date": "2026-09-01", "end_date": "2026-09-24"}]
    assert captured["card_segments"]["raw"]["available"] is True
