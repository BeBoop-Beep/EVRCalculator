"""FastAPI endpoints for frontend proxy consumption."""

from __future__ import annotations

import logging
import os
from time import perf_counter
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel  # type: ignore[reportMissingImports]

from backend.db.services.collection_freshness_service import (
    ensure_fresh_user_collection_summary,
)
from backend.db.services.collection_portfolio_service import (
    get_collection_entry_detail_for_user_id,
    get_collection_items_for_user_id,
    get_current_user_portfolio_dashboard_data,
    get_public_collection_entry_by_username_and_item_id,
    get_public_collection_data_by_username,
)
from backend.db.services.collection_summary_service import (
    refresh_user_summary_with_history_and_deltas,
    run_daily_portfolio_reconciliation_all_users,
)
from backend.db.services.frontend_proxy_service import (
    get_current_profile,
    get_me,
    get_products,
    get_public_profile,
    search_ebay_items,
    get_tcg_options,
    login_user,
    login_user_legacy,
    resend_confirmation_email,
    signup_user,
    update_customer_password,
    update_customer_profile,
    update_profile,
)


openapi_tags = [
    {
        "name": "Auth",
        "description": "Identity, authentication, and session access endpoints.",
    },
    {
        "name": "Collection Dashboard",
        "description": "Aggregate portfolio and showcase summary endpoints for dashboard surfaces.",
    },
    {
        "name": "Collection Items",
        "description": "Collection browser grid and entry detail endpoints for private and public views.",
    },
    {
        "name": "Portfolio Jobs",
        "description": "Operational portfolio maintenance job endpoints.",
    },
    {
        "name": "Health",
        "description": "Service monitoring and health check endpoints.",
    },
]


app = FastAPI(
    title="EVR Collection API",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


@app.on_event("startup")
def _startup_event() -> None:
    """Initialize background scheduler on API startup."""
    try:
        from backend.jobs.scheduler_service import initialize_scheduler
        
        initialize_scheduler()
        logger.info("api_main: background scheduler initialized on startup")
    except Exception as exc:
        logger.warning(
            "api_main: failed to initialize background scheduler error=%s (nightly jobs will not run unless triggered manually)",
            exc,
        )
        # Don't fail startup - the REST API should still work


@app.on_event("shutdown")
def _shutdown_event() -> None:
    """Stop background scheduler on API shutdown."""
    try:
        from backend.jobs.scheduler_service import stop_scheduler
        
        stop_scheduler()
        logger.info("api_main: background scheduler stopped")
    except Exception as exc:
        logger.warning("api_main: error stopping scheduler error=%s", exc)


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class ResendConfirmationRequest(BaseModel):
    email: str


def _auth_env_presence() -> Dict[str, bool]:
    return {
        "JWT_SECRET": bool(os.getenv("JWT_SECRET")),
        "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_SERVICE_ROLE_KEY": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "SUPABASE_ANON_KEY": bool(os.getenv("SUPABASE_ANON_KEY")),
    }


def _is_truthy(value: Optional[str]) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"1", "true", "yes"}


def _require_user_id(user_id_query: Optional[str], user_id_header: Optional[str]) -> str:
    user_id = (user_id_header or user_id_query or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _extract_token(authorization: Optional[str], token_cookie: Optional[str]) -> Optional[str]:
    logger.info(
        "auth_token_extract: cookie_present=%s authorization_present=%s authorization_bearer=%s",
        bool(token_cookie),
        bool(authorization),
        bool(authorization and authorization.lower().startswith("bearer ")),
    )
    if token_cookie:
        return token_cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def _extract_token_source(authorization: Optional[str], token_cookie: Optional[str]) -> str:
    if token_cookie:
        return "cookie"
    if authorization and authorization.lower().startswith("bearer "):
        return "authorization"
    return "none"


def _resolve_correlation_id(incoming_value: Optional[str]) -> str:
    normalized = str(incoming_value or "").strip()
    return normalized or str(uuid4())


def _as_http_500_with_detail(error_message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=error_message)


@app.get(
    "/collection/dashboard",
    tags=["Collection Dashboard"],
    summary="Get Collection Dashboard",
    description=(
        "Returns aggregate portfolio and showcase summary data for the dashboard/header surfaces. "
        "This endpoint is for summary metrics and is not the collection item grid feed."
    ),
)
def get_collection_dashboard(
    include_collection_items: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
):
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)
    include_items = _is_truthy(include_collection_items)

    # Freshness safety net: ensure summary is not stale before returning
    try:
        ensure_fresh_user_collection_summary(resolved_user_id)
    except Exception as exc:
        logger.warning(
            "collection_dashboard.freshness_check failed user_id=%s error=%s (continuing with potentially stale data)",
            resolved_user_id,
            exc,
        )
        # Don't fail the endpoint if freshness check fails - just continue with potentially stale summary

    dashboard_payload = get_current_user_portfolio_dashboard_data(resolved_user_id)
    if not include_items:
        return {"dashboard": dashboard_payload}

    items = get_collection_items_for_user_id(resolved_user_id, include_private_fields=True)
    return {
        "dashboard": dashboard_payload,
        "collection_items": items,
    }


