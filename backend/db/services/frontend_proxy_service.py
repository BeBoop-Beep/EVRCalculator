from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from backend.db.clients.supabase_client import supabase
from backend.db.services.collection_portfolio_service import get_public_collection_data_by_username
from backend.db.services.public_identity_service import normalize_profile_username, resolve_public_user_by_username

PROFILE_SELECT_FIELDS = (
    "id, email, username, display_name, bio, avatar_url, location, "
    "favorite_tcg_id, is_profile_public, show_portfolio_value, show_activity, created_at, updated_at"
)

EDITABLE_PROFILE_FIELDS = {
    "display_name",
    "bio",
    "location",
    "favorite_tcg_id",
    "is_profile_public",
    "show_portfolio_value",
    "show_activity",
}

logger = logging.getLogger(__name__)

_PROFILE_TRACE_LOG_PATH = Path(__file__).resolve().parents[2] / "profile_me_trace.log"


def _profile_me_trace(message: str, *args: Any) -> None:
    rendered = message % args if args else message
    logger.warning(rendered)
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        _PROFILE_TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PROFILE_TRACE_LOG_PATH.open("a", encoding="utf-8") as trace_file:
            trace_file.write(f"{timestamp} {rendered}\n")
    except Exception:
        # Keep tracing best-effort and never impact request flow.
        pass


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _normalize_email(email: Any) -> str:
    if not isinstance(email, str):
        return ""
    return email.strip().lower()


def _as_nullable_trimmed_string(value: Any) -> Optional[str] | Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return ...
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_favorite_tcg_id(value: Any) -> Optional[str] | Any:
    if value in (None, ""):
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return ...


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise ValueError("Server authentication is not configured.")
    return secret


def issue_token(user_id: str, email: Optional[str], name: Optional[str]) -> str:
    secret = _get_jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "id": str(user_id),
        "email": email,
        "name": name or "",
        "exp": now + timedelta(days=1),
        "iat": now,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Dict[str, Any], int]]]:
    if not token:
        return None, ({"message": "Not authenticated"}, 401)

    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
        if not isinstance(payload, dict):
            return None, ({"message": "Invalid token"}, 401)
        return payload, None
    except ValueError as exc:
        return None, ({"message": str(exc)}, 500)
    except ExpiredSignatureError:
        return None, ({"message": "Token expired"}, 401)
    except InvalidTokenError:
        return None, ({"message": "Invalid token"}, 401)


