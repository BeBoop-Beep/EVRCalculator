from __future__ import annotations

import re
from typing import Any, Dict, Optional

from backend.db.repositories.calculation_runs_repository import get_latest_run_snapshot_for_target
from backend.db.repositories.sets_repository import (
    get_set_by_canonical_key,
    get_set_by_id,
    get_set_by_pokemon_api_set_id,
    get_set_by_name,
)


_UUID_V4_OR_V5_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def _is_uuid_like(value: str) -> bool:
    return bool(_UUID_V4_OR_V5_PATTERN.fullmatch(str(value or "").strip()))


def _extract_set_row_from_name_lookup(name: str) -> Optional[Dict[str, Any]]:
    try:
        response = get_set_by_name(name)
    except Exception:
        return None
    data = getattr(response, "data", None)
    return data if isinstance(data, dict) else None


def _append_unique(items: list[str], value: Any) -> None:
    normalized = str(value or "").strip()
    if normalized and normalized not in items:
        items.append(normalized)


def _set_target_candidates(raw_target_id: str) -> list[str]:
    candidates: list[str] = []
    _append_unique(candidates, raw_target_id)

    lookup_rows: list[Dict[str, Any]] = []

    if _is_uuid_like(raw_target_id):
        row = get_set_by_id(raw_target_id)
        if isinstance(row, dict):
            lookup_rows.append(row)
    else:
        by_api_id = get_set_by_pokemon_api_set_id(raw_target_id)
        if isinstance(by_api_id, dict):
            lookup_rows.append(by_api_id)

        by_canonical = get_set_by_canonical_key(raw_target_id)
        if isinstance(by_canonical, dict):
            lookup_rows.append(by_canonical)

        by_name = _extract_set_row_from_name_lookup(raw_target_id)
        if isinstance(by_name, dict):
            lookup_rows.append(by_name)

    for row in lookup_rows:
        _append_unique(candidates, row.get("id"))
        _append_unique(candidates, row.get("pokemon_api_set_id"))
        _append_unique(candidates, row.get("canonical_key"))
        _append_unique(candidates, row.get("name"))

    return candidates


def _normalize_snapshot_contract(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(snapshot)
    run = normalized.get("run") if isinstance(normalized.get("run"), dict) else {}
    simulation_summary = (
        normalized.get("simulation_summary")
        if isinstance(normalized.get("simulation_summary"), dict)
        else {}
    )

    if "summary" not in normalized and simulation_summary:
        normalized["summary"] = simulation_summary

    calculation_run_id = str(normalized.get("calculation_run_id") or "").strip()
    if not calculation_run_id:
        calculation_run_id = str(run.get("id") or "").strip() or str(
            simulation_summary.get("calculation_run_id") or ""
        ).strip()
    if calculation_run_id:
        normalized["calculation_run_id"] = calculation_run_id

    return normalized


def get_latest_evr_run_snapshot(*, target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
    """Service wrapper for latest EVR run snapshot retrieval."""
    normalized_target_type = str(target_type or "").strip()
    normalized_target_id = str(target_id or "").strip()

    if not normalized_target_type:
        raise ValueError("target_type is required")
    if not normalized_target_id:
        raise ValueError("target_id is required")

    if normalized_target_type.lower() == "set":
        for candidate_target_id in _set_target_candidates(normalized_target_id):
            snapshot = get_latest_run_snapshot_for_target(
                normalized_target_type,
                candidate_target_id,
            )
            if snapshot is not None:
                return _normalize_snapshot_contract(snapshot)
        return None

    snapshot = get_latest_run_snapshot_for_target(
        normalized_target_type,
        normalized_target_id,
    )
    if snapshot is None:
        return None
    return _normalize_snapshot_contract(snapshot)
