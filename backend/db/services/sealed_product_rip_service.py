"""Stage 1 sealed-product RIP scoring.

PIPELINE
--------
    existing pack simulator  ->  finished empirical vector X
                             ->  sealed-product bootstrap  ->  Y_k
                             ->  build_financial_rip_v3(Y_k, product market cost)
                             ->  set-level Collector Appeal (inherited, unchanged)
                             ->  compute_overall_rip_v8(...)
                             ->  simulation_sealed_product_results

Every scoring contract here is REUSED, not reimplemented: there is no
sealed-product Financial RIP formula, no product Collector Appeal, no local
90/10 blend, and no second sealed-product classifier. This module's whole job is
to pick real SKUs, hand each one the right outcome vector and its own real market
price, and record what came back.

WHAT MAKES A PRODUCT SCORABLE
-----------------------------
1. Its classified family is one of the three Stage 1 families.
2. It exists in the sealed market snapshot as a real ``sealed_product_id``.
3. It has a finite, strictly positive current market price of its OWN.

There is no fallback for (3). Not ``pack_price * pack_count``, not MSRP, not an
average of history, not a sibling SKU's price - a product with no current market
price simply has no Stage 1 cost, and a score computed against an invented cost
would look like a measurement while being a guess.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.derived_metrics import (
    compute_downside_metrics,
    compute_probability_metrics,
)
from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
)
from backend.calculations.evr.sealed_product_distribution import (
    DEFAULT_CHUNK_SIZE,
    PACK_INDEPENDENCE_ASSUMPTION,
    STAGE1_DISTRIBUTION_MODEL_VERSION,
    build_stage1_product_distributions,
    extract_pack_outcome_vector,
    normalize_pack_outcome_vector,
)
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V4_VERSION
from backend.desirability.weighted_rip import compute_overall_rip_v8
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.domain.pokemon.sealed_product_composition import (
    COMPOSITION_INTEGRITY_VERSION,
    STAGE1_COMPOSITION_VERSION,
    SUPPORTED_STAGE1_FAMILIES,
    resolve_stage1_composition,
    stage1_composition_disqualifier,
)

logger = logging.getLogger(__name__)

STAGE1_SERVICE_VERSION = "sealed-product-rip-stage1-v1"

# Machine-readable outcome vocabulary. Callers branch on these, never on prose.
REASON_NO_SUPPORTED_PRODUCTS = "no_supported_stage1_products"
REASON_INVALID_PRICE = "invalid_or_missing_market_price"
REASON_COLLECTOR_APPEAL_UNAVAILABLE = "collector_appeal_unavailable"
REASON_NO_SEALED_SNAPSHOT = "no_sealed_market_snapshot"
REASON_UNSUPPORTED_FAMILY = "unsupported_product_family"


# ---------------------------------------------------------------------------
# Product discovery
# ---------------------------------------------------------------------------

def _resolve_family(product: Mapping[str, Any]) -> str:
    """The classified family for one snapshot product row.

    The snapshot already carries the canonical classifier's verdict; it is used
    directly. Only when it is absent does this fall back to calling the SAME
    canonical classifier on the name. No substring matching happens here.
    """
    family = str(product.get("productFamily") or "").strip()
    if family:
        return family
    return str(classify_sealed_product(product.get("name")).get("productFamily"))


def _positive_price(value: Any) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(price) or price <= 0.0:
        return None
    return price


def select_stage1_products(snapshot_payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Split a sealed market snapshot into Stage 1 candidates and skips.

    Multiple SKUs in the same family stay SEPARATE candidates. Two sleeved
    booster products with two ids and two prices are two products in the market
    and must remain two rows; collapsing them would silently pick a winner.
    """
    candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    products = (snapshot_payload or {}).get("products") or []
    for product in products:
        if not isinstance(product, Mapping):
            continue
        family = _resolve_family(product)
        composition = resolve_stage1_composition(family)
        product_id = product.get("sealedProductId")
        if composition is None:
            # Not a Stage 1 product at all (ETB, enhanced booster box, blister,
            # collection product, ...). Recorded, not treated as a failure.
            skipped.append(
                {
                    "sealedProductId": product_id,
                    "name": product.get("name"),
                    "productFamily": family,
                    "reason": REASON_UNSUPPORTED_FAMILY,
                }
            )
            continue

        disqualifier = stage1_composition_disqualifier(product.get("name"), product_family=family)
        if disqualifier is not None:
            # Right family, wrong pack count (half boxes) or extra contents in
            # the price (composite SKUs). Stage 1 has no composition for these.
            skipped.append(
                {
                    "sealedProductId": product_id,
                    "name": product.get("name"),
                    "productFamily": family,
                    "reason": disqualifier,
                }
            )
            continue

        price = _positive_price(product.get("currentPrice"))
        if price is None:
            skipped.append(
                {
                    "sealedProductId": product_id,
                    "name": product.get("name"),
                    "productFamily": family,
                    "reason": REASON_INVALID_PRICE,
                    "currentPrice": product.get("currentPrice"),
                }
            )
            continue

        candidates.append(
            {
                "sealed_product_id": product_id,
                "name": product.get("name"),
                "product_family": family,
                "composition": composition,
                "product_market_cost": price,
                "price_as_of": product.get("priceAsOf"),
                "price_source": product.get("source"),
            }
        )

    return {"candidates": candidates, "skipped": skipped}


