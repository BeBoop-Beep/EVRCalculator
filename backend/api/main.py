"""FastAPI endpoints for frontend proxy consumption."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel  # type: ignore[reportMissingImports]

from backend.db.services.collection_holdings_service import mutate_holding
from backend.db.services.collection_freshness_service import ensure_fresh_user_collection_summary
from backend.db.services.collection_portfolio_service import (
    get_collection_items_for_user_id,
    get_current_user_portfolio_dashboard_data,
    get_public_collection_data_by_username,
)
from backend.db.clients.supabase_client import public_read_client
from backend.db.services.calculation_run_query_service import get_latest_evr_run_snapshot
from backend.db.services.frontend_proxy_service import (
    decode_token,
    get_current_profile,
    get_me,
    get_products,
    get_public_profile,
    get_tcg_options,
    login_user,
    login_user_legacy,
    signup_user,
    update_customer_password,
    update_customer_profile,
    update_profile,
)
from backend.db.services.public_profile_page_service import PublicProfilePageError, get_public_profile_page_payload
from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload
from backend.db.services.explore_rip_statistics_service import (
    ExploreRipStatisticsTargetsError,
    get_rip_statistics_targets_payload,
)


app = FastAPI(title="EVR Collection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class HoldingMutateRequest(BaseModel):
    holding_type: str   # "card" | "sealed_product" | "graded_card"
    holding_id: str
    action: str         # "increment" | "decrement" | "remove"


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
    if token_cookie:
        return token_cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


@app.get("/collection/dashboard")
def get_collection_dashboard(
    include_collection_items: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
):
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)
    include_items = _is_truthy(include_collection_items)

    # Keep reads fresh without blocking mutation flows on heavy recompute work.
    try:
        ensure_fresh_user_collection_summary(UUID(resolved_user_id))
    except Exception as exc:
        logger.warning(
            "collection_dashboard.ensure_fresh failed user_id=%s error=%s",
            resolved_user_id,
            exc,
        )

    dashboard_payload = get_current_user_portfolio_dashboard_data(resolved_user_id)
    if not include_items:
        return {"dashboard": dashboard_payload}

    items = get_collection_items_for_user_id(resolved_user_id, include_private_fields=True)
    return {
        "dashboard": dashboard_payload,
        "collection_items": items,
    }


@app.get("/collection/items")
def get_collection_items(
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
):
    resolved_user_id = _require_user_id(user_id_query=user_id, user_id_header=x_user_id)
    items = get_collection_items_for_user_id(resolved_user_id, include_private_fields=True)
    return {
        "collection_items": items,
    }


@app.get("/collection/items/public/{username}")
def get_public_collection_items(
    username: str,
    include_collection_items: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
):
    include_items = _is_truthy(include_collection_items)
    viewer_user_id = (x_user_id or user_id or "").strip() or None

    payload, error = get_public_collection_data_by_username(
        username=username,
        include_collection_items=include_items,
        viewer_user_id=viewer_user_id,
        db_client=public_read_client,
    )

    if error == "Invalid username.":
        raise HTTPException(status_code=400, detail=error)
    if error == "User not found.":
        raise HTTPException(status_code=404, detail=error)

    if payload is None:
        raise HTTPException(status_code=500, detail="Failed to load collection summary.")

    return payload


@app.get("/public/profiles/{username}")
def get_public_profile_page(
    username: str,
    include_collection_items: Optional[str] = Query(default="1"),
    viewer_user_id: Optional[str] = Query(default=None),
):
    include_items = _is_truthy(include_collection_items if include_collection_items is not None else "1")

    try:
        payload = get_public_profile_page_payload(
            username=username,
            include_collection_items=include_items,
            viewer_user_id=(viewer_user_id or "").strip() or None,
        )
        return payload
    except PublicProfilePageError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/public/profiles/%s unexpected error", username)
        return JSONResponse(
            content={"message": "Unable to load public profile", "code": "PUBLIC_PROFILE_PAGE_FAILED"},
            status_code=500,
        )


@app.post("/collection/holdings/mutate")
async def collection_holdings_mutate(
    payload: HoldingMutateRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Increment, decrement, or remove a holding.  Requires a valid JWT."""
    token = _extract_token(authorization, token_cookie)
    token_user, token_error = decode_token(token)
    if token_error:
        error_body, status_code = token_error
        return JSONResponse(content=error_body, status_code=status_code)

    user_id = str(token_user.get("id") or "").strip()
    if not user_id:
        return JSONResponse(content={"message": "Not authenticated"}, status_code=401)

    result, error = mutate_holding(
        user_id=user_id,
        holding_type=payload.holding_type,
        holding_id=payload.holding_id,
        action=payload.action,
    )

    if error:
        return JSONResponse(content={"message": error["message"]}, status_code=error["status"])

    return JSONResponse(content=result, status_code=200)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/evr/runs/latest")
