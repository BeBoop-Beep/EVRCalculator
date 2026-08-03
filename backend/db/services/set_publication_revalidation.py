"""Best-effort cache invalidation after a set snapshot is published.

Downstream public snapshots seed the Next.js set-detail page through tagged,
time-revalidated data-cache entries (``pokemon-set-shell:<setId>`` and
``pokemon-set-overview:<setId>:<window>``). Without an explicit signal those
entries serve a cached response until their timer elapses, so a freshly
published July-25 snapshot can be shadowed by an older cached response.

After a successful publication the publisher calls
:func:`notify_set_snapshot_published`, which POSTs to the frontend's
``/api/internal/revalidate-set`` route to invalidate those tags immediately.

This is intentionally best-effort and non-fatal: it is a no-op when the
frontend URL / secret are not configured, and it never raises into the publish
path (a cache-bust failure must not fail an otherwise-successful publication).
Configure via env: ``SET_REVALIDATION_URL`` and ``SET_REVALIDATION_SECRET``.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, Iterable, List, MutableSet, Optional

logger = logging.getLogger(__name__)

_TAG = "[set-revalidation]"
_TIMEOUT_SECONDS = 5

# Visible publication diagnostics.
#
# Tagged seed invalidation is best-effort by design, which previously made it
# invisible: a run where the frontend URL was never configured and a run where
# every POST succeeded produced the same (silent) publication summary, so
# "database is current but the page still shows yesterday" had no evidence trail.
# These counters make each publication state distinguishable in the log without
# changing the best-effort, non-fatal contract.
_DIAGNOSTICS: Dict[str, Any] = {
    "configured": None,
    "sets_considered": 0,
    "sets_attempted": 0,
    "sets_succeeded": 0,
    "sets_failed": 0,
    "sets_skipped_dry_run": 0,
    "sets_skipped_duplicate": 0,
    "failed_sets": [],
}


def reset_revalidation_diagnostics() -> None:
    """Start a fresh accounting window (one publication run)."""
    _DIAGNOSTICS.update(
        {
            "configured": None,
            "sets_considered": 0,
            "sets_attempted": 0,
            "sets_succeeded": 0,
            "sets_failed": 0,
            "sets_skipped_dry_run": 0,
            "sets_skipped_duplicate": 0,
            "failed_sets": [],
        }
    )


def get_revalidation_diagnostics() -> Dict[str, Any]:
    """Snapshot of this run's cache-invalidation accounting."""
    snapshot = dict(_DIAGNOSTICS)
    snapshot["failed_sets"] = list(_DIAGNOSTICS["failed_sets"])
    return snapshot


def format_revalidation_diagnostics() -> str:
    """One greppable line stating exactly what happened to the tagged seeds."""
    diagnostics = get_revalidation_diagnostics()
    configured = diagnostics["configured"]
    configured_text = "unknown" if configured is None else ("yes" if configured else "no")
    line = (
        f"{_TAG} publication diagnostics: cache_invalidation_configured={configured_text} "
        f"sets_considered={diagnostics['sets_considered']} "
        f"attempted={diagnostics['sets_attempted']} "
        f"succeeded={diagnostics['sets_succeeded']} "
        f"failed={diagnostics['sets_failed']} "
        f"skipped_dry_run={diagnostics['sets_skipped_dry_run']} "
        f"skipped_duplicate={diagnostics['sets_skipped_duplicate']}"
    )
    if diagnostics["failed_sets"]:
        line += f" failed_sets={','.join(diagnostics['failed_sets'])}"
    if configured is False and diagnostics["sets_considered"]:
        line += (
            " note=tagged seeds were NOT invalidated; the set page serves its cached seed "
            "until the tag timer elapses"
        )
    return line


def log_revalidation_diagnostics() -> str:
    """Emit the diagnostics line at INFO and return it."""
    line = format_revalidation_diagnostics()
    logger.info("%s", line)
    return line

# Overview cache-tag windows the frontend seeds a set page from. Mirrors
# OVERVIEW_WINDOWS in frontend/app/api/internal/revalidate-set/route.js: every
# publication invalidates the whole family so no window can keep serving an
# older market date than its siblings.
DEFAULT_OVERVIEW_WINDOWS = ("365d", "180d", "90d", "30d", "7d")

# Identity columns the frontend may address a set by. All of them are
# invalidated because the seed's cache tag is built from whichever identifier
# the incoming route used.
_SET_IDENTIFIER_FIELDS = ("canonical_key", "id", "set_id", "pokemon_api_set_id")


