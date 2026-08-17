from __future__ import annotations

from typing import Any

from backend.db.services.pack_outcome_artifact_service import (
    PackOutcomeArtifactUnavailable,
    load_pack_outcomes,
)
from backend.db.services.sealed_product_rip_service import run_stage1_sealed_product_rip


def replay_sealed_products_for_run(client: Any, calculation_run_id: Any, *, scorer=run_stage1_sealed_product_rip) -> dict[str, Any]:
    """Replay sealed-product scoring from the run's exact empirical pack vector."""
    run_id = str(calculation_run_id)
    response = (
        client.table("calculation_runs")
        .select("id,target_type,target_id,calculation_config_id")
        .eq("id", run_id).limit(1).execute()
    )
    rows = response.data if response and response.data else []
    if not rows:
        raise ValueError(f"unknown calculation run: {run_id}")
    run = rows[0]
    if run.get("target_type") != "set":
        raise ValueError(f"calculation run {run_id} is not a set run")
    try:
        vector = load_pack_outcomes(client, run_id)
    except PackOutcomeArtifactUnavailable as exc:
        return {"status": "unavailable", "reason": "exact_pack_outcome_artifact_unavailable",
                "calculation_run_id": run_id, "detail": str(exc)}

    set_response = client.table("sets").select("id,canonical_key").eq("id", str(run["target_id"])).limit(1).execute()
    set_rows = set_response.data if set_response and set_response.data else []
    if not set_rows:
        raise ValueError(f"calculation run {run_id} references an unknown set")
    config_response = (
        client.table("calculation_configs").select("config_hash")
        .eq("id", str(run["calculation_config_id"])).limit(1).execute()
    )
    config_rows = config_response.data if config_response and config_response.data else []
    if not config_rows:
        raise ValueError(f"calculation run {run_id} references an unknown calculation config")
    return scorer(
        sim_results={"values": vector}, set_id=run["target_id"],
        canonical_set_key=set_rows[0]["canonical_key"], calculation_run_id=run_id,
        run_fingerprint=str(config_rows[0]["config_hash"]),
    )
