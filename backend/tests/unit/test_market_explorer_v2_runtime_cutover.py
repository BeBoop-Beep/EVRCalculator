from __future__ import annotations

import ast
from pathlib import Path


RUNTIME_FILES = (
    "backend/db/services/pokemon_market_explorer_query_service.py",
    "backend/db/services/market_explorer_constituent_movement.py",
    "backend/scripts/publish_market_explorer_daily_projection.py",
    "backend/scripts/run_market_explorer_daily_publication.py",
    "backend/scripts/check_market_explorer_maintained_cache_health.py",
    "backend/scripts/backfill_market_explorer_variant_intervals.py",
)

RETIRED_V1_RELATIONS = {
    "pokemon_market_explorer_card_daily_states",
    "pokemon_market_explorer_card_daily_coverage",
    "pokemon_card_variant_market_price_intervals",
}

RETIRED_V1_RUNTIME_TOKENS = {
    "V1_DAILY_PROJECTION_RPC",
    "v1_daily",
    "materialized_hybrid",
    "reproject_pokemon_market_explorer_card_daily_states",
}


def _literal_strings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_active_market_explorer_runtime_cannot_reference_retired_v1_storage():
    repo_root = Path(__file__).resolve().parents[3]
    failures: list[str] = []

    for relative in RUNTIME_FILES:
        path = repo_root / relative
        source = path.read_text(encoding="utf-8")
        literals = _literal_strings(path)

        for relation in RETIRED_V1_RELATIONS:
            if relation in literals:
                failures.append(f"{relative}: exact retired relation literal {relation}")

        for token in RETIRED_V1_RUNTIME_TOKENS:
            if token in source:
                failures.append(f"{relative}: retired runtime token {token}")

    assert failures == []
