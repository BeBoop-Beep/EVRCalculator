"""FastAPI endpoints for frontend proxy consumption."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import Body, Cookie, FastAPI, Header, HTTPException, Query, Request  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse  # type: ignore[reportMissingImports]
from pydantic import BaseModel, Field  # type: ignore[reportMissingImports]
from pydantic import ConfigDict
from backend.db.services.billing_service import BillingService
from backend.domain.billing.catalog import BillingOfferNotConfigured
from backend.domain.billing.errors import (
    BillingError,
    BillingOwnershipError,
    BillingProviderError,
    BillingPortalUnavailable,
    BillingSubscriptionAlreadyManaged,
    InvalidWebhookSignature,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
    UnmappedStripePrice,
    UnsupportedSubscriptionShape,
)

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
from backend.benchmarking.preview_v1 import PrivateBenchmarkReader
from backend.benchmarking.registry_v1 import (
    BenchmarkContractUnavailable,
    resolve_active_contract,
)
from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError
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
from backend.db.services.market_activity_v1 import (
    discover_activity_capabilities,
    read_constituent_activity_page,
    read_group_activity,
    read_instrument_activity,
)
from backend.domain.pokemon.market_activity_contract import SchemaRegistry
from backend.domain.access.index_plan_access import (
    FEATURE_CARD_CHASE_EFFICIENCY,
    FEATURE_CARD_COLLECTOR_APPEAL,
    FEATURE_MARKET_BREADTH,
    FEATURE_MARKET_EXPLORER_PREPARED_COMPARE,
    FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
    FEATURE_PACK_ECONOMICS,
    FEATURE_PRODUCT_RIP,
    FEATURE_PRODUCT_CHASE_INTELLIGENCE,
    FEATURE_SET_RIP_ANALYTICS,
    evaluate_market_query_access,
    filter_set_market_signal_access,
    has_index_plus_access,
    market_explorer_active_market_limit,
    has_index_premium_access,
    has_index_feature_access,
    is_canonical_rarity_query_shape,
    project_card_detail_response,
    project_insights_critical_response,
    project_product_chase_access_response,
    project_product_rankings_response,
    project_product_family_rankings_response,
    project_public_era_rankings_response,
    project_opening_economics_response,
    project_rankings_response,
    project_set_rankings_lens_response,
    project_sealed_market_response,
    project_sealed_product_detail_response,
    project_set_page_response,
    project_set_rip_simulation_evidence_response,
)
from backend.db.services.budget_product_ranking_authority import load_pinned_cohort, most_recent_available_price_as_of
from backend.db.services.product_chase_access_authority import resolve_product_chase_access
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
    get_pokemon_homepage_benchmark_summary_payload,
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
    run_market_explorer_query,
)
from backend.db.services.card_collector_appeal_query_service import query_card_collector_appeal
from backend.db.services.market_explorer_options_snapshot import (
    MarketExplorerOptionsUnavailable,
    read_market_explorer_options_snapshot,
)
from backend.db.services.market_explorer_prepared_directory import (
    PreparedSurfaceValidationError,
    read_prepared_comparison_bundle, read_prepared_constituents, enrich_prepared_constituent_page,
    read_prepared_directory,
    read_prepared_screen, read_set_context_ranking,
)
from backend.db.services.market_explorer_surface_v2 import (
    SurfaceV2Error, is_selectable_canonical_rarity, read_asset_options, read_comparison_v2_first,
    read_constituents_v2_first, read_directory_v2_first, search_catalog,
)
from backend.db.services.market_explorer_direct_instrument import (
    DirectInstrumentError, read_direct_instrument,
)
from backend.db.services.market_explorer_exact_basket import (
    MarketExplorerExactBasketUnavailable, run_exact_basket_v2,
)
from backend.db.services.market_explorer_query_planner import (
    GLOBAL_MARKET_EXPLORER_PLANNER,
    GLOBAL_PREPARED_EQUIVALENCE_REGISTRY,
    MarketExplorerBuildInProgress,
    MarketExplorerCacheRefreshing,
    PersistentMarketExplorerCache,
    resolve_explorer_comparison_through,
    resolve_scope_set_ids,
)
from backend.domain.pokemon.market_explorer_preflight import (
    MarketExplorerPreflightError,
    call_filtered_cards_preflight,
)
from backend.db.services.market_explorer_instrument_search import (
    LeafSearchError, search_market_explorer_instruments, search_market_explorer_leaves,
)
from backend.db.services.sitewide_search import search_sitewide
from backend.db.services.public_overall_product_rankings_service import read_public_overall_product_rankings
from backend.db.services import rip_release
from backend.db.services.budget_product_ranking_service import load_latest_snapshot
from backend.db.services.product_rankings_v2_service import (
    query_product_rankings, read_product_authority, read_public_product_catalogue_page,
)
from backend.db.services.pokemon_rip_stats_service import read_public_opening_economics
from backend.db.services.rankings_redesign_contract_service import (
    project_product_contract,
    read_product_best_open_map,
    read_card_facets,
    read_financial_cohort,
    read_financial_history_page,
    read_overview_v2,
    read_pack_economics,
    read_public_headlines,
    read_public_pack_economics_preview,
    read_scorecards,
)
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
    POLICY_INSTRUMENT_SEARCH,
    POLICY_SITE_SEARCH,
    POLICY_INTERACTIVE_DETAIL,
    POLICY_RANKED_INTELLIGENCE,
    emit_security_event,
    paid_analytics_limiter,
)


app = FastAPI(title="EVR Collection API")


class BenchmarkEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["set", "era", "sealed_product"]
    entity_id: UUID


class BenchmarkCurrentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: List[BenchmarkEntityRequest] = Field(min_length=1, max_length=10)


class BenchmarkBatchCurrentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: List[BenchmarkEntityRequest] = Field(min_length=1, max_length=200)


class BenchmarkFinancialHistoryEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["set", "era"]
    entity_id: UUID


class BenchmarkFinancialHistoryCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    market_date: date = Field(alias="marketDate")
    entity_type: Literal["set", "era"] = Field(alias="entityType")
    entity_id: UUID = Field(alias="entityId")


class BenchmarkFinancialHistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: List[BenchmarkFinancialHistoryEntityRequest] = Field(min_length=1, max_length=22)
    start_date: date
    end_date: date
    limit: int = Field(default=10000, ge=1, le=10000)
    after: Optional[BenchmarkFinancialHistoryCursor] = None


class BenchmarkHistoryRequest(BenchmarkCurrentRequest):
    start_date: date
    end_date: date
    limit: int = Field(default=500, ge=1, le=1000)
    after: Optional[Dict[str, Any]] = None


class BenchmarkSetHeadlinesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    set_ids: List[UUID] = Field(min_length=1, max_length=10)


def _benchmark_client():
    from backend.db.clients.supabase_client import create_short_timeout_service_client
    return create_short_timeout_service_client()


def _benchmark_reader(client: Any) -> PrivateBenchmarkReader:
    return PrivateBenchmarkReader(require_access=lambda: True,
                                  client_factory=lambda _timeout: client,
                                  timeout_seconds=10)


def _benchmark_unavailable(exc: BenchmarkContractUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "RIP_BENCHMARK_CONTRACT_UNAVAILABLE",
        "message": str(exc),
    })


def _benchmark_runtime_error(exc: RuntimeError) -> HTTPException:
    if "history publications changed; restart pagination" in str(exc):
        return HTTPException(status_code=409, detail={
            "code": "RIP_BENCHMARK_HISTORY_REVISION_CHANGED",
            "message": "Benchmark history changed during pagination; restart from the first page.",
        })
    raise exc


def _with_benchmark_freshness(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Expose certified dates explicitly; never infer freshness from updated_at."""
    result = dict(payload)
    if result.get("status") == "available":
        market_date = result.get("market_date")
        result["freshness"] = {
            "benchmarkMarketDate": market_date,
            "modelSourceDate": market_date,
            "financialEvidenceDate": market_date,
            "activeModelVersion": result.get("overall_model_version"),
        }
    return result


_PUBLIC_SET_HEADLINE_ROW_FIELDS = {
    "entity_type", "entity_id", "metric_key", "benchmark_score", "rank", "cohort_size",
    "benchmark_status", "benchmark_reason", "model_status", "model_reason", "source_market_date",
    "model_version",
}


