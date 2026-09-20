"""Lightweight routing authority for Pokemon set-detail routes.

This deliberately reads narrow relational columns from the canonical RIP view;
it never reads or trims the multi-megabyte Rankings publication JSON.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import service_read_client
from backend.db.services.public_read_retry import run_public_read_with_retry


ROUTE_DIRECTORY_COLUMNS = (
    "set_id,set_name,canonical_key,run_at,pack_score,relative_pack_score,"
    "pack_rank,pack_tier,ranked_set_count,pack_score_is_placeholder"
)
logger = logging.getLogger(__name__)


def _load_canonical_card_counts(set_ids: List[str]) -> Optional[Dict[str, int]]:
    """Best-effort canonical checklist counts for route-directory display.

    Route membership must never depend on this enrichment. The route-directory
    RPC remains the sole membership/identity authority; if the aggregate count
    RPC is temporarily unavailable, callers still receive the complete route
    directory with card_count left unavailable.
    """
    clean_ids = [str(value) for value in set_ids if str(value or "").strip()]
    if not clean_ids:
        return {}

    try:
        result = run_public_read_with_retry(
            lambda client: client.rpc(
                "get_pokemon_canonical_card_counts_by_set",
                {"p_set_ids": clean_ids},
            ).execute(),
            operation_name="pokemon_set_route_directory_card_counts",
            initial_client=service_read_client,
        )
    except Exception:
        logger.warning(
            "Canonical Pokemon set route directory card-count enrichment failed",
            exc_info=True,
        )
        return None

    counts: Dict[str, int] = {}
    for row in list(getattr(result, "data", None) or []):
        set_id = str(row.get("set_id") or "").strip()
        try:
            card_count = int(row.get("card_count"))
        except (TypeError, ValueError):
            continue
        if set_id and card_count >= 0:
            counts[set_id] = card_count
    return counts


def get_pokemon_set_route_directory_payload(limit: int = 200) -> Dict[str, Any]:
    resolved_limit = max(1, min(int(limit or 200), 200))
    try:
        projected = list(
            run_public_read_with_retry(
                lambda client: client.rpc(
                    "get_pokemon_set_route_directory", {"p_limit": resolved_limit}
                ).execute(),
                operation_name="pokemon_set_route_directory",
                initial_client=service_read_client,
            ).data
            or []
        )
    except Exception as exc:
        logger.exception("Canonical Pokemon set route directory RPC failed")
        raise RuntimeError("Canonical Pokemon set route directory is temporarily unavailable") from exc
    if projected:
        set_ids = [str(row.get("target_id") or "").strip() for row in projected]
        canonical_card_counts = _load_canonical_card_counts(set_ids)
        targets = [
            {
                "target_type": "set",
                "target_id": str(row.get("target_id") or ""),
                "setId": str(row.get("target_id") or ""),
                "name": row.get("name"),
                "canonical_key": row.get("canonical_key"),
                "slug": row.get("canonical_key"),
                "release_date": row.get("release_date"),
                "pokemon_api_set_id": row.get("pokemon_api_set_id"),
                "logo_image_url": row.get("logo_image_url"),
                "symbol_image_url": row.get("symbol_image_url"),
                "hero_image_url": row.get("hero_image_url"),
                "era": row.get("era"),
                "card_count": (
                    canonical_card_counts.get(str(row.get("target_id") or ""), 0)
                    if canonical_card_counts is not None
                    else None
                ),
                "cardCount": (
                    canonical_card_counts.get(str(row.get("target_id") or ""), 0)
                    if canonical_card_counts is not None
                    else None
                ),
                "pack_score": row.get("pack_score"),
                "relative_pack_score": row.get("relative_pack_score"),
                "pack_rank": row.get("pack_rank"),
                "pack_tier": row.get("pack_tier"),
                "ranked_set_count": row.get("ranked_set_count"),
            }
            for row in projected
        ]
        return {
            "targets": targets,
            "default_target": targets[0] if targets else None,
            "meta": {
                "source": "get_pokemon_set_route_directory",
                "contract": "pokemon-set-route-directory-v1",
                "count": len(targets),
                "stale": False,
                "fallbackReason": None,
                "cardCountSource": (
                    "get_pokemon_canonical_card_counts_by_set"
                    if canonical_card_counts is not None
                    else "unavailable"
                ),
                "readAt": datetime.now(timezone.utc).isoformat(),
            },
        }
    raise RuntimeError("Canonical Pokemon set route directory returned no targets")
