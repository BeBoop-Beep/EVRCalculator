"""Pure source adapters for the private benchmark layer. No live writes.

Opening Economics and model authority are different inputs. These helpers never
turn EV into Financial RIP or rerank an existing publication.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError, day, fingerprint, identifier, number

V3_CONTRACT = "pokemon-rip-stats-v3"
V3_BASIS = "all_modeled_products_per_pack_equivalent"
V3_METHOD = "hierarchical_product_per_pack_empirical_v1"
V3_WEIGHT = "equal-set_equal-family_equal-sku-v1"
VALUE_PERCENTILES = ("05", "10", "25", "50", "75", "90", "95", "99")
NORMALIZED_PERCENTILES = ("10", "25", "50", "75", "90", "95", "99")
EVIDENCE_FIELDS = frozenset({
    "cost_per_pack", "expected_value_per_pack", "top_1pct_mean_per_pack",
    "chance_to_recover_cost", "expected_loss_when_losing_per_pack",
    "modeled_return_on_spend", "mean_outcome_retention", "top_1pct_ev_share",
    *(f"p{q}_value_per_pack" for q in VALUE_PERCENTILES),
    *(f"normalized_p{q}" for q in NORMALIZED_PERCENTILES),
})


def validate_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(evidence) - EVIDENCE_FIELDS
    if unknown:
        raise BenchmarkError(f"unknown financial evidence: {sorted(unknown)}")
    result = {k: number(v) if v is not None else None for k, v in evidence.items()}
    if result.get("cost_per_pack") is None or result["cost_per_pack"] <= 0:
        raise BenchmarkError("positive per-pack cost required")
    if result.get("expected_value_per_pack") is None:
        raise BenchmarkError("per-pack expected value required")
    if any(v is not None and v < 0 for v in result.values()):
        raise BenchmarkError("negative financial evidence")
    for key in ("chance_to_recover_cost", "top_1pct_ev_share"):
        if result.get(key) is not None and result[key] > 1:
            raise BenchmarkError("probability/share outside 0..1")
    for keys in ([f"p{q}_value_per_pack" for q in VALUE_PERCENTILES],
                 [f"normalized_p{q}" for q in NORMALIZED_PERCENTILES]):
        values = [result[k] for k in keys if result.get(k) is not None]
        if any(a > b for a, b in zip(values, values[1:])):
            raise BenchmarkError("nonmonotone supplied quantiles")
    return result


def compatible_v3(snapshot: Mapping[str, Any], market_date: str) -> Mapping[str, Any]:
    economics = (snapshot.get("payload_json") or {}).get("openingEconomics") or {}
    methodology = economics.get("methodology") or {}
    if (snapshot.get("publication_status") != "published" or
        snapshot.get("market_date") != day(market_date).isoformat() or
        snapshot.get("contract_version") != V3_CONTRACT or
        snapshot.get("methodology_version") != V3_METHOD or
        snapshot.get("weighting_version") != V3_WEIGHT or
        economics.get("contractVersion") != V3_CONTRACT or
        economics.get("basis") != V3_BASIS or economics.get("status") != "available" or
        economics.get("marketDate") != market_date or
        methodology.get("version") != V3_METHOD or methodology.get("weightingVersion") != V3_WEIGHT):
        raise BenchmarkError("incompatible or differently dated Opening Economics V3")
    identifier(snapshot.get("id"))
    return economics


def evidence_from_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Copy published weighted statistics verbatim; never average medians."""
    result = {
        "cost_per_pack": scope.get("averageCostPerPack"),
        "expected_value_per_pack": scope.get("averageModelBreakEvenPerPack"),
        "modeled_return_on_spend": scope.get("modeledReturnOnSpend"),
        "mean_outcome_retention": scope.get("meanOutcomeRetention"),
        "chance_to_recover_cost": scope.get("chanceToRecoverCost"),
    }
    values = scope.get("valuePerPackPercentiles") or {}
    returns = scope.get("normalizedReturnPercentiles") or {}
    result.update({f"p{q}_value_per_pack": values.get(f"p{q}") for q in VALUE_PERCENTILES})
    result.update({f"normalized_p{q}": returns.get(f"p{q}") for q in NORMALIZED_PERCENTILES})
    # top-1% mean/share and conditional loss are not derivable from P99 alone.
    return validate_evidence(result)