def _public_set_headlines(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Narrow current-only replacement for the already-public Set score headlines."""
    freshness = _with_benchmark_freshness(payload).get("freshness") or {}
    rows = []
    for source in payload.get("rows", []):
        if source.get("entity_type") != "set" or source.get("metric_key") not in {"overall", "financial", "chase", "collector"}:
            continue
        rows.append({key: source.get(key) for key in _PUBLIC_SET_HEADLINE_ROW_FIELDS if key in source})
    return {
        "contract_version": "rip-benchmark-set-headlines-v1",
        "status": payload.get("status", "unavailable"),
        "publication_id": payload.get("publication_id"),
        "market_date": payload.get("market_date"),
        "rows": rows,
        "freshness": {
            "benchmarkMarketDate": freshness.get("benchmarkMarketDate"),
            "modelSourceDate": freshness.get("modelSourceDate"),
            "activeModelVersion": freshness.get("activeModelVersion"),
        },
    }


def _with_benchmark_history_context(client: Any, payload: Dict[str, Any], contract: Any) -> Dict[str, Any]:
    """Attach bounded public chart metadata; never expose source manifests."""
    result = dict(payload)
    base = lambda: client.table("pokemon_rip_benchmark_publications_v1").select("market_date") \
        .eq("benchmark_key", contract.benchmark_key).eq("calibration_version", contract.calibration_version) \
        .eq("publication_status", "published")
    earliest = list(base().order("market_date").limit(1).execute().data or [])
    latest = list(base().order("market_date", desc=True).limit(1).execute().data or [])
    result["historyAvailableFrom"] = earliest[0]["market_date"] if earliest else None
    result["historyAvailableThrough"] = latest[0]["market_date"] if latest else None
    dates = sorted({str(row.get("market_date"))[:10] for row in result.get("rows", []) if row.get("market_date")})
    publications = []
    if dates:
        publications = list(client.table("pokemon_rip_benchmark_publications_v1")
            .select("market_date,opening_economics_snapshot_id")
            .eq("benchmark_key", contract.benchmark_key).eq("calibration_version", contract.calibration_version)
            .eq("publication_status", "published").in_("market_date", dates).limit(250).execute().data or [])
    snapshot_ids = sorted({str(row["opening_economics_snapshot_id"]) for row in publications if row.get("opening_economics_snapshot_id")})
    snapshots = []
    if snapshot_ids:
        snapshots = list(client.table("pokemon_rip_stats_snapshots").select("id,market_date,payload_json").in_("id", snapshot_ids).execute().data or [])
    references = {}
    for snapshot in snapshots:
        economics = (snapshot.get("payload_json") or {}).get("openingEconomics") or {}
        global_scope = economics.get("global") or {}
        references[str(snapshot.get("market_date"))[:10]] = {
            "market_date": str(snapshot.get("market_date"))[:10],
            "modeled_return_on_spend": global_scope.get("modeledReturnOnSpend"),
            "cost_per_pack": global_scope.get("averageCostPerPack"),
            "expected_value_per_pack": global_scope.get("averageModelBreakEvenPerPack"),
        }
    result["opening_economics_references"] = references
    return result


def _with_current_opening_reference(client: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(payload)
    publication_id = result.get("publication_id")
    if not publication_id:
        return result
    headers = list(client.table("pokemon_rip_benchmark_publications_v1").select("opening_economics_snapshot_id")
        .eq("id", publication_id).limit(1).execute().data or [])
    snapshot_id = headers[0].get("opening_economics_snapshot_id") if headers else None
    if not snapshot_id:
        return result
    snapshots = list(client.table("pokemon_rip_stats_snapshots").select("market_date,payload_json")
        .eq("id", snapshot_id).limit(1).execute().data or [])
    if snapshots:
        economics = (snapshots[0].get("payload_json") or {}).get("openingEconomics") or {}
        scope = economics.get("global") or {}
        result["opening_economics_reference"] = {
            "market_date": str(snapshots[0].get("market_date"))[:10],
            "modeled_return_on_spend": scope.get("modeledReturnOnSpend"),
            "cost_per_pack": scope.get("averageCostPerPack"),
            "expected_value_per_pack": scope.get("averageModelBreakEvenPerPack"),
        }
    return result


def _benchmark_entity_dicts(items: List[BenchmarkEntityRequest]) -> List[Dict[str, str]]:
    entities = [item.model_dump(mode="json") for item in items]
    identities = [(item["entity_type"], item["entity_id"]) for item in entities]
    if len(set(identities)) != len(identities):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST",
            "message": "duplicate requested entity",
        })
    return entities


def _benchmark_generation_signature(payload: Dict[str, Any]) -> tuple[Any, ...]:
    return tuple(payload.get(key) for key in (
        "publication_id", "market_date", "benchmark_key", "calibration_version",
        "cohort_fingerprint", "overall_model_version",
    ))


def _read_current_benchmark_batch(
    client: Any, entities: List[Dict[str, str]], contract: Any
) -> Dict[str, Any]:
    reader = _benchmark_reader(client)
    payloads = [
        reader.current(
            entities[index:index + 10],
            benchmark_key=contract.benchmark_key,
            calibration_version=contract.calibration_version,
        )
        for index in range(0, len(entities), 10)
    ]
    if not payloads:
        raise BenchmarkError("at least one Benchmark entity is required")
    signature = _benchmark_generation_signature(payloads[0])
    if any(_benchmark_generation_signature(payload) != signature for payload in payloads[1:]):
        raise RuntimeError("mixed current Benchmark publications; retry the request")
    result = dict(payloads[0])
    result["rows"] = [
        row for payload in payloads
        for row in (payload.get("rows") or [])
    ]
    return result


def _financial_history_range(client: Any, contract: Any) -> Dict[str, Optional[str]]:
    query = lambda: (
        client.table("pokemon_rip_benchmark_publications_v1")
        .select("market_date")
        .eq("benchmark_key", contract.benchmark_key)
        .eq("calibration_version", contract.calibration_version)
        .eq("publication_status", "published")
    )
    earliest = list(query().order("market_date").limit(1).execute().data or [])
    latest = list(query().order("market_date", desc=True).limit(1).execute().data or [])
    return {
        "historyAvailableFrom": str(earliest[0]["market_date"])[:10] if earliest else None,
        "historyAvailableThrough": str(latest[0]["market_date"])[:10] if latest else None,
    }


def _public_benchmark_overview_headlines(client: Any, contract: Any) -> Dict[str, Any]:
    headers = list(
        client.table("pokemon_rip_benchmark_publications_v1")
        .select("id,market_date,opening_economics_snapshot_id")
        .eq("benchmark_key", contract.benchmark_key)
        .eq("calibration_version", contract.calibration_version)
        .eq("publication_status", "published")
        .order("market_date", desc=True)
        .limit(1)
        .execute().data or []
    )
    if not headers:
        return {
            "contractVersion": "rip-benchmark-overview-headlines-v1",
            "status": "unavailable", "marketDate": None,
            "topSet": None, "topEra": None,
        }
    header = headers[0]
    rows = list(
        client.table("pokemon_rip_benchmark_rows_v1")
        .select("entity_type,entity_id,benchmark_score,rank,cohort_size,benchmark_status,model_status")
        .eq("publication_id", header["id"])
        .eq("metric_key", "overall")
        .eq("rank", 1)
        .in_("entity_type", ["set", "era"])
        .execute().data or []
    )
    opening_rows = list(
        client.table("pokemon_rip_stats_snapshots")
        .select("payload_json")
        .eq("id", header.get("opening_economics_snapshot_id"))
        .limit(1)
        .execute().data or []
    ) if header.get("opening_economics_snapshot_id") else []
    economics = ((opening_rows[0].get("payload_json") or {}).get("openingEconomics") or {}) if opening_rows else {}
    set_names = {
        str(item.get("setId")): {
            "name": item.get("setName"),
            "canonicalKey": item.get("setCanonicalKey"),
        }
        for item in (economics.get("sets") or [])
        if item.get("setId")
    }
    era_names = {
        str(item.get("eraId")): item.get("eraName")
        for item in (economics.get("sets") or [])
        if item.get("eraId") and item.get("eraName")
    }
    def project(entity_type: str) -> Optional[Dict[str, Any]]:
        row = next((item for item in rows if item.get("entity_type") == entity_type), None)
        if not row:
            return None
        entity_id = str(row.get("entity_id") or "")
        identity = set_names.get(entity_id, {}) if entity_type == "set" else {}
        return {
            "entityType": entity_type,
            "entityId": entity_id,
            "name": identity.get("name") if entity_type == "set" else era_names.get(entity_id),
            **({"canonicalKey": identity.get("canonicalKey")} if entity_type == "set" else {}),
            "benchmarkScore": row.get("benchmark_score"),
            "rank": row.get("rank"),
            "cohortSize": row.get("cohort_size"),
            "status": row.get("benchmark_status"),
        }
    return {
        "contractVersion": "rip-benchmark-overview-headlines-v1",
        "status": "available",
        "marketDate": str(header.get("market_date"))[:10],
        "topSet": project("set"),
        "topEra": project("era"),
    }


@app.post("/tcgs/pokemon/rip-benchmark/current")
def pokemon_rip_benchmark_current(body: BenchmarkCurrentRequest,
                                  authorization: Optional[str] = Header(None),
                                  token_cookie: Optional[str] = Cookie(None, alias="token")):
    _require_index_feature(feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
                           message="RIP Benchmark requires Index Plus.",
                           authorization=authorization, token_cookie=token_cookie)
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        result = _benchmark_reader(client).current(
            _benchmark_entity_dicts(body.entities),
            benchmark_key=contract.benchmark_key,
            calibration_version=contract.calibration_version,
        )
        return _with_benchmark_freshness(_with_current_opening_reference(client, result))
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_RIP_BENCHMARK_REQUEST", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise _benchmark_runtime_error(exc) from exc


@app.post("/tcgs/pokemon/rip-benchmark/current-batch")
def pokemon_rip_benchmark_current_batch(
    request: Request,
    body: BenchmarkBatchCurrentRequest,
    authorization: Optional[str] = Header(None),
    token_cookie: Optional[str] = Cookie(None, alias="token"),
):
    user_id = _require_index_feature(
        feature=FEATURE_PRODUCT_RIP,
        code="INDEX_PLUS_REQUIRED",
        message="Product RIP Benchmark requires Index Plus.",
        authorization=authorization,
        token_cookie=token_cookie,
    )
    _enforce_paid_abuse(
        request, user_id=user_id, policy_class=POLICY_RANKED_INTELLIGENCE,
        route="/tcgs/pokemon/rip-benchmark/current-batch",
    )
    if any(item.entity_type != "sealed_product" for item in body.entities):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST",
            "message": "Product Benchmark batch accepts sealed_product entities only.",
        })
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        result = _read_current_benchmark_batch(
            client, _benchmark_entity_dicts(body.entities), contract
        )
        return _with_benchmark_freshness(_with_current_opening_reference(client, result))
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST", "message": str(exc)
        }) from exc
    except RuntimeError as exc:
        raise _benchmark_runtime_error(exc) from exc


@app.post("/tcgs/pokemon/rip-benchmark/set-headlines")
def pokemon_rip_benchmark_set_headlines(body: BenchmarkSetHeadlinesRequest):
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        result = _benchmark_reader(client).current(
            [{"entity_type": "set", "entity_id": str(set_id)} for set_id in dict.fromkeys(body.set_ids)],
            benchmark_key=contract.benchmark_key,
            calibration_version=contract.calibration_version,
        )
        return _public_set_headlines(result)
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_RIP_BENCHMARK_REQUEST", "message": str(exc)}) from exc


@app.get("/tcgs/pokemon/rip-benchmark/overview-headlines")
def pokemon_rip_benchmark_overview_headlines():
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        return _public_benchmark_overview_headlines(client, contract)
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc


@app.post("/tcgs/pokemon/rip-benchmark/history")
def pokemon_rip_benchmark_history(body: BenchmarkHistoryRequest,
                                  authorization: Optional[str] = Header(None),
                                  token_cookie: Optional[str] = Cookie(None, alias="token")):
    _require_index_feature(feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
                           message="RIP Benchmark history requires Index Plus.",
                           authorization=authorization, token_cookie=token_cookie)
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        result = _benchmark_reader(client).history_page(
            [item.model_dump(mode="json") for item in body.entities],
            start_date=body.start_date.isoformat(), end_date=body.end_date.isoformat(),
            benchmark_key=contract.benchmark_key, calibration_version=contract.calibration_version,
            limit=body.limit, after=body.after,
        )
        return _with_benchmark_history_context(client, result, contract)
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_RIP_BENCHMARK_REQUEST", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise _benchmark_runtime_error(exc) from exc


@app.post("/tcgs/pokemon/rip-benchmark/financial-history")
def pokemon_financial_rip_history(
    body: BenchmarkFinancialHistoryRequest,
    authorization: Optional[str] = Header(None),
    token_cookie: Optional[str] = Cookie(None, alias="token"),
):
    _require_index_feature(
        feature=FEATURE_SET_RIP_ANALYTICS,
        code="INDEX_PLUS_REQUIRED",
        message="Financial RIP history requires Index Plus.",
        authorization=authorization,
        token_cookie=token_cookie,
    )
    if (body.end_date - body.start_date).days > 3652:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST",
            "message": "Financial RIP history window must be at most 10 years.",
        })
    entities = [item.model_dump(mode="json") for item in body.entities]
    identities = [(item["entity_type"], item["entity_id"]) for item in entities]
    if len(set(identities)) != len(identities):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST",
            "message": "duplicate requested entity",
        })
    client = _benchmark_client()
    try:
        return read_financial_history_page(
            client, entities=entities, start_date=body.start_date,
            end_date=body.end_date, limit=body.limit,
            after=body.after.model_dump(mode="json", by_alias=True) if body.after else None,
        )
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc
    except BenchmarkError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_RIP_BENCHMARK_REQUEST", "message": str(exc)
        }) from exc


@app.get("/tcgs/pokemon/rankings/overview-v2")
def pokemon_rankings_overview_v2():
    """Public narrow first-render projection; no paid Benchmark dependency."""
    global _rankings_overview_cache
    cached = _rankings_overview_cache
    if cached and cached[0] > time.monotonic():
        return cached[1]
    client = _benchmark_client()
    try:
        contract = resolve_active_contract(client)
        result = read_overview_v2(
            client, legacy_headlines=_public_benchmark_overview_headlines(client, contract)
        )
        _rankings_overview_cache = (time.monotonic() + 60.0, result)
        return result
    except BenchmarkContractUnavailable as exc:
        raise _benchmark_unavailable(exc) from exc


@app.get("/tcgs/pokemon/rankings/financial-cohort")
def pokemon_rankings_financial_cohort():
    """Public identities only: the 22-Set Financial opening cohort."""
    return read_financial_cohort(_benchmark_client())


@app.get("/tcgs/pokemon/rankings/scorecards")
def pokemon_rankings_scorecards(
    entity_type: Literal["set", "era"] = Query(...),
    authorization: Optional[str] = Header(None),
    token_cookie: Optional[str] = Cookie(None, alias="token"),
):
    _require_index_feature(feature=FEATURE_SET_RIP_ANALYTICS, code="INDEX_PLUS_REQUIRED",
                           message="Rankings scorecards require Index Plus.",
                           authorization=authorization, token_cookie=token_cookie)
    client = _benchmark_client()
    contract = resolve_active_contract(client)
    return read_scorecards(client, entity_type=entity_type, benchmark_key=contract.benchmark_key,
                           calibration_version=contract.calibration_version)


@app.get("/tcgs/pokemon/rankings/headlines")
def pokemon_rankings_public_headlines(entity_type: Literal["set", "era"] = Query(...)):
    """Public, publication-bound Overall score/rank only."""
    client = _benchmark_client()
    contract = resolve_active_contract(client)
    return read_public_headlines(client, entity_type=entity_type, benchmark_key=contract.benchmark_key,
                                 calibration_version=contract.calibration_version)


@app.get("/tcgs/pokemon/rankings/pack-economics-preview")
def pokemon_rankings_pack_economics_preview():
    return read_public_pack_economics_preview(_benchmark_client())


@app.get("/tcgs/pokemon/rankings/product-catalogue")
def pokemon_rankings_product_catalogue(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    search: Optional[str] = Query(default=None), family: Optional[str] = Query(default=None),
):
    return read_public_product_catalogue_page(
        _benchmark_client(), page=page, page_size=page_size, search=search, family=family)


@app.get("/tcgs/pokemon/rankings/pack-economics")
def pokemon_rankings_pack_economics(
    authorization: Optional[str] = Header(None),
    token_cookie: Optional[str] = Cookie(None, alias="token"),
):
    """Plus prepared economics joined to exact, independently dated Best-Open."""
    _require_index_feature(
        feature=FEATURE_PACK_ECONOMICS, code="INDEX_PLUS_REQUIRED",
        message="Detailed Pack Economics requires Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    return read_pack_economics(_benchmark_client())


logger = logging.getLogger(__name__)

# These contain only shared, publication-bound authority data. Entitlement is
# still checked on every paid request and paid HTTP responses remain no-store.
_rankings_overview_cache: tuple[float, Dict[str, Any]] | None = None
_rankings_product_authority_cache: tuple[tuple[str, str, str], Dict[str, Any]] | None = None

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
    activity_read = request.url.path.startswith("/market/explorer/activity")
    if activity_read or request.headers.get("authorization") or request.cookies.get("token"):
        response.headers["Cache-Control"] = "private, no-store" if activity_read else "no-store"
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


class MarketExplorerQualifiedInstrument(BaseModel):
    asset: str
    instrumentId: str = Field(min_length=1)


class MarketExplorerQueryRequest(BaseModel):
    asset: str = "cards"
    membershipMode: str = "filters"
    instrumentIds: List[str] = Field(default_factory=list, max_length=25)
    instruments: List[MarketExplorerQualifiedInstrument] = Field(default_factory=list, max_length=25)
    eraIds: List[str] = Field(default_factory=list)
    setIds: List[str] = Field(default_factory=list)
    segmentIds: List[str] = Field(default_factory=list)
    pokemonIds: List[str] = Field(default_factory=list)
    priceSegmentIds: List[str] = Field(default_factory=list)
    releaseAgeCohortIds: List[str] = Field(default_factory=list)
    mode: str = "all"
    topN: Optional[int] = Field(default=None, ge=1, le=100)
    responseMode: str = "full"


class MarketExplorerConstituentPageRequest(MarketExplorerQueryRequest):
    limit: int = Field(default=100, ge=1, le=100)
    afterRank: int = Field(default=0, ge=0)


class MarketExplorerPreflightRequest(BaseModel):
    """A cheap 'how many cards/sets would this match' check.

    Filters-only: Exact Basket (explicit instrument) membership is
    intentionally out of scope for preflight, matching the RPC it calls.
    """
    eraIds: List[str] = Field(default_factory=list)
    setIds: List[str] = Field(default_factory=list)
    segmentIds: List[str] = Field(default_factory=list)
    pokemonIds: List[str] = Field(default_factory=list)
    priceSegmentIds: List[str] = Field(default_factory=list)
    releaseAgeCohortIds: List[str] = Field(default_factory=list)


class PreparedComparisonRequest(BaseModel):
    marketKeys: List[str] = Field(min_length=1, max_length=25)
    # Keys already on the caller's chart. NEVER read here (each market's rows are
    # independent, so the client fetches only what it is adding); they exist
    # solely so the Index+ "compare" entitlement is judged on the whole
    # workspace rather than being bypassed by one-market-at-a-time requests.
    contextMarketKeys: List[str] = Field(default_factory=list, max_length=25)
    startDate: Optional[date] = None


class DirectInstrumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Literal["cards", "sealed"]
    instrumentId: str = Field(min_length=1, max_length=64)
    startDate: Optional[date] = None


class BillingCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offerKey: str = Field(min_length=1, max_length=80)


class BillingPlanChangePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offerKey: str = Field(min_length=1, max_length=80)


class BillingPlanChangeConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offerKey: str = Field(min_length=1, max_length=80)
    previewToken: Optional[str] = Field(default=None, max_length=4096)


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


# Profile and Portfolio are not production-ready. Public read surfaces that
# expose their data are hard-stopped here, BEFORE any DB/service call, so a
# request can never reach a loader that would leak private collection or
# profile data. This mirrors the existing "feature not available" convention
# used for billing (e.g. BILLING_NOT_CONFIGURED / BILLING_PROVIDER_UNAVAILABLE
# at 503) rather than treating the route as truly nonexistent (404) — the
# routes are real, temporarily switched off. This must NEVER be applied to
# /profile/me, auth/session endpoints, or collection/portfolio mutation
# endpoints — only to public read endpoints that expose Profile/Portfolio
# data to third parties.
def _public_profile_portfolio_disabled_response() -> JSONResponse:
    return JSONResponse(
        content={
            "message": "This feature is temporarily unavailable.",
            "code": "FEATURE_TEMPORARILY_DISABLED",
        },
        status_code=503,
    )


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
    spec: Dict[str, Any], *, authorization: Optional[str], token_cookie: Optional[str],
    allow_public_canonical_rarity: bool = False,
    public_identity: Optional[str] = None,
) -> str:
    """Authorize one normalized definition before any query/cache work.

    The sole unauthenticated seam is an exact canonical-rarity preset verified
    against the current DB registry. Callers must opt into that seam; constituent
    paging deliberately does not, so constituent entitlement remains Index+.
    """
    if allow_public_canonical_rarity and is_canonical_rarity_query_shape(spec):
        try:
            options = read_asset_options(service_read_client, "cards")
        except (SurfaceV2Error, ValueError):
            options = None
        rarity_key = str((spec.get("segmentIds") or ("",))[0])
        if is_selectable_canonical_rarity(options, rarity_key):
            return public_identity or f"public-canonical-rarity:{rarity_key}"

    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    plan = _resolve_index_plan(authorization, token_cookie)
    decision = evaluate_market_query_access(plan, spec)
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


def _require_card_collector_appeal(
    *, authorization: Optional[str], token_cookie: Optional[str]
) -> str:
    """Gate prepared card Collector Appeal before any database access."""
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    if not has_index_feature_access(
        _resolve_index_plan(authorization, token_cookie), FEATURE_CARD_COLLECTOR_APPEAL
    ):
        emit_security_event("entitlement_denied", route="card_collector_appeal",
                            policy_class=POLICY_RANKED_INTELLIGENCE, user_id=user_id,
                            required_capability=FEATURE_CARD_COLLECTOR_APPEAL, authenticated=True)
        raise HTTPException(status_code=403, detail={
            "message": "Collector Appeal card rankings require Index Plus.",
            "code": "CARD_COLLECTOR_APPEAL_PLUS_REQUIRED",
            "requiredFeature": FEATURE_CARD_COLLECTOR_APPEAL,
        })
    return user_id


def _require_product_chase_intelligence(
    *, authorization: Optional[str], token_cookie: Optional[str]
) -> str:
    """Authenticate and resolve Premium from the canonical profile server-side.

    Product Chase Intelligence (O_budget) is Premium-only and DISTINCT from
    Card Chase Efficiency - a Plus or Free request must never receive this
    payload, including via direct API access, not merely a hidden frontend
    control. See ``test_product_chase_access_api.py`` for the negative test.
    """
    user_id = _require_authenticated_user_id(
        authorization=authorization, token_cookie=token_cookie
    )
    if not has_index_feature_access(
        _resolve_index_plan(authorization, token_cookie), FEATURE_PRODUCT_CHASE_INTELLIGENCE
    ):
        emit_security_event("entitlement_denied", route="product_chase_intelligence",
                            policy_class=POLICY_RANKED_INTELLIGENCE, user_id=user_id,
                            required_capability=FEATURE_PRODUCT_CHASE_INTELLIGENCE, authenticated=True)
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Product Chase Intelligence requires Index Premium.",
                "code": "PRODUCT_CHASE_INTELLIGENCE_PREMIUM_REQUIRED",
                "requiredFeature": FEATURE_PRODUCT_CHASE_INTELLIGENCE,
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


_MARKET_ACTIVITY_SCHEMA_REGISTRY = SchemaRegistry(
    Path(__file__).resolve().parents[2] / "docs" / "research" / "market_activity_v1" / "contracts"
)


def _require_market_activity_access(
    payload: Any, *, authorization: Optional[str], token_cookie: Optional[str],
) -> str:
    """Authenticate, resolve the canonical profile plan, then enforce Activity access."""
    _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    plan = _resolve_index_plan(authorization, token_cookie)
    market_keys: list[str] = []
    custom_roster = False
    if isinstance(payload, dict):
        if isinstance(payload.get("marketKey"), str):
            market_keys.append(payload["marketKey"])
        for item in payload.get("markets", []) if isinstance(payload.get("markets"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("marketKey"), str):
                market_keys.append(item["marketKey"])
            if (isinstance(item, dict) and isinstance(item.get("rosterRef"), dict)
                    and item["rosterRef"].get("kind") == "QUERY_CACHE_PUBLISHED_REVISION"):
                custom_roster = True
        if (isinstance(payload.get("rosterRef"), dict)
                and payload["rosterRef"].get("kind") == "QUERY_CACHE_PUBLISHED_REVISION"):
            custom_roster = True
    custom = custom_roster or any(key.startswith("custom:") for key in market_keys)
    allowed = has_index_premium_access(plan) if custom else has_index_plus_access(plan)
    if not allowed:
        raise HTTPException(status_code=403, detail={
            "message": "Custom Market Activity requires Index Premium." if custom
                       else "Market Activity requires Index Plus.",
            "code": "MARKET_ACTIVITY_PLAN_REQUIRED",
            "requiredPlan": "premium" if custom else "plus",
        })
    return str(plan)


def _market_activity_request(payload: Any, schema_name: str) -> Dict[str, Any]:
    errors = _MARKET_ACTIVITY_SCHEMA_REGISTRY.validate(payload, schema_name)
    if errors:
        raise HTTPException(status_code=400, detail={
            "message": "Invalid Market Activity request.",
            "code": "MARKET_ACTIVITY_REQUEST_INVALID", "errors": errors[:8],
        })
    return dict(payload)


def _market_activity_response(payload: Dict[str, Any], schema_name: str) -> JSONResponse:
    errors = _MARKET_ACTIVITY_SCHEMA_REGISTRY.validate(payload, schema_name)
    if errors:
        logger.error("market_activity.contract_violation schema=%s errors=%s",
                     schema_name, errors[:3])
        return JSONResponse(status_code=500, headers={"Cache-Control": "private, no-store"}, content={
            "message": "Market Activity response contract violation.",
            "code": "MARKET_ACTIVITY_CONTRACT_VIOLATION",
        })
    return JSONResponse(content=payload, headers={"Cache-Control": "private, no-store"})


def _market_activity_capability_request(payload: Any, plan: str) -> tuple[list[Dict[str, Any]], int]:
    errors: list[str] = []
    if not isinstance(payload, dict) or set(payload) != {"markets", "windowDays"}:
        errors.append("$: expected exactly markets and windowDays")
    markets = payload.get("markets") if isinstance(payload, dict) else None
    window_days = payload.get("windowDays") if isinstance(payload, dict) else None
    if not isinstance(markets, list) or not 1 <= len(markets) <= 10:
        errors.append("$.markets: expected 1..10 items")
        markets = []
    limit = market_explorer_active_market_limit(plan)
    if len(markets) > limit:
        errors.append(f"$.markets: plan permits at most {limit} active markets")
    if window_days not in (7, 30, 90, 180) or isinstance(window_days, bool):
        errors.append("$.windowDays: expected one of 7, 30, 90, 180")
    focus_keys: list[str] = []
    market_keys: list[str] = []
    for index, item in enumerate(markets):
        if not isinstance(item, dict) or set(item) != {"focusKey", "marketKey", "rosterRef"}:
            errors.append(f"$.markets[{index}]: invalid fields")
            continue
        if not isinstance(item.get("focusKey"), str) or not item["focusKey"]:
            errors.append(f"$.markets[{index}].focusKey: expected non-empty string")
        if not isinstance(item.get("marketKey"), str) or not item["marketKey"]:
            errors.append(f"$.markets[{index}].marketKey: expected non-empty string")
        if not isinstance(item.get("rosterRef"), dict):
            errors.append(f"$.markets[{index}].rosterRef: expected object")
        else:
            roster_ref = item["rosterRef"]
            if roster_ref.get("kind") == "SURFACE_V2_GENERATION":
                if set(roster_ref) != {"kind", "generationId", "marketKey"}:
                    errors.append(f"$.markets[{index}].rosterRef: invalid prepared reference")
                try:
                    UUID(str(roster_ref.get("generationId")))
                except (TypeError, ValueError):
                    errors.append(f"$.markets[{index}].rosterRef.generationId: invalid UUID")
                if roster_ref.get("marketKey") != item.get("marketKey"):
                    errors.append(f"$.markets[{index}].rosterRef.marketKey: mismatch")
            elif roster_ref.get("kind") == "QUERY_CACHE_PUBLISHED_REVISION":
                # A bare fingerprint is syntactically accepted so discovery can
                # fail closed as unavailable instead of guessing a revision.
                full = {"kind", "queryFingerprint", "revisionId", "computedThrough"}
                if set(roster_ref) != full and set(roster_ref) != {"kind", "queryFingerprint"}:
                    errors.append(f"$.markets[{index}].rosterRef: invalid custom reference")
                if not isinstance(roster_ref.get("queryFingerprint"), str) or not roster_ref["queryFingerprint"]:
                    errors.append(f"$.markets[{index}].rosterRef.queryFingerprint: invalid")
                if set(roster_ref) == full:
                    try:
                        UUID(str(roster_ref.get("revisionId")))
                        date.fromisoformat(str(roster_ref.get("computedThrough")))
                    except (TypeError, ValueError):
                        errors.append(f"$.markets[{index}].rosterRef: invalid immutable revision")
            else:
                errors.append(f"$.markets[{index}].rosterRef.kind: unsupported")
        focus_keys.append(item.get("focusKey"))
        market_keys.append(item.get("marketKey"))
    if len(set(focus_keys)) != len(focus_keys):
        errors.append("$.markets: duplicate focusKey")
    if len(set(market_keys)) != len(market_keys):
        errors.append("$.markets: duplicate marketKey")
    if errors:
        raise HTTPException(status_code=400, detail={
            "message": "Invalid Market Activity request.",
            "code": "MARKET_ACTIVITY_REQUEST_INVALID", "errors": errors[:8],
        })
    return [dict(item) for item in markets], int(window_days)


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
    return f"{origin}/billing/success", f"{origin}/billing/cancel"


def _billing_portal_return_url() -> str:
    origin = (os.getenv("FRONTEND_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
    if os.getenv("APP_ENV", "").lower() == "production" and not origin.startswith("https://"):
        raise HTTPException(status_code=503, detail={"code": "BILLING_NOT_CONFIGURED"})
    return f"{origin}/account-settings?section=billing"


def _enforce_billing_post_origin(request: Request) -> None:
    """Reject browser cross-site POSTs while preserving non-browser bearer clients."""
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    origin = (request.headers.get("origin") or "").rstrip("/")
    trusted = (os.getenv("FRONTEND_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
    if fetch_site == "cross-site" or (origin and origin != trusted):
        raise HTTPException(status_code=403, detail={"code": "BILLING_CROSS_SITE_REQUEST_REJECTED"})


@app.post("/billing/checkout-session")
def create_billing_checkout_session(
    payload: BillingCheckoutRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
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
    except BillingSubscriptionAlreadyManaged:
        raise HTTPException(status_code=409, detail={"code": "BILLING_SUBSCRIPTION_ALREADY_MANAGED"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


@app.post("/billing/change-plan/preview")
def preview_billing_plan_change(
    payload: BillingPlanChangePreviewRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().preview_plan_change(user_id=user_id, offer_key=payload.offerKey)
        return _tiered_response(dto)
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    except UnsupportedSubscriptionShape as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except UnmappedStripePrice as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


@app.post("/billing/change-plan/confirm")
def confirm_billing_plan_change(
    payload: BillingPlanChangeConfirmRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().confirm_plan_change(
            user_id=user_id, offer_key=payload.offerKey, preview_token=payload.previewToken
        )
        return _tiered_response(dto)
    except PlanChangePreviewStale as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    except UnsupportedSubscriptionShape as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except UnmappedStripePrice as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


@app.post("/billing/change-plan/cancel-scheduled")
def cancel_billing_scheduled_plan_change(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        dto = BillingService().cancel_scheduled_plan_change(user_id=user_id)
        return _tiered_response(dto)
    except PlanChangeNotAllowed as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)})
    except BillingOwnershipError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    except BillingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


@app.get("/billing/me")
def get_billing_me(
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    return _tiered_response(BillingService().billing_status(user_id))


@app.get("/billing/catalog")
def get_billing_catalog():
    """Public commercial display data; contains no provider identifiers."""
    return _tiered_response(BillingService().public_catalog())


@app.post("/billing/customer-portal")
def create_billing_customer_portal(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    _enforce_billing_post_origin(request)
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    try:
        portal_url = BillingService().create_customer_portal(
            user_id=user_id, return_url=_billing_portal_return_url())
        return _tiered_response({"portalUrl": portal_url})
    except BillingPortalUnavailable:
        raise HTTPException(status_code=409, detail={"code": "BILLING_PORTAL_UNAVAILABLE"})
    except BillingProviderError:
        raise HTTPException(status_code=503, detail={"code": "BILLING_PROVIDER_UNAVAILABLE"})
    except BillingError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code})


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
    # Public Portfolio surface is not production-ready — hard-stop before any
    # DB/service call. See _public_profile_portfolio_disabled_response.
    return _public_profile_portfolio_disabled_response()


@app.get("/public/profiles/{username}")
def get_public_profile_page(
    username: str,
    include_collection_items: Optional[str] = Query(default="1"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    # Public Profile surface is not production-ready — hard-stop before any
    # DB/service call. See _public_profile_portfolio_disabled_response.
    return _public_profile_portfolio_disabled_response()


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


@app.get("/explore/rankings/homepage-summary")
def get_explore_rankings_homepage_summary(limit: Optional[str] = Query(default=None)):
    """The Homepage's narrow public Rankings projection (Prompt 2 / A2).

    Deliberately takes NO Authorization/Cookie parameters: every field this
    endpoint returns is intentionally public and must be byte-identical for
    anonymous, Base, Plus, and Premium visitors, so there is no session state
    for this handler to resolve in the first place -- unlike
    `/explore/rip-statistics/targets` and `/explore/rankings/lens/{lens}`,
    which both resolve plan entitlement before projecting. This does not
    change either of those endpoints' contracts or behavior.
    """
    try:
        client = _benchmark_client()
        contract = resolve_active_contract(client)
        payload = get_pokemon_homepage_benchmark_summary_payload(client, contract, limit=limit or 60)
        return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})
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
        logger.exception("/explore/rankings/homepage-summary unexpected error")
        return JSONResponse(
            content={"message": "Unable to load Homepage Rankings summary", "code": "HOMEPAGE_RANKINGS_SUMMARY_FAILED"},
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
            return _tiered_response(project_set_rankings_lens_response(payload, plan))
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


@app.get("/explore/card-collector-appeal")
def get_card_collector_appeal_rankings(
    request: Request,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    search: Optional[str] = Query(default=None), era: Optional[str] = Query(default=None),
    set_id: Optional[str] = Query(default=None, alias="set"), rarity: Optional[str] = Query(default=None),
    sort: str = Query(default="rank"), direction: str = Query(default="asc"),
    lens: Literal["overall", "pokemon", "trainer", "artist", "playability"] = Query(default="overall"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    user_id = _require_card_collector_appeal(authorization=authorization, token_cookie=token_cookie)
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_RANKED_INTELLIGENCE,
                        route="/explore/card-collector-appeal")
    try:
        return _tiered_response(query_card_collector_appeal(
            service_read_client, page=page, page_size=page_size, search=search,
            era=era, set_id=set_id, rarity=rarity, sort=sort, direction=direction, lens=lens,
        ))
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "CARD_COLLECTOR_APPEAL_QUERY_INVALID"}, status_code=400)
    except Exception:
        logger.exception("/explore/card-collector-appeal unexpected error")
        return JSONResponse(content={"message": "Unable to load Collector Appeal", "code": "CARD_COLLECTOR_APPEAL_FAILED"}, status_code=500)


@app.get("/explore/card-ranking-facets")
def get_card_ranking_facets(
    lens: Literal["collector", "chase"] = Query(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    # Facet membership itself reveals the paid ranking universe, so apply the
    # same gate as the corresponding rows before touching the pointer view.
    if lens == "collector":
        _require_card_collector_appeal(authorization=authorization, token_cookie=token_cookie)
    else:
        _require_card_chase_efficiency(authorization=authorization, token_cookie=token_cookie)
    return _tiered_response(read_card_facets(service_read_client, lens=lens))


def _rankings_product_v2(
    *, view: str, request: Request, authorization: Optional[str], token_cookie: Optional[str],
    page: int, page_size: int, search: Optional[str], family: Optional[str],
    sort: Optional[str], direction: str,
):
    user_id = _require_index_feature(
        feature=FEATURE_PRODUCT_RIP, code="INDEX_PLUS_REQUIRED",
        message="Product Rankings require Index Plus.",
        authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_RANKED_INTELLIGENCE,
                        route=f"/explore/product-rankings/{view}")
    global _rankings_product_authority_cache
    release = rip_release.resolve_release_or_marked_fallback(service_read_client)
    ranking_kwargs = {} if release.ranking_method_version == "budget_product_ranking_v1" else {
        "ranking_method_version": release.ranking_method_version}
    snapshot = load_latest_snapshot(service_read_client, **ranking_kwargs)
    identity = None if not snapshot else (str(snapshot.get("id")), str(snapshot.get("published_at")),
                                          str(snapshot.get("cohort_fingerprint")))
    cached = _rankings_product_authority_cache
    if identity is not None and cached and cached[0] == identity:
        authority = cached[1]
    else:
        authority = read_product_authority(service_read_client, release=release)
        if authority.get("available"):
            _rankings_product_authority_cache = (authority["publicationIdentity"], authority)
    return _tiered_response(query_product_rankings(
        service_read_client, authority, view=view, page=page, page_size=page_size,
        search=search, family=family, sort=sort, direction=direction,
    ))


@app.get("/explore/product-rankings/scores")
def get_product_ranking_scores(
    request: Request,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    search: Optional[str] = Query(default=None), family: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None), direction: str = Query(default="asc"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    return _rankings_product_v2(view="scores", request=request, authorization=authorization,
                                token_cookie=token_cookie, page=page, page_size=page_size,
                                search=search, family=family, sort=sort, direction=direction)


@app.get("/explore/product-rankings/economics")
def get_product_ranking_economics(
    request: Request,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    search: Optional[str] = Query(default=None), family: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None), direction: str = Query(default="asc"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    return _rankings_product_v2(view="economics", request=request, authorization=authorization,
                                token_cookie=token_cookie, page=page, page_size=page_size,
                                search=search, family=family, sort=sort, direction=direction)


@app.get("/explore/product-chase-intelligence")
def get_product_chase_intelligence(
    request: Request,
    budget: Optional[float] = Query(default=None, ge=0),
    price_as_of: Optional[str] = Query(default=None),
    sealed_product_id: Optional[str] = Query(default=None),
    set_id: Optional[str] = Query(default=None, alias="set"),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """PREMIUM-ONLY. Chase Access at Budget (O_budget) for the same pinned
    budget-ranking cohort the normal Plus budget ranking already resolves.

    This is a SEPARATE contract from the normal Plus product/budget rankings
    endpoint (``/explore/product-rankings/overall``) and from
    ``/explore/card-chase-efficiency`` (Card Chase Efficiency, a distinct
    Premium construct). It is never routed through either. A Plus or Free
    request is rejected before any cohort/authority data is touched.

    ``sealed_product_id`` (Phase 12 perf fix): a single product-detail-page
    request scopes the cohort down to that one product's row before the
    orchestration call below runs - which batches its Accessibility and
    variant-universe reads once per DISTINCT SET in the cohort it is handed.
    Without this scoping, every single product-page load resolved the FULL
    18-set/117-product global cohort (1 Accessibility batch read + 18
    variant-universe reads) just to render one product's row. Scoped to one
    product, the same call issues 1 Accessibility read + 1 variant-universe
    read. Cross-product ranking context (``oBudgetRank``) is meaningless
    against a 1-product cohort (it would trivially always read "#1"), so it
    is stripped in scoped mode; a caller that wants the real cross-format
    Product Chase ranking must omit ``sealed_product_id`` and pay for the
    full (deliberately more expensive) cohort resolution instead.
    """
    user_id = _require_product_chase_intelligence(authorization=authorization, token_cookie=token_cookie)
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_RANKED_INTELLIGENCE,
                        route="/explore/product-chase-intelligence")
    try:
        # UI-5 Phase 17 fix: this is a live, non-persisting read - unlike the
        # offline publish CLI, there is no human present to break a tie
        # between multiple equally-complete price_as_of dates. Resolve to the
        # freshest complete date ourselves rather than letting
        # `load_pinned_cohort`'s publish-time "refuse to guess" gate (correct
        # for a persisted snapshot) take down every Premium request with a
        # 503 whenever such a tie exists. A caller-supplied `price_as_of`
        # still wins unchanged.
        effective_price_as_of = price_as_of
        if effective_price_as_of is None:
            effective_price_as_of = most_recent_available_price_as_of(service_read_client)
        cohort, _authority = load_pinned_cohort(service_read_client, price_as_of=effective_price_as_of)
        scoped = False
        if sealed_product_id:
            cohort = [row for row in cohort if str(row.get("sealed_product_id")) == str(sealed_product_id)]
            scoped = True
            if isinstance(set_id, str) and set_id:
                cohort = [row for row in cohort if str(row.get("set_id")) == str(set_id)]
            if len(cohort) != 1:
                return JSONResponse(
                    content={"message": "Product identity is missing, duplicated, or does not match its set",
                             "code": "PRODUCT_CHASE_INTELLIGENCE_IDENTITY_MISMATCH", "products": []},
                    status_code=404 if not cohort else 409,
                )
        resolved = resolve_product_chase_access(service_read_client, cohort, budget=budget)
        if scoped:
            for row in resolved.get("products", []):
                row["oBudgetRank"] = None
        return _tiered_response(project_product_chase_access_response(
            resolved, _resolve_index_plan(authorization, token_cookie),
        ))
    except HTTPException:
        raise
    except Exception:
        logger.exception("/explore/product-chase-intelligence unexpected error budget=%s", budget)
        return JSONResponse(
            content={"message": "Unable to load Product Chase Intelligence",
                     "code": "PRODUCT_CHASE_INTELLIGENCE_FAILED", "products": []},
            status_code=503,
        )


@app.get("/tcgs/pokemon/set-route-directory")
def get_pokemon_set_route_directory(limit: int = Query(default=500, ge=1, le=500)):
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


@app.post("/market/explorer/activity/capabilities")
def post_market_explorer_activity_capabilities(
    payload: Any = Body(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    plan = _require_market_activity_access(
        payload, authorization=authorization, token_cookie=token_cookie,
    )
    markets, window_days = _market_activity_capability_request(payload, plan)
    try:
        response = discover_activity_capabilities(service_read_client, markets, window_days)
    except Exception:
        logger.exception("market_activity.capability_read_failed market_count=%s window_days=%s",
                         len(markets), window_days)
        return JSONResponse(status_code=500, headers={"Cache-Control": "private, no-store"}, content={
            "message": "Market Activity capability discovery failed.",
            "code": "MARKET_ACTIVITY_READ_FAILED",
        })
    return JSONResponse(content=response, headers={"Cache-Control": "private, no-store"})


def _post_market_activity_read(
    payload: Any, *, request_schema: str, response_schema: str, reader: Any,
    authorization: Optional[str], token_cookie: Optional[str],
) -> JSONResponse:
    _require_market_activity_access(payload, authorization=authorization, token_cookie=token_cookie)
    validated = _market_activity_request(payload, request_schema)
    try:
        response = reader(service_read_client, validated)
    except Exception:
        logger.exception("market_activity.read_failed schema=%s market=%s generation=%s",
                         request_schema, validated.get("marketKey"),
                         validated.get("activityGenerationId"))
        return JSONResponse(status_code=500, headers={"Cache-Control": "private, no-store"}, content={
            "message": "Market Activity read failed.", "code": "MARKET_ACTIVITY_READ_FAILED",
        })
    return _market_activity_response(response, response_schema)


@app.post("/market/explorer/activity")
def post_market_explorer_activity(
    payload: Any = Body(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    return _post_market_activity_read(
        payload, request_schema="activity_request.schema.json",
        response_schema="activity_response.schema.json", reader=read_group_activity,
        authorization=authorization, token_cookie=token_cookie,
    )


@app.post("/market/explorer/activity/constituents")
def post_market_explorer_activity_constituents(
    payload: Any = Body(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    return _post_market_activity_read(
        payload, request_schema="constituent_page_request.schema.json",
        response_schema="constituent_page_response.schema.json",
        reader=read_constituent_activity_page,
        authorization=authorization, token_cookie=token_cookie,
    )


@app.post("/market/explorer/activity/instrument")
def post_market_explorer_activity_instrument(
    payload: Any = Body(...),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    return _post_market_activity_read(
        payload, request_schema="instrument_detail_request.schema.json",
        response_schema="instrument_detail_response.schema.json", reader=read_instrument_activity,
        authorization=authorization, token_cookie=token_cookie,
    )


@app.get("/market/explorer/prepared-directory")
def get_market_explorer_prepared_directory():
    """Public, compact Browse authority. No Builder or query cache involved."""
    try:
        return {"markets": read_directory_v2_first(service_read_client)}
    except Exception:
        logger.exception("/market/explorer/prepared-directory unexpected error")
        return JSONResponse(content={"message": "Prepared markets are temporarily unavailable", "code": "PREPARED_DIRECTORY_FAILED"}, status_code=503)


@app.post("/market/explorer/prepared-comparison")
def post_market_explorer_prepared_comparison(payload: PreparedComparisonRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token")):
    comparing = len(set(payload.marketKeys) | set(payload.contextMarketKeys)) > 1
    if comparing:
        _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    if comparing:
        plan = _resolve_index_plan(authorization, token_cookie)
        if not has_index_plus_access(plan):
            raise HTTPException(status_code=403, detail={"message": "Compare markets with Index+.", "requiredPlan": "plus"})
        limit = market_explorer_active_market_limit(plan)
        if len(set(payload.marketKeys) | set(payload.contextMarketKeys)) > limit:
            raise HTTPException(status_code=403, detail={"message": f"Your plan supports up to {limit} active comparison markets.", "code": "ACTIVE_MARKET_LIMIT", "limit": limit})
    keys = list(dict.fromkeys(payload.marketKeys))
    try:
        return read_comparison_v2_first(
            service_read_client, keys, payload.startDate.isoformat() if payload.startDate else None,
        )
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "PREPARED_COMPARISON_INVALID"}, status_code=400)
    except PreparedSurfaceValidationError as exc:
        return JSONResponse(content={"message": "Prepared comparison authority is inconsistent", "code": exc.code}, status_code=409)
    except Exception as exc:
        # Live QA (2026-09-22) reproduced a bare, unhandled 500 ("Internal
        # Server Error") from this route for even a single Set market, taking
        # 10-16s against the underlying RPCs' own `statement_timeout = '5s'`
        # — almost certainly a Postgres statement timeout or similar RPC-level
        # failure surfacing uncaught because only ValueError was handled here.
        # This does not fix the slow query itself (root cause needs direct DB
        # access this session did not have), but it stops a raw crash from
        # reaching the client and matches the graceful-failure shape already
        # used by /market/explorer/prepared-screen and /prepared-directory.
        logger.exception("/market/explorer/prepared-comparison unexpected error", extra={"marketKeys": keys})
        if _is_statement_timeout(exc):
            return JSONResponse(content={"message": "This market took too long to load. Try again.", "code": "PREPARED_COMPARISON_TIMEOUT"}, status_code=504)
        return JSONResponse(content={"message": "Prepared comparison is temporarily unavailable", "code": "PREPARED_COMPARISON_FAILED"}, status_code=503)


@app.post("/market/explorer/direct-instrument")
def post_market_explorer_direct_instrument(payload: DirectInstrumentRequest):
    """Public discovery read for exactly one server-verified physical item.

    This route accepts no basket/spec/list and therefore does not weaken the
    Premium explicit-instruments builder entitlement.
    """
    try:
        return read_direct_instrument(
            service_read_client, payload.asset, payload.instrumentId, payload.startDate,
        )
    except DirectInstrumentError as exc:
        return JSONResponse(content={"message": exc.message, "code": exc.code},
                            status_code=exc.status_code)
    except Exception as exc:
        logger.exception("/market/explorer/direct-instrument unexpected error",
                         extra={"asset": payload.asset})
        if _is_statement_timeout(exc):
            return JSONResponse(content={"message": "Direct item history timed out. Try again.",
                                         "code": "DIRECT_INSTRUMENT_TIMEOUT"}, status_code=504)
        return JSONResponse(content={"message": "Direct item history is temporarily unavailable",
                                     "code": "DIRECT_INSTRUMENT_FAILED"}, status_code=503)


def _is_statement_timeout(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "57014" in text or "statement timeout" in text or "timeout" in text


@app.get("/market/explorer/prepared-constituents")
def get_market_explorer_prepared_constituents(
    marketKey: str = Query(min_length=1, max_length=200),
    generationId: str = Query(min_length=1, max_length=64),
    afterRank: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """One bounded, generation-pinned page of a PREPARED market's constituents.

    Read-only. Per-market-type authority is dispatched by the RPC from the
    directory row's own source_kind (maintained query cache / canonical Set
    roster / published sealed roster). Movement is attached only for cards, from
    the accepted V2 constituent-movement authority.
    """
    _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    if not has_index_plus_access(_resolve_index_plan(authorization, token_cookie)):
        raise HTTPException(status_code=403, detail={"message": "Constituents are included with Index+.", "requiredPlan": "plus"})
    try:
        page = read_constituents_v2_first(service_read_client, marketKey, generationId, afterRank, limit)
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "PREPARED_CONSTITUENTS_INVALID"}, status_code=400)
    except Exception as exc:
        logger.exception("/market/explorer/prepared-constituents unexpected error", extra={"marketKey": marketKey})
        if _is_statement_timeout(exc):
            return JSONResponse(content={"message": "Constituents took too long to load. Try again.", "code": "PREPARED_CONSTITUENTS_TIMEOUT"}, status_code=504)
        return JSONResponse(content={"message": "Constituents are temporarily unavailable", "code": "PREPARED_CONSTITUENTS_FAILED"}, status_code=503)
    code = page.get("code")
    if code == "GENERATION_MISMATCH":
        return JSONResponse(content=page, status_code=409, headers={"Cache-Control": "no-store"})
    if code == "UNKNOWN_MARKET":
        return JSONResponse(content=page, status_code=404, headers={"Cache-Control": "no-store"})
    if code == "INVALID_CURSOR":
        return JSONResponse(content=page, status_code=400, headers={"Cache-Control": "no-store"})
    if not page:
        return JSONResponse(content={"message": "Constituents are temporarily unavailable", "code": "PREPARED_CONSTITUENTS_FAILED"}, status_code=503)
    return _tiered_response(enrich_prepared_constituent_page(service_read_client, page))


@app.get("/market/explorer/prepared-screen")
def get_market_explorer_prepared_screen(screen: str, asset: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=10)):
    """Public prepared discovery metadata; comparison entitlement is separate."""
    try:
        return {"results": read_prepared_screen(service_read_client, screen, asset, limit)}
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "PREPARED_SCREEN_INVALID"}, status_code=400)
    except PreparedSurfaceValidationError as exc:
        return JSONResponse(content={"message": "Prepared Screen authority is inconsistent", "code": exc.code}, status_code=409)
    except Exception:
        logger.exception("/market/explorer/prepared-screen failed", extra={"screen": screen, "asset": asset, "limit": limit})
        return JSONResponse(content={"message": "Prepared Screen is temporarily unavailable", "code": "PREPARED_SCREEN_FAILED"}, status_code=503)


@app.get("/market/explorer/set-context-ranking")
def get_market_explorer_set_context_ranking(set_id: UUID, ranking: str, timeframe: str = "7D",
    limit: int = Query(default=10, ge=1, le=25), as_of: Optional[date] = None,
    authorization: Optional[str] = Header(default=None, alias="authorization"), token_cookie: Optional[str] = Cookie(default=None, alias="token")):
    _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    if not has_index_plus_access(_resolve_index_plan(authorization, token_cookie)):
        raise HTTPException(status_code=403, detail={"message": "Analytical rankings require Index+.", "requiredPlan": "plus"})
    return read_set_context_ranking(service_read_client, str(set_id), ranking, timeframe, limit, as_of.isoformat() if as_of else None)


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
        options = read_market_explorer_options_snapshot(service_read_client)
        _market_explorer_options_cache = (
            now + _MARKET_EXPLORER_OPTIONS_CACHE_TTL_SECONDS,
            options,
        )
        return _tiered_response(options)
    except MarketExplorerOptionsUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_OPTIONS_REFRESHING",
                                     "retryAfterSeconds": 15}, status_code=503,
                            headers={"Retry-After": "15"})
    except Exception:
        logger.exception("/market/explorer/query/options unexpected error")
        return JSONResponse(content={"message": "Unable to load Market Explorer filters", "code": "MARKET_EXPLORER_OPTIONS_FAILED"}, status_code=500)


@app.get("/market/explorer/instruments/search")
def get_market_explorer_instrument_search(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    asset: str = Query(default="all"),
    limit: int = Query(default=20, ge=1, le=50),
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Search canonical eligible physical cards and sealed products."""
    user_id = _require_authenticated_user_id(authorization=authorization, token_cookie=token_cookie)
    # Discovery is part of the Plus Builder surface: a Plus user may compose
    # and retain an exact-item draft, while the query endpoint independently
    # enforces Premium before any exact market executes. Keeping search behind
    # Premium made the honest locked-draft UX impossible and did not strengthen
    # the execution boundary.
    if not has_index_plus_access(_resolve_index_plan(authorization, token_cookie)):
        raise HTTPException(status_code=403, detail={
            "message": "Exact-instrument discovery requires Index Plus.",
            "code": "MARKET_EXPLORER_PLAN_REQUIRED", "requiredPlan": "plus",
            "requiredFeature": FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
        })
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_INSTRUMENT_SEARCH,
                        route="/market/explorer/instruments/search")
    try:
        return _tiered_response(search_market_explorer_instruments(
            service_read_client, q=q, asset=asset, limit=limit,
        ))
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "MARKET_EXPLORER_SEARCH_INVALID"}, status_code=400)


