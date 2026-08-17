from __future__ import annotations

"""Shared classification for temporary Supabase/PostgREST failures."""

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpcore
import httpx


# PGRST002: PostgREST cannot reach the schema cache.
# 57014: `canceling statement due to statement timeout`. Postgres cancels the
# statement, not the connection, so the same query can succeed on a retry once
# the pages it touches are in the buffer cache. Cold TOAST reads on a throttled
# volume are the observed source, and they recover without intervention.
TRANSIENT_POSTGREST_CODES = frozenset({"PGRST002", "57014"})
# 520 is Cloudflare's "unknown error" from the origin and sits alongside the 521
# and 522 already listed here; omitting it classified a Supabase edge failure as
# permanent and skipped the retry entirely.
#
# 429 and 500 are additive. 429 is a pure rate signal and says nothing about the
# request's validity. 500 is the harder call: PostgREST returns 500 for genuine
# database errors too, so on its own it would make a deterministic failure look
# retryable. It is safe HERE only because `_deterministic_sqlstate` below vetoes
# the whole classification whenever the exception chain carries a real SQLSTATE -
# a constraint violation, a bad UUID cast or an undefined column all arrive with
# one, and none of them will ever be retried regardless of the HTTP status the
# edge happened to attach.
TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504, 520, 521, 522})

# A Postgres SQLSTATE is exactly five alphanumerics; a PostgREST error code is
# `PGRST` plus three digits. HTTP statuses are three digits, so the length check
# is what keeps `code: 502` (the observed Cloudflare case) from being mistaken
# for a database error class.
_SQLSTATE_PATTERN = re.compile(r"^[0-9A-Z]{5}$")
_POSTGREST_CODE_PATTERN = re.compile(r"^PGRST[0-9]{3}$")


@dataclass(frozen=True)
class DataServiceFailure:
    transient: bool
    code: Optional[str]
    status_code: Optional[int]
    error_type: str


_HTTPX_TRANSIENT_TYPES = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)
_HTTPCORE_TRANSIENT_TYPES = (
    httpcore.TimeoutException,
    httpcore.NetworkError,
    httpcore.RemoteProtocolError,
)


def _exception_chain(exc: BaseException) -> Iterable[BaseException]:
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _structured_code(exc: BaseException) -> Optional[str]:
    value = getattr(exc, "code", None)
    if value is None:
        raw = getattr(exc, "_raw_error", None)
        if isinstance(raw, dict):
            value = raw.get("code")
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _structured_status(exc: BaseException) -> Optional[int]:
    candidates: list[Any] = [
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
    ]
    response = getattr(exc, "response", None)
    if response is not None:
        candidates.append(getattr(response, "status_code", None))
    for value in candidates:
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    code = _structured_code(exc)
    if code and code.isdigit():
        return int(code)
    return None


def _deterministic_sqlstate(exc: BaseException) -> Optional[str]:
    """The first DETERMINISTIC database error code in the chain, if any.

    A SQLSTATE or a PostgREST `PGRST1xx` code means the database understood the
    request and rejected it: a unique violation, a foreign-key failure, an
    invalid UUID, an undefined column, an RLS denial. Repeating that request
    produces the same rejection, so its presence vetoes every transient signal
    that might otherwise be read off the HTTP status.

    The two codes that are known to recover on their own -
    :data:`TRANSIENT_POSTGREST_CODES` - are explicitly not deterministic.
    """
    for current in _exception_chain(exc):
        code = _structured_code(current)
        if not code or code in TRANSIENT_POSTGREST_CODES:
            continue
        if _SQLSTATE_PATTERN.match(code) or _POSTGREST_CODE_PATTERN.match(code):
            return code
    return None


def classify_data_service_error(exc: BaseException) -> DataServiceFailure:
    """Prefer structured exception attributes; use narrow text fallbacks last."""

    deterministic_code = _deterministic_sqlstate(exc)
    if deterministic_code is not None:
        return DataServiceFailure(
            False, deterministic_code, _structured_status(exc), type(exc).__name__
        )

    first_code: Optional[str] = None
    first_status: Optional[int] = None
    for current in _exception_chain(exc):
        code = _structured_code(current)
        status = _structured_status(current)
        first_code = first_code or code
        first_status = first_status or status
        if code in TRANSIENT_POSTGREST_CODES or status in TRANSIENT_HTTP_STATUSES:
            return DataServiceFailure(True, code, status, type(current).__name__)
        if isinstance(current, _HTTPX_TRANSIENT_TYPES + _HTTPCORE_TRANSIENT_TYPES):
            return DataServiceFailure(True, code, status, type(current).__name__)

        # Some connection resets surface as built-in exceptions after the HTTP
        # client has discarded the original transport type.
        if isinstance(current, (ConnectionError, TimeoutError)):
            return DataServiceFailure(True, code, status, type(current).__name__)

    # Older postgrest/http clients can discard a gateway status while rendering
    # the response. Keep this deliberately narrow and only after structured data.
    rendered = " ".join(str(item).lower() for item in _exception_chain(exc))
    transient_text = (
        "connection reset",
        "connection refused",
        "connection aborted",
        "temporarily unavailable",
        "temporary failure",
        "read timeout",
        "connect timeout",
        "gateway timeout",
        "bad gateway",
        "service unavailable",
    )
    if any(token in rendered for token in transient_text):
        return DataServiceFailure(True, first_code, first_status, type(exc).__name__)

    return DataServiceFailure(False, first_code, first_status, type(exc).__name__)


def is_transient_data_service_error(exc: BaseException) -> bool:
    return classify_data_service_error(exc).transient

