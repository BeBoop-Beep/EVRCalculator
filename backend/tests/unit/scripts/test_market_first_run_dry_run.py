from types import SimpleNamespace

from backend.db.services.pokemon_market_index_service import build_index_rows
from backend.scripts import build_pokemon_explore_set_value_snapshot as builder


def test_first_run_dry_run_uses_in_memory_index_and_performs_zero_writes(monkeypatch):
    day = "2026-08-17"
    sets = [{"id": "set-a", "canonical_key": "a", "name": "Alpha", "supports_opening_simulation": True}]
    source = [{"set_id": "set-a", "snapshot_date": day, "value_scope": "standard", "set_value": 100,
               "priced_card_count": 20, "source": "canonical", "updated_at": day},
              {"set_id": "set-a", "snapshot_date": day, "value_scope": "top10", "set_value": 60,
               "priced_card_count": 10, "source": "canonical", "updated_at": day}]
    index_history = build_index_rows(sets, source)
    canonical = {"set-a": [{"set_id": "set-a", "snapshot_date": day, "set_value": 100}]}
    dashboard = {"set_id": "set-a", "window_key": "365d", "latest_market_date": day,
                 "set_value_histories_json": {"standard": [{"date": day, "setValue": 100}]}}
    monkeypatch.setattr(builder, "_load_sets", lambda _client: sets)
    monkeypatch.setattr(builder, "_load_canonical_histories", lambda _client, _ids: canonical)
    monkeypatch.setattr(builder, "upsert_explore_set_value_snapshot", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write")))
    class Query:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def execute(self): return SimpleNamespace(data=[dashboard])
    class Client:
        def table(self, name):
            assert name != "pokemon_market_index_daily_history", "empty persisted index must not be read"
            return Query()
    row = builder.build(client=Client(), market_date=day, commit=False, market_index_history=index_history)
    assert row["payload_json"]["marketOverview"]["marketDate"] == day
    assert row["payload_json"]["marketOverview"]["raw"]["indexValue"] == 100


def test_commit_candidate_reads_authoritative_persisted_index_when_not_injected(monkeypatch):
    day = "2026-08-17"; sets = [{"id": "set-a", "canonical_key": "a", "name": "Alpha", "supports_opening_simulation": True}]
    source = [{"set_id": "set-a", "snapshot_date": day, "value_scope": scope, "set_value": value,
               "priced_card_count": count, "source": "canonical", "updated_at": day}
              for scope, value, count in (("standard", 100, 20), ("top10", 60, 10))]
    history = build_index_rows(sets, source); reads = []
    monkeypatch.setattr(builder, "_load_sets", lambda _client: sets)
    monkeypatch.setattr(builder, "_load_canonical_histories", lambda *_a: {"set-a": [{"set_id": "set-a", "snapshot_date": day, "set_value": 100}]})
    monkeypatch.setattr(builder, "read_index_history", lambda *_a, **_k: reads.append(True) or history)
    class Query:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def in_(self, *_a): return self
        def execute(self): return SimpleNamespace(data=[{"set_id": "set-a", "window_key": "365d", "latest_market_date": day,
            "set_value_histories_json": {"standard": [{"date": day, "setValue": 100}]}}])
    class Client:
        def table(self, _name): return Query()
    builder.build(client=Client(), market_date=day, commit=False)
    assert reads == [True]