def get_profile_by_user_id(user_id: str, email: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    normalized_user_id = str(user_id or "").strip()
    normalized_email = _normalize_email(email) if isinstance(email, str) else ""

    profile = None

    _profile_me_trace(
        "[PROFILE_ME_TRACE] lookup_start user_id=%s email=%s",
        normalized_user_id,
        normalized_email,
    )

    if normalized_user_id:
        result = (
            supabase.table("users")
            .select(PROFILE_SELECT_FIELDS)
            .eq("id", normalized_user_id)
            .limit(1)
            .execute()
        )
        profile = _first_row(result)
        _profile_me_trace(
            "[PROFILE_ME_TRACE] primary_lookup_by_id ran=true row_found=%s",
            bool(profile),
        )
    else:
        _profile_me_trace("[PROFILE_ME_TRACE] primary_lookup_by_id ran=false row_found=false")

    # Some legacy tokens may carry an id that does not match users.id.
    # Fall back to token email so profile fields still resolve.
    if not profile and normalized_email:
        _profile_me_trace("[PROFILE_ME_TRACE] fallback_lookup_by_email ran=true")
        result = (
            supabase.table("users")
            .select(PROFILE_SELECT_FIELDS)
            .eq("email", normalized_email)
            .limit(1)
            .execute()
        )
        profile = _first_row(result)
        _profile_me_trace(
            "[PROFILE_ME_TRACE] fallback_lookup_by_email row_found=%s",
            bool(profile),
        )
    elif not profile:
        _profile_me_trace("[PROFILE_ME_TRACE] fallback_lookup_by_email ran=false row_found=false")

    if not profile:
        return None, "Profile not found"

    favorite_tcg_id = profile.get("favorite_tcg_id")
    favorite_tcg_name = None

    if favorite_tcg_id:
        tcg_result = (
            supabase.table("tcgs")
            .select("id, name")
            .eq("id", favorite_tcg_id)
            .limit(1)
            .execute()
        )
        tcg = _first_row(tcg_result)
        favorite_tcg_name = tcg.get("name") if tcg else None

    return {
        **profile,
        "favorite_tcg_name": favorite_tcg_name,
    }, None


def login_user(email: Any, password: Any) -> Tuple[Dict[str, Any], int]:
    normalized_email = _normalize_email(email)
    if not normalized_email or not isinstance(password, str) or not password:
        return {"message": "Email and password are required."}, 400

    logger.info("login_user: attempting sign_in_with_password email_present=%s", bool(normalized_email))

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": normalized_email,
                "password": password,
            }
        )
    except Exception as exc:
        logger.exception("login_user: supabase sign_in_with_password failed (%s)", type(exc).__name__)
        return {"message": "Invalid credentials"}, 401

    user = getattr(auth_response, "user", None)
    if not user:
        return {"message": "Invalid credentials"}, 401

    user_id = getattr(user, "id", None)
    user_email = getattr(user, "email", None)
    user_metadata = getattr(user, "user_metadata", {}) or {}

    user_name = user_metadata.get("username") or user_metadata.get("name") or ""

    try:
        profile_result = (
            supabase.table("users")
            .select("username, email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile = _first_row(profile_result)
        if profile and isinstance(profile.get("username"), str) and profile.get("username"):
            user_name = profile.get("username")
    except Exception:
        profile = None

    token = issue_token(str(user_id), user_email, user_name)

    return {
        "id": user_id,
        "email": user_email,
        "name": user_name,
        "token": token,
    }, 200


def login_user_legacy(email: Any, password: Any) -> Tuple[Dict[str, Any], int]:
    normalized_email = _normalize_email(email)
    if not normalized_email or not isinstance(password, str) or not password:
        return {"message": "Email and password are required."}, 400

    logger.info("login_user_legacy: attempting sign_in_with_password email_present=%s", bool(normalized_email))

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": normalized_email,
                "password": password,
            }
        )
    except Exception as exc:
        logger.exception("login_user_legacy: supabase sign_in_with_password failed (%s)", type(exc).__name__)
        return {"message": str(exc) or "Invalid email or password."}, 401

    user = getattr(auth_response, "user", None)
    if not user:
        return {"message": "Invalid email or password."}, 400

    user_id = getattr(user, "id", None)
    user_email = getattr(user, "email", None)
    user_metadata = getattr(user, "user_metadata", {}) or {}

    user_name = user_metadata.get("username") or user_metadata.get("name") or ""

    try:
        profile_result = (
            supabase.table("users")
            .select("username, email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile = _first_row(profile_result)
        if profile and isinstance(profile.get("username"), str) and profile.get("username"):
            user_name = profile.get("username")
    except Exception:
        pass

    token = issue_token(str(user_id), user_email, user_name)

    return {
        "id": user_id,
        "name": user_name,
        "email": user_email,
        "token": token,
    }, 200


def signup_user(name: Any, email: Any, password: Any) -> Tuple[Dict[str, Any], int]:
    normalized_email = _normalize_email(email)
    if not isinstance(name, str) or not name.strip() or not normalized_email or not isinstance(password, str) or not password:
        return {"error": "Please provide all required fields."}, 400

    user_name = name.strip()

    logger.info("signup_user: attempting sign_up name_present=%s email_present=%s", bool(user_name), bool(normalized_email))

    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": normalized_email,
                "password": password,
                "options": {
                    "data": {
                        "username": user_name,
                    }
                },
            }
        )
    except Exception as exc:
        message = str(exc) or "Signup failed."
        logger.exception("signup_user: supabase sign_up failed (%s)", type(exc).__name__)
        normalized_message = message.lower()
        is_client_input_error = any(
            token in normalized_message
            for token in ("invalid", "required", "password", "email", "already")
        )
        return {"error": message}, 400 if is_client_input_error else 500

    user = getattr(auth_response, "user", None)
    session = getattr(auth_response, "session", None)

    if not user:
        return {"error": "Signup failed."}, 500

    user_id = getattr(user, "id", None)

    try:
        supabase.table("users").upsert(
            {
                "id": user_id,
                "email": normalized_email,
                "username": user_name,
            },
            on_conflict="id",
        ).execute()
    except Exception as exc:
        logger.exception("signup_user: failed to upsert profile row (%s)", type(exc).__name__)
        return {"error": "Failed to create customer profile."}, 500

    if not session:
        return {
            "message": "Signup successful. Please confirm your email before logging in.",
            "requiresEmailConfirmation": True,
            "user": {
                "id": user_id,
                "name": user_name,
                "email": normalized_email,
            },
        }, 201

    token = issue_token(str(user_id), normalized_email, user_name)

    return {
        "message": "Signup successful",
        "user": {
            "id": user_id,
            "name": user_name,
            "email": normalized_email,
        },
        "token": token,
    }, 201


