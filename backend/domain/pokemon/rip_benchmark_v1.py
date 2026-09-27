"""Additive benchmark primitives. No model computation, rank assignment, or activation.

Calibration is deliberately NOT selected here. A caller must supply a versioned
calibration for a shadow preview. No calibration has been approved for production.
Decimal values go to PostgreSQL as exact numeric strings; round only in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

METRICS = ("financial", "chase", "collector", "overall")
ENTITY_TYPES = ("set", "era", "sealed_product")
TRANSFORM_VERSION = "centered_linear_clipped_shadow_v1"
APPROVED_CALIBRATION_VERSION = "rip_benchmark_v1_fin5_chase10_collector10_overall5"
APPROVED_BENCHMARK_KEY = "pokemon_equal_weight_eligible_sets_v1"
APPROVED_MODEL_VERSIONS = {
    "financial": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5",
    "chase": "chase_accessibility_v1_hc_value_squared_modeled_probability",
    "collector": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2",
    "overall": "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
}
APPROVED_SCALES = {"financial": Decimal("5"), "chase": Decimal("10"),
                   "collector": Decimal("10"), "overall": Decimal("5")}
APPROVED_CALIBRATION_VERSIONS: frozenset[str] = frozenset({APPROVED_CALIBRATION_VERSION})


class BenchmarkError(ValueError):
    """Input cannot be represented without changing its meaning."""


def number(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise BenchmarkError("finite numeric value required")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BenchmarkError("finite numeric value required") from exc
    if not result.is_finite():
        raise BenchmarkError("non-finite numeric value")
    return result


def identifier(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise BenchmarkError("canonical UUID required") from exc


def day(value: Any) -> date:
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise BenchmarkError("ISO calendar date required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BenchmarkError("ISO calendar date required") from exc
    if parsed.isoformat() != value:
        raise BenchmarkError("ISO calendar date required")
    return parsed


def wire(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(number(value))
    if isinstance(value, Mapping):
        return {str(k): wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if isinstance(value, float):
        number(value)  # JSON NaN/Infinity must not survive nested metadata.
    return value


def fingerprint(value: Any) -> str:
    encoded = json.dumps(wire(value), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Calibration:
    version: str
    metric_key: str
    source_model_version: str
    benchmark_key: str
    scale: Decimal
    transform_version: str = TRANSFORM_VERSION

    def __post_init__(self) -> None:
        if not self.version or self.metric_key not in METRICS:
            raise BenchmarkError("explicit calibration identity required")
        if not self.source_model_version or not self.benchmark_key:
            raise BenchmarkError("calibration must name model and benchmark")
        if self.transform_version != TRANSFORM_VERSION:
            raise BenchmarkError("unregistered transform")
        object.__setattr__(self, "scale", number(self.scale))
        if self.scale <= 0:
            raise BenchmarkError("positive fixed calibration scale required")


def approved_calibrations(model_versions: Mapping[str, str]) -> dict[str, Calibration]:
    """Return the reviewed calibration only for its exact V12/V4 model family."""
    if dict(model_versions) != APPROVED_MODEL_VERSIONS:
        raise BenchmarkError("approved calibration does not match exact certified model family")
    return {metric: Calibration(APPROVED_CALIBRATION_VERSION, metric, version,
                                APPROVED_BENCHMARK_KEY, APPROVED_SCALES[metric])
            for metric, version in APPROVED_MODEL_VERSIONS.items()}


def preview_score(raw: Any, reference: Any, calibration: Calibration) -> Decimal:
    """Shadow candidate: clamp(5 + (raw-reference)/scale, 0, 10).

    Rank never comes from this number: clipping can tie distinct raw values.
    Even extremely small representable differences must not become false 5s.
    """
    raw, reference = number(raw), number(reference)
    if raw == reference:
        return Decimal(5)
    with localcontext() as ctx:
        ctx.prec = 80
        result = max(Decimal(0), min(Decimal(10),
                     Decimal(5) + (raw - reference) / calibration.scale))
    if (raw > reference and result <= 5) or (raw < reference and result >= 5):
        raise BenchmarkError("calibration precision would erase benchmark direction")
    return result


@dataclass(frozen=True)
class Reference:
    benchmark_key: str
    metric_key: str
    source_model_version: str
    market_date: str
    raw_value: Decimal
    source_fingerprint: str


def equal_weight_reference(observations: Sequence[Mapping[str, Any]], *,
                           expected_entity_ids: Iterable[str], benchmark_key: str,
                           metric_key: str, source_model_version: str,
                           market_date: str) -> Reference:
    """Mean of a COMPLETE, explicitly named native-model cohort, not UI filters.

    Caller chooses the approved unit (sets or same-family products). Passing the
    same parent set once per SKU is invalid. EV, medians and leader scores are
    not acceptable substitutes for raw_model_value.
    """
    expected_list = [identifier(x) for x in expected_entity_ids]
    expected = set(expected_list)
    if not expected or len(expected) != len(expected_list):
        raise BenchmarkError("nonempty unique expected cohort required")
    seen: dict[str, Decimal] = {}
    source_proofs = []
    for row in observations:
        entity_id = identifier(row.get("entity_id"))
        if entity_id in seen or entity_id not in expected:
            raise BenchmarkError("duplicate or unexpected reference member")
        if (row.get("model_status") != "available" or
            row.get("metric_key") != metric_key or
            row.get("source_model_version") != source_model_version or
            row.get("source_market_date") != day(market_date).isoformat()):
            raise BenchmarkError("reference cohort source mismatch or unavailable member")
        seen[entity_id] = number(row.get("raw_model_value"))
        source_proofs.append((entity_id, str(seen[entity_id]), row.get("source_fingerprint")))
    if set(seen) != expected:
        raise BenchmarkError("incomplete reference cohort; do not silently renormalize")
    with localcontext() as ctx:
        ctx.prec = 80
        value = sum(seen.values(), Decimal(0)) / len(seen)
    return Reference(benchmark_key, metric_key, source_model_version,
                     day(market_date).isoformat(), value,
                     fingerprint({"weighting": "equal_native_entity_v1",
                                  "key": benchmark_key, "metric": metric_key,
                                  "version": source_model_version, "date": market_date,
                                  "members": sorted(source_proofs)}))


def metric_row(*, entity_type: str, entity_id: str, metric_key: str,
               market_date: str, source: Mapping[str, Any] | None = None,
               parent_set_id: str | None = None,
               unavailable_reason: str = "canonical_source_unavailable",
               reference: Reference | None = None,
               calibration: Calibration | None = None) -> dict[str, Any]:
    """Prepare one DB metric row; source date/model/rank are never repaired here."""
    if entity_type not in ENTITY_TYPES or metric_key not in METRICS:
        raise BenchmarkError("unknown entity or metric")
    eid = identifier(entity_id)
    parent = identifier(parent_set_id) if parent_set_id is not None else None
    target_day = day(market_date)
    if entity_type == "sealed_product" and parent is None:
        raise BenchmarkError("product parent set required")
    row: dict[str, Any] = {
        "entity_type": entity_type, "entity_id": eid, "metric_key": metric_key,
        "parent_set_id": parent, "model_status": "unavailable",
        "model_reason": unavailable_reason, "benchmark_status": "unavailable",
        "benchmark_reason": "model_unavailable", "raw_model_value": None,
        "benchmark_raw_value": None, "benchmark_score": None,
        "rank": None, "cohort_size": None, "reconstruction_status": "unavailable",
        "source_lineage": {}, "financial_evidence_status":
            "unavailable" if metric_key == "financial" else "not_applicable",
        "financial_evidence_reason": "financial_evidence_unavailable" if metric_key == "financial" else None,
    }
    if source is None:
        if not unavailable_reason:
            raise BenchmarkError("unavailability reason required")
        row["source_fingerprint"] = fingerprint({"entity": eid, "metric": metric_key,
                                                 "date": market_date, "reason": unavailable_reason})
        return row
    source = dict(source)
    inherited = entity_type == "sealed_product" and metric_key in ("chase", "collector")
    expected_type, expected_id = ("set", parent) if inherited else (entity_type, eid)
    if source.get("entity_type") != expected_type or identifier(source.get("entity_id")) != expected_id:
        raise BenchmarkError("source entity mismatch; product chase/collector must inherit parent set")
    source_day = day(source.get("market_date"))
    lineage = dict(source.get("lineage") or {})
    if source_day > target_day:
        raise BenchmarkError("future source date")
    if source_day != target_day:
        interval_ok = (metric_key == "collector" and source.get("collector_run_id") and
                       lineage.get("effective_from") and lineage.get("effective_until"))
        if not interval_ok or not day(lineage["effective_from"]) <= target_day <= day(lineage["effective_until"]):
            raise BenchmarkError("stale source requires unavailable row or proven Collector effective interval")
    if not source.get("model_version"):
        raise BenchmarkError("source model identity required")
    rank, size = source.get("rank"), source.get("cohort_size")
    if (rank is None) != (size is None):
        raise BenchmarkError("rank and cohort size must be supplied together")
    if rank is not None and (type(rank) is not int or type(size) is not int or not 1 <= rank <= size):
        raise BenchmarkError("invalid canonical rank")
    raw = number(source.get("raw_model_value"))
    row.update(model_status="inherited" if inherited else "available", model_reason=None,
               raw_model_value=raw, source_model_version=source["model_version"],
               source_market_date=source_day.isoformat(), source_entity_type=expected_type,
               source_entity_id=expected_id, source_lineage=lineage,
               source_fingerprint=fingerprint(source),
               rank=None if inherited else rank, cohort_size=None if inherited else size,
               reconstruction_status="inherited_parent_set" if inherited else source.get("reconstruction_status"))
    allowed_reconstruction = ("inherited_parent_set",) if inherited else ("persisted_exact", "reconstructed_compatible")
    if row["reconstruction_status"] not in allowed_reconstruction:
        raise BenchmarkError("invalid reconstruction status")
    for key in ("source_publication_id", "calculation_run_id", "source_result_id", "collector_run_id"):
        if source.get(key) is not None:
            row[key] = identifier(source[key])
    row["benchmark_reason"] = "reference_unavailable" if reference is None else "calibration_unapproved"
    if reference is not None:
        if (reference.metric_key != metric_key or reference.source_model_version != source["model_version"] or
                reference.market_date != target_day.isoformat()):
            raise BenchmarkError("benchmark reference source mismatch")
        row.update(benchmark_raw_value=reference.raw_value,
                   benchmark_source_fingerprint=reference.source_fingerprint)
        if calibration is not None:
            if (calibration.metric_key != metric_key or calibration.source_model_version != source["model_version"] or
                    calibration.benchmark_key != reference.benchmark_key):
                raise BenchmarkError("calibration identity mismatch")
            row.update(benchmark_score=preview_score(raw, reference.raw_value, calibration),
                       benchmark_status="available", benchmark_reason=None)
            row["source_lineage"] = {**lineage, "benchmark_calibration": {
                "version": calibration.version, "transform": calibration.transform_version,
                "scale": str(calibration.scale), "reference_key": reference.benchmark_key,
            }}
    return row


def history_windows(start: str, end: str) -> list[tuple[str, str]]:
    """Split ALL into non-overlapping <=366-day windows, without filling gaps."""
    first, last = day(start), day(end)
    if last < first:
        raise BenchmarkError("reversed date window")
    windows = []
    while first <= last:
        finish = min(last, first + timedelta(days=365))
        windows.append((first.isoformat(), finish.isoformat()))
        if finish == last:
            break
        first = finish + timedelta(days=1)
    return windows