# ---------------------------------------------------------------------------
# Collector Appeal (inherited from the set, unchanged)
# ---------------------------------------------------------------------------

def resolve_set_collector_appeal(set_id: Any) -> Dict[str, Any]:
    """The set's canonical Collector Appeal, or an explicit unavailable state.

    Stage 1 products are homogeneous same-set pack products with no modeled
    guaranteed card, so their collector appeal IS the set's - recomputing it from
    six or thirty-six packs would produce a different construct wearing the same
    name. The DECLARED version is checked: a payload that is not the canonical
    Collector Appeal V4 is refused rather than fed to V8, which would compute a
    number that is neither V7 nor V8.
    """
    # Imported lazily: the Collector Appeal service builds a Supabase client at
    # module import, and the Stage 1 scoring path must stay importable without
    # database credentials.
    from backend.db.services.collector_appeal_service import get_collector_appeal

    payload = get_collector_appeal(str(set_id)) if set_id is not None else None
    appeal = (payload or {}).get("collectorAppeal") if isinstance(payload, Mapping) else None
    if not isinstance(appeal, Mapping):
        return {"score": None, "version": None, "available": False, "reason": REASON_COLLECTOR_APPEAL_UNAVAILABLE}

    version = appeal.get("version")
    score = appeal.get("score")
    if version != COLLECTOR_APPEAL_V4_VERSION or score is None:
        return {
            "score": None,
            "version": version,
            "available": False,
            "reason": REASON_COLLECTOR_APPEAL_UNAVAILABLE,
        }
    return {"score": float(score), "version": version, "available": True, "reason": None}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _distribution_statistics(values: np.ndarray, cost: float) -> Dict[str, Any]:
    """Plain empirical statistics of one product's opening distribution.

    Every one of these is computed from the composed vector Y. None is a scaled
    per-pack number: only the mean is linear in pack count, so scaling anything
    else would be arithmetic on the wrong object.
    """
    probability = compute_probability_metrics(values, cost)
    downside = compute_downside_metrics(values, cost)
    mean_value = float(values.mean())
    return {
        "expected_value": mean_value,
        "median_value": float(np.median(values)),
        "p05_value": float(np.percentile(values, 5)),
        "p95_value": float(np.percentile(values, 95)),
        "p99_value": float(np.percentile(values, 99)),
        "min_value": float(values.min()),
        "max_value": float(values.max()),
        "standard_deviation": float(values.std()),
        "chance_to_recover_cost": float(probability["prob_profit"]),
        "expected_loss_when_losing": downside["expected_loss_given_loss"],
        "median_loss_when_losing": downside["median_loss_given_loss"],
        "total_value_to_cost_ratio": mean_value / cost,
    }


