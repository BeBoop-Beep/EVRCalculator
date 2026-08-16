"""The RIP decision-layer READ contract.

WHAT THIS IS
------------
A compact, publishable projection of decision data that other passes already
computed and persisted:

* the scored sealed-product SKUs for ONE set, from the ONE calculation run the
  snapshot is publishing; and
* the ONE canonical Top Chase card for that same run.

ONE RUN, OR NOTHING
-------------------
The caller supplies the current ``calculation_run_id`` and it is the single run
identity for every section. Nothing here resolves "the latest scored run" on its
own: a second resolution is a chance to disagree with the page it is part of,
and a page showing one run's product economics beside another run's opening
model gives the reader no way to see the mismatch. When there is no current run,
both sections publish empty and NO historical row is read.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a model. Every number here is either copied from a stored column or is a
  reversible arithmetic transformation of two of them (see
  ``backend.domain.pokemon.rip_decision_metrics``).
* NOT a ranking. Product rows keep the repository's order; nothing is sorted by
  score, no rank is assigned, no product family is compared to another, and no
  "best product" or set-level consensus is produced. The repository's comparison
  scope is ``within_product_family_only`` and this layer publishes that policy
  alongside the rows rather than restating or relaxing it.
* NOT a recommendation surface. No key here labels a product good or bad.

TOP CHASE, DEFINED
------------------
The highest CURRENT Near Mint market-value card in the run's simulation input
that has a valid positive modeled pull probability. It is NOT the largest EV
contributor, the most desirable Pokemon, the highest rarity, or a hardcoded
pick. Price and probability come from different places on purpose: the price
should be today's, the probability MUST be the one the opening model actually
ran with, so it is read from the same ``calculation_run_id``.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.db.repositories.sealed_product_results_repository import (
    get_sealed_product_results_for_run,
)
from backend.db.services.data_service_health import is_transient_data_service_error
from backend.domain.pokemon.rip_decision_metrics import (
    exact_card_probability_contract,
    product_decision_metrics,
)
from backend.domain.pokemon.sealed_product_comparison_scope import (
    sealed_product_comparison_scope_contract,
)

logger = logging.getLogger(__name__)

RIP_DECISION_CONTRACT_VERSION = "rip-decision-contract-v1"

#: Page size for the two whole-run reads the Top Chase selection needs. Paging
#: exists so a set larger than one PostgREST page cannot be silently truncated -
#: truncation would not fail, it would return a DIFFERENT card. The page count
#: is a function of set size, never of card count, so this is not a per-card
#: loop: a normal set is one page per read.
RUN_POPULATION_PAGE_SIZE = 1000

#: Hard ceiling on pages per read. A run needing more than this is not a set,
#: it is a bug or a corrupted run, and it stops the build rather than quietly
#: publishing whatever the first 50k rows happened to contain.
RUN_POPULATION_MAX_PAGES = 50

NEAR_MINT_PRICE_VIEW = "simulation_input_cards_with_near_mint_price"
INPUT_CARDS_TABLE = "simulation_input_cards"

REASON_EXPECTED_VALUE_UNAVAILABLE = "expected_value_unavailable"
REASON_MARKET_PRICE_UNAVAILABLE = "market_price_unavailable"

#: Whether the published section describes the run the page is publishing, or
#: nothing at all. There is deliberately no third state: this contract has no
#: "stale but shown" mode, because product economics from an older run next to
#: the current run's opening model is a mismatch a reader cannot see.
RUN_STATUS_CURRENT = "current_run"
RUN_STATUS_NO_CURRENT_RUN = "no_current_run"


# ---------------------------------------------------------------------------
# Sealed product decision contract
# ---------------------------------------------------------------------------

def _optional_float(value: Any) -> Optional[float]:
    """A finite float, or ``None``.

    NaN and Infinity are refused here rather than at each call site: they are
    not JSON values, and a consumer that receives one has no way to render it
    honestly. Zero passes through untouched - it is a legitimate measurement for
    a probability, a loss or a score, and coercing invalid values TO zero would
    be indistinguishable from it.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_int(value: Any) -> Optional[int]:
    number = _optional_float(value)
    return None if number is None else int(number)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _product_availability(row: Mapping[str, Any], metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Why a product's decision metrics are or are not usable.

    An explicit reason rather than a bare null: "we have no price for this SKU"
    and "this SKU has no modeled opening value" are different states with
    different fixes, and a reader cannot tell them apart from a missing ratio.
    """
    if metrics.get("modelBreakEvenPrice") is None:
        reason: Optional[str] = REASON_EXPECTED_VALUE_UNAVAILABLE
    elif metrics.get("modeledReturnRatio") is None:
        reason = REASON_MARKET_PRICE_UNAVAILABLE
    else:
        reason = None

    return {
        "decisionMetricsAvailable": reason is None,
        "reason": reason,
        "financialRipStatus": _optional_str(row.get("financial_rip_v3_status")),
        "financialRipRankable": bool(row.get("financial_rip_v3_rankable")),
        "overallRipRankable": bool(row.get("overall_rip_rankable")),
        "collectorAppealAvailable": row.get("collector_appeal_score") is not None,
    }


def _product_composition(row: Mapping[str, Any]) -> Dict[str, Any]:
    """The composition this product's opening model was built on.

    Published with the numbers because "36 packs" and "36 packs plus a
    guaranteed promo and an accessory that carries no modeled value" are
    different products wearing similar pack counts.
    """
    return {
        "compositionVersion": _optional_str(row.get("composition_version")),
        "compositionId": _optional_str(row.get("composition_id")),
        "distributionModelVersion": _optional_str(row.get("distribution_model_version")),
        "randomPackCount": _optional_int(row.get("random_pack_count")),
        "guaranteedComponentCount": _optional_int(row.get("guaranteed_component_count")),
        "guaranteedComponentMarketValue": _optional_float(row.get("guaranteed_component_market_value")),
        "accessoryValueIncluded": bool(row.get("accessory_value_included")),
    }


def _product_decision_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = product_decision_metrics(
        expected_value=row.get("expected_value"),
        product_market_cost=row.get("product_market_cost"),
    )
    market_price = _optional_float(row.get("product_market_cost"))
    if market_price is not None and market_price <= 0.0:
        market_price = None

    return {
        "sealedProductId": _optional_str(row.get("sealed_product_id")),
        "productName": _optional_str(row.get("product_name")),
        "productFamily": _optional_str(row.get("product_family")),
        "packCount": _optional_int(row.get("pack_count")),
        "marketPrice": market_price,
        **metrics,
        "typicalOpening": _optional_float(row.get("median_value")),
        "chanceToRecoverCost": _optional_float(row.get("chance_to_recover_cost")),
        "expectedLossWhenLosing": _optional_float(row.get("expected_loss_when_losing")),
        "financialRipScore": _optional_float(row.get("financial_rip_v3_score")),
        "collectorAppealScore": _optional_float(row.get("collector_appeal_score")),
        "overallRipScore": _optional_float(row.get("overall_rip_score")),
        "priceAsOf": _optional_str(row.get("price_as_of")),
        "priceSource": _optional_str(row.get("price_source")),
        "composition": _product_composition(row),
        "availability": _product_availability(row, metrics),
    }


def build_sealed_product_decision_contract(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_status: str = RUN_STATUS_CURRENT,
) -> Dict[str, Any]:
    """The set's product decision table, from EXACTLY one calculation run.

    Row order is the repository's (pack count ascending) and is preserved: any
    reordering by score inside a single payload is the first half of a ranking,
    and cross-format ranking is not validated.
    """
    product_rows = [row for row in rows or [] if isinstance(row, Mapping)]
    run_ids = {_optional_str(row.get("calculation_run_id")) for row in product_rows}
    run_ids.discard(None)
    if len(run_ids) > 1:
        # A table built from two runs would silently compare two different pack
        # models. Loud failure beats a plausible-looking mixed table.
        raise ValueError(
            "sealed product decision contract may not mix calculation_run_id values: "
            f"{sorted(run_ids)}"
        )

    return {
        "contractVersion": RIP_DECISION_CONTRACT_VERSION,
        "runStatus": run_status,
        "sourceCalculationRunId": next(iter(run_ids)) if run_ids else None,
        "productCount": len(product_rows),
        "products": [_product_decision_row(row) for row in product_rows],
        **sealed_product_comparison_scope_contract(),
    }


def _load_current_run_product_rows(
    *, run_id: str, set_id: Any, client: Any
) -> List[Mapping[str, Any]]:
    """The product rows of ONE named run, checked against the set being built.

    Reading by run rather than by "latest for this set" is the whole point: the
    snapshot has already decided which run it is publishing, and any second
    resolution is a chance to disagree with it.

    The set check is defensive rather than expected. ``calculation_run_id`` is
    per-set, so a run returning another set's rows means an identity assumption
    has broken somewhere upstream; publishing that quietly would put one set's
    product prices on another set's page.
    """
    rows = list(get_sealed_product_results_for_run(run_id, client=client))
    expected_set_id = _optional_str(set_id)
    if expected_set_id is None:
        return rows

    foreign = sorted(
        {
            row_set_id
            for row_set_id in (_optional_str(row.get("set_id")) for row in rows)
            if row_set_id is not None and row_set_id != expected_set_id
        }
    )
    if foreign:
        raise ValueError(
            f"calculation run {run_id} returned sealed product rows for set_id "
            f"{foreign} while building set_id {expected_set_id}"
        )
    return rows


# ---------------------------------------------------------------------------
# Top chase
# ---------------------------------------------------------------------------

def select_top_chase_card(
    price_rows: Iterable[Mapping[str, Any]],
    pull_rate_by_variant_id: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """The priciest card that the model can actually produce.

    Two filters, in this order: the card must have a current Near Mint price,
    and it must have a positive modeled pull rate in the SAME run. A card with
    no modeled probability is not a chase the model can speak about, however
    expensive it is; a card with a rate of zero cannot be pulled at all.

    ``ev_contribution`` is deliberately unused. It is a product of rate and
    price, so ordering by it answers "which card drives the pack's value", which
    is a different question with a frequently different answer.
    """
    best: Optional[Dict[str, Any]] = None
    best_key: Optional[tuple] = None

    for row in price_rows or []:
        if not isinstance(row, Mapping):
            continue
        price = _optional_float(row.get("current_near_mint_price"))
        if price is None or price <= 0.0:
            continue
        variant_id = _optional_str(row.get("card_variant_id"))
        if variant_id is None:
            continue
        probability = _optional_float(pull_rate_by_variant_id.get(variant_id))
        if probability is None or probability <= 0.0:
            continue
        # Ties are broken by the rarer pull, then by id, so the same run always
        # publishes the same chase card.
        key = (price, -probability, variant_id)
        if best_key is None or key > best_key:
            best_key = key
            best = {**row, "effective_pull_rate": probability}

    return best


def _load_run_population(
    client: Any, *, table: str, select: str, run_id: str
) -> List[Dict[str, Any]]:
    """Every row of one table for one run, read in whole pages.

    Both Top Chase reads are set-level rather than top-N, because the answer
    depends on the intersection of two populations: a price-ordered prefix of
    the priced rows can exclude the priciest MODELED card entirely. Paging keeps
    the read complete without making the query count depend on card count.
    """
    rows: List[Dict[str, Any]] = []
    for page in range(RUN_POPULATION_MAX_PAGES):
        start = page * RUN_POPULATION_PAGE_SIZE
        result = (
            client.table(table)
            .select(select)
            .eq("calculation_run_id", run_id)
            .range(start, start + RUN_POPULATION_PAGE_SIZE - 1)
            .execute()
        )
        batch = list(result.data or [])
        rows.extend(batch)
        if len(batch) < RUN_POPULATION_PAGE_SIZE:
            return rows
    raise ValueError(
        f"{table} returned more than "
        f"{RUN_POPULATION_MAX_PAGES * RUN_POPULATION_PAGE_SIZE} rows for run {run_id}; "
        "refusing to publish a possibly truncated Top Chase population"
    )


def _load_modeled_pull_rates(client: Any, *, run_id: str) -> Dict[str, float]:
    """The run's modeled per-pack rates, keyed by card variant.

    Read from ``simulation_input_cards`` rather than the priced view because the
    stored ``effective_pull_rate`` is the authoritative model output, and this
    keeps the probability tied to the run regardless of what the view projects.

    Only rates in ``0 < p <= 1`` are kept: a rate of zero, a negative, a NaN or
    a rate above one describes no card the model can actually produce, and
    carrying them forward would only let them lose a comparison later.
    """
    rates: Dict[str, float] = {}
    for row in _load_run_population(
        client,
        table=INPUT_CARDS_TABLE,
        select="card_variant_id,effective_pull_rate",
        run_id=run_id,
    ):
        variant_id = _optional_str(row.get("card_variant_id"))
        probability = _optional_float(row.get("effective_pull_rate"))
        if variant_id is None or probability is None:
            continue
        if 0.0 < probability <= 1.0:
            rates[variant_id] = probability
    return rates


def _load_run_near_mint_prices(client: Any, *, run_id: str) -> List[Dict[str, Any]]:
    """Current Near Mint prices for the run's cards."""
    return _load_run_population(
        client,
        table=NEAR_MINT_PRICE_VIEW,
        select="card_id,card_variant_id,card_name,rarity_bucket,current_near_mint_price",
        run_id=run_id,
    )


def _chase_image_fields(client: Any, *, card_id: Optional[str], variant_id: Optional[str]) -> Dict[str, Optional[str]]:
    """Images for the ONE chosen card. Never a per-card loop over the set."""
    variant_row: Dict[str, Any] = {}
    card_row: Dict[str, Any] = {}
    try:
        if variant_id:
            variant_rows = (
                client.table("card_variants")
                .select("id,card_id,image_small_url,image_large_url")
                .eq("id", variant_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            variant_row = variant_rows[0] if variant_rows else {}
        resolved_card_id = card_id or _optional_str(variant_row.get("card_id"))
        if resolved_card_id:
            card_rows = (
                client.table("cards")
                .select("id,image_small_url,image_large_url")
                .eq("id", resolved_card_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            card_row = card_rows[0] if card_rows else {}
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("top chase image lookup failed variant_id=%s", variant_id, exc_info=True)
        return {"imageUrl": None, "imageSmallUrl": None, "imageLargeUrl": None}

    small = _optional_str(variant_row.get("image_small_url")) or _optional_str(card_row.get("image_small_url"))
    large = _optional_str(variant_row.get("image_large_url")) or _optional_str(card_row.get("image_large_url"))
    return {"imageUrl": small or large, "imageSmallUrl": small, "imageLargeUrl": large}


def build_top_chase_contract(*, run_id: Any, client: Any) -> Optional[Dict[str, Any]]:
    """The one canonical Top Chase card for a run, or ``None``.

    The modeled population is read FIRST and in full, then priced. Doing it the
    other way round - taking the N priciest cards and asking which are modeled -
    silently answers a different question, because a set's most expensive cards
    are frequently ones these packs cannot produce.

    ``None`` is a real answer: a run whose cards carry no modeled pull rate has
    no chase this contract can honestly describe, and an invented one would be
    indistinguishable from a real one.
    """
    resolved_run_id = _optional_str(run_id)
    if resolved_run_id is None:
        return None

    try:
        pull_rates = _load_modeled_pull_rates(client, run_id=resolved_run_id)
        if not pull_rates:
            # Nothing modeled means nothing to price against; the price read is
            # skipped rather than issued and discarded.
            return None
        candidates = _load_run_near_mint_prices(client, run_id=resolved_run_id)
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("top chase read failed run_id=%s", resolved_run_id, exc_info=True)
        return None

    chosen = select_top_chase_card(candidates, pull_rates)
    if chosen is None:
        return None

    card_id = _optional_str(chosen.get("card_id"))
    variant_id = _optional_str(chosen.get("card_variant_id"))
    return {
        "cardId": card_id,
        "cardVariantId": variant_id,
        "cardName": _optional_str(chosen.get("card_name")),
        "rarity": _optional_str(chosen.get("rarity_bucket")),
        **_chase_image_fields(client, card_id=card_id, variant_id=variant_id),
        "currentMarketPrice": _optional_float(chosen.get("current_near_mint_price")),
        **exact_card_probability_contract(chosen.get("effective_pull_rate")),
        "priceSource": NEAR_MINT_PRICE_VIEW,
        "sourceCalculationRunId": resolved_run_id,
        "contractVersion": RIP_DECISION_CONTRACT_VERSION,
    }


# ---------------------------------------------------------------------------
# Combined contract
# ---------------------------------------------------------------------------

def build_rip_decision_contract(
    *, set_id: Any, run_id: Any, client: Any
) -> Dict[str, Any]:
    """Both decision sections for one set, from ONE run, plus the policy.

    ``run_id`` is the snapshot's current calculation run and is the single run
    identity for the whole contract: products and Top Chase are both read for
    it, and neither section may resolve a run of its own.

    Without a current run the contract publishes an explicitly empty current
    state and reads nothing. Falling back to the newest historical product rows
    would publish real, correctly-provenanced economics from a run the rest of
    the page is not describing - which is worse than publishing nothing,
    because it looks right.
    """
    resolved_run_id = _optional_str(run_id)
    if resolved_run_id is None:
        return {
            "contractVersion": RIP_DECISION_CONTRACT_VERSION,
            "sourceCalculationRunId": None,
            "currentRunAvailable": False,
            "sealedProducts": build_sealed_product_decision_contract(
                [], run_status=RUN_STATUS_NO_CURRENT_RUN
            ),
            "topChase": None,
            **sealed_product_comparison_scope_contract(),
        }

    return {
        "contractVersion": RIP_DECISION_CONTRACT_VERSION,
        "sourceCalculationRunId": resolved_run_id,
        "currentRunAvailable": True,
        "sealedProducts": build_sealed_product_decision_contract(
            _load_current_run_product_rows(
                run_id=resolved_run_id, set_id=set_id, client=client
            ),
            run_status=RUN_STATUS_CURRENT,
        ),
        "topChase": build_top_chase_contract(run_id=resolved_run_id, client=client),
        **sealed_product_comparison_scope_contract(),
    }