def map_era_identities(set_entries: Sequence[Mapping[str, Any]],
                       era_entries: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Use canonical UUIDs in the SAME snapshot's members, never name hashing."""
    by_name: dict[str, set[str]] = {}
    seen_sets = set()
    for item in set_entries:
        sid = identifier(item.get("setId"))
        if sid in seen_sets:
            raise BenchmarkError("duplicate member set")
        seen_sets.add(sid)
        name = item.get("eraName")
        if not isinstance(name, str) or not name.strip():
            raise BenchmarkError("member has no era name")
        by_name.setdefault(name, set()).add(identifier(item.get("eraId")))
    resolved: dict[str, str] = {}
    for era in era_entries:
        name = era.get("eraName")
        ids = by_name.get(name, set())
        if name in resolved or len(ids) != 1:
            raise BenchmarkError("ambiguous or unmapped era")
        resolved[name] = next(iter(ids))
        members = sum(s.get("eraName") == name for s in set_entries)
        if type(era.get("setCount")) is not int or era["setCount"] != members:
            raise BenchmarkError("era member count mismatch")
    if set(resolved) != set(by_name) or len(set(resolved.values())) != len(resolved):
        raise BenchmarkError("era partition does not reconcile")
    return resolved


def select_exact_product_results(published_products: Sequence[Mapping[str, Any]],
                                 results: Sequence[Mapping[str, Any]], *,
                                 run_by_set: Mapping[str, str]) -> list[dict[str, Any]]:
    """Resolve by published (product, run), not latest date or ledger duplicates."""
    index: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for result in results:
        key = (identifier(result.get("sealed_product_id")), identifier(result.get("calculation_run_id")))
        index.setdefault(key, []).append(result)
    selected, seen = [], set()
    expected_runs = {identifier(k): identifier(v) for k, v in run_by_set.items()}
    for product in published_products:
        pid = identifier(product.get("sealedProductId"))
        sid = identifier(product.get("setId"))
        run = identifier(product.get("calculationRunId"))
        if pid in seen:
            raise BenchmarkError("duplicate published product; do not average or rerank")
        seen.add(pid)
        if run != expected_runs.get(sid):
            raise BenchmarkError("published product does not belong to exact verified set run")
        matches = index.get((pid, run), [])
        if len(matches) != 1:
            raise BenchmarkError("missing or ambiguous exact product result")
        result = matches[0]
        if identifier(result.get("set_id")) != sid:
            raise BenchmarkError("result owner mismatch")
        identifier(result.get("id"))
        selected.append(dict(result))
    return selected


def product_evidence(result: Mapping[str, Any], *, market_date: str,
                     expected_run_id: str, expected_result_id: str) -> dict[str, Any]:
    if identifier(result.get("calculation_run_id")) != identifier(expected_run_id):
        raise BenchmarkError("product calculation run mismatch")
    if identifier(result.get("id")) != identifier(expected_result_id):
        raise BenchmarkError("product exact result mismatch")
    if result.get("price_as_of") != day(market_date).isoformat():
        raise BenchmarkError("product cost is not observed for evidence date")
    n = number(result.get("pack_count"))
    random = number(result.get("random_pack_count"))
    if n <= 0 or n != n.to_integral_value() or random != n:
        raise BenchmarkError("verified integral random pack count required")
    if result.get("accessory_value_included") is not False:
        raise BenchmarkError("accessory exclusion must be explicit")
    cost = number(result.get("product_market_cost"))
    ev = number(result.get("expected_value"))
    if cost <= 0 or ev < 0:
        raise BenchmarkError("invalid product cost/EV")
    data: dict[str, Any] = {"cost_per_pack": cost / n, "expected_value_per_pack": ev / n,
                            "modeled_return_on_spend": ev / cost,
                            "chance_to_recover_cost": result.get("chance_to_recover_cost")}
    # expected_value/quantiles ALREADY include guaranteed cards. Do not add them again.
    for q, field in (("05", "p05_value"), ("50", "median_value"), ("95", "p95_value"), ("99", "p99_value")):
        if result.get(field) is not None:
            data[f"p{q}_value_per_pack"] = number(result[field]) / n
            if q != "05":
                data[f"normalized_p{q}"] = number(result[field]) / cost
    if result.get("expected_loss_when_losing") is not None:
        data["expected_loss_when_losing_per_pack"] = number(result["expected_loss_when_losing"]) / n
    return validate_evidence(data)


def attach_evidence(row: Mapping[str, Any], evidence: Mapping[str, Any], *,
                    market_date: str, source_snapshot_id: str | None = None,
                    calculation_run_id: str | None = None,
                    source_result_id: str | None = None) -> dict[str, Any]:
    """Evidence remains available even when a model or calibration is unavailable."""
    if row.get("metric_key") != "financial":
        raise BenchmarkError("financial evidence belongs only on financial metric row")
    result = dict(row)
    values = validate_evidence(evidence)
    proof: dict[str, Any] = {"market_date": day(market_date).isoformat(), "values": values}
    if row.get("entity_type") == "sealed_product":
        result["calculation_run_id"] = identifier(calculation_run_id)
        result["source_result_id"] = identifier(source_result_id)
        proof.update(calculation_run_id=result["calculation_run_id"], source_result_id=result["source_result_id"])
    else:
        proof["opening_economics_snapshot_id"] = identifier(source_snapshot_id)
    result.update(values)
    result.update(financial_evidence_status="available", financial_evidence_reason=None,
                  financial_evidence_market_date=day(market_date).isoformat(),
                  source_fingerprint=fingerprint({"model": row["source_fingerprint"], "financial_evidence": proof}))
    result["source_lineage"] = {**dict(row.get("source_lineage") or {}), "financial_evidence": proof}
    return result
