"""Regression coverage for compact Set Page reads in the resilient market audit."""

from __future__ import annotations

from backend.scripts import audit_pokemon_market_publication as core
from backend.scripts import audit_pokemon_market_publication_resilient as runtime


DATE = "2026-09-15"


def test_compact_page_loader_preserves_the_fields_the_canonical_audit_reads(monkeypatch):
    calls = []

    def fake_load_rows(client, table, columns, set_ids, *, chunk_size=200, **filters):
        calls.append((table, columns, list(set_ids), chunk_size, filters))
        assert table == runtime._PAGES_TABLE
        assert columns == runtime._PAGES_COMPACT_COLUMNS
        return {
            "set-1": {
                "set_id": "set-1",
                "payload_meta": {"snapshot": {"marketAsOfDate": DATE}},
                "payload_summary": {"setValue": 123.45},
                "payload_set_value": 123.45,
                "title_card_json": {},
                "market_summary_json": {"setValue": 123.45},
                "as_of": DATE,
                "updated_at": f"{DATE}T12:00:00Z",
            }
        }

    monkeypatch.setattr(runtime, "_ORIGINAL_LOAD_ROWS", fake_load_rows)

    rows = runtime._runtime_load_rows(
        object(),
        runtime._PAGES_TABLE,
        runtime._PAGES_HEAVY_COLUMNS,
        ["set-1"],
        chunk_size=200,
    )

    row = rows["set-1"]
    assert core.page_snapshot_generation_date(row) == DATE
    assert core.displayed_set_value(row) == 123.45
    assert row["payload_json"]["meta"]["snapshot"]["marketAsOfDate"] == DATE
    assert row["payload_json"]["summary"]["setValue"] == 123.45
    assert row["payload_json"]["setValue"] == 123.45
    assert calls == [(
        runtime._PAGES_TABLE,
        runtime._PAGES_COMPACT_COLUMNS,
        ["set-1"],
        runtime._PAGES_COMPACT_CHUNK_SIZE,
        {},
    )]


def test_page_loader_caps_the_compact_read_chunk_size(monkeypatch):
    observed = {}

    def fake_load_rows(client, table, columns, set_ids, *, chunk_size=200, **filters):
        observed["chunk_size"] = chunk_size
        observed["columns"] = columns
        return {}

    monkeypatch.setattr(runtime, "_ORIGINAL_LOAD_ROWS", fake_load_rows)

    runtime._runtime_load_rows(
        object(),
        runtime._PAGES_TABLE,
        runtime._PAGES_HEAVY_COLUMNS,
        [f"set-{i}" for i in range(165)],
        chunk_size=200,
    )

    assert observed["chunk_size"] == runtime._PAGES_COMPACT_CHUNK_SIZE
    assert observed["columns"] == runtime._PAGES_COMPACT_COLUMNS
    assert "payload_json,title_card_json" not in observed["columns"]
