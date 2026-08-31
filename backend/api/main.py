"""FastAPI endpoints for frontend proxy consumption."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel, Field  # type: ignore[reportMissingImports]
from pydantic import ConfigDict
from backend.db.services.billing_service import BillingService
from backend.domain.billing.catalog import BillingOfferNotConfigured
from backend.domain.billing.errors import BillingError, BillingProviderError, InvalidWebhookSignature

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
from backend.db.clients.supabase_client import service_read_client
from backend.db.services.public_read_retry import run_public_read_with_retry
from backend.db.services.calculation_run_query_service import get_latest_evr_run_snapshot
from backend.db.services.frontend_proxy_service import (
    decode_token,
    exchange_supabase_access_token,
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
from backend.domain.access.index_plan_access import (
    FEATURE_CARD_CHASE_EFFICIENCY,
    FEATURE_MARKET_BREADTH,
    FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
    FEATURE_PACK_ECONOMICS,
    FEATURE_PRODUCT_RIP,
    FEATURE_SET_RIP_ANALYTICS,
    evaluate_market_query_access,
    filter_set_market_signal_access,
    has_index_plus_access,
    has_index_feature_access,
    project_card_detail_response,
    project_insights_critical_response,
    project_product_rankings_response,
    project_product_family_rankings_response,
    project_public_era_rankings_response,
    project_opening_economics_response,
    project_rankings_response,
    project_sealed_market_response,
    project_sealed_product_detail_response,
    project_set_page_response,
)
from backend.db.services.chase_efficiency_query_service import (
    get_card_chase_efficiency as read_card_chase_efficiency,
    query_chase_efficiency,
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
from backend.db.services.pokemon_card_detail_service import (
    PokemonCardDetailError,
    get_pokemon_card_detail_payload,
)
from backend.db.services.pokemon_set_market_service import (
    PokemonSetMarketError,
    resolve_pokemon_set_identifier,
)
from backend.db.services.pokemon_public_snapshot_service import (
    get_pokemon_explore_rankings_snapshot_payload,
    get_pokemon_explore_rankings_lens_payload,
    get_pokemon_set_card_validation_snapshot_payload,
    get_pokemon_set_cards_page_snapshot_payload,
    get_pokemon_set_cards_snapshot_payload,
    get_pokemon_set_insights_critical_snapshot_payload,
    get_pokemon_set_insights_secondary_snapshot_payload,
    get_pokemon_set_insights_snapshot_payload,
    get_pokemon_set_simulation_evidence_snapshot_payload,
    get_pokemon_set_rip_bootstrap_snapshot_payload,
    get_pokemon_set_rip_simulation_evidence_snapshot_payload,
    get_pokemon_set_rip_advanced_snapshot_payload,
    get_pokemon_set_rip_global_context_payload,
    get_pokemon_set_rip_rank_context_payload,
    get_pokemon_set_market_dashboard_snapshot_payload,
    get_pokemon_set_market_bootstrap_snapshot_payload,
    get_pokemon_set_market_signals_snapshot_payload,
    get_pokemon_set_market_movers_snapshot_payload,
    get_pokemon_set_overview_snapshot_payload,
    get_pokemon_set_page_snapshot_payload,
    get_pokemon_set_pull_rates_snapshot_payload,
    get_pokemon_set_shell_snapshot_payload,
    get_pokemon_set_top_chase_snapshot_payload,
    get_pokemon_set_top_market_cards_snapshot_payload,
    get_pokemon_set_value_history_snapshot_payload,
)
from backend.db.services.pokemon_sealed_product_detail_service import (
    PokemonSealedProductDetailError,
    get_pokemon_sealed_product_detail_payload,
)
from backend.db.services.pokemon_set_route_directory_service import (
    get_pokemon_set_route_directory_payload,
)
from backend.db.services.pokemon_explore_card_movers_service import (
    ExploreCardMoversUnavailable,
    read_explore_card_movers_snapshot,
)
from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    read_market_explorer_snapshot,
    read_explore_set_value_snapshot,
)
from backend.db.services.pokemon_set_sealed_market_snapshot_service import read_snapshot as read_sealed_market_snapshot
from backend.db.services.pokemon_sealed_market_explorer_query_service import (
    SealedMarketExplorerQueryUnavailable,
    published_sealed_family_options,
    run_sealed_market_explorer_query,
)
from backend.db.services.pokemon_market_explorer_query_service import (
    MarketExplorerQueryUnavailable,
    build_market_explorer_filter_options,
    run_market_explorer_query,
)
from backend.db.services.market_explorer_query_planner import (
    GLOBAL_MARKET_EXPLORER_PLANNER,
    GLOBAL_PREPARED_EQUIVALENCE_REGISTRY,
    MarketExplorerBuildInProgress,
    PersistentMarketExplorerCache,
    resolve_canonical_through,
)
from backend.db.services.public_overall_product_rankings_service import read_public_overall_product_rankings
from backend.db.services.pokemon_rip_stats_service import read_public_opening_economics
from backend.domain.pokemon.market_explorer_query import (
    ASSET_SEALED,
    SUPPORTED_ASSETS,
    MarketExplorerQueryError,
    normalize_query_spec,
    query_fingerprint,
)
from backend.api.market_request_metrics import build_identity, market_request_metrics_middleware
from backend.api.paid_abuse_control import (
    POLICY_CUSTOM_QUERY,
    POLICY_INTERACTIVE_DETAIL,
    POLICY_RANKED_INTELLIGENCE,
    emit_security_event,
    paid_analytics_limiter,
)


app = FastAPI(title="EVR Collection API")

logger = logging.getLogger(__name__)

_MARKET_EXPLORER_QUERY_CACHE_TTL_SECONDS = 300
_MARKET_EXPLORER_QUERY_CACHE_MAX_ENTRIES = 128
# Backward-compatible diagnostics/test alias. The planner owns this L1; there
# is no second endpoint-local query cache.
_market_explorer_query_cache = GLOBAL_MARKET_EXPLORER_PLANNER.l1._entries
_MARKET_EXPLORER_OPTIONS_CACHE_TTL_SECONDS = 900
_market_explorer_options_cache: tuple[float, Dict[str, Any]] | None = None

_DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]


@app.middleware("http")
async def authenticated_response_cache_boundary(request: Request, call_next):
    """Never place an identity/entitlement-sensitive response in a public cache."""
    response = await call_next(request)
    if request.headers.get("authorization") or request.cookies.get("token"):
        response.headers["Cache-Control"] = "no-store"
        vary = {item.strip() for item in response.headers.get("Vary", "").split(",") if item.strip()}
        vary.update({"Cookie", "Authorization"})
        response.headers["Vary"] = ", ".join(sorted(vary))
    return response


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class SupabaseExchangeRequest(BaseModel):
    access_token: str = Field(min_length=1)


class HoldingMutateRequest(BaseModel):
    holding_type: str   # "card" | "sealed_product" | "graded_card"
    holding_id: str
    action: str         # "increment" | "decrement" | "remove"


class WaitlistSignupRequest(BaseModel):
    email: str
    source: str = "landing_page"


class WaitlistVerifyRequest(BaseModel):
    token: str


class MarketExplorerQueryRequest(BaseModel):
    asset: str = "cards"
    eraIds: List[str] = Field(default_factory=list)
    setIds: List[str] = Field(default_factory=list)
    segmentIds: List[str] = Field(default_factory=list)
    pokemonIds: List[str] = Field(default_factory=list)
    priceSegmentIds: List[str] = Field(default_factory=list)
    releaseAgeCohortIds: List[str] = Field(default_factory=list)
    mode: str = "all"
    topN: Optional[int] = Field(default=None, ge=1, le=100)


class BillingCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offerKey: str = Field(min_length=1, max_length=80)


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


def _resolve_index_plan(authorization: Optional[str], token_cookie: Optional[str]) -> Optional[str]:
    """The CANONICAL server-side plan for the caller, or None.

    Read from the profile row through the same projection `/auth/me` uses, so
    the API and the browser can never disagree about what someone is entitled
    to. A client-supplied plan claim is never trusted, and is not even accepted
    as an argument here.
    """
    payload, status = get_me(_extract_token(authorization, token_cookie))
    if status != 200:
        return None
    return ((payload or {}).get("user") or {}).get("index_plan")


def _require_market_explorer_query_access(
    spec: Dict[str, Any], *, authorization: Optional[str], token_cookie: Optional[str]
) -> str:
    """Authenticate and authorize the normalized definition before any query work."""
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    decision = evaluate_market_query_access(
        _resolve_index_plan(authorization, token_cookie), spec
    )
    if not decision["allowed"]:
        emit_security_event("entitlement_denied", route="market_explorer", policy_class=POLICY_CUSTOM_QUERY,
                            user_id=user_id, required_capability=decision["capability"],
                            authenticated=True, required_plan=decision["requiredPlan"],
                            active_filter_axes=decision["activeFilterAxes"])
        raise HTTPException(
            status_code=403,
            detail={
                "message": decision["reason"],
                "code": "MARKET_EXPLORER_PLAN_REQUIRED",
                "requiredPlan": decision["requiredPlan"],
                "requiredFeature": decision["capability"],
                "activeFilterAxes": decision["activeFilterAxes"],
            },
        )
    return user_id


def _require_card_chase_efficiency(
    *, authorization: Optional[str], token_cookie: Optional[str]
) -> str:
    """Authenticate and resolve Premium from the canonical profile server-side."""
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    if not has_index_feature_access(
        _resolve_index_plan(authorization, token_cookie), FEATURE_CARD_CHASE_EFFICIENCY
    ):
        emit_security_event("entitlement_denied", route="card_chase_efficiency",
                            policy_class=POLICY_RANKED_INTELLIGENCE, user_id=user_id,
                            required_capability=FEATURE_CARD_CHASE_EFFICIENCY, authenticated=True)
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Chase Efficiency requires Index Premium.",
                "code": "CARD_CHASE_EFFICIENCY_PREMIUM_REQUIRED",
                "requiredFeature": FEATURE_CARD_CHASE_EFFICIENCY,
            },
        )
    return user_id


def _require_index_feature(
    *, feature: str, code: str, message: str,
    authorization: Optional[str], token_cookie: Optional[str],
) -> Optional[str]:
    """Authenticate first, then resolve a capability from the canonical profile."""
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    plan = _resolve_index_plan(authorization, token_cookie)
    if not has_index_feature_access(plan, feature):
        emit_security_event("entitlement_denied", route=feature, policy_class=POLICY_INTERACTIVE_DETAIL,
                            user_id=user_id, required_capability=feature, authenticated=True,
                            normalized_plan=plan)
        raise HTTPException(
            status_code=403,
            detail={"message": message, "code": code, "requiredFeature": feature},
        )
    return user_id


def _enforce_paid_abuse(request: Request, *, user_id: str, policy_class: str, route: str) -> None:
    request_id = request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or "unassigned"
    decision = paid_analytics_limiter.check(
        policy_name=policy_class, user_id=user_id, route=route,
        headers=request.headers, client_host=request.client.host if request.client else None,
        request_id=request_id,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail={"message": "Too many requests.", "code": "PAID_ANALYTICS_RATE_LIMITED",
                    "retryAfterSeconds": decision.retry_after_seconds},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _limit_paid_projection(
    request: Request, *, authorization: Optional[str], token_cookie: Optional[str],
    feature: str, policy_class: str, route: str, access_context: Optional[Dict[str, Any]] = None,
) -> None:
    plan = access_context.get("plan") if access_context is not None else _resolve_index_plan(authorization, token_cookie)
    if not has_index_feature_access(plan, feature):
        return
    user_id = access_context.get("user_id") if access_context is not None else None
    if not user_id:
        user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    _enforce_paid_abuse(request, user_id=user_id, policy_class=policy_class, route=route)


def _resolve_request_access(
    authorization: Optional[str], token_cookie: Optional[str], *, feature: str,
) -> Dict[str, Any]:
    """Resolve the canonical profile once and reuse it throughout one request."""
    plan = _resolve_index_plan(authorization, token_cookie)
    user_id = None
    if has_index_feature_access(plan, feature):
        user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    return {"plan": plan, "user_id": user_id}


def _tiered_response(content: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=content,
        headers={"Cache-Control": "no-store", "Vary": "Cookie, Authorization"},
    )


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
app.middleware("http")(market_request_metrics_middleware)


@app.get("/health")
def get_health():
    """Deployment identity for operators; contains no configuration secrets."""
    return {"status": "ok", "build": build_identity()}


def _billing_redirect_urls() -> tuple[str, str]:
    origin = (os.getenv("FRONTEND_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
    if os.getenv("APP_ENV", "").lower() == "production" and not origin.startswith("https://"):
        raise HTTPException(status_code=503, detail={"code": "BILLING_NOT_CONFIGURED"})
    return f"{origin}/account-settings?billing=success", f"{origin}/account-settings?billing=canceled"


@app.post("/billing/checkout-session")
def create_billing_checkout_session(
    payload: BillingCheckoutRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    success_url, cancel_url = _billing_redirect_urls()
    try:
        checkout_url = BillingService().create_checkout(user_id=user_id, offer_key=payload.offerKey,
            success_url=success_url, cancel_url=cancel_url)
        return _tiered_response({"checkoutUrl": checkout_url})
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "BILLING_OFFER_UNKNOWN"})
    except BillingOfferNotConfigured:
        raise HTTPException(status_code=409, detail={"code": "BILLING_OFFER_NOT_CONFIGURED"})
    except BillingProviderError:
        raise HTTPException(status_code=503, detail={"code": "BILLING_PROVIDER_UNAVAILABLE"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


@app.get("/billing/me")
def get_billing_me(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    return _tiered_response(BillingService().billing_status(user_id))


@app.post("/billing/stripe/webhook")
async def stripe_billing_webhook(request: Request, stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature")):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail={"code": "BILLING_INVALID_WEBHOOK_SIGNATURE"})
    service = BillingService()
    raw_body = await request.body()
    try:
        event = service.provider.construct_event(raw_body, stripe_signature)
        outcome = service.handle_event(event)
        return {"received": True, "outcome": outcome}
    except InvalidWebhookSignature:
        raise HTTPException(status_code=400, detail={"code": "BILLING_INVALID_WEBHOOK_SIGNATURE"})
    except BillingError as exc:
        logger.exception("billing.webhook.failed code=%s", exc.code)
        raise HTTPException(status_code=503, detail={"code": exc.code})
    except Exception:
        logger.exception("billing.webhook.failed code=BILLING_WEBHOOK_PROCESSING_FAILED")
        raise HTTPException(status_code=503, detail={"code": "BILLING_WEBHOOK_PROCESSING_FAILED"})


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
        db_client=service_read_client,
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
    request: Request,
    target_type: str = Query(...),
    target_id: str = Query(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Detailed EVR runs require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/evr/runs/latest")
    snapshot = get_latest_evr_run_snapshot(target_type=target_type, target_id=target_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No EVR run snapshot found")
    return {"snapshot": snapshot}


@app.get("/explore/page")
def get_explore_page(
    request: Request,
    target_type: str = Query(...),
    target_id: str = Query(...),
    limit_distribution_bins: Optional[str] = Query(default=None),
    limit_top_hits: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return complete Explore page payload for a target (set, edition, pack, etc.)."""
    try:
        if str(target_type or "").strip().lower() == "set":
            return _tiered_response(project_set_page_response(
                get_pokemon_set_page_snapshot_payload(set_id=target_id),
                _resolve_index_plan(authorization, token_cookie),
            ))
        user_id = _require_index_feature(
            feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
            message="Detailed Explore analytics require Index Plus.",
            authorization=authorization, token_cookie=token_cookie,
        )
        _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL, route="/explore/page")
        plan = _resolve_index_plan(authorization, token_cookie)
        payload = get_explore_page_payload(
            target_type=target_type,
            target_id=target_id,
            limit_distribution_bins=limit_distribution_bins,
            limit_top_hits=limit_top_hits,
        )
        return _tiered_response(project_set_page_response(payload, plan))
    except HTTPException:
        raise
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
    request: Request,
    limit: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return available RIP Statistics targets plus the best default target."""
    try:
        _limit_paid_projection(request, authorization=authorization, token_cookie=token_cookie,
                               feature=FEATURE_SET_RIP_ANALYTICS, policy_class=POLICY_RANKED_INTELLIGENCE,
                               route="/explore/rip-statistics/targets")
        return _tiered_response(project_rankings_response(
            get_pokemon_explore_rankings_snapshot_payload(limit=limit),
            _resolve_index_plan(authorization, token_cookie),
        ))
    except HTTPException:
        raise
    except ExploreRipStatisticsTargetsError as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if getattr(exc, "retry_after_seconds", None)
            else None
        )
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
            headers=headers,
        )
    except Exception:
        logger.exception("/explore/rip-statistics/targets unexpected error")
        return JSONResponse(
            content={"message": "Unable to load RIP Statistics targets", "code": "RIP_STATISTICS_TARGETS_FAILED"},
            status_code=500,
        )


@app.get("/explore/rankings/lens/{lens}")
def get_explore_rankings_lens(
    request: Request,
    lens: str,
    limit: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """One narrow prepared Rankings publication; no full-cohort enrichment."""
    try:
        normalized_lens = str(lens or "").strip().lower()
        access_context = _resolve_request_access(
            authorization, token_cookie, feature=FEATURE_SET_RIP_ANALYTICS
        )
        _limit_paid_projection(request, authorization=authorization, token_cookie=token_cookie,
                               feature=FEATURE_SET_RIP_ANALYTICS, policy_class=POLICY_RANKED_INTELLIGENCE,
                               route="/explore/rankings/lens", access_context=access_context)
        payload = get_pokemon_explore_rankings_lens_payload(lens=normalized_lens, limit=limit)
        plan = access_context["plan"]
        if normalized_lens == "sets":
            return _tiered_response(project_rankings_response(payload, plan))
        if normalized_lens == "eras":
            entitled = has_index_feature_access(plan, FEATURE_SET_RIP_ANALYTICS)
            return _tiered_response({
                "meta": {key: (payload.get("meta") or {})[key] for key in ("source", "updatedAt", "warnings", "snapshot", "limit") if key in (payload.get("meta") or {})},
                "access": {"rankingsIntelligence": entitled, "requiredPlan": "plus"},
                "eraSetStrengthV1": project_public_era_rankings_response(payload),
            })
        if normalized_lens == "products":
            payload = {
                "meta": {key: (payload.get("meta") or {})[key] for key in ("source", "updatedAt", "warnings", "snapshot", "limit") if key in (payload.get("meta") or {})},
                "productFamilyRankings": project_product_family_rankings_response(
                    payload.get("productFamilyRankings") or {}, plan
                ),
                "overallProductRankings": read_public_overall_product_rankings(
                    "full_market", product_family_rankings=payload.get("productFamilyRankings") or {}
                ),
            }
            payload["overallProductRankings"] = project_product_rankings_response(
                payload["overallProductRankings"], plan
            )
            return _tiered_response(payload)
        return JSONResponse(
            content={"message": "Unsupported Rankings lens", "code": "RANKINGS_LENS_INVALID"},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except ExploreRipStatisticsTargetsError as exc:
        headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds else None
        return JSONResponse(
            content={"message": exc.message, "code": exc.code, "retryable": exc.status_code >= 500},
            status_code=exc.status_code,
            headers=headers,
        )
    except Exception:
        logger.exception("/explore/rankings/lens/%s unexpected error", lens)
        return JSONResponse(
            content={"message": "Unable to load Rankings lens", "code": "RANKINGS_LENS_FAILED"},
            status_code=500,
        )


@app.get("/explore/product-rankings/overall")
def get_overall_product_rankings(
    request: Request,
    budget: str = Query(default="full_market"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return one allowlisted budget cohort; analytical tables remain private."""
    try:
        access_context = _resolve_request_access(
            authorization, token_cookie, feature=FEATURE_PRODUCT_RIP
        )
        _limit_paid_projection(request, authorization=authorization, token_cookie=token_cookie,
                               feature=FEATURE_PRODUCT_RIP, policy_class=POLICY_RANKED_INTELLIGENCE,
                               route="/explore/product-rankings/overall", access_context=access_context)
        rankings = get_pokemon_explore_rankings_lens_payload(lens="products", limit=200)
        payload = read_public_overall_product_rankings(
            budget, product_family_rankings=rankings.get("productFamilyRankings") or {}
        )
        return _tiered_response(project_product_rankings_response(
            payload, access_context["plan"]
        ))
    except HTTPException:
        raise
    except Exception:
        logger.exception("/explore/product-rankings/overall unexpected error budget=%s", budget)
        return JSONResponse(content={"available": False, "reason": "backend_error", "rows": []}, status_code=503)


