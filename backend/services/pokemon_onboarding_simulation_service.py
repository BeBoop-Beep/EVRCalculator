from __future__ import annotations

import json
from typing import Any, Dict, Optional


def parse_simulation_json(stdout: str) -> Dict[str, Any]:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("SIMULATION_JSON="):
            return json.loads(line.split("=", 1)[1])
    raise ValueError("run_all_v2_sets did not emit SIMULATION_JSON")


def latest_simulation_evidence(client: Any, set_id: str) -> Dict[str, Any]:
    runs = (
        client.table("calculation_runs").select("id,target_id,created_at")
        .eq("target_type", "set").eq("target_id", set_id)
        .order("created_at", desc=True).limit(1).execute().data or []
    )
    run = runs[0] if runs else {}
    run_id = str(run.get("id") or "")
    summary = (
        client.table("simulation_run_summary").select("calculation_run_id,simulation_count")
        .eq("calculation_run_id", run_id).limit(1).execute().data or []
    ) if run_id else []
    inputs = (
        client.table("simulation_input_cards").select("calculation_run_id")
        .eq("calculation_run_id", run_id).limit(1000).execute().data or []
    ) if run_id else []
    derived = (
        client.table("simulation_derived_metrics").select("calculation_run_id")
        .eq("calculation_run_id", run_id).limit(1).execute().data or []
    ) if run_id else []
    return {
        "run_id": run_id or None, "target_id": run.get("target_id"),
        "created_at": run.get("created_at"), "input_count": len(inputs),
        "summary_count": len(summary), "derived_count": len(derived),
        "details_complete": bool(inputs and summary and derived),
    }