@app.get("/market/explorer/catalog/search")
def get_market_explorer_catalog_search(
    request: Request,
    asset: str = Query(default="cards", max_length=16),
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Contextual Explorer catalog search. General discovery: NOT plan-gated."""
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    network_identity = forwarded or (request.client.host if request.client else "unknown")
    _enforce_paid_abuse(request, user_id=f"explorer-catalog-search:{network_identity}",
                        policy_class=POLICY_SITE_SEARCH, route="/market/explorer/catalog/search")
    try:
        return JSONResponse(content={"results": search_catalog(service_read_client, asset, q, limit)},
                            headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "CATALOG_SEARCH_INVALID"}, status_code=400)
    except SurfaceV2Error as exc:
        logger.error("/market/explorer/catalog/search failed", extra={"code": exc.code})
        return JSONResponse(content={"message": "Search is temporarily unavailable", "code": exc.code}, status_code=503)
    except Exception:
        logger.exception("/market/explorer/catalog/search unexpected error")
        return JSONResponse(content={"message": "Search is temporarily unavailable", "code": "CATALOG_SEARCH_FAILED"}, status_code=503)


@app.get("/market/explorer/leaves/search")
def get_market_explorer_leaf_search(
    request: Request,
    asset: str = Query(default="cards", max_length=16),
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public, bounded physical-leaf discovery for Explorer's top search.

    Aggregate Set/Era/prepared markets remain on the directory controls. This
    endpoint deliberately reuses the canonical instrument adapter and does not
    grant permission to execute the discovered exact market.
    """
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    network_identity = forwarded or (request.client.host if request.client else "unknown")
    _enforce_paid_abuse(request, user_id=f"explorer-leaf-search:{network_identity}",
                        policy_class=POLICY_SITE_SEARCH, route="/market/explorer/leaves/search")
    try:
        return JSONResponse(
            content=search_market_explorer_leaves(
                service_read_client, asset=asset, q=q, limit=limit,
            ),
            headers={"Cache-Control": "no-store"},
        )
    except ValueError:
        return JSONResponse(content={"message": "Invalid leaf search request", "code": "LEAF_SEARCH_INVALID"}, status_code=400)
    except LeafSearchError as exc:
        logger.error("/market/explorer/leaves/search failed", extra={"code": exc.code})
        return JSONResponse(content={"message": "Leaf search is temporarily unavailable", "code": exc.code}, status_code=503)
    except Exception:
        logger.exception("/market/explorer/leaves/search unexpected error")
        return JSONResponse(content={"message": "Leaf search is temporarily unavailable", "code": "LEAF_SEARCH_FAILED"}, status_code=503)


@app.get("/market/explorer/asset-options")
def get_market_explorer_asset_options(asset: str = Query(default="cards", max_length=16)):
    """Truthful rarity / sealed-type availability states published by the DB."""
    try:
        return JSONResponse(content=read_asset_options(service_read_client, asset),
                            headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "ASSET_OPTIONS_INVALID"}, status_code=400)
    except SurfaceV2Error as exc:
        logger.error("/market/explorer/asset-options failed", extra={"code": exc.code})
        return JSONResponse(content={"message": "Options are temporarily unavailable", "code": exc.code}, status_code=503)