@app.get("/explore/card-chase-efficiency")
def get_card_chase_efficiency_rankings(
    request: Request,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    search: Optional[str] = Query(default=None), era: Optional[str] = Query(default=None),
    set_id: Optional[str] = Query(default=None, alias="set"), rarity: Optional[str] = Query(default=None),
    min_price: Optional[float] = Query(default=None), max_price: Optional[float] = Query(default=None),
    sort: str = Query(default="rank"), direction: str = Query(default="asc"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    # Gate before touching the latest pointer: row ordering is Premium data.
    user_id = _require_card_chase_efficiency(authorization=authorization, token_cookie=token_cookie)
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_RANKED_INTELLIGENCE,
                        route="/explore/card-chase-efficiency")
    try:
        return _tiered_response(query_chase_efficiency(
            service_read_client, page=page, page_size=page_size, search=search, era=era,
            set_id=set_id, rarity=rarity, min_price=min_price, max_price=max_price,
            sort=sort, direction=direction,
        ))
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "CARD_CHASE_EFFICIENCY_QUERY_INVALID"}, status_code=400)
    except Exception:
        logger.exception("/explore/card-chase-efficiency unexpected error")
        return JSONResponse(content={"message": "Unable to load Chase Efficiency", "code": "CARD_CHASE_EFFICIENCY_FAILED"}, status_code=500)


