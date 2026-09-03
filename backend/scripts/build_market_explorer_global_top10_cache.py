"""Global Top 10 maintained-cache build only (All Raw already succeeded)."""
import json
from backend.scripts.build_market_explorer_global_maintained_caches import build_one, create_service_role_client
from backend.domain.pokemon.market_explorer_query import normalize_query_spec

def main():
    control = create_service_role_client()
    spec = normalize_query_spec(mode="chase", asset="cards", era_ids=[], set_ids=[], top_n=10)
    result = build_one(control, "global_top10", spec)
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()
