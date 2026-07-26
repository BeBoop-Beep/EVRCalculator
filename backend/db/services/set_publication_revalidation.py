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
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

_TAG = "[set-revalidation]"
_TIMEOUT_SECONDS = 5


def _dedupe(identifiers: Iterable[Optional[str]]) -> List[str]:
    seen: set[str] = set()
    resolved: List[str] = []
    for identifier in identifiers:
        text = str(identifier or "").strip()
        if text and text not in seen:
            seen.add(text)
            resolved.append(text)
    return resolved


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