@app.post(
    "/collection/summary/refresh",
    tags=["Collection Dashboard"],
    summary="Refresh Collection Dashboard Summary",
    description=(
        "Recomputes and returns refreshed aggregate collection summary data for dashboard/showcase metrics. "
        "This is a summary refresh endpoint, not an item-level grid endpoint."
    ),
)
def refresh_collection_summary(
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
):
    """Recompute and return user summary with portfolio snapshot/delta refresh.

    Orchestration insertion note:
    - Route/controller: backend/api/main.py::refresh_collection_summary
    - Service orchestration: backend/db/services/collection_summary_service.py::refresh_user_summary_with_history_and_deltas
    - Repository/DB access: backend/db/repositories/user_collection_summary_repository.py
    """
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)

    try:
        refreshed_summary = refresh_user_summary_with_history_and_deltas(resolved_user_id)
    except RuntimeError as exc:
        raise _as_http_500_with_detail(str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "collection_summary.refresh_endpoint unexpected_failure user_id=%s error_type=%s",
            resolved_user_id,
            type(exc).__name__,
        )
        raise _as_http_500_with_detail("Failed to refresh collection summary") from exc

    return {"collection_summary": refreshed_summary}


@app.post(
    "/jobs/portfolio/daily-reconciliation",
    tags=["Portfolio Jobs"],
    summary="Run Portfolio Daily Reconciliation Job",
    description=(
        "Runs portfolio reconciliation maintenance across users for operational/system workflows. "
        "This endpoint is for background/admin job execution, not normal interactive browsing."
    ),
)
def run_portfolio_daily_reconciliation_job():
    """Backend-invokable entry point for scheduler/cron daily reconciliation."""
    try:
        result = run_daily_portfolio_reconciliation_all_users()
    except RuntimeError as exc:
        raise _as_http_500_with_detail(str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "collection_summary.daily_reconciliation_endpoint unexpected_failure error_type=%s",
            type(exc).__name__,
        )
        raise _as_http_500_with_detail("Failed to run daily portfolio reconciliation") from exc

    return result


@app.get(
    "/collection/items",
    tags=["Collection Items"],
    summary="Get Private Collection Items",
    description=(
        "Returns the authenticated user's private collection browser items/grid data, including item-level rows. "
        "This endpoint is for item listings and not dashboard aggregate metrics."
    ),
)
def get_collection_items(
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    include_private_fields: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    endpoint_started_at = perf_counter()
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)
    correlation_id = _resolve_correlation_id(x_correlation_id)
    items = get_collection_items_for_user_id(
        resolved_user_id,
        include_private_fields=include_private_fields,
        limit=limit,
        offset=offset,
        correlation_id=correlation_id,
    )
    payload = {
        "collection_items": items,
    }
    response = JSONResponse(content=payload, status_code=200)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "collection_items.endpoint correlation_id=%s user_id=%s include_private_fields=%s path_used=%s item_count=%s payload_size_bytes=%s limit=%s offset=%s endpoint_ms=%.2f",
        correlation_id,
        resolved_user_id,
        include_private_fields,
        "full_assembly_bounded",
        len(items),
        len(str(payload).encode("utf-8")),
        limit,
        offset,
        (perf_counter() - endpoint_started_at) * 1000,
    )
    return response


@app.get(
    "/collection/entries/{entry_id}",
    tags=["Collection Items"],
    summary="Get Collection Entry Detail",
    description=(
        "Returns detail for a specific authenticated collection entry/item. "
        "This is an item detail endpoint and not a dashboard summary endpoint."
    ),
)
def get_collection_entry_detail(
    entry_id: str,
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    endpoint_started_at = perf_counter()
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)
    correlation_id = _resolve_correlation_id(x_correlation_id)
    entry = get_collection_entry_detail_for_user_id(
        user_id=resolved_user_id,
        entry_id=entry_id,
        include_private_fields=True,
        correlation_id=correlation_id,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Collection entry not found.")

    payload = {"entry": entry}
    response = JSONResponse(content=payload, status_code=200)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "collection_entry.endpoint correlation_id=%s user_id=%s entry_id=%s collectible_type=%s payload_size_bytes=%s endpoint_ms=%.2f",
        correlation_id,
        resolved_user_id,
        entry_id,
        entry.get("collectible_type"),
        len(str(payload).encode("utf-8")),
        (perf_counter() - endpoint_started_at) * 1000,
    )
    return response