def score_stage1_sealed_products(
    *,
    pack_values: Any,
    candidates: Sequence[Mapping[str, Any]],
    canonical_set_key: Any,
    collector_appeal: Mapping[str, Any],
    run_fingerprint: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_simulation_count: int = FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
) -> Dict[str, Any]:
    """Score every Stage 1 candidate against its own market cost.

    Distributions are generated ONCE per required pack count and shared across
    every SKU with that composition; only the cost differs per SKU. That is not
    an optimization detail - regenerating Y per SKU would make two identical
    products differ by Monte Carlo noise alone.
    """
    extract_started = time.perf_counter()
    x = normalize_pack_outcome_vector(pack_values)
    extract_ms = (time.perf_counter() - extract_started) * 1000.0
    if not candidates:
        return {
            "status": "empty",
            "reason": REASON_NO_SUPPORTED_PRODUCTS,
            "products": [],
            "distributionMeta": None,
            "timings": {},
        }

    required_counts = sorted({int(c["composition"].pack_count) for c in candidates})
    bootstrap_started = time.perf_counter()
    built = build_stage1_product_distributions(
        x,
        pack_counts=required_counts,
        canonical_set_key=canonical_set_key,
        run_fingerprint=run_fingerprint,
        chunk_size=chunk_size,
    )
    bootstrap_ms = (time.perf_counter() - bootstrap_started) * 1000.0
    distributions = built["distributions"]

    appeal_score = collector_appeal.get("score") if isinstance(collector_appeal, Mapping) else None
    appeal_version = collector_appeal.get("version") if isinstance(collector_appeal, Mapping) else None

    products: List[Dict[str, Any]] = []
    # Per-SKU phase timings. Kept as plain accumulators so profiling never needs
    # a second, differently-shaped code path to measure.
    financial_ms_by_sku: List[Dict[str, Any]] = []
    stats_ms_total = 0.0
    overall_ms_total = 0.0

    for candidate in candidates:
        composition = candidate["composition"]
        pack_count = int(composition.pack_count)
        y = distributions[pack_count]
        cost = float(candidate["product_market_cost"])

        financial_started = time.perf_counter()
        financial = build_financial_rip_v3(y, cost, min_simulation_count=min_simulation_count)
        financial_ms = (time.perf_counter() - financial_started) * 1000.0

        overall_started = time.perf_counter()
        overall = compute_overall_rip_v8(financial.get("score"), appeal_score)
        overall_ms_total += (time.perf_counter() - overall_started) * 1000.0

        stats_started = time.perf_counter()
        stats = _distribution_statistics(y, cost)
        stats_ms_total += (time.perf_counter() - stats_started) * 1000.0

        financial_ms_by_sku.append(
            {
                "sealedProductId": candidate["sealed_product_id"],
                "productFamily": candidate["product_family"],
                "packCount": pack_count,
                "elapsedMs": round(financial_ms, 3),
            }
        )

        products.append(
            {
                "sealed_product_id": candidate["sealed_product_id"],
                "product_name": candidate.get("name"),
                "product_family": candidate["product_family"],
                "pack_count": pack_count,
                "composition_version": composition.composition_version,
                "distribution_model_version": STAGE1_DISTRIBUTION_MODEL_VERSION,
                "pack_independence_assumption": PACK_INDEPENDENCE_ASSUMPTION,
                "product_market_cost": cost,
                "price_as_of": candidate.get("price_as_of"),
                "price_source": candidate.get("price_source"),
                "simulation_count": int(y.size),
                **stats,
                "financial_rip_v3_score": financial.get("score"),
                "financial_rip_v3_status": financial.get("status"),
                "financial_rip_v3_rankable": bool(financial.get("rankable")),
                "financial_rip_v3_version": financial.get("scoreVersion"),
                "financial_rip_v3_payload": financial,
                "collector_appeal_score": appeal_score,
                "collector_appeal_version": appeal_version,
                "overall_rip_score": overall.get("score"),
                "overall_rip_version": overall.get("version"),
                "overall_rip_rankable": bool(overall.get("rankable")),
                "overall_rip_payload": overall,
            }
        )

    return {
        "status": "ok",
        "reason": None,
        "products": products,
        "distributionMeta": built["meta"],
        "timings": {
            "packVectorValidationMs": round(extract_ms, 3),
            "bootstrapMs": round(bootstrap_ms, 3),
            "financialRipV3TotalMs": round(sum(e["elapsedMs"] for e in financial_ms_by_sku), 3),
            "financialRipV3BySku": financial_ms_by_sku,
            "productStatisticsMs": round(stats_ms_total, 3),
            "overallRipMs": round(overall_ms_total, 3),
        },
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _to_row(product: Mapping[str, Any], *, calculation_run_id: Any, set_id: Any) -> Dict[str, Any]:
    return {
        "calculation_run_id": str(calculation_run_id),
        "sealed_product_id": str(product["sealed_product_id"]),
        "set_id": str(set_id),
        "product_family": product["product_family"],
        "product_name": product.get("product_name"),
        "pack_count": int(product["pack_count"]),
        "composition_version": product["composition_version"],
        "distribution_model_version": product["distribution_model_version"],
        "pack_independence_assumption": bool(product["pack_independence_assumption"]),
        "product_market_cost": float(product["product_market_cost"]),
        "price_as_of": product.get("price_as_of"),
        "price_source": product.get("price_source"),
        "simulation_count": int(product["simulation_count"]),
        "expected_value": product.get("expected_value"),
        "median_value": product.get("median_value"),
        "p05_value": product.get("p05_value"),
        "p95_value": product.get("p95_value"),
        "p99_value": product.get("p99_value"),
        "min_value": product.get("min_value"),
        "max_value": product.get("max_value"),
        "standard_deviation": product.get("standard_deviation"),
        "chance_to_recover_cost": product.get("chance_to_recover_cost"),
        "expected_loss_when_losing": product.get("expected_loss_when_losing"),
        "median_loss_when_losing": product.get("median_loss_when_losing"),
        "total_value_to_cost_ratio": product.get("total_value_to_cost_ratio"),
        "financial_rip_v3_score": product.get("financial_rip_v3_score"),
        "financial_rip_v3_status": product.get("financial_rip_v3_status"),
        "financial_rip_v3_rankable": product.get("financial_rip_v3_rankable"),
        "financial_rip_v3_version": product.get("financial_rip_v3_version"),
        "financial_rip_v3_payload": product.get("financial_rip_v3_payload"),
        "collector_appeal_score": product.get("collector_appeal_score"),
        "collector_appeal_version": product.get("collector_appeal_version"),
        "overall_rip_score": product.get("overall_rip_score"),
        "overall_rip_version": product.get("overall_rip_version"),
        "overall_rip_rankable": product.get("overall_rip_rankable"),
        "overall_rip_payload": product.get("overall_rip_payload"),
    }


def run_stage1_sealed_product_rip(
    *,
    sim_results: Mapping[str, Any],
    set_id: Any,
    canonical_set_key: Any,
    calculation_run_id: Any,
    read_snapshot_fn=None,
    persist_fn=None,
    collector_appeal_fn=None,
    run_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """Discover, score and persist Stage 1 sealed products for one finished run.

    Additive by construction: it consumes an ALREADY-COMPLETED pack simulation
    and an already-persisted parent run, so nothing about the loose-pack path
    depends on it. Expected data gaps (no snapshot, no supported SKU, a SKU with
    no price, no Collector Appeal) return structured states; genuine contract
    violations are allowed to raise.
    """
    started = time.perf_counter()

    if read_snapshot_fn is None:
        from backend.db.clients.supabase_client import supabase
        from backend.db.services.pokemon_set_sealed_market_snapshot_service import read_snapshot

        def read_snapshot_fn(target_set_id):  # type: ignore[misc]
            return read_snapshot(supabase, target_set_id)

    if persist_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            upsert_sealed_product_results as persist_fn,  # type: ignore[misc]
        )

    if collector_appeal_fn is None:
        collector_appeal_fn = resolve_set_collector_appeal

    phase_ms: Dict[str, Any] = {}

    snapshot_started = time.perf_counter()
    snapshot = read_snapshot_fn(str(set_id))
    phase_ms["sealedSnapshotReadMs"] = round((time.perf_counter() - snapshot_started) * 1000.0, 3)
    if not snapshot:
        return _summary(
            status="skipped",
            reason=REASON_NO_SEALED_SNAPSHOT,
            canonical_set_key=canonical_set_key,
            started=started,
        )

    selection_started = time.perf_counter()
    selection = select_stage1_products(snapshot)
    phase_ms["productDiscoveryMs"] = round((time.perf_counter() - selection_started) * 1000.0, 3)
    candidates = selection["candidates"]
    skipped = selection["skipped"]
    if not candidates:
        return _summary(
            status="skipped",
            reason=REASON_NO_SUPPORTED_PRODUCTS,
            canonical_set_key=canonical_set_key,
            skipped=skipped,
            started=started,
        )

    extract_started = time.perf_counter()
    pack_values = extract_pack_outcome_vector(sim_results)
    phase_ms["packVectorExtractionMs"] = round((time.perf_counter() - extract_started) * 1000.0, 3)

    appeal_started = time.perf_counter()
    appeal = collector_appeal_fn(set_id)
    phase_ms["collectorAppealMs"] = round((time.perf_counter() - appeal_started) * 1000.0, 3)
    if not appeal.get("available"):
        # Financial RIP stays available; Overall RIP does not. A missing appeal
        # is never converted to zero.
        logger.warning(
            "Stage 1 sealed products for set=%s have no canonical Collector Appeal (%s); "
            "Overall RIP will be unavailable.",
            canonical_set_key,
            appeal.get("reason"),
        )

    scored = score_stage1_sealed_products(
        pack_values=pack_values,
        candidates=candidates,
        canonical_set_key=canonical_set_key,
        collector_appeal=appeal,
        run_fingerprint=run_fingerprint,
    )

    rows = [
        _to_row(product, calculation_run_id=calculation_run_id, set_id=set_id)
        for product in scored["products"]
    ]
    persist_started = time.perf_counter()
    persisted = persist_fn(rows)
    phase_ms["persistenceMs"] = round((time.perf_counter() - persist_started) * 1000.0, 3)
    phase_ms.update(scored.get("timings") or {})

    summary = _summary(
        status="ok",
        reason=None,
        canonical_set_key=canonical_set_key,
        skipped=skipped,
        started=started,
        products=scored["products"],
        distribution_meta=scored["distributionMeta"],
        persisted_count=len(persisted) if persisted is not None else len(rows),
        collector_appeal=appeal,
        phase_ms=phase_ms,
    )
    logger.info(
        "Stage 1 sealed-product RIP: set=%s pack_outcomes=%s pack_counts=%s "
        "distributions=%s scored=%s skipped=%s collector_appeal=%s elapsed_ms=%.1f",
        canonical_set_key,
        summary["packOutcomeCount"],
        summary["requiredPackCounts"],
        summary["generatedDistributionCount"],
        summary["scoredProductCount"],
        summary["skippedProductCount"],
        appeal.get("version"),
        summary["elapsedMs"],
    )
    return summary


def _summary(
    *,
    status: str,
    reason: Optional[str],
    canonical_set_key: Any,
    started: float,
    skipped: Optional[Sequence[Mapping[str, Any]]] = None,
    products: Optional[Sequence[Mapping[str, Any]]] = None,
    distribution_meta: Optional[Mapping[str, Any]] = None,
    persisted_count: int = 0,
    collector_appeal: Optional[Mapping[str, Any]] = None,
    phase_ms: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact, machine-readable Stage 1 summary. Never carries raw vectors."""
    skipped_list = list(skipped or [])
    product_list = list(products or [])
    meta = dict(distribution_meta or {})
    skip_reasons: Dict[str, int] = {}
    for entry in skipped_list:
        key = str(entry.get("reason"))
        skip_reasons[key] = skip_reasons.get(key, 0) + 1

    return {
        "serviceVersion": STAGE1_SERVICE_VERSION,
        "compositionVersion": STAGE1_COMPOSITION_VERSION,
        "compositionIntegrityVersion": COMPOSITION_INTEGRITY_VERSION,
        "distributionModel": STAGE1_DISTRIBUTION_MODEL_VERSION,
        "supportedFamilies": sorted(SUPPORTED_STAGE1_FAMILIES),
        "status": status,
        "reason": reason,
        "canonicalSetKey": str(canonical_set_key or ""),
        "packOutcomeCount": meta.get("packOutcomeCount"),
        "requiredPackCounts": meta.get("packCounts") or [],
        "generatedDistributionCount": len(meta.get("packCounts") or []),
        "chunkSize": meta.get("chunkSize"),
        "distributionSeed": meta.get("seed"),
        "distributionElapsedMs": meta.get("elapsedMs"),
        "scoredProductCount": len(product_list),
        "persistedProductCount": int(persisted_count),
        "skippedProductCount": len(skipped_list),
        "skippedReasons": skip_reasons,
        "skipped": skipped_list,
        "collectorAppealVersion": (collector_appeal or {}).get("version"),
        "collectorAppealAvailable": bool((collector_appeal or {}).get("available")),
        "products": [
            {
                key: product.get(key)
                for key in (
                    "sealed_product_id",
                    "product_name",
                    "product_family",
                    "pack_count",
                    "product_market_cost",
                    "expected_value",
                    "median_value",
                    "p95_value",
                    "p99_value",
                    "chance_to_recover_cost",
                    "financial_rip_v3_score",
                    "financial_rip_v3_status",
                    "collector_appeal_score",
                    "overall_rip_score",
                    "overall_rip_version",
                )
            }
            for product in product_list
        ],
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
        # Per-phase wall time. Diagnostic only: nothing branches on it, and it is
        # never persisted.
        "phaseTimingsMs": dict(phase_ms or {}),
    }