def get_latest_evr_run(
    target_type: str = Query(...),
    target_id: str = Query(...),
):
    snapshot = get_latest_evr_run_snapshot(target_type=target_type, target_id=target_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No EVR run snapshot found")
    return {"snapshot": snapshot}


@app.get("/explore/page")
def get_explore_page(
    target_type: str = Query(...),
    target_id: str = Query(...),
    limit_distribution_bins: Optional[str] = Query(default=None),
    limit_top_hits: Optional[str] = Query(default=None),
):
    """Return complete Explore page payload for a target (set, edition, pack, etc.)."""
    try:
        payload = get_explore_page_payload(
            target_type=target_type,
            target_id=target_id,
            limit_distribution_bins=limit_distribution_bins,
            limit_top_hits=limit_top_hits,
        )
        return payload
    except ExplorePageError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception as exc:
        logger.exception(
            "/explore/page unexpected error target_type=%s target_id=%s",
            target_type,
            target_id,
        )
        return JSONResponse(
            content={"message": "Unable to load explore page data", "code": "EXPLORE_PAGE_FAILED"},
            status_code=500,
        )


@app.get("/explore/rip-statistics/targets")
def get_explore_rip_statistics_targets(
    limit: Optional[str] = Query(default=None),
):
    """Return available RIP Statistics targets plus the best default target."""
    try:
        return get_rip_statistics_targets_payload(limit=limit)
    except ExploreRipStatisticsTargetsError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/explore/rip-statistics/targets unexpected error")
        return JSONResponse(
            content={"message": "Unable to load RIP Statistics targets", "code": "RIP_STATISTICS_TARGETS_FAILED"},
            status_code=500,
        )


@app.get("/auth/me")
def auth_me(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    payload, status = get_me(_extract_token(authorization, token_cookie))
    return JSONResponse(content=payload, status_code=status)


@app.post("/auth/login")
async def auth_login(payload: LoginRequest):
    logger.info("/auth/login: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/login: request body parsed successfully")

    try:
        response_payload, status = login_user(payload.email, payload.password)
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/login: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.post("/auth/login-legacy")
async def auth_login_legacy(payload: LoginRequest):
    logger.info("/auth/login-legacy: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/login-legacy: request body parsed successfully")

    try:
        response_payload, status = login_user_legacy(payload.email, payload.password)
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/login-legacy: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.post("/auth/signup")
async def auth_signup(payload: SignupRequest):
    logger.info("/auth/signup: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/signup: request body parsed successfully")

    try:
        response_payload, status = signup_user(payload.name, payload.email, payload.password)
        return JSONResponse(content=response_payload, status_code=status)
    except Exception:
        logger.exception("/auth/signup: unexpected error")
        return JSONResponse(content={"message": "Unexpected server error"}, status_code=500)


@app.put("/customer/update")
async def customer_update(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    body = await request.json()
    payload, status = update_customer_profile(_extract_token(authorization, token_cookie), body)
    return JSONResponse(content=payload, status_code=status)


@app.put("/customer/update-password")
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


@app.get("/products")
def products_get():
    payload, status = get_products()
    return JSONResponse(content=payload, status_code=status)


@app.get("/profile/me")
def profile_me(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    token = _extract_token(authorization, token_cookie)
    has_cookie_header = bool(request.headers.get("cookie"))
    has_authorization_header = bool(request.headers.get("authorization"))

    resolved_user_id = None
    try:
        token_user, token_error = decode_token(token)
        if not token_error and token_user:
            resolved_user_id = str(token_user.get("id") or "").strip() or None
    except Exception:
        resolved_user_id = None

    try:
        payload, status = get_current_profile(token)
    except Exception as exc:
        logger.exception(
            "/profile/me unhandled exception path=%s user_id=%r has_cookie_header=%s has_authorization_header=%s exception_type=%s exception_message=%s",
            request.url.path,
            resolved_user_id,
            has_cookie_header,
            has_authorization_header,
            type(exc).__name__,
            str(exc),
        )
        return JSONResponse(content={"message": "Unable to fetch profile"}, status_code=500)

    if status >= 500:
        logger.error(
            "/profile/me failed path=%s user_id=%r has_cookie_header=%s has_authorization_header=%s profile_found=%s status=%s message=%r",
            request.url.path,
            resolved_user_id,
            has_cookie_header,
            has_authorization_header,
            bool(isinstance(payload, dict) and isinstance(payload.get("profile"), dict)),
            status,
            payload.get("message") if isinstance(payload, dict) else None,
        )

    return JSONResponse(content=payload, status_code=status)


@app.put("/profile/me")
def profile_me_update(
    payload: Dict[str, Any] = Body(default={}),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    response_payload, status = update_profile(_extract_token(authorization, token_cookie), payload)
    return JSONResponse(content=response_payload, status_code=status)


@app.get("/profile/public/{username}")
def profile_public_get(
    username: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    payload, status = get_public_profile(username, _extract_token(authorization, token_cookie))
    return JSONResponse(content=payload, status_code=status)


@app.get("/profile/tcgs")
def profile_tcgs_get():
    payload, status = get_tcg_options()
    return JSONResponse(content=payload, status_code=status)