def _dedupe(identifiers: Iterable[Optional[str]]) -> List[str]:
    seen: set[str] = set()
    resolved: List[str] = []
    for identifier in identifiers:
        text = str(identifier or "").strip()
        if text and text not in seen:
            seen.add(text)
            resolved.append(text)
    return resolved


def is_revalidation_configured() -> bool:
    """True when both the frontend URL and the shared secret are configured."""
    return bool(
        str(os.getenv("SET_REVALIDATION_URL", "")).strip()
        and str(os.getenv("SET_REVALIDATION_SECRET", "")).strip()
    )


def resolve_set_revalidation_identifiers(set_row: Any) -> List[str]:
    """Every identifier the frontend may address this set by, deduped."""
    if isinstance(set_row, dict):
        return _dedupe(set_row.get(field) for field in _SET_IDENTIFIER_FIELDS)
    return _dedupe([set_row])


def resolve_revalidation_windows(window: Optional[str] = None) -> List[str]:
    """The requested window (when given) plus the standard Overview windows."""
    return _dedupe([window, *DEFAULT_OVERVIEW_WINDOWS])


def notify_set_publication(
    set_row: Any,
    *,
    window: Optional[str] = None,
    commit: bool = True,
    seen: Optional[MutableSet[str]] = None,
) -> bool:
    """Publish-success cache invalidation for ONE fully published set.

    This is the single entry point every publisher calls. Contract:

    * Call it only AFTER every write required for that set has committed —
      never between the Cards write and the dashboard write of one coordinated
      operation, so a later failure can never leave a "revalidated" claim
      behind a partial publication.
    * ``commit=False`` (dry-run) is a hard no-op: a run that wrote nothing must
      never touch the cache.
    * ``seen`` de-duplicates within a single process run, so one set published
      once is invalidated once no matter how many writes it involved.

    Best-effort and non-fatal by design: an unreachable frontend logs a visible
    warning but leaves the publication successful.
    """
    _DIAGNOSTICS["sets_considered"] += 1
    if not commit:
        _DIAGNOSTICS["sets_skipped_dry_run"] += 1
        return False
    identifiers = resolve_set_revalidation_identifiers(set_row)
    if not identifiers:
        return False
    if seen is not None:
        if identifiers[0] in seen:
            _DIAGNOSTICS["sets_skipped_duplicate"] += 1
            return False
        seen.add(identifiers[0])

    configured = is_revalidation_configured()
    _DIAGNOSTICS["configured"] = configured
    _DIAGNOSTICS["sets_attempted"] += 1

    ok = notify_set_snapshot_published(*identifiers, windows=resolve_revalidation_windows(window))
    if ok:
        _DIAGNOSTICS["sets_succeeded"] += 1
        logger.info("%s cache invalidation OK set=%s", _TAG, identifiers[0])
    else:
        _DIAGNOSTICS["sets_failed"] += 1
        _DIAGNOSTICS["failed_sets"].append(identifiers[0])
    if not ok and configured:
        logger.warning(
            "%s cache invalidation FAILED for published set=%s; the publication itself succeeded "
            "and the frontend will serve the older cached seed until its timer elapses",
            _TAG,
            identifiers[0],
        )
    return ok


def notify_set_snapshot_published(
    *identifiers: Optional[str],
    windows: Optional[List[str]] = None,
) -> bool:
    """Invalidate the frontend cache for a published set. Never raises.

    ``identifiers`` are the set keys the frontend may address the set by
    (canonical key and/or uuid); each is invalidated so whichever seeds the
    page is refreshed. Returns True when at least one invalidation POST
    succeeded, False otherwise (including the unconfigured no-op case).
    """
    base_url = str(os.getenv("SET_REVALIDATION_URL", "")).strip()
    secret = str(os.getenv("SET_REVALIDATION_SECRET", "")).strip()
    if not base_url or not secret:
        logger.info("%s not configured (SET_REVALIDATION_URL/SECRET); skipping cache invalidation", _TAG)
        return False

    any_ok = False
    for set_identifier in _dedupe(identifiers):
        payload = {"setId": set_identifier}
        if windows:
            payload["windows"] = list(windows)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            base_url,
            data=data,
            headers={"Content-Type": "application/json", "x-revalidate-secret": secret},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                if 200 <= getattr(response, "status", 200) < 300:
                    any_ok = True
        except Exception as exc:  # best-effort: cache-bust failure must not fail publish
            logger.warning("%s revalidation POST failed set=%s: %s", _TAG, set_identifier, exc)
    return any_ok
