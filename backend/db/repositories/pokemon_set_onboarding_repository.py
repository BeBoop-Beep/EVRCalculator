from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from ..clients.supabase_client import supabase

TABLE = "pokemon_set_onboarding_jobs"


def list_source_identities(source_system: str = "tcgplayer") -> set[str]:
    response = supabase.table(TABLE).select("source_set_id").eq("source_system", source_system).execute()
    return {str(row["source_set_id"]) for row in (response.data or []) if row.get("source_set_id")}


def list_source_identity_statuses(source_system: str = "tcgplayer") -> Dict[str, str]:
    """Provider identity -> current job status, used to separate baseline rows from live jobs."""
    response = (
        supabase.table(TABLE).select("source_set_id,status").eq("source_system", source_system).execute()
    )
    return {
        str(row["source_set_id"]): str(row.get("status") or "")
        for row in (response.data or [])
        if row.get("source_set_id")
    }


def get_by_source_identity(source_system: str, source_set_id: str) -> Optional[Dict[str, Any]]:
    response = (
        supabase.table(TABLE).select("*").eq("source_system", source_system)
        .eq("source_set_id", str(source_set_id)).limit(1).execute()
    )
    return (response.data or [None])[0]


def upsert_discovery(row: Dict[str, Any]) -> Dict[str, Any]:
    response = supabase.table(TABLE).upsert(
        row, on_conflict="source_system,source_set_id", ignore_duplicates=False
    ).execute()
    if not response.data:
        raise RuntimeError("onboarding discovery upsert returned no row")
    return response.data[0]


def claim_next(
    worker_id: str, lease_seconds: int = 1800, *,
    job_id: Optional[str] = None, force_retry: bool = False,
) -> Optional[Dict[str, Any]]:
    response = supabase.rpc("claim_next_pokemon_set_onboarding_job", {
        "p_worker_id": worker_id, "p_lease_seconds": lease_seconds,
        "p_job_id": job_id, "p_force_retry": force_retry,
    }).execute()
    return (response.data or [None])[0]


def heartbeat(job_id: str, worker_id: str, lease_seconds: int = 1800) -> Optional[Dict[str, Any]]:
    response = supabase.rpc("heartbeat_pokemon_set_onboarding_job", {
        "p_job_id": job_id, "p_worker_id": worker_id, "p_lease_seconds": lease_seconds,
    }).execute()
    return (response.data or [None])[0]


def update_claimed(job_id: str, worker_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    response = (
        supabase.table(TABLE).update(payload).eq("id", job_id)
        .eq("status", "running").eq("worker_id", worker_id).execute()
    )
    return (response.data or [None])[0]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    response = supabase.table(TABLE).select("*").eq("id", job_id).limit(1).execute()
    return (response.data or [None])[0]


def list_jobs(
    *, include_waiting: bool = False, include_manual_review: bool = False, limit: int = 25,
) -> list[Dict[str, Any]]:
    statuses = ["detected", "ready", "retry"]
    if include_waiting:
        statuses.append("waiting")
    if include_manual_review:
        statuses.append("manual_review")
    response = (
        supabase.table(TABLE).select("*").in_("status", statuses)
        .order("next_attempt_at").limit(max(1, limit)).execute()
    )
    return response.data or []


def release_for_retry(
    job_id: str, worker_id: str, *, code: str, message: str, delay_seconds: int = 3600
) -> Optional[Dict[str, Any]]:
    return update_claimed(job_id, worker_id, {
        "status": "retry",
        "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
        "worker_id": None, "lease_expires_at": None, "heartbeat_at": None,
        "last_error_code": code, "last_error_message": message[:2000],
    })


def list_registered_set_urls() -> Iterable[Dict[str, Any]]:
    response = supabase.table("sets").select("card_details_url,sealed_details_url").execute()
    return response.data or []
