from __future__ import annotations

from typing import Any, Dict, Optional

from backend.db.repositories.calculation_runs_repository import get_latest_run_snapshot_for_target


def get_latest_evr_run_snapshot(*, target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
    """Service wrapper for latest EVR run snapshot retrieval."""
    normalized_target_type = str(target_type or "").strip()
    normalized_target_id = str(target_id or "").strip()

    if not normalized_target_type:
        raise ValueError("target_type is required")
    if not normalized_target_id:
        raise ValueError("target_id is required")

    return get_latest_run_snapshot_for_target(
        normalized_target_type,
        normalized_target_id,
    )
