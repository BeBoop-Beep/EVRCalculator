from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from backend.db.clients.supabase_client import reset_service_role_auth, supabase

logger = logging.getLogger(__name__)


def normalize_public_username(username: Any) -> str:
    if not isinstance(username, str):
        return ""

    normalized = username.strip().lower()
    normalized = " ".join(normalized.split())
    normalized = normalized.replace(" ", "-")
    normalized = "".join(ch for ch in normalized if ch.isalnum() or ch in {"-", "_", "."})
    normalized = normalized.strip("-._")
    return normalized


def normalize_profile_username(profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(profile, dict):
        return profile

    normalized_username = normalize_public_username(profile.get("username"))
    if not normalized_username:
        return profile

    return {
        **profile,
        "username": normalized_username,
    }


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def resolve_public_user_by_username(
    username: Any,
    *,
    correlation_id: Optional[str] = None,
    db_client: Any = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    client = db_client or supabase
    if db_client is None:
        reset_service_role_auth()
    requested_username = str(username or "").strip()
    normalized_username = normalize_public_username(requested_username)

    trace: Dict[str, Any] = {
        "correlation_id": correlation_id,
        "requested_username": requested_username,
        "normalized_username": normalized_username,
        "lookup_strategy": None,
        "row_found": False,
        "resolved_user_id": None,
        "resolved_username": None,
        "reason": None,
    }

    if not normalized_username:
        trace["reason"] = "INVALID_USERNAME"
        return None, trace

    lookup_attempts = [
        ("username_eq_requested", "eq", requested_username),
        ("username_eq_normalized", "eq", normalized_username),
    ]

    spaced_candidate = normalized_username.replace("-", " ")
    if spaced_candidate and spaced_candidate != requested_username and spaced_candidate != normalized_username:
        lookup_attempts.append(("username_ilike_spaced", "ilike", spaced_candidate))

    user = None
    for strategy_name, operator, candidate in lookup_attempts:
        if not candidate:
            continue

        try:
            query = client.table("users").select("id,username,display_name,email,is_profile_public").limit(1)
            if operator == "eq":
                result = query.eq("username", candidate).execute()
            else:
                result = query.ilike("username", candidate).execute()
            user = _first_row(result)
        except Exception:
            logger.exception(
                "public_identity.resolve_public_user_by_username: lookup failed correlation_id=%s strategy=%s candidate=%s",
                correlation_id,
                strategy_name,
                candidate,
            )
            trace["lookup_strategy"] = strategy_name
            trace["reason"] = "LOOKUP_EXCEPTION"
            return None, trace

        if user:
            trace["lookup_strategy"] = strategy_name
            trace["row_found"] = True
            trace["resolved_user_id"] = user.get("id")
            trace["resolved_username"] = user.get("username")
            return user, trace

    trace["lookup_strategy"] = lookup_attempts[-1][0]
    trace["reason"] = "USER_NOT_FOUND"
    return None, trace