def get_me(token: Optional[str]) -> Tuple[Dict[str, Any], int]:
    token_user, token_error = decode_token(token)
    if token_error:
        return token_error

    user_id = str(token_user.get("id") or "").strip()
    token_email = token_user.get("email") if isinstance(token_user.get("email"), str) else None
    if not user_id:
        return {"message": "Invalid token"}, 401

    username = token_user.get("username")
    display_name = None

    try:
        profile, _ = get_profile_by_user_id(user_id, token_email)
        if profile:
            username = profile.get("username") or username
            display_name = profile.get("display_name")
    except Exception:
        pass

    user = {
        **token_user,
        "username": username,
        "display_name": display_name,
    }

    return {"user": user}, 200


def update_customer_profile(token: Optional[str], payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    token_user, token_error = decode_token(token)
    if token_error:
        message = token_error[0].get("message")
        if message == "Invalid token":
            return {"message": "Invalid or expired token"}, 401
        return token_error

    update_fields: Dict[str, Any] = {}
    name = payload.get("name")
    email = payload.get("email")

    if isinstance(name, str) and name.strip():
        update_fields["username"] = name.strip()

    normalized_email = _normalize_email(email)
    if normalized_email:
        update_fields["email"] = normalized_email

    if not update_fields:
        return {"message": "No fields provided for update"}, 400

    user_id = str(token_user.get("id") or "")
    if not user_id:
        return {"message": "Invalid or expired token"}, 401

    try:
        result = (
            supabase.table("users")
            .update(update_fields)
            .eq("id", user_id)
            .select("id, username, email")
            .limit(1)
            .execute()
        )
        updated_customer = _first_row(result)
    except Exception:
        return {"message": "Failed to update customer"}, 500

    if not updated_customer:
        return {"message": "Customer not found"}, 404

    token = issue_token(
        str(updated_customer.get("id")),
        updated_customer.get("email"),
        updated_customer.get("username"),
    )

    return {
        "id": updated_customer.get("id"),
        "name": updated_customer.get("username"),
        "email": updated_customer.get("email"),
        "token": token,
    }, 200


def update_customer_password(token: Optional[str], current_password: Any, new_password: Any) -> Tuple[Dict[str, Any], int]:
    token_user, token_error = decode_token(token)
    if token_error:
        return {"error": token_error[0].get("message", "Not authenticated")}, token_error[1]

    if not isinstance(current_password, str) or not current_password or not isinstance(new_password, str) or not new_password:
        return {"error": "All fields are required"}, 400

    email = token_user.get("email")
    user_id = token_user.get("id")

    if not isinstance(email, str) or not email or not user_id:
        return {"error": "Invalid token payload"}, 401

    try:
        supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": current_password,
            }
        )
    except Exception:
        return {"error": "Current password is incorrect"}, 401

    try:
        supabase.auth.admin.update_user_by_id(str(user_id), {"password": new_password})
    except Exception:
        return {"error": "Failed to update password"}, 500

    return {"message": "Password updated successfully"}, 200


