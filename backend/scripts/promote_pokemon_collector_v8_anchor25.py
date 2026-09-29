"""Fail-closed one-time Collector V8 ANCHOR25 cutover.

This command does not participate in the daily scheduler and never changes
Overall RIP. Default execution is read-only. A production cutover requires both
--commit and --i-understand-this-promotes-collector-v8.

The promotion is bound to the exact frozen V7 authority used by the calibration,
historical replay, temporal validation, and accepted V8 shadow. If that authority
has changed, this command refuses to stage or promote anything.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.build_pokemon_collector_appeal_v8_anchor25 import (
    MODEL_VERSION as V8_VERSION,
    V7_VERSION,
    build_frozen_cutover,
    persist_built_model,
)
from backend.scripts.operationalize_historical_rip import (
    V8_FROZEN_FORMULA_FINGERPRINT,
    _append_current_collector_history,
    _default_set_pages,
)

EXPECTED_V7_RUN_ID = "e282f26e-2136-4105-b0a3-f0974c4d9d70"
EXPECTED_V7_MODEL_FINGERPRINT = "3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d"
EXPECTED_V7_FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
EXPECTED_V7_CARD_FINGERPRINT = "7dbe5e989c6eb7bcb9d4684707f9c239ab1ca701fc429a7a0605657d79f2ab90"
EXPECTED_V7_SET_FINGERPRINT = "744f088e7e1e33e5f8b40aca707b8f7e0d93bf7def8308b860da0277257a4b52"
EXPECTED_V8_CARD_FINGERPRINT = "0b66d491565717a9595c5c1da86f75d1c3009a13c0a7886f9dce2e8e26ebd9d7"
EXPECTED_V8_SET_FINGERPRINT = "71fc319f473a65743e1855260ecc7dbe87ecd21868be1c105d5100d36098daa9"
MODEL_AS_OF_DATE = date(2026, 9, 11)

# Despite the historical name, the live function body validates generation/run
# affinity and delegates to the generic model promotion + generation activation
# functions in one transaction. It does not restrict model version.
ATOMIC_PROMOTION_RPC = "promote_pokemon_collector_v7_with_set_page_generation"


def _current_control(client: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    current = (
        client.table("pokemon_collector_appeal_current")
        .select("scope,model_run_id,model_version,as_of_date")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )
    if not current:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_NO_CURRENT_AUTHORITY")
    model = (
        client.table("pokemon_collector_appeal_model_runs")
        .select(
            "id,model_version,as_of_date,status,validation_passed,input_fingerprint,"
            "source_run_ids,scoring_config_json"
        )
        .eq("id", current["model_run_id"])
        .single()
        .execute()
        .data
    )
    return current, model


def validate_exact_v7_control(
    current: Mapping[str, Any],
    model: Mapping[str, Any],
    built: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = model.get("scoring_config_json") or {}
    checks = {
        "currentVersion": current.get("model_version") == V7_VERSION,
        "currentRun": str(current.get("model_run_id")) == EXPECTED_V7_RUN_ID,
        "modelRun": str(model.get("id")) == EXPECTED_V7_RUN_ID,
        "modelPublished": model.get("status") == "published" and model.get("validation_passed") is True,
        "modelFingerprint": model.get("input_fingerprint") == EXPECTED_V7_MODEL_FINGERPRINT,
        "formulaFingerprint": manifest.get("formulaFingerprint") == EXPECTED_V7_FORMULA_FINGERPRINT,
        "cardFingerprint": manifest.get("cardFingerprint") == EXPECTED_V7_CARD_FINGERPRINT,
        "setFingerprint": manifest.get("setFingerprint") == EXPECTED_V7_SET_FINGERPRINT,
        "v8FormulaFingerprint": built["manifest"].get("formulaFingerprint") == V8_FROZEN_FORMULA_FINGERPRINT,
        "sourceAuthority": (built["manifest"].get("sourceRunIds") or []) == (model.get("source_run_ids") or []),
        "v8ControlReplay": (built["manifest"].get("calibrationAnalysis") or {}).get("controlReplayExact") is True,
        "pokemonUnchanged": (built["manifest"].get("calibrationAnalysis") or {}).get("pokemonUnchanged") is True,
        "trainerPreservation": float(
            (built["manifest"].get("calibrationAnalysis") or {}).get("trainerWithinDomainSpearman") or 0.0
        ) >= 0.995,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_CONTROL_MISMATCH:" + ",".join(failed))
    return checks



def validate_exact_v8_current(
    current: Mapping[str, Any],
    model: Mapping[str, Any],
    built: Mapping[str, Any],
) -> dict[str, Any]:
    """Recognize only the exact accepted V8 authority for interruption recovery."""
    manifest = model.get("scoring_config_json") or {}
    checks = {
        "currentVersion": current.get("model_version") == V8_VERSION,
        "modelRunMatchesCurrent": str(model.get("id")) == str(current.get("model_run_id")),
        "modelPublished": model.get("status") == "published" and model.get("validation_passed") is True,
        "modelAsOfDate": str(model.get("as_of_date")) == MODEL_AS_OF_DATE.isoformat(),
        "formulaFingerprint": manifest.get("formulaFingerprint") == V8_FROZEN_FORMULA_FINGERPRINT,
        "cardFingerprint": manifest.get("cardFingerprint") == EXPECTED_V8_CARD_FINGERPRINT,
        "setFingerprint": manifest.get("setFingerprint") == EXPECTED_V8_SET_FINGERPRINT,
        "builtFormulaFingerprint": built["manifest"].get("formulaFingerprint") == V8_FROZEN_FORMULA_FINGERPRINT,
        "builtCardFingerprint": built["manifest"].get("cardFingerprint") == EXPECTED_V8_CARD_FINGERPRINT,
        "builtSetFingerprint": built["manifest"].get("setFingerprint") == EXPECTED_V8_SET_FINGERPRINT,
        "sourceAuthority": (model.get("source_run_ids") or []) == (built["manifest"].get("sourceRunIds") or []),
        "v8ControlReplay": (built["manifest"].get("calibrationAnalysis") or {}).get("controlReplayExact") is True,
        "pokemonUnchanged": (built["manifest"].get("calibrationAnalysis") or {}).get("pokemonUnchanged") is True,
        "trainerPreservation": float(
            (built["manifest"].get("calibrationAnalysis") or {}).get("trainerWithinDomainSpearman") or 0.0
        ) >= 0.995,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_EXISTING_V8_MISMATCH:" + ",".join(failed))
    return checks


def _validated_generation_for_model(client: Any, model_run_id: str) -> dict[str, Any] | None:
    rows = (
        client.table("pokemon_set_page_snapshot_generations")
        .select("id,status,validation_passed,validation_json,collector_model_run_id,created_at")
        .eq("collector_model_run_id", str(model_run_id))
        .in_("status", ["validated", "published"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    row = rows[0]
    if (
        row.get("validation_passed") is not True
        or (row.get("validation_json") or {}).get("passed") is not True
        or str(row.get("collector_model_run_id")) != str(model_run_id)
    ):
        return None
    return row


def promotion_plan(client: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    built = build_frozen_cutover()
    current, model = _current_control(client)
    if current.get("model_version") == V7_VERSION:
        checks = validate_exact_v7_control(current, model, built)
        decision = "COLLECTOR_V8_CUTOVER_PREFLIGHT_PASS"
        cutover_state = "promotion_required"
    elif current.get("model_version") == V8_VERSION:
        checks = validate_exact_v8_current(current, model, built)
        decision = "COLLECTOR_V8_CUTOVER_ALREADY_PROMOTED_EXACT"
        cutover_state = "already_promoted_exact"
    else:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_UNSUPPORTED_CURRENT_AUTHORITY")

    return built, {
        "decision": decision,
        "cutoverState": cutover_state,
        "currentModelRunId": current["model_run_id"],
        "currentModelVersion": current["model_version"],
        "v8Version": V8_VERSION,
        "v8FormulaFingerprint": built["manifest"]["formulaFingerprint"],
        "v8CardFingerprint": built["manifest"]["cardFingerprint"],
        "v8SetFingerprint": built["manifest"]["setFingerprint"],
        "cards": len(built["cards"]),
        "sets": len(built["sets"]),
        "scoredSets": sum(row.get("collector_appeal") is not None for row in built["sets"]),
        "modelAsOfDate": MODEL_AS_OF_DATE.isoformat(),
        "controlChecks": checks,
        "overallRipMutation": "NONE",
        "defaultMode": "read_only",
    }


def _readback(client: Any, expected_run_id: str) -> dict[str, Any]:
    current = (
        client.table("pokemon_collector_appeal_current")
        .select("model_run_id,model_version,as_of_date,promoted_at")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )
    generation = (
        client.table("pokemon_set_page_snapshot_current_generation")
        .select("generation_id")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )
    if str(current.get("model_run_id")) != str(expected_run_id) or current.get("model_version") != V8_VERSION:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_READBACK_CURRENT_MISMATCH")
    return {"collectorCurrent": current, "setPageCurrentGeneration": generation}


def execute(
    client: Any,
    *,
    commit: bool,
    acknowledged: bool,
    history_as_of: date,
) -> dict[str, Any]:
    built, plan = promotion_plan(client)
    if not commit:
        return {**plan, "mode": "dry-run", "mutationsPerformed": 0}
    if not acknowledged:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_EXPLICIT_ACKNOWLEDGEMENT_REQUIRED")

    if plan.get("cutoverState") == "already_promoted_exact":
        # Recovery path for a process interruption after atomic promotion but
        # before temporal-history append/readback. No second promotion occurs.
        run_id = str(plan["currentModelRunId"])
        history_rows = _append_current_collector_history(
            client,
            as_of=history_as_of,
            model_version=V8_VERSION,
        )
        readback = _readback(client, run_id)
        return {
            **plan,
            "decision": "COLLECTOR_V8_CUTOVER_RECOVERED_EXACT_V8",
            "mode": "commit",
            "modelRunId": run_id,
            "modelCreated": False,
            "historyAsOfDate": history_as_of.isoformat(),
            "historyRowsInserted": history_rows,
            "readback": readback,
            "overallRipMutation": "NONE",
        }

    run_id, validation, created = persist_built_model(
        client,
        built,
        as_of_date=MODEL_AS_OF_DATE,
    )
    if not validation or validation.get("passed") is not True:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_STAGED_MODEL_NOT_VALIDATED")

    existing_generation = _validated_generation_for_model(client, run_id)
    if existing_generation is not None:
        pages = {
            "status": "reused_validated",
            "generationId": str(existing_generation["id"]),
        }
    else:
        pages = _default_set_pages(client, run_id, True)
    generation_id = pages.get("generationId")
    if not generation_id:
        raise RuntimeError("COLLECTOR_V8_CUTOVER_SET_PAGE_GENERATION_MISSING")

    client.rpc(
        ATOMIC_PROMOTION_RPC,
        {"p_model_run_id": run_id, "p_generation_id": generation_id},
    ).execute()

    history_rows = _append_current_collector_history(
        client,
        as_of=history_as_of,
        model_version=V8_VERSION,
    )
    readback = _readback(client, run_id)
    return {
        **plan,
        "decision": "COLLECTOR_V8_CUTOVER_PROMOTED",
        "mode": "commit",
        "modelRunId": run_id,
        "modelCreated": created,
        "validation": validation,
        "setPageGeneration": pages,
        "historyAsOfDate": history_as_of.isoformat(),
        "historyRowsInserted": history_rows,
        "readback": readback,
        "overallRipMutation": "NONE",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--i-understand-this-promotes-collector-v8", action="store_true")
    parser.add_argument("--history-as-of-date", required=True)
    args = parser.parse_args(argv)

    if args.i_understand_this_promotes_collector_v8 and not args.commit:
        raise SystemExit("acknowledgement flag requires --commit")

    load_dotenv(ROOT / "backend/.env", override=False)
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        options=ClientOptions(postgrest_client_timeout=90),
    )
    report = execute(
        client,
        commit=args.commit,
        acknowledged=args.i_understand_this_promotes_collector_v8,
        history_as_of=date.fromisoformat(args.history_as_of_date),
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
