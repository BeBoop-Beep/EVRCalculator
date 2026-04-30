"""Dedicated waitlist signup and verification service.

Writes only to public.waitlist_signups via the service-role client.
This module is fully isolated:
    - No auth user creation
    - No profile row creation
    - No session mutation
    - No connection to Explore, portfolio, or collection pipelines
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.parse import urlencode

from backend.db.clients.supabase_client import supabase
from backend.db.services.waitlist_email_service import send_waitlist_verification_email

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{3,}$", re.IGNORECASE)
_FRONTEND_BASE_URL = (
        os.getenv("FRONTEND_BASE_URL")
        or os.getenv("NEXT_PUBLIC_FRONTEND_BASE_URL")
        or "http://localhost:3000"
).rstrip("/")
_TOKEN_HASH_SECRET = os.getenv("WAITLIST_TOKEN_HASH_SECRET", "")
_TOKEN_TTL_HOURS = 24
_RESEND_COOLDOWN_SECONDS = int(os.getenv("WAITLIST_VERIFICATION_RESEND_COOLDOWN_SECONDS", "600"))

_STATUS_PENDING_VERIFICATION = "pending_verification"
_STATUS_ACTIVE = "active"

_CHECK_EMAIL_MESSAGE = "Check your email to finish joining the waitlist."
_RESEND_SENT_MESSAGE = "Verification email sent. Check your inbox."
_INVALID_TOKEN_MESSAGE = "Verification link is invalid or expired."

logger.info("waitlist_service: token_hash_secret_present=%s", bool(_TOKEN_HASH_SECRET))

# --------------------------------------------------------------------------- #
# Private helpers                                                              #
# --------------------------------------------------------------------------- #


def _normalise(email: str) -> str:
    """Trim whitespace and lowercase the address."""
    return email.strip().lower()


def _is_valid_format(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _hash_token(raw_token: str) -> str:
    digest_input = f"{_TOKEN_HASH_SECRET}:{raw_token}".encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def _hash_prefix(value: str) -> str:
    return (value or "")[:8]


def _build_verification_url(raw_token: str) -> str:
    query = urlencode({"token": raw_token})
    return f"{_FRONTEND_BASE_URL}/waitlist/verify?{query}"


def _fetch_signup_by_email(email: str) -> dict | None:
    result = (
        supabase.table("waitlist_signups")
        .select("id,email,status,verification_sent_at,verified_at")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


def _send_verification(email: str, source: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    logger.info(
        "waitlist_signup: token_generated secret_present=%s token_len=%s hash_prefix=%s email=%s source=%s",
        bool(_TOKEN_HASH_SECRET),
        len(raw_token),
        _hash_prefix(token_hash),
        email,
        source,
    )
    verification_url = _build_verification_url(raw_token)
    send_waitlist_verification_email(
        recipient_email=email,
        verification_url=verification_url,
        source=source,
    )
    return token_hash


def _is_resend_allowed(signup_row: dict) -> bool:
    sent_at = _parse_timestamp(signup_row.get("verification_sent_at"))
    if sent_at is None:
        return True
    return (_now_utc() - sent_at) >= timedelta(seconds=_RESEND_COOLDOWN_SECONDS)


def _verification_token_is_expired(signup_row: dict) -> bool:
    sent_at = _parse_timestamp(signup_row.get("verification_sent_at"))
    if sent_at is None:
        return True
    return (_now_utc() - sent_at) > timedelta(hours=_TOKEN_TTL_HOURS)


def _pending_response() -> tuple[dict, None]:
    return {
        "status": "verification_pending",
        "message": _CHECK_EMAIL_MESSAGE,
    }, None


def _resend_sent_response() -> tuple[dict, None]:
    return {
        "status": "verification_pending",
        "message": _RESEND_SENT_MESSAGE,
    }, None


def _server_error_response() -> tuple[dict, dict]:
    return {}, {
        "status": "server_error",
        "message": "Signup failed. Please try again.",
        "http_status": 500,
    }


def _handle_existing_signup(signup_row: dict, source: str) -> tuple[dict, dict | None]:
    signup_id = signup_row.get("id")
    status = str(signup_row.get("status") or "").strip().lower()

    if status == _STATUS_ACTIVE:
        return {
            "status": "already_exists",
            "message": "You're already on the list.",
        }, None

    if status == _STATUS_PENDING_VERIFICATION:
        if not _is_resend_allowed(signup_row):
            return _pending_response()

        token_hash = _send_verification(str(signup_row.get("email") or ""), source)
        supabase.table("waitlist_signups").update(
            {
                "verification_token_hash": token_hash,
                "verification_sent_at": _to_iso_z(_now_utc()),
                "source": source,
            }
        ).eq("id", signup_id).execute()
        return _resend_sent_response()

    token_hash = _send_verification(str(signup_row.get("email") or ""), source)
    supabase.table("waitlist_signups").update(
        {
            "status": _STATUS_PENDING_VERIFICATION,
            "verified_at": None,
            "verification_token_hash": token_hash,
            "verification_sent_at": _to_iso_z(_now_utc()),
            "source": source,
        }
    ).eq("id", signup_id).execute()
    return _pending_response()


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def insert_waitlist_signup(
    email: str,
    source: str = "landing_page",
) -> Tuple[dict, dict | None]:
    """Attempt to insert or re-send verification for a waitlist signup."""
    normalised = _normalise(email)

    if not normalised or not _is_valid_format(normalised):
        return {}, {
            "status": "invalid_email",
            "message": "Please enter a valid email address.",
            "http_status": 400,
        }

    try:
        existing_signup = _fetch_signup_by_email(normalised)
        if existing_signup:
            return _handle_existing_signup(existing_signup, source)

        token_hash = _send_verification(normalised, source)
        response = (
            supabase.table("waitlist_signups")
            .insert(
                {
                    "email": normalised,
                    "source": source,
                    "status": _STATUS_PENDING_VERIFICATION,
                    "verified_at": None,
                    "verification_token_hash": token_hash,
                    "verification_sent_at": _to_iso_z(_now_utc()),
                }
            )
            .execute()
        )

        if response.data:
            logger.info("waitlist_signup: pending_verification email=%s source=%s", normalised, source)
            return _pending_response()

        # Supabase returned no data and no exception — treat as server error.
        logger.warning("waitlist_signup: insert returned empty data email=%s", normalised)
        return _server_error_response()

    except Exception as exc:
        exc_msg = str(exc)
        if "duplicate key" in exc_msg or "unique" in exc_msg.lower():
            existing_signup = _fetch_signup_by_email(normalised)
            if existing_signup:
                return _handle_existing_signup(existing_signup, source)
            return {
                "status": "already_exists",
                "message": "You're already on the list.",
            }, None

        logger.exception("waitlist_signup: unexpected error email=%s", normalised)
        return _server_error_response()


def verify_waitlist_signup_token(token: str) -> Tuple[dict, dict | None]:
    """Verify an emailed waitlist token and activate the signup."""
    raw_token = (token or "").strip()
    if not raw_token:
        return {}, {
            "status": "invalid_or_expired",
            "message": _INVALID_TOKEN_MESSAGE,
            "http_status": 400,
        }

    token_hash = _hash_token(raw_token)
    logger.info(
        "waitlist_verify: token_received secret_present=%s token_len=%s hash_prefix=%s",
        bool(_TOKEN_HASH_SECRET),
        len(raw_token),
        _hash_prefix(token_hash),
    )

    try:
        result = (
            supabase.table("waitlist_signups")
            .select("id,email,status,verified_at,verification_sent_at")
            .eq("verification_token_hash", token_hash)
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
        if not row:
            recent_pending = (
                supabase.table("waitlist_signups")
                .select("id", count="exact")
                .eq("status", _STATUS_PENDING_VERIFICATION)
                .gte("created_at", _to_iso_z(_now_utc() - timedelta(hours=24)))
                .limit(1)
                .execute()
            )
            recent_pending_count = recent_pending.count if recent_pending is not None else None

            recent_verified = (
                supabase.table("waitlist_signups")
                .select("id,email,verified_at", count="exact")
                .eq("status", _STATUS_ACTIVE)
                .gte("verified_at", _to_iso_z(_now_utc() - timedelta(hours=_TOKEN_TTL_HOURS)))
                .limit(2)
                .execute()
            )
            recent_verified_rows = recent_verified.data or []
            recent_verified_count = (
                recent_verified.count if recent_verified is not None and recent_verified.count is not None else len(recent_verified_rows)
            )

            if recent_verified_count == 1:
                logger.info(
                    "waitlist_verify: hash_not_found_fallback_already_verified hash_prefix=%s",
                    _hash_prefix(token_hash),
                )
                return {
                    "status": "already_verified",
                    "message": "You're already on the list.",
                }, None

            logger.warning(
                "waitlist_verify: hash_not_found hash_prefix=%s recent_pending_count=%s recent_verified_count=%s",
                _hash_prefix(token_hash),
                recent_pending_count,
                recent_verified_count,
            )
            return {}, {
                "status": "invalid_or_expired",
                "message": _INVALID_TOKEN_MESSAGE,
                "http_status": 400,
            }

        signup_id = row.get("id")
        current_status = str(row.get("status") or "").strip().lower()
        is_verified = row.get("verified_at") is not None

        if _verification_token_is_expired(row):
            supabase.table("waitlist_signups").update(
                {"verification_token_hash": None}
            ).eq("id", signup_id).execute()
            return {}, {
                "status": "invalid_or_expired",
                "message": _INVALID_TOKEN_MESSAGE,
                "http_status": 400,
            }

        if current_status == _STATUS_ACTIVE and is_verified:
            return {
                "status": "already_verified",
                "message": "You're already on the list.",
            }, None

        if current_status != _STATUS_PENDING_VERIFICATION:
            return {}, {
                "status": "invalid_or_expired",
                "message": _INVALID_TOKEN_MESSAGE,
                "http_status": 400,
            }

        supabase.table("waitlist_signups").update(
            {
                "status": _STATUS_ACTIVE,
                "verified_at": _to_iso_z(_now_utc()),
            }
        ).eq("id", signup_id).execute()

        return {
            "status": "verified",
            "message": "You're on the list.",
        }, None

    except Exception:
        logger.exception("waitlist_verify: unexpected error")
        return {}, {
            "status": "server_error",
            "message": "Verification failed. Please try again.",
            "http_status": 500,
        }
