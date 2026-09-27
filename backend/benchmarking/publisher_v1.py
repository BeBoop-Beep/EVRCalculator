"""Write boundary for the already-validated RIP Benchmark V1 candidate."""
from __future__ import annotations
from typing import Any, Mapping

from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError


def publish_candidate(client: Any, candidate: Mapping[str, Any]) -> dict[str, Any]:
    request = candidate["publish_rpc_request"]
    header = request["arguments"]["p_header"]
    current = list(client.table("pokemon_rip_benchmark_publications_v1").select("id")
                   .eq("benchmark_key", header["benchmark_key"])
                   .eq("calibration_version", header["calibration_version"])
                   .eq("market_date", header["market_date"])
                   .eq("publication_status", "published").limit(1).execute().data or [])
    arguments = dict(request["arguments"])
    arguments["p_expected_previous_id"] = current[0]["id"] if current else None
    response = client.rpc(request["rpc"], arguments).execute()
    publication_id = response.data
    if isinstance(publication_id, list): publication_id = publication_id[0] if publication_id else None
    if not publication_id: raise BenchmarkError("benchmark publication RPC returned no publication id")
    return {"status": "published", "publication_id": str(publication_id),
            "market_date": candidate["market_date"], "entity_count": candidate["expected_entity_count"],
            "row_count": candidate["expected_row_count"]}
