"""Build and atomically publish canonical Explorer options outside web requests."""
from __future__ import annotations

import argparse
import json
import time

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_options_snapshot import publish_market_explorer_options_snapshot
from backend.db.services.pokemon_market_explorer_query_service import build_market_explorer_filter_options


def run_publication(client):
    started = time.perf_counter()
    payload = build_market_explorer_filter_options(client)
    built_ms = round((time.perf_counter() - started) * 1000, 1)
    publish_started = time.perf_counter()
    receipt = publish_market_explorer_options_snapshot(client, payload)
    return {**receipt, "buildMs": built_ms,
            "publishMs": round((time.perf_counter() - publish_started) * 1000, 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_publication(create_service_role_client()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