@app.get("/search")
def get_sitewide_search(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=30),
):
    """Public navigation search composed from prepared and canonical leaf authorities."""
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    network_identity = forwarded or (request.client.host if request.client else "unknown")
    _enforce_paid_abuse(request, user_id=f"public-search:{network_identity}",
                        policy_class=POLICY_SITE_SEARCH, route="/search")
    try:
        return JSONResponse(content=search_sitewide(service_read_client, q=q, limit=limit),
                            headers={"Cache-Control": "public, max-age=30, stale-while-revalidate=60"})
    except ValueError as exc:
        return JSONResponse(content={"message": str(exc), "code": "SITE_SEARCH_INVALID"}, status_code=400)
    except Exception:
        logger.exception("/search unexpected error")
        return JSONResponse(content={"message": "Search is temporarily unavailable", "code": "SITE_SEARCH_FAILED"}, status_code=503)


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
    if payload.asset not in (*SUPPORTED_ASSETS, "mixed"):
        return JSONResponse(content={"message": f"Unsupported asset: {payload.asset}", "code": "QUERY_INVALID"}, status_code=400)
    if payload.responseMode not in ("full", "summary"):
        return JSONResponse(content={"message": "responseMode must be full or summary", "code": "QUERY_INVALID"}, status_code=400)
    if payload.mode == "chase" and payload.topN not in (None, 10):
        return JSONResponse(content={"message": "Only Top 10 queries are supported", "code": "QUERY_INVALID"}, status_code=400)
    try:
        # Normalized BEFORE the cache is consulted, so an invalid spec is
        # rejected rather than keyed, and equivalent selections share one entry.
        normalized = normalize_query_spec(
            asset=payload.asset, mode=payload.mode, era_ids=payload.eraIds,
            set_ids=payload.setIds, segment_ids=payload.segmentIds,
            pokemon_ids=payload.pokemonIds, price_segment_ids=payload.priceSegmentIds,
            release_age_cohort_ids=payload.releaseAgeCohortIds, top_n=payload.topN,
            membership_mode=payload.membershipMode, instrument_ids=payload.instrumentIds,
            instruments=[item.model_dump() for item in payload.instruments],
        )
        user_id = _require_market_explorer_query_access(
            normalized, authorization=authorization, token_cookie=token_cookie,
            allow_public_canonical_rarity=True,
            public_identity="public-canonical-rarity:" + (
                str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
                or (request.client.host if request.client else "unknown")
            ),
        )
        public_canonical = user_id.startswith("public-canonical-rarity:")
        _enforce_paid_abuse(request, user_id=user_id,
                            policy_class=POLICY_SITE_SEARCH if public_canonical else POLICY_CUSTOM_QUERY,
                            route="/market/explorer/query")
        is_exact_v2 = bool(normalized.get("instruments"))
        runner = (run_exact_basket_v2 if is_exact_v2 else
                  run_sealed_market_explorer_query if normalized["asset"] == ASSET_SEALED
                  else run_market_explorer_query)
        persistent = PersistentMarketExplorerCache(
            service_read_client, metrics=GLOBAL_MARKET_EXPLORER_PLANNER.metrics,
        )

        def build_market(previous_through: str | None, canonical_date: str) -> Dict[str, Any]:
            if is_exact_v2:
                return runner(
                    service_read_client,
                    instruments=normalized["instruments"],
                    start_date=previous_through or "1999-01-01",
                    end_date=canonical_date,
                )
            return runner(
                service_read_client,
                mode=normalized["mode"],
                era_ids=normalized["eraIds"], set_ids=normalized["setIds"],
                segment_ids=normalized["segmentIds"],
                pokemon_ids=normalized["pokemonIds"],
                price_segment_ids=normalized["priceSegmentIds"],
                release_age_cohort_ids=normalized["releaseAgeCohortIds"],
                top_n=normalized["topN"],
                membership_mode=normalized.get("membershipMode"),
                instrument_ids=normalized.get("instrumentIds", ()),
                # A forward refresh includes the cached anchor date. The
                # planner rescales/appends and drops that duplicate point.
                start_date=previous_through or "1999-01-01",
                end_date=canonical_date,
            )

        planned = GLOBAL_MARKET_EXPLORER_PLANNER.execute(
            spec=normalized,
            prepared=GLOBAL_PREPARED_EQUIVALENCE_REGISTRY,
            persistent=persistent,
            canonical_through=lambda: resolve_explorer_comparison_through(
                service_read_client, normalized,
            ),
            novel_builder=build_market,
            summary=payload.responseMode == "summary",
        )
        return _tiered_response({
            **planned.payload,
            "comparisonAsOf": str(planned.payload.get("asOf") or "")[:10] or None,
        })
    except HTTPException:
        raise
    except MarketExplorerQueryError as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_INVALID"}, status_code=400)
    except (MarketExplorerQueryUnavailable, SealedMarketExplorerQueryUnavailable) as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_UNAVAILABLE"}, status_code=404)
    except MarketExplorerExactBasketUnavailable as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_UNAVAILABLE"}, status_code=404)
    except MarketExplorerCacheRefreshing as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_CACHE_REFRESHING"}, status_code=503)
    except MarketExplorerBuildInProgress as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_BUILDING"}, status_code=503)
    except Exception:
        logger.exception("/market/explorer/query unexpected error")
        return JSONResponse(content={"message": "Unable to execute Market Explorer query", "code": "QUERY_FAILED"}, status_code=500)