@app.get(
    "/collection/items/public/{username}",
    tags=["Collection Items"],
    summary="Get Public Collection Items",
    description=(
        "Returns public showcase collection browser items/grid rows for a profile username. "
        "This endpoint powers public item listings, not aggregate dashboard summaries."
    ),
)
def get_public_collection_items(
    username: str,
    include_collection_items: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    endpoint_started_at = perf_counter()
    include_items = _is_truthy(include_collection_items)
    viewer_user_id = (x_user_id or user_id or "").strip() or None
    correlation_id = _resolve_correlation_id(x_correlation_id)

    payload, error = get_public_collection_data_by_username(
        username=username,
        include_collection_items=include_items,
        viewer_user_id=viewer_user_id,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset,
    )

    if error == "Invalid username.":
        raise HTTPException(status_code=400, detail=error)
    if error == "User not found.":
        raise HTTPException(status_code=404, detail=error)

    if payload is None:
        raise HTTPException(status_code=500, detail="Failed to load collection summary.")

    response = JSONResponse(content=payload, status_code=200)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "public_collection.endpoint correlation_id=%s username=%s include_items=%s endpoint_ms=%.2f",
        correlation_id,
        username,
        include_items,
        (perf_counter() - endpoint_started_at) * 1000,
    )
    return response


@app.get(
    "/collection/items/public/{username}/entry/{item_id}",
    tags=["Collection Items"],
    summary="Get Public Collection Entry Detail",
    description=(
        "Returns public detail for a single collection item entry by username and item id. "
        "This is an item detail endpoint and not a dashboard endpoint."
    ),
)
def get_public_collection_entry(
    username: str,
    item_id: str,
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    endpoint_started_at = perf_counter()
    correlation_id = _resolve_correlation_id(x_correlation_id)
    viewer_user_id = (x_user_id or user_id or "").strip() or None
    entry, error = get_public_collection_entry_by_username_and_item_id(
        username=username,
        item_id=item_id,
        viewer_user_id=viewer_user_id,
        correlation_id=correlation_id,
    )

    if error == "User not found.":
        raise HTTPException(status_code=404, detail=error)
    if error == "Collection entry not found.":
        raise HTTPException(status_code=404, detail=error)
    if entry is None:
        raise HTTPException(status_code=500, detail="Failed to load public collection entry.")

    payload = {"entry": entry}
    response = JSONResponse(content=payload, status_code=200)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "public_collection_entry.endpoint correlation_id=%s username=%s item_id=%s collectible_type=%s payload_size_bytes=%s endpoint_ms=%.2f",
        correlation_id,
        username,
        item_id,
        entry.get("collectible_type"),
        len(str(payload).encode("utf-8")),
        (perf_counter() - endpoint_started_at) * 1000,
    )
    return response


@app.get(
    "/health",
    tags=["Health"],
    summary="Get Service Health",
    description="Service health/monitoring endpoint used for readiness and basic operational checks.",
)
def health_check():
    return {"status": "ok"}


