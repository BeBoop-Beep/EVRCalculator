from pathlib import Path

from backend.db.services import pokemon_public_snapshot_service as snapshots


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


def test_consumer_sealed_endpoint_projection_excludes_legacy_contracts():
    source = (ROOT / "backend/api/main.py").read_text()
    start = source.index('def get_pokemon_set_consumer_sealed_market')
    end = source.index('\n\n@app.get(', start)
    endpoint = source[start:end]
    assert "setPageConsumerMarket" in endpoint
    assert "setPageConsumerTopProducts" in endpoint
    assert "payload_json->products" not in endpoint
    assert "payload_json->setMarket" not in endpoint