@app.post("/market/explorer/query/preflight")
def post_market_explorer_query_preflight(
    request: Request,
    payload: MarketExplorerPreflightRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    """Cheap point-in-time readiness check for a Filtered Cards query.

    THIS IS NOT THE QUERY ENGINE. It calls the bounded, read-only DB preflight
    RPC (preflight_pokemon_market_explorer_filtered_cards_v1) once, transports
    no constituent IDs, builds no index, and never chain-links history. Its
    only job is to answer "how many cards/sets would this match, and is that
    answer trustworthy right now" cheaply enough to run ahead of a Build click.
    """
    try:
        # Filters-first validation: reuses the same normalization the real
        # query endpoint uses, so a spec that would be rejected there is
        # rejected here identically, before the RPC is ever called.
        normalized = normalize_query_spec(
            asset="cards", mode="all", era_ids=payload.eraIds, set_ids=payload.setIds,
            segment_ids=payload.segmentIds, pokemon_ids=payload.pokemonIds,
            price_segment_ids=payload.priceSegmentIds,
            release_age_cohort_ids=payload.releaseAgeCohortIds,
        )
        user_id = _require_market_explorer_query_access(
            normalized, authorization=authorization, token_cookie=token_cookie,
            allow_public_canonical_rarity=True,
            public_identity="public-canonical-rarity:" + (
                str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
                or (request.client.host if request.client else "unknown")
            ),
        )
        public_canonical = user_id.startswith("public-canonical-rarity:")
        _enforce_paid_abuse(request, user_id=user_id,
                            policy_class=POLICY_SITE_SEARCH if public_canonical else POLICY_CUSTOM_QUERY,
                            route="/market/explorer/query/preflight")
        resolved_set_ids = resolve_scope_set_ids(
            service_read_client, normalized["eraIds"], normalized["setIds"],
        )
        comparison_as_of = None
        try:
            comparison_as_of = resolve_explorer_comparison_through(service_read_client, normalized)
        except RuntimeError:
            # No accepted publication date yet -- let the RPC's own
            # `no_approved_market_date` status describe that, rather than
            # failing the whole preflight request.
            pass
        result = call_filtered_cards_preflight(
            service_read_client,
            set_ids=resolved_set_ids,
            segment_ids=normalized["segmentIds"],
            pokemon_ids=normalized["pokemonIds"],
            price_segment_ids=normalized["priceSegmentIds"],
            release_age_cohort_ids=normalized["releaseAgeCohortIds"],
            comparison_as_of=comparison_as_of,
        )
        return _tiered_response(result)
    except HTTPException:
        raise
    except MarketExplorerQueryError as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_INVALID"}, status_code=400)
    except MarketExplorerPreflightError as exc:
        return JSONResponse(content={"message": str(exc), "code": "QUERY_UNAVAILABLE"}, status_code=404)
    except Exception:
        logger.exception("/market/explorer/query/preflight unexpected error")
        return JSONResponse(content={"message": "Unable to preflight this market query", "code": "QUERY_FAILED"}, status_code=500)


@app.post("/market/explorer/query/constituents")
def post_market_explorer_query_constituents(
    request: Request,
    payload: MarketExplorerConstituentPageRequest,
    authorization: Optional[str] = Header(default=None, alias="authorization"),
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
):
    normalized = normalize_query_spec(
        asset=payload.asset, mode=payload.mode, era_ids=payload.eraIds,
        set_ids=payload.setIds, segment_ids=payload.segmentIds,
        pokemon_ids=payload.pokemonIds, price_segment_ids=payload.priceSegmentIds,
        release_age_cohort_ids=payload.releaseAgeCohortIds, top_n=payload.topN,
        membership_mode=payload.membershipMode, instrument_ids=payload.instrumentIds,
        instruments=[item.model_dump() for item in payload.instruments],
    )
    user_id = _require_market_explorer_query_access(
        normalized, authorization=authorization, token_cookie=token_cookie,
    )
    _enforce_paid_abuse(request, user_id=user_id, policy_class=POLICY_CUSTOM_QUERY,
                        route="/market/explorer/query/constituents")
    page = PersistentMarketExplorerCache(service_read_client).constituent_page(
        query_fingerprint(normalized), limit=payload.limit, after_rank=payload.afterRank,
    )
    if page is None:
        return JSONResponse(content={"message": "Market summary must be built first",
                                     "code": "MARKET_EXPLORER_QUERY_UNAVAILABLE"}, status_code=404)
    if normalized.get("asset") in {"cards", "sealed"}:
        from backend.db.services.market_explorer_constituent_movement import enrich_constituent_page
        try:
            page = enrich_constituent_page(service_read_client, page, normalized["asset"])
            page["movementAvailable"] = any(
                any(value is not None for value in (row.get("changes") or {}).values())
                for row in (page.get("items") or [])
            )
        except Exception:
            logger.exception("Market Explorer query constituent movement failed",
                             extra={"asset": normalized.get("asset")})
            page = dict(page)
            page["movementAvailable"] = False
            page["movementReason"] = "Constituent movement is temporarily unavailable."
    return _tiered_response(page)


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
    # Public Profile surface is not production-ready — hard-stop before any
    # DB/service call. See _public_profile_portfolio_disabled_response.
    return _public_profile_portfolio_disabled_response()


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
    # PUBLIC (auth-invariant): the opening-distribution graph must render for
    # anonymous/Base callers. Access is resolved for cache/abuse isolation
    # only — never used to reject the request — and the response is run
    # through project_set_rip_simulation_evidence_response() before it
    # leaves this process, so Base/anonymous physically cannot receive paid
    # fields (openingOutcomeProfile, evRepresentativeness, financialRip,
    # collectorAppeal, advanced evidence, or any unknown future field).
    access_context = _resolve_request_access(authorization, token_cookie, feature=FEATURE_SET_RIP_ANALYTICS)
    _limit_paid_projection(request, authorization=authorization, token_cookie=token_cookie,
                           feature=FEATURE_SET_RIP_ANALYTICS, policy_class=POLICY_INTERACTIVE_DETAIL,
                           route="/tcgs/pokemon/sets/{set_id}/rip/simulation-evidence",
                           access_context=access_context)
    result = _set_rip_response(get_pokemon_set_rip_simulation_evidence_snapshot_payload, set_id)
    if isinstance(result, JSONResponse):
        return result
    return _tiered_response(project_set_rip_simulation_evidence_response(result, access_context["plan"]))


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
