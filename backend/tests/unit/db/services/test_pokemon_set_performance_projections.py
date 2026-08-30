from pathlib import Path
import pytest

from backend.db.services import pokemon_public_snapshot_service as snapshots
from backend.db.services import pokemon_set_route_directory_service as directory


ROOT = Path(__file__).resolve().parents[5]


def test_market_bootstrap_projection_never_selects_full_dashboard_payload():
    columns = snapshots._MARKET_BOOTSTRAP_COLUMNS
    assert "payload_json->cardsMarket" in columns
    assert "set_value_histories_json->standard" in columns
    assert "set_value_histories_json->top10" in columns
    assert "top_chase_cards_json" in columns
    assert "top_chase_card_histories_json" not in columns
    assert "performance_vs_cost_history_json" not in columns
    assert ",payload_json," not in f",{columns},"


def test_route_directory_rpc_projects_published_targets_inside_postgres():
    sql = (ROOT / "backend/db/migrations/20260828014500_create_pokemon_set_route_directory_rpc.sql").read_text()
    assert "jsonb_array_elements(ranking_payload_json -> 'targets') with ordinality" in sql
    assert "order by p.ordinal" in sql
    assert "grant execute" in sql and "service_role" in sql
    assert "security invoker" in sql
    assert "from anon, authenticated" in sql


def test_route_directory_has_no_noncanonical_relational_fallback():
    source = (ROOT / "backend/db/services/pokemon_set_route_directory_service.py").read_text()
    assert 'table("explore_rip_statistics_latest")' not in source
    assert "temporarily unavailable" in source


def test_route_directory_rpc_failure_is_retryable_error_not_reordered_fallback(monkeypatch):
    class FailedRpc:
        def execute(self):
            raise TimeoutError("forced transport failure")

    class Client:
        def rpc(self, *_args, **_kwargs):
            return FailedRpc()

    monkeypatch.setattr(directory, "service_read_client", Client())
    monkeypatch.setattr(directory, "run_public_read_with_retry", lambda *_args, **_kwargs: FailedRpc().execute())
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        directory.get_pokemon_set_route_directory_payload()


def test_consumer_sealed_endpoint_projection_excludes_legacy_contracts():
    source = (ROOT / "backend/api/main.py").read_text()
    start = source.index('def get_pokemon_set_consumer_sealed_market')
    end = source.index('\n\n@app.get(', start)
    endpoint = source[start:end]
    assert "setPageConsumerMarket" in endpoint
    assert "setPageConsumerTopProducts" in endpoint
    assert "payload_json->products" not in endpoint
    assert "payload_json->setMarket" not in endpoint


def test_market_bootstrap_does_not_publish_summary_top10_as_history():
    source = (ROOT / "backend/db/services/pokemon_public_snapshot_service.py").read_text()
    start = source.index("def get_pokemon_set_market_bootstrap_snapshot_payload")
    end = source.index("\ndef ", start + 10)
    builder = source[start:end]
    assert '"setValueHistoriesByScope": {"standard": standard}' in builder
    assert '"chaseConcentration"' in builder


def test_bootstrap_projects_optional_paid_breadth_server_side():
    source = (ROOT / "backend/api/main.py").read_text()
    bootstrap_start = source.index("def get_pokemon_set_market_bootstrap(")
    signals_start = source.index("def get_pokemon_set_market_signals(")
    bootstrap = source[bootstrap_start:signals_start]
    signals = source[signals_start:source.index("\n\n@app.get(", signals_start)]
    assert "_resolve_index_plan(authorization, token_cookie)" in bootstrap
    assert "filter_set_market_signal_access(payload, plan)" in bootstrap
    assert '"Cache-Control": "private, no-store"' in bootstrap
    assert "_require_index_feature(" in signals
    assert "get_pokemon_set_market_signals_snapshot_payload" in signals
    assert '"Cache-Control": "no-store"' in signals


def test_market_bootstrap_embeds_compact_chase_preview_without_histories():
    source = (ROOT / "backend/db/services/pokemon_public_snapshot_service.py").read_text()
    start = source.index("def get_pokemon_set_market_bootstrap_snapshot_payload")
    end = source.index("\ndef ", start + 10)
    builder = source[start:end]
    assert '"topChaseCards": _compact_top_chase_preview' in builder
    assert "top_chase_card_histories_json" not in builder
    assert '"topChasePreviewOnly": True' in builder


def test_market_signals_projection_is_breadth_only():
    columns = snapshots._MARKET_SIGNALS_COLUMNS
    assert "payload_json->cardsMarket->marketBreadth" in columns
    for forbidden in (
        "set_value_histories_json",
        "performance_vs_cost_history_json",
        "available_scopes_json",
        "top_chase_cards_json",
        "top_chase_card_histories_json",
        "payload_json->cardsMarket,",
        ",payload_json,",
    ):
        assert forbidden not in f",{columns},"


def test_market_signals_reader_uses_bounded_retry_and_returns_prepared_breadth(monkeypatch):
    breadth = {"7D": {"available": True, "advancing": 9, "declining": 4}}
    captured = {}

    class Result:
        data = [{"set_id": "75cd439d-aaa2-41cb-86f3-2fefa5b26e29", "window_key": "365d", "latest_market_date": "2026-08-27", "updated_at": "2026-08-28T00:00:00Z", "marketBreadth": breadth}]

    class Query:
        def select(self, columns): captured["columns"] = columns; return self
        def eq(self, *_args): return self
        def limit(self, *_args): return self
        def execute(self): return Result()

    class Client:
        def table(self, name): captured["table"] = name; return Query()

    client = Client()
    monkeypatch.setattr(snapshots, "service_read_client", client)

    def retry(operation, **kwargs):
        captured.update(kwargs)
        return operation(client)

    monkeypatch.setattr(snapshots, "run_public_read_with_retry", retry)
    payload = snapshots.get_pokemon_set_market_signals_snapshot_payload("75cd439d-aaa2-41cb-86f3-2fefa5b26e29")
    assert payload["marketBreadth"] == breadth
    assert captured["columns"] == snapshots._MARKET_SIGNALS_COLUMNS
    assert captured["operation_name"] == "pokemon_set_market_signals"
    assert captured["initial_client"] is client


@pytest.mark.parametrize(
    ("rows", "status", "code"),
    [
        ([], 404, "POKEMON_SET_MARKET_SIGNALS_UNAVAILABLE"),
        ([{"marketBreadth": None}], 503, "POKEMON_SET_MARKET_SIGNALS_SNAPSHOT_INCOMPLETE"),
    ],
)
def test_market_signals_missing_and_incomplete_contracts(monkeypatch, rows, status, code):
    class Result:
        data = rows

    monkeypatch.setattr(snapshots, "run_public_read_with_retry", lambda *_args, **_kwargs: Result())
    with pytest.raises(snapshots.PokemonSetMarketError) as exc:
        snapshots.get_pokemon_set_market_signals_snapshot_payload("75cd439d-aaa2-41cb-86f3-2fefa5b26e29")
    assert exc.value.status_code == status
    assert exc.value.code == code
