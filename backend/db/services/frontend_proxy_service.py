from __future__ import annotations

import logging
import os
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError, loads
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from backend.db.clients.supabase_client import create_service_role_client, reset_service_role_auth, supabase
from backend.db.services.collection_portfolio_service import get_public_collection_data_by_username
from backend.db.services.public_identity_service import (
    normalize_profile_username,
    normalize_public_username,
    resolve_public_user_by_username,
)

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


def _create_auth_client():
    return create_service_role_client()


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


def _derive_username_candidate(username_hint: Any, normalized_email: str, user_id: str) -> str:
    candidate = normalize_public_username(username_hint)
    if candidate:
        return candidate

    if normalized_email and "@" in normalized_email:
        local_part = normalized_email.split("@", 1)[0]
        candidate = normalize_public_username(local_part)
        if candidate:
            return candidate

    suffix = str(user_id or "").strip().replace("-", "")[:8]
    return f"collector-{suffix}" if suffix else "collector"


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


def get_profile_by_user_id(
    user_id: str,
    email: Optional[str] = None,
    username_hint: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    reset_service_role_auth()
    normalized_user_id = str(user_id or "").strip()
    normalized_email = _normalize_email(email) if isinstance(email, str) else ""

    profile = None

    if normalized_user_id:
        result = (
            supabase.table("users")
            .select(PROFILE_SELECT_FIELDS)
            .eq("id", normalized_user_id)
            .limit(1)
            .execute()
        )
        profile = _first_row(result)

    # Some legacy tokens may carry an id that does not match users.id.
    # Fall back to token email so profile fields still resolve.
    if not profile and normalized_email:
        result = (
            supabase.table("users")
            .select(PROFILE_SELECT_FIELDS)
            .eq("email", normalized_email)
            .limit(1)
            .execute()
        )
        profile = _first_row(result)

    # If the profile row was removed or never created, rebuild a minimal row so
    # auth identity and public profile lookups can recover.
    if not profile and normalized_user_id and normalized_email:
        username_candidate = _derive_username_candidate(username_hint, normalized_email, normalized_user_id)

        try:
            supabase.table("users").upsert(
                {
                    "id": normalized_user_id,
                    "email": normalized_email,
                    "username": username_candidate,
                },
                on_conflict="id",
            ).execute()

            result = (
                supabase.table("users")
                .select(PROFILE_SELECT_FIELDS)
                .eq("id", normalized_user_id)
                .limit(1)
                .execute()
            )
            profile = _first_row(result)
        except Exception:
            pass

    if not profile:
        return None, "Profile not found"

    profile = normalize_profile_username(profile)

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
        auth_client = _create_auth_client()
        auth_response = auth_client.auth.sign_in_with_password(
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
        auth_client = _create_auth_client()
        auth_response = auth_client.auth.sign_in_with_password(
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
        auth_client = _create_auth_client()
        auth_response = auth_client.auth.sign_up(
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


def resend_confirmation_email(email: Any) -> Tuple[Dict[str, Any], int]:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return {"message": "Email is required."}, 400

    try:
        auth_client = _create_auth_client()
        auth_client.auth.resend(
            {
                "type": "signup",
                "email": normalized_email,
            }
        )
    except Exception as exc:
        message = str(exc) or "Unable to resend confirmation email."
        logger.exception("resend_confirmation_email: supabase resend failed (%s)", type(exc).__name__)
        return {"message": message}, 400

    return {
        "message": "Confirmation email sent. Please check your inbox and spam folder."
    }, 200


def get_me(
    token: Optional[str],
    correlation_id: Optional[str] = None,
    token_source: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    logger.info(
        "auth_me.trace correlation_id=%s token_source=%s token_present=%s",
        correlation_id,
        token_source or "unknown",
        bool(token),
    )
    token_user, token_error = decode_token(token)
    if token_error:
        logger.warning(
            "auth_me.trace correlation_id=%s token_source=%s decoded_user_id=%s decoded_email=%s row_found=false reason=%s status=%s",
            correlation_id,
            token_source or "unknown",
            None,
            None,
            token_error[0].get("message"),
            token_error[1],
        )
        return token_error

    user_id = str(token_user.get("id") or "").strip()
    token_email = token_user.get("email") if isinstance(token_user.get("email"), str) else None
    token_username = token_user.get("username") if isinstance(token_user.get("username"), str) else None
    token_name = token_user.get("name") if isinstance(token_user.get("name"), str) else None
    logger.info(
        "auth_me.trace correlation_id=%s token_source=%s decoded_user_id=%s decoded_email=%s decoded_username=%s decoded_name=%s",
        correlation_id,
        token_source or "unknown",
        user_id or None,
        token_email,
        token_username,
        token_name,
    )
    if not user_id:
        return {"message": "Invalid token"}, 401

    username = token_username or token_name
    display_name = token_user.get("display_name") if isinstance(token_user.get("display_name"), str) else None
    profile_error = None

    try:
        profile, profile_error = get_profile_by_user_id(
            user_id,
            token_email,
            username_hint=(token_username or token_name),
        )
        logger.info(
            "auth_me.trace correlation_id=%s token_source=%s profile_found=%s profile_error=%s resolved_profile_id=%s resolved_username=%s resolved_display_name=%s",
            correlation_id,
            token_source or "unknown",
            bool(profile),
            profile_error,
            profile.get("id") if isinstance(profile, dict) else None,
            profile.get("username") if isinstance(profile, dict) else None,
            profile.get("display_name") if isinstance(profile, dict) else None,
        )
        if profile:
            username = profile.get("username") or username
            display_name = profile.get("display_name") or display_name
            token_email = profile.get("email") if isinstance(profile.get("email"), str) else token_email
    except Exception:
        logger.exception("auth_me.trace correlation_id=%s token_source=%s profile_resolution_exception=true", correlation_id, token_source or "unknown")

    if profile_error:
        logger.warning("auth_me.trace correlation_id=%s token_source=%s profile_resolution_warning=%s", correlation_id, token_source or "unknown", profile_error)

    if not username and token_email:
        username = token_email.split("@", 1)[0]

    normalized_username = normalize_public_username(username)
    username = normalized_username or username

    # Canonical identity label priority: display_name > username > empty.
    canonical_name = display_name or username or ""
    if not isinstance(token_user.get("name"), str) or not token_user.get("name"):
        token_user["name"] = canonical_name

    user = {
        **token_user,
        "email": token_email,
        "username": username,
        "display_name": display_name,
        "name": canonical_name,
    }

    logger.info(
        "auth_me.trace correlation_id=%s token_source=%s resolved_profile_id=%s username=%s display_name=%s",
        correlation_id,
        token_source or "unknown",
        user.get("id"),
        user.get("username"),
        user.get("display_name"),
    )

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
        auth_client = _create_auth_client()
        auth_client.auth.sign_in_with_password(
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
    reset_service_role_auth()
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
    reset_service_role_auth()
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


def search_ebay_items(query: Any) -> Tuple[Dict[str, Any], int]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"error": "Query is required"}, 400

    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {"error": "eBay integration is not configured"}, 500

    basic_token = b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    auth_body = "grant_type=client_credentials&scope=https://api.ebay.com/oauth/api_scope".encode("utf-8")
    auth_request = Request(
        "https://api.ebay.com/identity/v1/oauth2/token",
        data=auth_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_token}",
        },
        method="POST",
    )

    try:
        with urlopen(auth_request, timeout=15) as response:
            auth_payload_raw = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        logger.warning("search_ebay_items: eBay auth failed status=%s", getattr(exc, "code", None))
        return {"error": "Failed to fetch data", "details": details}, 502
    except URLError:
        logger.exception("search_ebay_items: eBay auth request failed")
        return {"error": "Failed to fetch data"}, 502

    try:
        access_token = (loads(auth_payload_raw) or {}).get("access_token")
    except (JSONDecodeError, TypeError):
        access_token = None

    if not access_token:
        return {"error": "Failed to fetch data", "details": "Missing eBay access token"}, 502

    search_query = urlencode({"q": normalized_query, "limit": 10})
    search_request = Request(
        f"https://api.ebay.com/buy/browse/v1/item_summary/search?{search_query}",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urlopen(search_request, timeout=20) as response:
            search_payload_raw = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        logger.warning("search_ebay_items: eBay browse failed status=%s", getattr(exc, "code", None))
        return {"error": "Failed to fetch data", "details": details}, 502
    except URLError:
        logger.exception("search_ebay_items: eBay browse request failed")
        return {"error": "Failed to fetch data"}, 502

    try:
        payload = loads(search_payload_raw) or {}
    except (JSONDecodeError, TypeError):
        return {"error": "Failed to fetch data", "details": "Invalid eBay response"}, 502

    summaries = payload.get("itemSummaries") if isinstance(payload, dict) else None
    if not isinstance(summaries, list):
        summaries = []

    results = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        price_obj = item.get("price") if isinstance(item.get("price"), dict) else {}
        image_obj = item.get("image") if isinstance(item.get("image"), dict) else {}
        results.append(
            {
                "title": item.get("title"),
                "price": price_obj.get("value"),
                "image": image_obj.get("imageUrl") or "",
                "platform": "eBay",
            }
        )

    return {"results": results}, 200


def get_public_profile(
    username_param: Any,
    viewer_token: Optional[str],
    correlation_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    requested_username = str(username_param or "").strip()
    normalized_username = normalize_public_username(requested_username)
    if not normalized_username:
        logger.warning(
            "public_profile.trace correlation_id=%s requested_username=%s normalized_username=%s row_found=false reason=PROFILE_NOT_FOUND",
            correlation_id,
            requested_username,
            normalized_username,
        )
        return {"message": "Unable to fetch public profile", "code": "PROFILE_NOT_FOUND"}, 404

    viewer_user_id = None
    token_user, _ = decode_token(viewer_token)
    if token_user and token_user.get("id"):
        viewer_user_id = str(token_user.get("id"))

    user, trace = resolve_public_user_by_username(normalized_username, correlation_id=correlation_id)
    if trace.get("reason") == "LOOKUP_EXCEPTION":
        return {"message": "Unable to fetch public profile"}, 500

    if not user:
        logger.warning(
            "public_profile.trace correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s row_found=false reason=%s",
            correlation_id,
            requested_username,
            normalized_username,
            trace.get("lookup_strategy"),
            trace.get("reason") or "PROFILE_NOT_FOUND",
        )
        return {"message": "Public profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    try:
        result = (
            supabase.table("users")
            .select("id, username, display_name, avatar_url, bio, is_profile_public, location, favorite_tcg_id, created_at")
            .eq("id", user.get("id"))
            .limit(1)
            .execute()
        )
        profile = normalize_profile_username(_first_row(result))
    except Exception:
        return {"message": "Unable to fetch public profile"}, 500

    if not profile:
        logger.warning(
            "public_profile.trace correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s row_found=true resolved_user_id=%s reason=PROFILE_ROW_NOT_FOUND",
            correlation_id,
            requested_username,
            normalized_username,
            trace.get("lookup_strategy"),
            user.get("id"),
        )
        return {"message": "Public profile not found", "code": "PROFILE_NOT_FOUND"}, 404

    if profile.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(profile.get("id")):
            logger.warning(
                "public_profile.trace correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s row_found=true resolved_user_id=%s reason=VISIBILITY_REJECT viewer_user_id=%s",
                correlation_id,
                requested_username,
                normalized_username,
                trace.get("lookup_strategy"),
                profile.get("id"),
                viewer_user_id,
            )
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
        username=str(profile.get("username") or normalized_username),
        include_collection_items=False,
        viewer_user_id=viewer_user_id,
        correlation_id=correlation_id,
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

    logger.info(
        "public_profile.trace correlation_id=%s requested_username=%s normalized_username=%s lookup_strategy=%s row_found=true resolved_user_id=%s resolved_username=%s display_name=%s",
        correlation_id,
        requested_username,
        normalized_username,
        trace.get("lookup_strategy"),
        profile.get("id"),
        profile.get("username"),
        profile.get("display_name"),
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
    token_name = token_user.get("name") if isinstance(token_user.get("name"), str) else None
    token_username = token_user.get("username") if isinstance(token_user.get("username"), str) else None
    token_display_name = token_user.get("display_name") if isinstance(token_user.get("display_name"), str) else None
    if not user_id:
        return {"message": "Not authenticated", "code": "AUTH_REQUIRED"}, 401

    profile = None
    profile_error = None
    try:
        profile, profile_error = get_profile_by_user_id(
            user_id,
            token_email,
            username_hint=(token_username or token_name),
        )
    except Exception:
        logger.exception("get_current_profile: unexpected exception during profile lookup")
        profile_error = "PROFILE_LOOKUP_EXCEPTION"

    if profile:
        profile = normalize_profile_username(profile)
        return {"profile": profile}, 200

    if profile_error:
        logger.warning("get_current_profile: profile resolution warning=%s", profile_error)

    # Recovery path: preserve authenticated session UX when profile row is
    # temporarily unavailable, while keeping auth ownership on backend.
    fallback_user_payload, fallback_status = get_me(token)
    if fallback_status != 200:
        if profile_error == "Profile not found":
            return {"message": "Profile not found", "code": "PROFILE_NOT_FOUND"}, 404
        return {"message": "Unable to fetch profile"}, 500

    fallback_user = fallback_user_payload.get("user") if isinstance(fallback_user_payload, dict) else None
    if not isinstance(fallback_user, dict):
        if profile_error == "Profile not found":
            return {"message": "Profile not found", "code": "PROFILE_NOT_FOUND"}, 404
        return {"message": "Unable to fetch profile"}, 500

    fallback_username = fallback_user.get("username") if isinstance(fallback_user.get("username"), str) else token_username
    fallback_display_name = (
        fallback_user.get("display_name")
        if isinstance(fallback_user.get("display_name"), str)
        else token_display_name
    )
    fallback_email = fallback_user.get("email") if isinstance(fallback_user.get("email"), str) else token_email

    minimal_profile = {
        "id": user_id,
        "email": fallback_email,
        "username": fallback_username,
        "display_name": fallback_display_name,
        "bio": None,
        "avatar_url": None,
        "location": None,
        "favorite_tcg_id": None,
        "favorite_tcg_name": None,
        "is_profile_public": None,
        "show_portfolio_value": None,
        "show_activity": None,
        "created_at": None,
        "updated_at": None,
    }

    return {
        "profile": minimal_profile,
        "profile_warning": "PROFILE_FROM_TOKEN_FALLBACK",
    }, 200


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