def get_products() -> Tuple[Dict[str, Any], int]:
    try:
        result = (
            supabase.table("products")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        return {"message": "Failed to fetch products"}, 500

    products = getattr(result, "data", None)
    if not isinstance(products, list):
        products = []

    return {"products": products}, 200


def get_tcg_options() -> Tuple[Dict[str, Any], int]:
    try:
        result = (
            supabase.table("tcgs")
            .select("id, name")
            .order("name", desc=False)
            .execute()
        )
    except Exception:
        return {"message": "Unable to fetch TCG options", "code": "TCG_FETCH_FAILED"}, 500

    data = getattr(result, "data", None)
    if not isinstance(data, list):
        data = []

    return {"tcgs": data}, 200


def get_public_profile(username_param: Any, viewer_token: Optional[str]) -> Tuple[Dict[str, Any], int]:
    username = str(username_param or "").strip()
    if not username:
        return {"message": "Unable to fetch public profile", "code": "PROFILE_NOT_FOUND"}, 404

    viewer_user_id = None
    token_user, _ = decode_token(viewer_token)
    if token_user and token_user.get("id"):
        viewer_user_id = str(token_user.get("id"))

    public_user, public_user_trace = resolve_public_user_by_username(username)
    if not public_user or not public_user.get("id"):
        return {"message": "Public profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    profile = None
    profile_select_candidates = [
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at,view_count,profile_view_count,views_count",
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at,view_count",
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at",
    ]

    for select_clause in profile_select_candidates:
        try:
            result = supabase.table("users").select(select_clause).eq("id", public_user.get("id")).limit(1).execute()
            profile = _first_row(result)
            break
        except Exception:
            continue

    if profile is None:
        return {"message": "Unable to fetch public profile"}, 500

    profile = normalize_profile_username(profile)

    if not profile:
        return {"message": "Public profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    if profile.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(profile.get("id")):
            return {"message": "Public profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    favorite_tcg_name = None
    favorite_tcg_id = profile.get("favorite_tcg_id")

    if favorite_tcg_id:
        try:
            tcg_result = (
                supabase.table("tcgs")
                .select("id, name")
                .eq("id", favorite_tcg_id)
                .limit(1)
                .execute()
            )
            tcg = _first_row(tcg_result)
            favorite_tcg_name = tcg.get("name") if tcg else None
        except Exception:
            favorite_tcg_name = None

    summary_payload, summary_error = get_public_collection_data_by_username(
        username=str(profile.get("username") or username),
        include_collection_items=False,
        viewer_user_id=viewer_user_id,
        resolved_public_user=public_user,
        resolved_trace=public_user_trace,
    )

    collection_summary = None
    collection_summary_warning = None
    if summary_payload:
        collection_summary = summary_payload.get("collection_summary")
    if summary_error:
        collection_summary_warning = summary_error

    profile_payload = {
        **profile,
        "favorite_tcg_name": favorite_tcg_name,
        "collection_summary": collection_summary,
        "collection_summary_warning": collection_summary_warning,
    }

    logger.warning(
        "[public-profile-debug] public profile response username=%s profile_keys=%s summary_keys=%s portfolio_value=%s",
        username,
        sorted(profile_payload.keys()),
        sorted(collection_summary.keys()) if isinstance(collection_summary, dict) else [],
        collection_summary.get("portfolio_value") if isinstance(collection_summary, dict) else None,
    )

    return {
        "profile": profile_payload
    }, 200


def get_current_profile(token: Optional[str]) -> Tuple[Dict[str, Any], int]:
    token_user, token_error = decode_token(token)
    if token_error:
        return {"message": token_error[0].get("message", "Not authenticated"), "code": "AUTH_REQUIRED"}, token_error[1]

    user_id = str(token_user.get("id") or "").strip()
    token_email = token_user.get("email") if isinstance(token_user.get("email"), str) else None
    _profile_me_trace(
        "[PROFILE_ME_TRACE] token_values user_id=%s email=%s",
        user_id,
        token_email,
    )
    if not user_id:
        _profile_me_trace("[PROFILE_ME_TRACE] response_branch=AUTH_REQUIRED")
        return {"message": "Not authenticated", "code": "AUTH_REQUIRED"}, 401

    try:
        profile, profile_error = get_profile_by_user_id(user_id, token_email)
    except Exception:
        logger.exception("[PROFILE_ME_TRACE] response_branch=UNABLE_TO_FETCH_PROFILE_EXCEPTION")
        _profile_me_trace("[PROFILE_ME_TRACE] response_branch=UNABLE_TO_FETCH_PROFILE_EXCEPTION")
        return {"message": "Unable to fetch profile"}, 500

    if profile_error:
        if profile_error == "Profile not found":
            _profile_me_trace("[PROFILE_ME_TRACE] response_branch=PROFILE_NOT_FOUND")
            return {"message": profile_error, "code": "PROFILE_NOT_FOUND"}, 404
        _profile_me_trace("[PROFILE_ME_TRACE] response_branch=UNABLE_TO_FETCH_PROFILE")
        return {"message": "Unable to fetch profile"}, 500

    _profile_me_trace("[PROFILE_ME_TRACE] response_branch=SUCCESS")
    return {"profile": profile}, 200


def update_profile(token: Optional[str], payload: Any) -> Tuple[Dict[str, Any], int]:
    token_user, token_error = decode_token(token)
    if token_error:
        return {"message": token_error[0].get("message", "Not authenticated"), "code": "AUTH_REQUIRED"}, token_error[1]

    user_id = str(token_user.get("id") or "")
    if not user_id:
        return {"message": "Not authenticated", "code": "AUTH_REQUIRED"}, 401

    if not isinstance(payload, dict):
        return {"message": "Invalid update payload", "code": "INVALID_PAYLOAD"}, 400

    incoming_keys = list(payload.keys())
    if len(incoming_keys) == 0:
        return {"message": "No fields provided for update", "code": "EMPTY_PAYLOAD"}, 400

    for key in incoming_keys:
        if key not in EDITABLE_PROFILE_FIELDS:
            return {"message": f"Unsupported field: {key}", "code": "UNSUPPORTED_FIELD"}, 400

    normalized_favorite_tcg_id = _normalize_favorite_tcg_id(payload.get("favorite_tcg_id"))
    if payload.get("favorite_tcg_id") is not None and normalized_favorite_tcg_id is ...:
        return {
            "message": "favorite_tcg_id must be string, number, null, or empty string",
            "code": "INVALID_FAVORITE_TCG_ID",
        }, 400

    if payload.get("favorite_tcg_id") is not None and normalized_favorite_tcg_id is not None:
        try:
            tcg_result = (
                supabase.table("tcgs")
                .select("id")
                .eq("id", normalized_favorite_tcg_id)
                .limit(1)
                .execute()
            )
        except Exception:
            return {"message": "Selected favorite TCG does not exist", "code": "INVALID_FAVORITE_TCG"}, 400

        if not _first_row(tcg_result):
            return {"message": "Selected favorite TCG does not exist", "code": "INVALID_FAVORITE_TCG"}, 400

    next_payload: Dict[str, Any] = {}

    if "display_name" in payload:
        value = _as_nullable_trimmed_string(payload.get("display_name"))
        if value is ...:
            return {"message": "display_name must be a string or null", "code": "INVALID_DISPLAY_NAME"}, 400
        next_payload["display_name"] = value

    if "bio" in payload:
        value = _as_nullable_trimmed_string(payload.get("bio"))
        if value is ...:
            return {"message": "bio must be a string or null", "code": "INVALID_BIO"}, 400
        next_payload["bio"] = value

    if "location" in payload:
        value = _as_nullable_trimmed_string(payload.get("location"))
        if value is ...:
            return {"message": "location must be a string or null", "code": "INVALID_LOCATION"}, 400
        next_payload["location"] = value

    if "favorite_tcg_id" in payload:
        next_payload["favorite_tcg_id"] = normalized_favorite_tcg_id

    if "is_profile_public" in payload:
        if not isinstance(payload.get("is_profile_public"), bool):
            return {"message": "is_profile_public must be a boolean", "code": "INVALID_IS_PROFILE_PUBLIC"}, 400
        next_payload["is_profile_public"] = payload.get("is_profile_public")

    if "show_portfolio_value" in payload:
        if not isinstance(payload.get("show_portfolio_value"), bool):
            return {"message": "show_portfolio_value must be a boolean", "code": "INVALID_SHOW_PORTFOLIO_VALUE"}, 400
        next_payload["show_portfolio_value"] = payload.get("show_portfolio_value")

    if "show_activity" in payload:
        if not isinstance(payload.get("show_activity"), bool):
            return {"message": "show_activity must be a boolean", "code": "INVALID_SHOW_ACTIVITY"}, 400
        next_payload["show_activity"] = payload.get("show_activity")

    next_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            supabase.table("users")
            .update(next_payload)
            .eq("id", user_id)
            .select(PROFILE_SELECT_FIELDS)
            .limit(1)
            .execute()
        )
        updated_profile = _first_row(result)
    except Exception:
        return {"message": "Unable to update profile"}, 500

    if not updated_profile:
        return {"message": "Profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    favorite_tcg_name = None
    favorite_tcg_id = updated_profile.get("favorite_tcg_id")
    if favorite_tcg_id:
        try:
            tcg_result = (
                supabase.table("tcgs")
                .select("id, name")
                .eq("id", favorite_tcg_id)
                .limit(1)
                .execute()
            )
            tcg = _first_row(tcg_result)
            favorite_tcg_name = tcg.get("name") if tcg else None
        except Exception:
            favorite_tcg_name = None

    return {
        "profile": {
            **updated_profile,
            "favorite_tcg_name": favorite_tcg_name,
        }
    }, 200
