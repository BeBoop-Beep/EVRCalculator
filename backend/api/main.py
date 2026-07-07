"""FastAPI endpoints for frontend proxy consumption."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel  # type: ignore[reportMissingImports]

from backend.db.services.waitlist_signup_service import (
    insert_waitlist_signup,
    verify_waitlist_signup_token,
)
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
    update_customer_password,
    update_customer_profile,
    update_profile,
)
from backend.db.services.public_profile_page_service import PublicProfilePageError, get_public_profile_page_payload
from backend.db.services.explore_page_service import ExplorePageError, get_explore_page_payload
from backend.db.services.explore_rip_statistics_service import (
    ExploreRipStatisticsTargetsError,
)
from backend.db.services.pokemon_sets_catalog_service import (
    PokemonSetsCatalogError,
    get_pokemon_sets_catalog_payload,
)
from backend.db.services.pokemon_set_cards_service import (
    PokemonSetCardsError,
)
from backend.db.services.pokemon_set_market_service import (
    PokemonSetMarketError,
)
from backend.db.services.pokemon_public_snapshot_service import (
    get_pokemon_explore_rankings_snapshot_payload,
    get_pokemon_set_card_validation_snapshot_payload,
    get_pokemon_set_cards_page_snapshot_payload,
    get_pokemon_set_cards_snapshot_payload,
    get_pokemon_set_insights_snapshot_payload,
    get_pokemon_set_market_dashboard_snapshot_payload,
    get_pokemon_set_market_movers_snapshot_payload,
    get_pokemon_set_overview_snapshot_payload,
    get_pokemon_set_page_snapshot_payload,
    get_pokemon_set_pull_rates_snapshot_payload,
    get_pokemon_set_shell_snapshot_payload,
    get_pokemon_set_top_chase_snapshot_payload,
    get_pokemon_set_top_market_cards_snapshot_payload,
    get_pokemon_set_value_history_snapshot_payload,
)


app = FastAPI(title="EVR Collection API")

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]


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


class WaitlistSignupRequest(BaseModel):
    email: str
    source: str = "landing_page"


class WaitlistVerifyRequest(BaseModel):
    token: str


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


def _parse_allowed_origins(raw_value: Optional[str]) -> List[str]:
    if not raw_value:
        return list(_DEFAULT_ALLOWED_ORIGINS)

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or list(_DEFAULT_ALLOWED_ORIGINS)


def _extract_token(authorization: Optional[str], token_cookie: Optional[str]) -> Optional[str]:
    if token_cookie:
        return token_cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def _require_authenticated_user_id(
    *,
    authorization: Optional[str],
    token_cookie: Optional[str],
    user_id_query: Optional[str] = None,
    user_id_header: Optional[str] = None,
) -> str:
    token = _extract_token(authorization, token_cookie)
    token_user, token_error = decode_token(token)
    if token_error:
        message = token_error[0].get("message", "Not authenticated")
        raise HTTPException(status_code=token_error[1], detail=message)

    authenticated_user_id = str((token_user or {}).get("id") or "").strip()
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    supplied_user_id = (user_id_header or user_id_query or "").strip()
    if supplied_user_id and supplied_user_id != authenticated_user_id:
        logger.warning(
            "private_collection.user_id_mismatch authenticated_user_id=%s supplied_user_id=%s",
            authenticated_user_id,
            supplied_user_id,
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    return authenticated_user_id


def _get_authenticated_user_id_if_present(
    *,
    authorization: Optional[str],
    token_cookie: Optional[str],
) -> Optional[str]:
    token = _extract_token(authorization, token_cookie)
    if not token:
        return None

    token_user, token_error = decode_token(token)
    if token_error:
        logger.warning(
            "public_viewer.invalid_token status=%s",
            token_error[1],
        )
        return None

    authenticated_user_id = str((token_user or {}).get("id") or "").strip()
    return authenticated_user_id or None


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(os.getenv("ALLOWED_ORIGINS")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/collection/dashboard")
def get_collection_dashboard(
    include_collection_items: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    resolved_user_id = _require_authenticated_user_id(
        authorization=authorization,
        token_cookie=token_cookie,
        user_id_query=user_id,
        user_id_header=x_user_id,
    )
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
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    resolved_user_id = _require_authenticated_user_id(
        authorization=authorization,
        token_cookie=token_cookie,
        user_id_query=user_id,
        user_id_header=x_user_id,
    )
    items = get_collection_items_for_user_id(resolved_user_id, include_private_fields=True)
    return {
        "collection_items": items,
    }


@app.get("/collection/items/public/{username}")
def get_public_collection_items(
    username: str,
    include_collection_items: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    include_items = _is_truthy(include_collection_items)
    viewer_user_id = _get_authenticated_user_id_if_present(
        authorization=authorization,
        token_cookie=token_cookie,
    )

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
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    include_items = _is_truthy(include_collection_items if include_collection_items is not None else "1")
    viewer_user_id = _get_authenticated_user_id_if_present(
        authorization=authorization,
        token_cookie=token_cookie,
    )

    try:
        payload = get_public_profile_page_payload(
            username=username,
            include_collection_items=include_items,
            viewer_user_id=viewer_user_id,
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


@app.post("/waitlist/signup")
async def waitlist_signup(payload: WaitlistSignupRequest):
    """Create or update a pending waitlist signup only. Never creates an auth user."""
    result, error = insert_waitlist_signup(
        email=payload.email,
        source=payload.source or "landing_page",
    )
    if error:
        return JSONResponse(
            content={"status": error["status"], "message": error["message"]},
            status_code=error["http_status"],
        )
    return JSONResponse(content=result, status_code=200)


@app.post("/waitlist/verify")
async def waitlist_verify(payload: WaitlistVerifyRequest):
    """Verify waitlist token and activate signup only."""
    result, error = verify_waitlist_signup_token(token=payload.token)
    if error:
        return JSONResponse(
            content={"status": error["status"], "message": error["message"]},
            status_code=error["http_status"],
        )
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
        if str(target_type or "").strip().lower() == "set":
            return get_pokemon_set_page_snapshot_payload(set_id=target_id)
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
        return get_pokemon_explore_rankings_snapshot_payload(limit=limit)
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
async def auth_signup(_payload: SignupRequest):
    logger.info("/auth/signup: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/signup: request body parsed successfully")
    return JSONResponse(
        content={"detail": "Account creation is currently invite-only."},
        status_code=403,
    )


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


@app.get("/tcgs/pokemon/sets")
def get_pokemon_sets_catalog():
    """Return Pokemon set summary metadata for the public Sets catalog page."""
    try:
        return get_pokemon_sets_catalog_payload()
    except PokemonSetsCatalogError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets unexpected error")
        return JSONResponse(
            content={"message": "Unable to load Pokemon sets", "code": "POKEMON_SETS_CATALOG_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/cards")
def get_pokemon_set_cards(set_id: str):
    """Return checklist cards for a single Pokemon set."""
    try:
        return get_pokemon_set_cards_snapshot_payload(set_id=set_id)
    except PokemonSetCardsError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/cards unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set cards", "code": "POKEMON_SET_CARDS_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/cards/page")
def get_pokemon_set_cards_page(
    set_id: str,
    page: Optional[str] = Query(default=None),
    page_size: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    rarity: Optional[str] = Query(default=None),
    movement_filter: Optional[str] = Query(default=None),
    movement_sort: Optional[str] = Query(default=None),
):
    """Return a single paginated slice of checklist cards for a Pokemon set."""
    try:
        return get_pokemon_set_cards_page_snapshot_payload(
            set_id=set_id,
            page=page or 1,
            page_size=page_size,
            sort=sort or "set-number",
            query=q,
            rarity=rarity,
            movement_filter=movement_filter,
            movement_sort=movement_sort,
        )
    except (PokemonSetCardsError, PokemonSetMarketError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/cards/page unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set cards page", "code": "POKEMON_SET_CARDS_PAGE_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/cards/validation")
def get_pokemon_set_cards_validation(
    set_id: str,
    max_cards: Optional[str] = Query(default=None),
    include_plot_rows: Optional[str] = Query(default=None),
):
    """Return the slim Insights card-validation snapshot (validation-ready
    card rows + cardAppealMarketPriceCorrelation) for a Pokemon set."""
    try:
        return get_pokemon_set_card_validation_snapshot_payload(
            set_id=set_id,
            max_cards=max_cards or 300,
            include_plot_rows=True if include_plot_rows is None else include_plot_rows,
        )
    except (PokemonSetCardsError, PokemonSetMarketError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/cards/validation unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set card validation data", "code": "POKEMON_SET_CARDS_VALIDATION_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/pull-rates")
def get_pokemon_set_pull_rates(set_id: str):
    """Return the slim Pull Rates-tab snapshot (pull rate assumptions only) for a Pokemon set."""
    try:
        return get_pokemon_set_pull_rates_snapshot_payload(set_id=set_id)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/pull-rates unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set pull rates", "code": "POKEMON_SET_PULL_RATES_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/insights")
def get_pokemon_set_insights(set_id: str):
    """Return the slim Insights-tab snapshot (RIP breakdown inputs, outcome
    distribution, simulation drivers, value/rarity contribution, and
    desirability proof) for a Pokemon set."""
    try:
        return get_pokemon_set_insights_snapshot_payload(set_id=set_id)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/insights unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set insights", "code": "POKEMON_SET_INSIGHTS_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/shell")
def get_pokemon_set_shell(set_id: str):
    """Return the lightweight header/title-card snapshot for a Pokemon set (no payload_json)."""
    try:
        return get_pokemon_set_shell_snapshot_payload(set_id=set_id)
    except ExplorePageError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/shell unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set shell snapshot", "code": "POKEMON_SET_SHELL_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/page")
def get_pokemon_set_page(set_id: str):
    """Return page-ready public Pokemon set analytics snapshot."""
    try:
        return get_pokemon_set_page_snapshot_payload(set_id=set_id)
    except ExplorePageError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/page unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set page snapshot", "code": "POKEMON_SET_PAGE_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/dashboard")
def get_pokemon_set_market_dashboard(
    set_id: str,
    window: Optional[str] = Query(default=None),
    days: Optional[str] = Query(default=None),
):
    """Return page-ready market dashboard snapshot for a Pokemon set."""
    try:
        return get_pokemon_set_market_dashboard_snapshot_payload(set_id=set_id, window=window or "365d", days=days)
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/dashboard unexpected error", set_id)
        return JSONResponse(
            content={
                "message": "Unable to load Pokemon set market dashboard",
                "code": "POKEMON_SET_MARKET_DASHBOARD_FAILED",
            },
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/overview")
def get_pokemon_set_overview(
    set_id: str,
    window: Optional[str] = Query(default=None),
):
    """Return the slim Overview-tab snapshot (set value trend + performance vs cost) for a Pokemon set."""
    try:
        return get_pokemon_set_overview_snapshot_payload(set_id=set_id, window=window or "365d")
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/overview unexpected error", set_id)
        return JSONResponse(
            content={
                "message": "Unable to load Pokemon set overview",
                "code": "POKEMON_SET_OVERVIEW_FAILED",
            },
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/top-chase")
def get_pokemon_set_top_chase(
    set_id: str,
    window: Optional[str] = Query(default=None),
    limit: Optional[str] = Query(default=None),
):
    """Return the slim Top Chase Cards snapshot for a Pokemon set."""
    try:
        return get_pokemon_set_top_chase_snapshot_payload(set_id=set_id, window=window or "30D", limit=limit)
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/top-chase unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set top chase cards", "code": "POKEMON_SET_TOP_CHASE_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/movers")
def get_pokemon_set_market_movers(
    set_id: str,
    window: Optional[str] = Query(default=None),
    limit: Optional[str] = Query(default=None),
):
    """Return market movers for a single requested window for a Pokemon set."""
    try:
        return get_pokemon_set_market_movers_snapshot_payload(set_id=set_id, window=window or "30D", limit=limit)
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/movers unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set market movers", "code": "POKEMON_SET_MARKET_MOVERS_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/top-cards")
def get_pokemon_set_top_market_cards(
    set_id: str,
    limit: Optional[str] = Query(default=None),
    days: Optional[str] = Query(default=None),
):
    """Return highest-priced real market cards for a Pokemon set."""
    try:
        return get_pokemon_set_top_market_cards_snapshot_payload(set_id=set_id, limit=limit, days=days)
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/top-cards unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set market cards", "code": "POKEMON_SET_TOP_MARKET_CARDS_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/value-history")
def get_pokemon_set_value_history(
    set_id: str,
    days: Optional[str] = Query(default=None),
    value_scope: Optional[str] = Query(default=None),
):
    """Return historical real set value snapshots for a Pokemon set."""
    try:
        return get_pokemon_set_value_history_snapshot_payload(set_id=set_id, days=days, value_scope=value_scope)
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/value-history unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set value history", "code": "POKEMON_SET_VALUE_HISTORY_FAILED"},
            status_code=500,
        )