@app.get(
    "/auth/me",
    tags=["Auth"],
    summary="Get Current Authenticated User",
    description="Returns identity/session context for the current authenticated user.",
)
def auth_me(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    correlation_id = _resolve_correlation_id(x_correlation_id)
    token_source = _extract_token_source(authorization, token_cookie)
    logger.info(
        "/auth/me: request arrival correlation_id=%s authorization_present=%s token_cookie_present=%s token_source=%s",
        correlation_id,
        bool(authorization),
        bool(token_cookie),
        token_source,
    )
    payload, status = get_me(
        _extract_token(authorization, token_cookie),
        correlation_id=correlation_id,
        token_source=token_source,
    )
    response = JSONResponse(content=payload, status_code=status)
    response.headers["x-correlation-id"] = correlation_id
    return response


@app.post(
    "/auth/login",
    tags=["Auth"],
    summary="Login",
    description="Authenticates a user and returns login/session payload data for app sign-in flows.",
)
async def auth_login(payload: LoginRequest):
    logger.info("/auth/login: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/login: request body parsed successfully")

    try:
        response_payload, status = login_user(payload.email, payload.password)
        logger.info(
            "/auth/login: completed status=%s user_id_present=%s email_present=%s token_present=%s",
            status,
            bool(response_payload.get("id")),
            bool(response_payload.get("email")),
            bool(response_payload.get("token")),
        )
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/login: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.post(
    "/auth/login-legacy",
    tags=["Auth"],
    summary="Login (Legacy)",
    description="Authenticates a user via the legacy login pathway for compatibility scenarios.",
)
async def auth_login_legacy(payload: LoginRequest):
    logger.info("/auth/login-legacy: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/login-legacy: request body parsed successfully")

    try:
        response_payload, status = login_user_legacy(payload.email, payload.password)
        logger.info(
            "/auth/login-legacy: completed status=%s user_id_present=%s email_present=%s token_present=%s",
            status,
            bool(response_payload.get("id")),
            bool(response_payload.get("email")),
            bool(response_payload.get("token")),
        )
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/login-legacy: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.post(
    "/auth/signup",
    tags=["Auth"],
    summary="Signup",
    description="Creates a new user account for authentication and session onboarding flows.",
)
async def auth_signup(payload: SignupRequest):
    logger.info("/auth/signup: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/signup: request body parsed successfully")

    try:
        response_payload, status = signup_user(payload.name, payload.email, payload.password)
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/signup: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.post(
    "/auth/resend-confirmation",
    tags=["Auth"],
    summary="Resend Confirmation Email",
    description="Resends account confirmation email for authentication/account activation workflows.",
)
async def auth_resend_confirmation(payload: ResendConfirmationRequest):
    logger.info("/auth/resend-confirmation: started")

    try:
        response_payload, status = resend_confirmation_email(payload.email)
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/resend-confirmation: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.put(
    "/customer/update",
    description="Updates authenticated customer profile information.",
)
async def customer_update(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    body = await request.json()
    payload, status = update_customer_profile(_extract_token(authorization, token_cookie), body)
    return JSONResponse(content=payload, status_code=status)


@app.put(
    "/customer/update-password",
    description="Updates the authenticated customer's password.",
)
async def customer_update_password(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    body = await request.json()
    payload, status = update_customer_password(
        _extract_token(authorization, token_cookie),
        body.get("currentPassword"),
        body.get("newPassword"),
    )
    return JSONResponse(content=payload, status_code=status)


@app.get(
    "/products",
    description="Retrieves product catalog data for browsing surfaces.",
)
def products_get():
    payload, status = get_products()
    return JSONResponse(content=payload, status_code=status)


@app.get(
    "/integrations/ebay/search",
    description="Searches eBay listings via integration endpoint for marketplace lookup.",
)
def ebay_search_get(query: Optional[str] = Query(default=None)):
    payload, status = search_ebay_items(query)
    return JSONResponse(content=payload, status_code=status)


@app.get(
    "/profile/me",
    description="Returns the authenticated user's profile data.",
)
def profile_me(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    logger.info(
        "/profile/me: request arrival authorization_present=%s token_cookie_present=%s",
        bool(authorization),
        bool(token_cookie),
    )
    payload, status = get_current_profile(_extract_token(authorization, token_cookie))
    return JSONResponse(content=payload, status_code=status)


@app.put(
    "/profile/me",
    description="Updates the authenticated user's profile settings.",
)
def profile_me_update(
    payload: Dict[str, Any] = Body(default={}),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    response_payload, status = update_profile(_extract_token(authorization, token_cookie), payload)
    return JSONResponse(content=response_payload, status_code=status)


@app.get(
    "/profile/public/{username}",
    description="Returns public profile data for the specified username.",
)
def profile_public_get(
    username: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
    x_correlation_id: Optional[str] = Header(default=None, alias="x-correlation-id"),
):
    endpoint_started_at = perf_counter()
    correlation_id = _resolve_correlation_id(x_correlation_id)
    payload, status = get_public_profile(
        username,
        _extract_token(authorization, token_cookie),
        correlation_id=correlation_id,
    )
    response = JSONResponse(content=payload, status_code=status)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "public_profile.endpoint correlation_id=%s username=%s status=%s endpoint_ms=%.2f",
        correlation_id,
        username,
        status,
        (perf_counter() - endpoint_started_at) * 1000,
    )
    return response


@app.get(
    "/profile/tcgs",
    description="Returns available TCG options for profile and collection selection UI.",
)
def profile_tcgs_get():
    payload, status = get_tcg_options()
    return JSONResponse(content=payload, status_code=status)
