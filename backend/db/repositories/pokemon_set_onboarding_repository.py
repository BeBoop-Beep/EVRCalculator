from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from ..clients.supabase_client import supabase

TABLE = "pokemon_set_onboarding_jobs"


class LeaseFencingError(RuntimeError):
    """Raised when a worker-fenced update affected zero rows: the lease was lost or stolen."""


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


def list_baseline_catalog_jobs(source_system: str = "tcgplayer") -> list[Dict[str, Any]]:
    """Historical catalog identities recorded by the one-time cold-start baseline.

    Deliberately separate from `list_jobs`: these rows are `ignored` and must stay
    invisible to the nightly onboarding worker's queue read.
    """
    response = (
        supabase.table(TABLE).select("*").eq("source_system", source_system)
        .eq("status", "ignored").eq("current_step", "catalog_baseline")
        .order("source_set_id").execute()
    )
    return response.data or []


def update_baseline_job(job_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update a baseline row, guarded so only an untouched baseline row can move."""
    payload = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    response = (
        supabase.table(TABLE).update(payload).eq("id", job_id)
        .eq("status", "ignored").eq("current_step", "catalog_baseline").execute()
    )
    return (response.data or [None])[0]


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


def update_claimed(
    job_id: str, worker_id: str, fields: Dict[str, Any], *, strict: bool = False,
) -> Optional[Dict[str, Any]]:
    """Fenced update: only succeeds while this worker still owns the running lease.

    A zero-row result means the lease was lost, stolen, or already released. With
    strict=True (the primary state-transition write) that is treated as a hard
    failure rather than silently accepted as success.
    """
    payload = {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}
    response = (
        supabase.table(TABLE).update(payload).eq("id", job_id)
        .eq("status", "running").eq("worker_id", worker_id).execute()
    )
    result = (response.data or [None])[0]
    if strict and result is None:
        raise LeaseFencingError(
            f"update_claimed affected 0 rows for job {job_id} (worker {worker_id}); "
            "lease was lost, stolen, or already released"
        )
    return result


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    response = supabase.table(TABLE).select("*").eq("id", job_id).limit(1).execute()
    return (response.data or [None])[0]


# ---------------------------------------------------------------------------
# v2 RPCs (service-role, token-fenced). Kept alongside the v1 functions above
# as a temporary compatibility fallback; do not drop the v1 functions in this
# pass. The v2 lease is fenced by an opaque `lease_token` returned by
# claim_next_v2, threaded through heartbeat_v2 and transition_v2, rather than
# by (worker_id, status='running') alone.
# ---------------------------------------------------------------------------


def claim_next_v2(
    worker_id: str, lease_seconds: int = 1800, *,
    job_id: Optional[str] = None, include_waiting: bool = False, force_retry: bool = False,
) -> Optional[Dict[str, Any]]:
    response = supabase.rpc("claim_next_pokemon_set_onboarding_job_v2", {
        "p_worker_id": worker_id, "p_lease_seconds": lease_seconds,
        "p_job_id": job_id, "p_include_waiting": include_waiting, "p_force_retry": force_retry,
    }).execute()
    return (response.data or [None])[0]


def heartbeat_v2(
    job_id: str, worker_id: str, lease_token: str, lease_seconds: int = 1800,
) -> Optional[Dict[str, Any]]:
    """A zero-row response means ownership/token/lease is no longer valid; treat as lease loss."""
    response = supabase.rpc("heartbeat_pokemon_set_onboarding_job_v2", {
        "p_job_id": job_id, "p_worker_id": worker_id, "p_lease_token": lease_token,
        "p_lease_seconds": lease_seconds,
    }).execute()
    return (response.data or [None])[0]


def transition_v2(
    job_id: str, worker_id: str, lease_token: str, expected_step: str, fields: Dict[str, Any],
    *, strict: bool = False,
) -> Optional[Dict[str, Any]]:
    """Fenced normal/successful state transition via RPC, replacing an unfenced direct UPDATE.

    A zero-row response means the lease token/ownership/expected_step no longer
    matches. With strict=True that is a hard failure, matching update_claimed's
    strict behavior.
    """
    response = supabase.rpc("transition_pokemon_set_onboarding_job_v2", {
        "p_job_id": job_id, "p_worker_id": worker_id, "p_lease_token": lease_token,
        "p_expected_step": expected_step, "p_fields": fields,
    }).execute()
    result = (response.data or [None])[0]
    if strict and result is None:
        raise LeaseFencingError(
            f"transition_v2 affected 0 rows for job {job_id} (worker {worker_id}, "
            f"expected_step {expected_step}); lease token/ownership/step no longer matches"
        )
    return result


def reconcile_discovery_v2(
    *, source_system: str, source_set_id: str, source_set_name: str, candidate_status: str,
    discovery_json: Dict[str, Any], observed_at: Optional[str] = None,
    next_check_at: Optional[str] = None, card_listing_count: Optional[int] = None,
    sealed_listing_count: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Non-destructive discovery upsert. Never restarts or overwrites an existing
    identity's workflow metadata merely because discovery observed it again; the
    response's disposition is one of inserted / observed_existing / stale_observation_ignored.
    """
    response = supabase.rpc("reconcile_pokemon_set_onboarding_discovery_v2", {
        "p_source_system": source_system, "p_source_set_id": source_set_id,
        "p_source_set_name": source_set_name, "p_candidate_status": candidate_status,
        "p_discovery_json": discovery_json,
        "p_observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "p_next_check_at": next_check_at, "p_card_listing_count": card_listing_count,
        "p_sealed_listing_count": sealed_listing_count,
    }).execute()
    return (response.data or [None])[0]


def release_for_retry_v2(
    job_id: str, worker_id: str, lease_token: str, expected_step: str, *,
    code: str, message: str, delay_seconds: int = 3600,
) -> Optional[Dict[str, Any]]:
    return transition_v2(job_id, worker_id, lease_token, expected_step, {
        "status": "retry",
        "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
        "last_error_code": code, "last_error_message": message[:2000],
    })


def list_rechecks_v2(
    *, source_system: str = "tcgplayer", limit: int = 25, as_of: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """Bounded source of explicitly scheduled catalog rechecks (next_check_at due)."""
    response = supabase.rpc("list_pokemon_set_onboarding_rechecks_v2", {
        "p_source_system": source_system, "p_limit": limit,
        "p_as_of": as_of or datetime.now(timezone.utc).isoformat(),
    }).execute()
    return response.data or []


# Statuses runnable without an explicit resume sweep. Ordered ahead of waiting/manual_review
# so an old waiting row can never repeatedly out-rank newer runnable work.
_RUNNABLE_STATUSES = ("detected", "ready", "retry")

# Internal fetch cap for the priority sort below: large enough that a realistic backlog of
# waiting/manual_review rows can never push a runnable row off the page before Python gets
# to re-rank it, but still bounded so a pathological backlog can't turn this into a full
# table scan.
_LIST_JOBS_FETCH_CAP = 500


def _priority_class(status: Any) -> int:
    return 0 if status in _RUNNABLE_STATUSES else 1


def list_jobs(
    *, include_waiting: bool = False, include_manual_review: bool = False, limit: int = 25,
    due_only: bool = False,
) -> list[Dict[str, Any]]:
    """List candidate jobs, ranked so runnable work is never starved by older waiting rows.

    due_only=True restricts to rows whose next_attempt_at has passed (or is unset,
    e.g. a freshly detected job). Use it for unattended/scheduled resumption so a
    scheduled sweep cannot fire a job's next_attempt_at backoff early; leave it
    False for an operator's explicit --job-id lookup.

    Ranking is (priority_class, next_attempt_at, id): detected/ready/retry always sort
    ahead of waiting/manual_review regardless of how old the waiting row's
    next_attempt_at is, so a stale waiting job can never repeatedly win selection over
    newer runnable work. This is a read-side re-rank only; next_attempt_at itself is
    never rewritten here.
    """
    statuses = list(_RUNNABLE_STATUSES)
    if include_waiting:
        statuses.append("waiting")
    if include_manual_review:
        statuses.append("manual_review")
    query = supabase.table(TABLE).select("*").in_("status", statuses)
    if due_only:
        now = datetime.now(timezone.utc).isoformat()
        query = query.or_(f"next_attempt_at.is.null,next_attempt_at.lte.{now}")
    response = query.order("next_attempt_at").limit(_LIST_JOBS_FETCH_CAP).execute()
    rows = response.data or []
    rows.sort(key=lambda row: (
        _priority_class(row.get("status")), row.get("next_attempt_at") or "", str(row.get("id") or ""),
    ))
    return rows[:max(1, limit)]


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
