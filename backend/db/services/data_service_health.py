from __future__ import annotations

"""Shared classification for temporary Supabase/PostgREST failures."""

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpcore
import httpx


TRANSIENT_POSTGREST_CODES = frozenset({"PGRST002"})
TRANSIENT_HTTP_STATUSES = frozenset({502, 503, 504, 521, 522})


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


def classify_data_service_error(exc: BaseException) -> DataServiceFailure:
    """Prefer structured exception attributes; use narrow text fallbacks last."""

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
    )
    if any(token in rendered for token in transient_text):
        return DataServiceFailure(True, first_code, first_status, type(exc).__name__)

    return DataServiceFailure(False, first_code, first_status, type(exc).__name__)


def is_transient_data_service_error(exc: BaseException) -> bool:
    return classify_data_service_error(exc).transient

