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
from backend.domain.access.index_plan_access import (
    FEATURE_CARD_CHASE_EFFICIENCY,
    FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
    filter_set_market_signal_access,
    has_index_feature_access,
    has_index_premium_access,
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
    get_pokemon_set_card_validation_snapshot_payload,
    get_pokemon_set_cards_page_snapshot_payload,
    get_pokemon_set_cards_snapshot_payload,
    get_pokemon_set_insights_critical_snapshot_payload,
    get_pokemon_set_insights_secondary_snapshot_payload,
    get_pokemon_set_insights_snapshot_payload,
    get_pokemon_set_simulation_evidence_snapshot_payload,
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
from backend.db.services.pokemon_explore_card_movers_service import (
    ExploreCardMoversUnavailable,
    read_explore_card_movers_snapshot,
)
from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
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


app = FastAPI(title="EVR Collection API")

logger = logging.getLogger(__name__)

_MARKET_EXPLORER_QUERY_CACHE_TTL_SECONDS = 300
_MARKET_EXPLORER_QUERY_CACHE_MAX_ENTRIES = 128
_market_explorer_query_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}

_DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]


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
    mode: str = "all"
    topN: Optional[int] = None


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


def _require_market_explorer_custom_markets(
    *, authorization: Optional[str], token_cookie: Optional[str]
) -> str:
    """Authenticate, then require the Index Premium custom-markets entitlement.

    ENFORCED BEFORE ANY WORK. This runs ahead of spec normalization, the shared
    result cache and the query engine, so an Index Plus user cannot reach a
    cached Premium result by calling the endpoint directly, and an unentitled
    caller cannot make the database do work on their behalf.
    """
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    if not has_index_premium_access(_resolve_index_plan(authorization, token_cookie)):
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Building custom markets requires Index Premium.",
                "code": "MARKET_EXPLORER_PREMIUM_REQUIRED",
                "requiredFeature": FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
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
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Chase Efficiency requires Index Premium.",
                "code": "CARD_CHASE_EFFICIENCY_PREMIUM_REQUIRED",
                "requiredFeature": FEATURE_CARD_CHASE_EFFICIENCY,
            },
        )
    return user_id


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


@app.get("/explore/product-rankings/overall")
def get_overall_product_rankings(budget: str = Query(default="full_market")):
    """Return one allowlisted budget cohort; analytical tables remain private."""
    try:
        rankings = get_pokemon_explore_rankings_snapshot_payload(limit=200)
        return read_public_overall_product_rankings(
            budget, product_family_rankings=rankings.get("productFamilyRankings") or {}
        )
    except Exception:
        logger.exception("/explore/product-rankings/overall unexpected error budget=%s", budget)
        return JSONResponse(content={"available": False, "reason": "backend_error", "rows": []}, status_code=503)


@app.get("/explore/card-chase-efficiency")
def get_card_chase_efficiency_rankings(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    search: Optional[str] = Query(default=None), era: Optional[str] = Query(default=None),
    set_id: Optional[str] = Query(default=None, alias="set"), rarity: Optional[str] = Query(default=None),
    min_price: Optional[float] = Query(default=None), max_price: Optional[float] = Query(default=None),
    sort: str = Query(default="rank"), direction: str = Query(default="asc"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    # Gate before touching the latest pointer: row ordering is Premium data.
    _require_card_chase_efficiency(authorization=authorization, token_cookie=token_cookie)
    try:
        return query_chase_efficiency(
            service_read_client, page=page, page_size=page_size, search=search, era=era,
            set_id=set_id, rarity=rarity, min_price=min_price, max_price=max_price,
            sort=sort, direction=direction,
        )
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "CARD_CHASE_EFFICIENCY_QUERY_INVALID"}, status_code=400)
    except Exception:
        logger.exception("/explore/card-chase-efficiency unexpected error")
        return JSONResponse(content={"message": "Unable to load Chase Efficiency", "code": "CARD_CHASE_EFFICIENCY_FAILED"}, status_code=500)


@app.get("/explore/opening-economics")
def get_explore_opening_economics():
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
        return read_public_opening_economics(service_read_client)
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