@app.get("/tcgs/pokemon/set-route-directory")
def get_pokemon_set_route_directory(limit: int = Query(default=150, ge=1, le=200)):
    """Slim set-route membership/identity; never reads Rankings publication JSON."""
    try:
        return get_pokemon_set_route_directory_payload(limit=limit)
    except Exception:
        logger.exception("/tcgs/pokemon/set-route-directory unexpected error")
        return JSONResponse(
            content={"message": "Unable to load Pokemon set route directory", "code": "POKEMON_SET_ROUTE_DIRECTORY_FAILED", "retryable": True},
            status_code=503,
        )


@app.get("/explore/opening-economics")
def get_explore_opening_economics(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Global and per-era loose-pack opening economics from the canonical snapshot.

    PUBLIC. These are high-level educational market statistics and carry no
    per-product RIP intelligence, so no entitlement is resolved here; the paid
    product surfaces keep their existing database-backed gating untouched.

    Compact by construction - finalized scalars and two six-point ladders per
    scope. Failure is reported as an explicit unavailable contract rather than
    a 5xx, so the Overall lens can degrade on its own without taking Sets or
    Products down with it.
    """
    try:
        _limit_paid_projection(request, authorization=authorization, token_cookie=token_cookie,
                               feature=FEATURE_PACK_ECONOMICS, policy_class=POLICY_RANKED_INTELLIGENCE,
                               route="/explore/opening-economics")
        return _tiered_response(project_opening_economics_response(
            read_public_opening_economics(service_read_client),
            _resolve_index_plan(authorization, token_cookie),
        ))
    except HTTPException:
        raise
    except Exception:
        logger.exception("/explore/opening-economics unexpected error")
        return JSONResponse(
            content={"status": "unavailable", "reason": "backend_error",
                     "global": None, "eras": []},
            status_code=503,
        )


@app.get("/explore/card-market-movers")
def get_explore_card_market_movers(limit: Optional[str] = Query(default=None)):
    """Serve the prepared, fixed-window global Explore card-movers snapshot."""
    try:
        return read_explore_card_movers_snapshot(limit=limit or 30)
    except ExploreCardMoversUnavailable as exc:
        return JSONResponse(
            content={"message": str(exc), "code": "POKEMON_EXPLORE_CARD_MOVERS_UNAVAILABLE"},
            status_code=404,
        )
    except Exception:
        logger.exception("/explore/card-market-movers unexpected error")
        return JSONResponse(
            content={"message": "Unable to load Explore card market movers",
                     "code": "POKEMON_EXPLORE_CARD_MOVERS_FAILED"},
            status_code=500,
        )


@app.get("/explore/set-value-market")
def get_explore_set_value_market():
    """Serve the compact, prepared global Market Set Value snapshot."""
    try:
        return read_explore_set_value_snapshot()
    except ExploreSetValueUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "POKEMON_EXPLORE_SET_VALUE_UNAVAILABLE"}, status_code=404)
    except Exception:
        logger.exception("/explore/set-value-market unexpected error")
        return JSONResponse(content={"message": "Unable to load global Market Set Values", "code": "POKEMON_EXPLORE_SET_VALUE_FAILED"}, status_code=500)


@app.get("/market/explorer/snapshot")
def get_market_explorer_snapshot(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Serve the full prepared Market Explorer publication."""
    _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    if not has_index_plus_access(_resolve_index_plan(authorization, token_cookie)):
        raise HTTPException(status_code=403, detail={
            "message": "Prepared market intelligence requires Index Plus.",
            "code": "MARKET_EXPLORER_PLAN_REQUIRED",
            "requiredPlan": "plus",
        })
    try:
        return read_market_explorer_snapshot()
    except ExploreSetValueUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_SNAPSHOT_UNAVAILABLE"}, status_code=404)
    except Exception:
        logger.exception("/market/explorer/snapshot unexpected error")
        return JSONResponse(content={"message": "Unable to load Market Explorer snapshot", "code": "MARKET_EXPLORER_SNAPSHOT_FAILED"}, status_code=500)


@app.get("/market/explorer/query/options")
def get_market_explorer_query_options(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Read-only filter metadata for the Index Plus Explorer builder."""
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    plan = _resolve_index_plan(authorization, token_cookie)
    if not has_index_plus_access(plan):
        emit_security_event(
            "entitlement_denied", route="market_explorer_options",
            policy_class=POLICY_CUSTOM_QUERY, user_id=user_id,
            required_capability=FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
            authenticated=True, normalized_plan=plan,
        )
        raise HTTPException(status_code=403, detail={
            "message": "Market query options require Index Plus.",
            "code": "MARKET_EXPLORER_PLAN_REQUIRED",
            "requiredPlan": "plus",
            "requiredFeature": FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
        })
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_CUSTOM_QUERY,
                        route="/market/explorer/query/options")
    try:
        global _market_explorer_options_cache
        now = time.monotonic()
        if _market_explorer_options_cache and _market_explorer_options_cache[0] > now:
            return _tiered_response(_market_explorer_options_cache[1])
        options = build_market_explorer_filter_options(service_read_client)
        _market_explorer_options_cache = (
            now + _MARKET_EXPLORER_OPTIONS_CACHE_TTL_SECONDS,
            options,
        )
        return _tiered_response(options)
    except MarketExplorerQueryUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_UNAVAILABLE"}, status_code=404)
    except Exception:
        logger.exception("/market/explorer/query/options unexpected error")
        return JSONResponse(content={"message": "Unable to load Market Explorer filters", "code": "MARKET_EXPLORER_OPTIONS_FAILED"}, status_code=500)


@app.post("/market/explorer/query")
def post_market_explorer_query(
    request: Request,
    payload: MarketExplorerQueryRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Execute one normalized market query without exposing database RPCs.

    ONE ENDPOINT, TWO ASSETS. The spec layer normalizes and validates both, and
    the asset selects which engine runs. Cards and sealed products fingerprint
    apart because the asset is part of the spec, so the shared cache cannot
    serve one asset's result for the other.
    """
    if payload.asset not in SUPPORTED_ASSETS:
        return JSONResponse(content={"message": f"Unsupported asset: {payload.asset}", "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    if payload.mode == "chase" and payload.topN not in (None, 10):
        return JSONResponse(content={"message": "Only Top 10 queries are supported", "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    try:
        # Normalized BEFORE the cache is consulted, so an invalid spec is
        # rejected rather than keyed, and equivalent selections share one entry.
        normalized = normalize_query_spec(
            asset=payload.asset, mode=payload.mode, era_ids=payload.eraIds,
            set_ids=payload.setIds, segment_ids=payload.segmentIds,
            pokemon_ids=payload.pokemonIds, price_segment_ids=payload.priceSegmentIds,
            release_age_cohort_ids=payload.releaseAgeCohortIds, top_n=payload.topN,
        )
        user_id = _require_market_explorer_query_access(
            normalized, authorization=authorization, token_cookie=token_cookie
        )
        _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_CUSTOM_QUERY,
                            route="/market/explorer/query")
        runner = (
            run_sealed_market_explorer_query if payload.asset == ASSET_SEALED
            else run_market_explorer_query
        )
        persistent = PersistentMarketExplorerCache(
            service_read_client, metrics=GLOBAL_MARKET_EXPLORER_PLANNER.metrics,
        )

        def build_market(previous_through: str | None, canonical_date: str) -> Dict[str, Any]:
            return runner(
                service_read_client,
                mode=normalized["mode"],
                era_ids=normalized["eraIds"], set_ids=normalized["setIds"],
                segment_ids=normalized["segmentIds"],
                pokemon_ids=normalized["pokemonIds"],
                price_segment_ids=normalized["priceSegmentIds"],
                release_age_cohort_ids=normalized["releaseAgeCohortIds"],
                top_n=normalized["topN"],
                # A forward refresh includes the cached anchor date. The
                # planner rescales/appends and drops that duplicate point.
                start_date=previous_through or "1999-01-01",
                end_date=canonical_date,
            )

        planned = GLOBAL_MARKET_EXPLORER_PLANNER.execute(
            spec=normalized,
            prepared=GLOBAL_PREPARED_EQUIVALENCE_REGISTRY,
            persistent=persistent,
            canonical_through=lambda: resolve_canonical_through(
                service_read_client, normalized,
            ),
            novel_builder=build_market,
        )
        return _tiered_response(planned.payload)
    except HTTPException:
        raise
    except MarketExplorerQueryError as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    except (MarketExplorerQueryUnavailable, SealedMarketExplorerQueryUnavailable) as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_UNAVAILABLE"}, status_code=404)
    except MarketExplorerBuildInProgress as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_BUILDING"}, status_code=503)
    except Exception:
        logger.exception("/market/explorer/query unexpected error")
        return JSONResponse(content={"message": "Unable to execute Market Explorer query", "code": "MARKET_EXPLORER_QUERY_FAILED"}, status_code=500)


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


@app.post("/auth/supabase/exchange")
async def auth_supabase_exchange(payload: SupabaseExchangeRequest):
    response_payload, status = exchange_supabase_access_token(payload.access_token)
    return JSONResponse(content=response_payload, status_code=status)


@app.post("/auth/signup")
async def auth_signup(_payload: SignupRequest):
    logger.info("/auth/signup: started, env_presence=%s", _auth_env_presence())
    logger.info("/auth/signup: request body parsed successfully")
    return JSONResponse(
        content={"detail": "Use the Supabase signup flow and verified session exchange.", "code": "USE_SUPABASE_SIGNUP"},
        status_code=410,
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
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if getattr(exc, "retry_after_seconds", None)
            else None
        )
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
            headers=headers,
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
    movement_metric: Optional[str] = Query(default=None),
    sort_direction: Optional[str] = Query(default=None),
    section: Optional[str] = Query(default=None),
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
            movement_metric=movement_metric,
            sort_direction=sort_direction,
            section=section,
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
    request: Request,
    set_id: str,
    max_cards: int = Query(default=300, ge=1, le=300),
    include_plot_rows: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return the slim Insights card-validation snapshot (validation-ready
    card rows + cardAppealMarketPriceCorrelation) for a Pokemon set."""
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Card validation analytics require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/cards/validation")
    try:
        return get_pokemon_set_card_validation_snapshot_payload(
            set_id=set_id,
            max_cards=max_cards,
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


@app.get("/tcgs/pokemon/sets/{set_id}/cards/{card_id}")
def get_pokemon_card_detail(
    request: Request,
    set_id: str,
    card_id: str,
    variant_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return one canonical card and variant-aware Chase economics."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_PRODUCT_RIP, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/cards/{card_id}",
    )
    try:
        return _tiered_response(project_card_detail_response(
            get_pokemon_card_detail_payload(
                set_id=set_id, card_id=card_id, variant_id=variant_id
            ),
            _resolve_index_plan(authorization, token_cookie),
        ))
    except HTTPException:
        raise
    except PokemonCardDetailError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception(
            "/tcgs/pokemon/sets/%s/cards/%s unexpected error", set_id, card_id
        )
        return JSONResponse(
            content={"message": "Unable to load Pokemon card", "code": "POKEMON_CARD_DETAIL_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/cards/{card_id}/chase-efficiency")
def get_pokemon_card_chase_efficiency(
    request: Request, set_id: str, card_id: str, variant_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_card_chase_efficiency(authorization=authorization, token_cookie=token_cookie)
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/cards/{card_id}/chase-efficiency")
    try:
        result = read_card_chase_efficiency(
            service_read_client, set_id=set_id, card_id=card_id, variant_id=variant_id
        )
        return _tiered_response(result) if result.get("available") else JSONResponse(
            content=result, status_code=404,
            headers={"Cache-Control": "no-store", "Vary": "Cookie, Authorization"},
        )
    except Exception:
        logger.exception("card Chase Efficiency failed set=%s card=%s", set_id, card_id)
        return JSONResponse(content={"message": "Unable to load card Chase Efficiency", "code": "CARD_CHASE_EFFICIENCY_FAILED"}, status_code=500)


@app.get("/tcgs/pokemon/sealed-products/{product_id}")
def get_pokemon_sealed_product_detail(
    request: Request,
    product_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return one real sealed-product identity, market history, and published RIP contract."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_PRODUCT_RIP, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sealed-products/{product_id}",
    )
    try:
        return _tiered_response(project_sealed_product_detail_response(
            get_pokemon_sealed_product_detail_payload(product_id),
            _resolve_index_plan(authorization, token_cookie),
        ))
    except HTTPException:
        raise
    except PokemonSealedProductDetailError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sealed-products/%s unexpected error", product_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon sealed product", "code": "POKEMON_SEALED_PRODUCT_DETAIL_FAILED"},
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


@app.get("/tcgs/pokemon/sets/{set_id}/simulation-evidence")
def get_pokemon_set_simulation_evidence(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Simulation evidence requires Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/simulation-evidence")
    try:
        return get_pokemon_set_simulation_evidence_snapshot_payload(set_id=set_id)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code}, status_code=exc.status_code)
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/simulation-evidence unexpected error", set_id)
        return JSONResponse(content={"message": "Unable to load simulation evidence", "code": "POKEMON_SET_SIMULATION_EVIDENCE_FAILED"}, status_code=500)


def _set_rip_response(reader, set_id: str, **kwargs):
    try:
        return reader(set_id=set_id, **kwargs)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code, "retryable": exc.status_code >= 500},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/rip projection unexpected error", set_id)
        return JSONResponse(content={"message": "Unable to load Set RIP data", "code": "POKEMON_SET_RIP_FAILED", "retryable": True}, status_code=500)


@app.get("/tcgs/pokemon/sets/{set_id}/rip/bootstrap")
def get_pokemon_set_rip_bootstrap(set_id: str):
    return _set_rip_response(get_pokemon_set_rip_bootstrap_snapshot_payload, set_id)


@app.get("/tcgs/pokemon/sets/{set_id}/rip/simulation-evidence")
def get_pokemon_set_rip_simulation_evidence(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="RIP simulation evidence requires Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/rip/simulation-evidence")
    return _set_rip_response(get_pokemon_set_rip_simulation_evidence_snapshot_payload, set_id)


@app.get("/tcgs/pokemon/sets/{set_id}/rip/advanced")
def get_pokemon_set_rip_advanced(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Advanced RIP analytics require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/rip/advanced")
    return _set_rip_response(get_pokemon_set_rip_advanced_snapshot_payload, set_id)


@app.get("/tcgs/pokemon/sets/{set_id}/rip/global-context")
def get_pokemon_set_rip_global_context(
    request: Request, set_id: str, expected_calculation_run_id: str | None = None,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Global RIP context requires Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/rip/global-context")
    return _set_rip_response(
        get_pokemon_set_rip_global_context_payload, set_id,
        expected_calculation_run_id=expected_calculation_run_id,
    )


@app.get("/tcgs/pokemon/sets/{set_id}/rip/rank-context")
def get_pokemon_set_rip_rank_context(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_PRODUCT_RIP, code="INDEX_PLUS_REQUIRED",
        message="Product Family Rankings require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/rip/rank-context")
    return _set_rip_response(get_pokemon_set_rip_rank_context_payload, set_id)


@app.get("/tcgs/pokemon/sets/{set_id}/insights")
def get_pokemon_set_insights(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Detailed Set Insights require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/insights")
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


@app.get("/tcgs/pokemon/sets/{set_id}/insights/critical")
def get_pokemon_set_insights_critical(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Priority 1-3 slice of the Insights tab: RIP Score hero, pillar cards
    (interpretation), and the recommendation copy. Small, fast payload meant
    to render before /insights/secondary's charts/diagnostics arrive."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_SET_RIP_ANALYTICS, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/insights/critical",
    )
    try:
        return _tiered_response(project_insights_critical_response(
            get_pokemon_set_insights_critical_snapshot_payload(set_id=set_id),
            _resolve_index_plan(authorization, token_cookie),
        ))
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/insights/critical unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set insights", "code": "POKEMON_SET_INSIGHTS_CRITICAL_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/insights/secondary")
def get_pokemon_set_insights_secondary(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
        message="Detailed Set Insights require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/insights/secondary")
    """Priority 4-5 slice of the Insights tab: outcome distribution,
    simulation drivers, rarity contribution, history trend, and desirability
    diagnostics. Fetched independently of /insights/critical so a slow or
    failed secondary fetch never blocks the RIP Score hero/pillar cards."""
    try:
        return get_pokemon_set_insights_secondary_snapshot_payload(set_id=set_id)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code},
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/insights/secondary unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set insights", "code": "POKEMON_SET_INSIGHTS_SECONDARY_FAILED"},
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
def get_pokemon_set_page(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return page-ready public Pokemon set analytics snapshot."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_SET_RIP_ANALYTICS, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/page",
    )
    try:
        return _tiered_response(project_set_page_response(
            get_pokemon_set_page_snapshot_payload(set_id=set_id),
            _resolve_index_plan(authorization, token_cookie),
        ))
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
    request: Request,
    set_id: str,
    window: Optional[str] = Query(default=None),
    days: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return page-ready market dashboard snapshot for a Pokemon set."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_MARKET_BREADTH, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/market/dashboard",
    )
    try:
        return filter_set_market_signal_access(
            get_pokemon_set_market_dashboard_snapshot_payload(set_id=set_id, window=window or "365d", days=days),
            _resolve_index_plan(authorization, token_cookie),
        )
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
    request: Request,
    set_id: str,
    window: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return the slim Overview-tab snapshot (set value trend + performance vs cost) for a Pokemon set."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_MARKET_BREADTH, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/overview",
    )
    try:
        return filter_set_market_signal_access(
            get_pokemon_set_overview_snapshot_payload(set_id=set_id, window=window or "365d"),
            _resolve_index_plan(authorization, token_cookie),
        )
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


@app.get("/tcgs/pokemon/sets/{set_id}/market/bootstrap")
def get_pokemon_set_market_bootstrap(
    set_id: str,
    window: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Critical Market data with server-projected optional paid breadth."""
    try:
        payload = get_pokemon_set_market_bootstrap_snapshot_payload(set_id=set_id, window=window or "365d")
        plan = _resolve_index_plan(authorization, token_cookie)
        return JSONResponse(
            content=filter_set_market_signal_access(payload, plan),
            headers={"Cache-Control": "private, no-store", "Vary": "Cookie, Authorization"},
        )
    except PokemonSetMarketError as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code}, status_code=exc.status_code)
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/bootstrap unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load Pokemon set Market bootstrap", "code": "POKEMON_SET_MARKET_BOOTSTRAP_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/signals")
def get_pokemon_set_market_signals(
    request: Request,
    set_id: str,
    window: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Tiny authenticated Plus/Premium projection of prepared Market Breadth."""
    user_id = _require_index_feature(
        feature=FEATURE_MARKET_BREADTH, code="INDEX_PLUS_REQUIRED",
        message="Market Breadth requires Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INTERACTIVE_DETAIL,
                        route="/tcgs/pokemon/sets/{set_id}/market/signals")
    try:
        payload = get_pokemon_set_market_signals_snapshot_payload(set_id=set_id, window=window or "365d")
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "no-store", "Vary": "Cookie, Authorization"},
        )
    except PokemonSetMarketError as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code, "retryable": exc.status_code >= 500}, status_code=exc.status_code, headers={"Cache-Control": "no-store"})
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/signals unexpected error", set_id)
        return JSONResponse(content={"message": "Unable to load Market signals", "code": "POKEMON_SET_MARKET_SIGNALS_FAILED", "retryable": True}, status_code=503, headers={"Cache-Control": "no-store"})


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
        # 5xx here means "ask again" (an incomplete/malformed snapshot row), which
        # is what authorizes the client's single bounded retry. A 4xx is settled
        # and must not be retried.
        return JSONResponse(
            content={
                "message": exc.message,
                "code": exc.code,
                "retryable": exc.status_code >= 500,
            },
            status_code=exc.status_code,
        )
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/top-chase unexpected error", set_id)
        return JSONResponse(
            content={
                "message": "Unable to load Pokemon set top chase cards",
                "code": "POKEMON_SET_TOP_CHASE_FAILED",
                "retryable": True,
            },
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/sealed")
def get_pokemon_set_sealed_market(
    request: Request,
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Read the prepared sealed-market snapshot; never aggregates observations."""
    _limit_paid_projection(
        request, authorization=authorization, token_cookie=token_cookie,
        feature=FEATURE_PRODUCT_RIP, policy_class=POLICY_INTERACTIVE_DETAIL,
        route="/tcgs/pokemon/sets/{set_id}/market/sealed",
    )
    try:
        # Use the SHARED resolver, exactly like page/shell/cards/market-dashboard/
        # value-history/top-cards. This route used to hand-roll its own
        # `canonical_key.eq.<id>,pokemon_api_set_id.eq.<id>` lookup, and `.eq.` is
        # case-sensitive. The set page sends the NORMALIZED identifier
        # ("ascendedheroes"), not the canonical_key ("ascendedHeroes"), so sealed
        # 404'd on every set while every sibling module on the same Market tab
        # resolved the same identifier fine — the user-visible "Sealed Market:
        # unable to load / Retry". The shared resolver's normalized-slug fallback
        # accepts that form, and it additionally runs under
        # run_public_read_with_retry, so sealed now gets the same dead-pooled-socket
        # protection the other routes already had and this one entirely bypassed.
        try:
            resolved_set_id = str(resolve_pokemon_set_identifier(set_id, client=service_read_client)["id"])
        except PokemonSetMarketError as exc:
            return JSONResponse(
                content={"message": exc.message, "code": exc.code},
                status_code=exc.status_code,
            )
        payload = read_sealed_market_snapshot(service_read_client, resolved_set_id)
        if payload is None:
            return JSONResponse(
                content={"message": "Sealed market history is not available", "code": "POKEMON_SET_SEALED_MARKET_UNAVAILABLE"},
                status_code=404,
            )
        return _tiered_response(project_sealed_market_response(
            payload, _resolve_index_plan(authorization, token_cookie)
        ))
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/sealed unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load sealed market history", "code": "POKEMON_SET_SEALED_MARKET_FAILED"},
            status_code=500,
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/sealed-consumer")
def get_pokemon_set_consumer_sealed_market(set_id: str):
    """Set-Market consumer projection; excludes legacy products and setMarket."""
    try:
        resolved_set = resolve_pokemon_set_identifier(set_id, client=service_read_client)
        resolved_set_id = str(resolved_set["id"])
        result = run_public_read_with_retry(
            lambda client: client.table("pokemon_set_sealed_market_snapshot_latest")
                .select(
                    "set_id,marketDate:payload_json->marketDate,"
                    "setPageConsumerMarket:payload_json->setPageConsumerMarket,"
                    "setPageConsumerTopProducts:payload_json->setPageConsumerTopProducts,"
                    "meta:payload_json->meta"
                )
                .eq("set_id", resolved_set_id)
                .limit(1)
                .execute(),
            operation_name="pokemon_set_consumer_sealed_market",
            initial_client=service_read_client,
        )
        row = (result.data or [None])[0]
        if not row:
            return JSONResponse(
                content={"message": "Consumer sealed market is unavailable", "code": "POKEMON_SET_CONSUMER_SEALED_UNAVAILABLE"},
                status_code=404,
            )
        if not isinstance(row.get("setPageConsumerMarket"), dict):
            return JSONResponse(
                content={
                    "message": "Consumer sealed market publication is incomplete",
                    "code": "POKEMON_SET_CONSUMER_SEALED_INCOMPLETE",
                    "retryable": True,
                },
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return {
            "set": {"id": resolved_set_id, "name": resolved_set.get("name"), "slug": resolved_set.get("canonical_key")},
            "marketDate": row.get("marketDate"),
            "setPageConsumerMarket": row.get("setPageConsumerMarket"),
            "setPageConsumerTopProducts": row.get("setPageConsumerTopProducts") or [],
            "meta": row.get("meta") or {},
        }
    except PokemonSetMarketError as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code}, status_code=exc.status_code)
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/sealed-consumer unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load consumer sealed market", "code": "POKEMON_SET_CONSUMER_SEALED_FAILED"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )


@app.get("/tcgs/pokemon/sets/{set_id}/market/sealed-summary")
def get_pokemon_set_consumer_sealed_summary(set_id: str):
    """Aggregate-only consumer Sealed contract; top products remain deferred."""
    try:
        resolved_set = resolve_pokemon_set_identifier(set_id, client=service_read_client)
        resolved_set_id = str(resolved_set["id"])
        result = run_public_read_with_retry(
            lambda client: client.table("pokemon_set_sealed_market_snapshot_latest")
                .select(
                    "set_id,updated_at,marketDate:payload_json->marketDate,"
                    "setPageConsumerMarket:payload_json->setPageConsumerMarket,"
                    "meta:payload_json->meta"
                )
                .eq("set_id", resolved_set_id).limit(1).execute(),
            operation_name="pokemon_set_consumer_sealed_summary",
            initial_client=service_read_client,
        )
        row = (result.data or [None])[0]
        if not row:
            return JSONResponse(content={"message": "Consumer sealed summary is unavailable", "code": "POKEMON_SET_CONSUMER_SEALED_SUMMARY_UNAVAILABLE"}, status_code=404)
        if not isinstance(row.get("setPageConsumerMarket"), dict):
            return JSONResponse(content={"message": "Consumer sealed summary publication is incomplete", "code": "POKEMON_SET_CONSUMER_SEALED_SUMMARY_INCOMPLETE", "retryable": True}, status_code=503, headers={"Cache-Control": "no-store"})
        return {
            "set": {"id": resolved_set_id, "name": resolved_set.get("name"), "slug": resolved_set.get("canonical_key")},
            "marketDate": row.get("marketDate"),
            "setPageConsumerMarket": row.get("setPageConsumerMarket"),
            "meta": {**(row.get("meta") or {}), "updatedAt": row.get("updated_at")},
        }
    except PokemonSetMarketError as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code}, status_code=exc.status_code)
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/sealed-summary unexpected error", set_id)
        return JSONResponse(content={"message": "Unable to load consumer sealed summary", "code": "POKEMON_SET_CONSUMER_SEALED_SUMMARY_FAILED", "retryable": True}, status_code=503, headers={"Cache-Control": "no-store"})


@app.get("/tcgs/pokemon/sets/{set_id}/market/movers")
def get_pokemon_set_market_movers(
    set_id: str,
    window: Optional[str] = Query(default=None),
    limit: Optional[str] = Query(default=None),
    movement: Optional[str] = Query(default=None),
    surface: Optional[str] = Query(default=None),
    metric: Optional[str] = Query(default=None),
):
    """Return market movers for a single requested window for a Pokemon set.

    Default consumers share the canonical largest-dollar-move contract. The
    explicit Set-page 7D absolute-percent request reads its isolated published
    projection and fails closed while that projection is incomplete.
    """
    try:
        return get_pokemon_set_market_movers_snapshot_payload(
            set_id=set_id, window=window or "30D", limit=limit, movement=movement,
            surface=surface, metric=metric,
        )
    except PokemonSetMarketError as exc:
        return JSONResponse(
            content={"message": exc.message, "code": exc.code, "retryable": exc.status_code >= 500},
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
