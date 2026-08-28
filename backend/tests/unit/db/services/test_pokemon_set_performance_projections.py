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


def test_public_bootstrap_and_paid_signal_boundary_are_separate():
    source = (ROOT / "backend/api/main.py").read_text()
    bootstrap_start = source.index("def get_pokemon_set_market_bootstrap(")
    signals_start = source.index("def get_pokemon_set_market_signals(")
    bootstrap = source[bootstrap_start:signals_start]
    signals = source[signals_start:source.index("\n\n@app.get(", signals_start)]
    assert "filter_set_market_signal_access(payload, None)" in bootstrap
    assert "authorization" not in bootstrap
    assert "has_index_plus_access(plan)" in signals
    assert 'status_code=403' in signals
    assert "get_pokemon_set_market_signals_snapshot_payload" in signals
    assert '"Cache-Control": "no-store"' in signals