@app.get("/market/explorer/query/options")
def get_market_explorer_query_options(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Read-only filter metadata for the Explorer builder — Index Premium.

    The options ARE the custom-market builder's surface: era and set ids exist
    on this endpoint for no other purpose, so it carries the same gate as the
    query itself rather than a weaker one.
    """
    _require_market_explorer_custom_markets(
        authorization=authorization, token_cookie=token_cookie
    )
    try:
        return build_market_explorer_filter_options(service_read_client)
    except MarketExplorerQueryUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_UNAVAILABLE"}, status_code=404)
    except Exception:
        logger.exception("/market/explorer/query/options unexpected error")
        return JSONResponse(content={"message": "Unable to load Market Explorer filters", "code": "MARKET_EXPLORER_OPTIONS_FAILED"}, status_code=500)


@app.post("/market/explorer/query")
def post_market_explorer_query(
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
    _require_market_explorer_custom_markets(
        authorization=authorization, token_cookie=token_cookie
    )
    if payload.asset not in SUPPORTED_ASSETS:
        return JSONResponse(content={"message": f"Unsupported asset: {payload.asset}", "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    if payload.mode == "chase" and payload.topN not in (None, 10):
        return JSONResponse(content={"message": "Only Top 10 queries are supported", "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    try:
        today = date.today().isoformat()
        # Normalized BEFORE the cache is consulted, so an invalid spec is
        # rejected rather than keyed, and equivalent selections share one entry.
        normalized = normalize_query_spec(
            asset=payload.asset, mode=payload.mode, era_ids=payload.eraIds,
            set_ids=payload.setIds, segment_ids=payload.segmentIds, top_n=payload.topN,
        )
        cache_key = f"{query_fingerprint(normalized)}:{today}"
        cached = _market_explorer_query_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        runner = (
            run_sealed_market_explorer_query if payload.asset == ASSET_SEALED
            else run_market_explorer_query
        )
        result = runner(
            service_read_client,
            mode=payload.mode,
            era_ids=payload.eraIds,
            set_ids=payload.setIds,
            segment_ids=payload.segmentIds,
            top_n=payload.topN,
            start_date="1999-01-01",
            end_date=today,
        )
        _market_explorer_query_cache[cache_key] = (
            time.monotonic() + _MARKET_EXPLORER_QUERY_CACHE_TTL_SECONDS,
            result,
        )
        while len(_market_explorer_query_cache) > _MARKET_EXPLORER_QUERY_CACHE_MAX_ENTRIES:
            _market_explorer_query_cache.pop(next(iter(_market_explorer_query_cache)), None)
        return result
    except MarketExplorerQueryError as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_INVALID"}, status_code=400)
    except (MarketExplorerQueryUnavailable, SealedMarketExplorerQueryUnavailable) as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_QUERY_UNAVAILABLE"}, status_code=404)
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


@app.get("/tcgs/pokemon/sets/{set_id}/cards/{card_id}")
def get_pokemon_card_detail(
    set_id: str,
    card_id: str,
    variant_id: Optional[str] = Query(default=None),
):
    """Return one canonical card and variant-aware Chase economics."""
    try:
        return get_pokemon_card_detail_payload(
            set_id=set_id, card_id=card_id, variant_id=variant_id
        )
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
    set_id: str, card_id: str, variant_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _require_card_chase_efficiency(authorization=authorization, token_cookie=token_cookie)
    try:
        result = read_card_chase_efficiency(
            service_read_client, set_id=set_id, card_id=card_id, variant_id=variant_id
        )
        return result if result.get("available") else JSONResponse(content=result, status_code=404)
    except Exception:
        logger.exception("card Chase Efficiency failed set=%s card=%s", set_id, card_id)
        return JSONResponse(content={"message": "Unable to load card Chase Efficiency", "code": "CARD_CHASE_EFFICIENCY_FAILED"}, status_code=500)


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
def get_pokemon_set_simulation_evidence(set_id: str):
    try:
        return get_pokemon_set_simulation_evidence_snapshot_payload(set_id=set_id)
    except (PokemonSetMarketError, ExploreRipStatisticsTargetsError) as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code}, status_code=exc.status_code)
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/simulation-evidence unexpected error", set_id)
        return JSONResponse(content={"message": "Unable to load simulation evidence", "code": "POKEMON_SET_SIMULATION_EVIDENCE_FAILED"}, status_code=500)


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


@app.get("/tcgs/pokemon/sets/{set_id}/insights/critical")
def get_pokemon_set_insights_critical(set_id: str):
    """Priority 1-3 slice of the Insights tab: RIP Score hero, pillar cards
    (interpretation), and the recommendation copy. Small, fast payload meant
    to render before /insights/secondary's charts/diagnostics arrive."""
    try:
        return get_pokemon_set_insights_critical_snapshot_payload(set_id=set_id)
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
def get_pokemon_set_insights_secondary(set_id: str):
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
    set_id: str,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return page-ready public Pokemon set analytics snapshot."""
    try:
        return filter_set_market_signal_access(
            get_pokemon_set_page_snapshot_payload(set_id=set_id),
            _resolve_index_plan(authorization, token_cookie),
        )
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
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return page-ready market dashboard snapshot for a Pokemon set."""
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
    set_id: str,
    window: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Return the slim Overview-tab snapshot (set value trend + performance vs cost) for a Pokemon set."""
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
def get_pokemon_set_sealed_market(set_id: str):
    """Read the prepared sealed-market snapshot; never aggregates observations."""
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
        return payload
    except Exception:
        logger.exception("/tcgs/pokemon/sets/%s/market/sealed unexpected error", set_id)
        return JSONResponse(
            content={"message": "Unable to load sealed market history", "code": "POKEMON_SET_SEALED_MARKET_FAILED"},
            status_code=500,
        )


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

    Shares the canonical Cards filter/sort contract:
    section=market-movers, movement=all|heating|cooling, sort=largest-dollar-move.
    """
    try:
        return get_pokemon_set_market_movers_snapshot_payload(
            set_id=set_id, window=window or "30D", limit=limit, movement=movement,
            surface=surface, metric=metric,
        )
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
