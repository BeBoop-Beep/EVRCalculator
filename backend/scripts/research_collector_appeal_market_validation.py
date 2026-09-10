"""Collector Appeal market-validation harness (READ-ONLY research).

Default behavior prepares the price/scarcity/control cohort only. It does NOT
read the current Collector Appeal pointer and it does NOT evaluate an unfinished
model. Evaluation is enabled only by explicitly supplying a validation-input
artifact whose manifest says ``freeze.status == 'frozen'`` and
``priceInputExcluded == true``.

The statistical engine lives under ``backend/research`` so it can be tested on
synthetic data without Supabase. This script only owns extraction, frozen-input
validation, joining, and report serialization.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.collector_appeal_inputs import load_pull_rate_model  # noqa: E402
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.research.collector_appeal_market_validation import (  # noqa: E402
    ComponentSpec,
    compare_components,
)

HARNESS_VERSION = "collector_appeal_market_validation_harness_v1"
INPUT_CONTRACT_VERSION = "collector_appeal_market_validation_input_v1"
MARKET_COHORT_VERSION = "collector_appeal_market_validation_market_cohort_v1"
DEFAULT_MARKET_OUTPUT = ROOT / "backend/artifacts/collector_appeal_market_validation_market_cohort_v1.json"
DEFAULT_REPORT_OUTPUT = ROOT / "backend/artifacts/collector_appeal_market_validation_report_v1.json"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _paged_select(query_factory, *, page_size: int = 1000, attempts: int = 4) -> List[Dict[str, Any]]:
    """Exhaustive paged read; errors raise instead of silently truncating a study."""
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page = None
        last_error = None
        for attempt in range(attempts):
            try:
                response = query_factory().range(start, start + page_size - 1).execute()
                page = list(response.data or [])
                break
            except Exception as exc:  # pragma: no cover - network/runtime shape
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(1.0 * (attempt + 1))
        if page is None:
            raise RuntimeError(f"read failed after {attempts} attempts at offset {start}") from last_error
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _card_number(card: Mapping[str, Any]) -> Optional[int]:
    raw = str(card.get("printed_number") or card.get("number") or "")
    digits = "".join(ch for ch in raw.split("/")[0] if ch.isdigit())
    return int(digits) if digits else None


def _printed_set_size(card: Mapping[str, Any]) -> Optional[int]:
    raw = str(card.get("printed_number") or "")
    if "/" not in raw:
        return None
    digits = "".join(ch for ch in raw.split("/", 1)[1] if ch.isdigit())
    return int(digits) if digits else None


def _subtype_flags(card: Mapping[str, Any]) -> Dict[str, int]:
    subtypes = card.get("subtypes") if isinstance(card.get("subtypes"), list) else []
    normalized = {str(value).strip().casefold() for value in subtypes}
    return {
        "is_promo": int("promo" in normalized),
        "is_mechanic_card": int(bool(normalized & {"ex", "gx", "v", "vmax", "vstar", "mega"})),
        "is_stage2": int("stage 2" in normalized),
    }


def load_market_prices(client: Any, set_ids: Sequence[str]) -> Dict[str, float]:
    prices: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 5):
        rows = _paged_select(
            lambda chunk=chunk: client.table("pokemon_canonical_card_market_prices_latest")
            .select("canonical_card_id,market_price")
            .in_("set_id", list(chunk))
        )
        for row in rows:
            price = _finite(row.get("market_price"))
            card_id = str(row.get("canonical_card_id") or "")
            if card_id and price is not None and price > 0:
                prices[card_id] = price
    return prices


def load_candidate_cards(client: Any, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
    columns = (
        "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,number,printed_number,"
        "catalog_role,opening_eligible,canonical_review_status"
    )
    cards: List[Dict[str, Any]] = []
    for chunk in _chunked(sorted(set_ids), 5):
        cards.extend(
            _paged_select(
                lambda chunk=chunk: client.table("pokemon_canonical_cards")
                .select(columns)
                .in_("set_id", list(chunk))
                .eq("catalog_role", "main")
                .eq("opening_eligible", True)
                .eq("canonical_review_status", "approved")
            )
        )
    return [
        row for row in cards
        if str(row.get("supertype") or "").casefold() in {"pokémon", "pokemon", "trainer"}
    ]


def build_market_rows(
    *,
    cards: Sequence[Mapping[str, Any]],
    prices: Mapping[str, float],
    pull_model: Mapping[str, Mapping[str, Mapping[str, Any]]],
    sets_by_id: Mapping[str, Mapping[str, Any]],
    as_of: date,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Build price/scarcity/control rows without reading any appeal score."""
    sizes: Dict[str, List[int]] = {}
    for card in cards:
        parsed = _printed_set_size(card)
        if parsed:
            sizes.setdefault(str(card.get("set_id")), []).append(parsed)
    modal_size: Dict[str, int] = {}
    for set_id, candidates in sizes.items():
        modal_size[set_id] = max(set(candidates), key=candidates.count)

    dropped: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    for card in cards:
        card_id = str(card.get("id") or "")
        set_id = str(card.get("set_id") or "")
        price = _finite(prices.get(card_id))
        if price is None or price <= 0:
            dropped["no_positive_price"] = dropped.get("no_positive_price", 0) + 1
            continue
        rarity_key = normalize_rarity_key(str(card.get("rarity") or ""))
        if not rarity_key:
            dropped["no_rarity_key"] = dropped.get("no_rarity_key", 0) + 1
            continue
        rarity_model = (pull_model.get(set_id) or {}).get(rarity_key) or {}
        probability = _finite(rarity_model.get("probability"))
        if probability is None or probability <= 0 or probability > 1:
            dropped["no_modeled_pull_probability"] = dropped.get("no_modeled_pull_probability", 0) + 1
            continue
        set_row = sets_by_id.get(set_id) or {}
        try:
            release_date = datetime.fromisoformat(str(set_row.get("release_date"))).date()
        except (TypeError, ValueError):
            dropped["no_release_date"] = dropped.get("no_release_date", 0) + 1
            continue
        age_days = max((as_of - release_date).days, 0)
        number = _card_number(card)
        printed_size = modal_size.get(set_id)
        supertype = str(card.get("supertype") or "")
        rarity_class = classify_rarity(card.get("rarity"))
        rows.append({
            "card_id": card_id,
            "pokemon_tcg_api_card_id": card.get("pokemon_tcg_api_card_id"),
            "card_name": card.get("name"),
            "set_id": set_id,
            "set_name": set_row.get("name"),
            "era": set_row.get("era_name"),
            "supertype": supertype,
            "rarity": card.get("rarity"),
            "rarity_key": rarity_key,
            "market_price": price,
            "log_price": math.log(price),
            "pull_probability": probability,
            "pull_scarcity": -math.log10(probability),
            "slot_group": rarity_model.get("slot_group"),
            "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
            "log_release_age": math.log1p(age_days),
            "is_secret": int(number is not None and printed_size is not None and number > printed_size),
            "is_trainer": int(supertype.casefold() == "trainer"),
            "hit_eligibility": rarity_class.bucket in HIT_BUCKETS,
            **_subtype_flags(card),
        })
    return rows, dropped


def extract_market_cohort(client: Any, *, as_of: Optional[date] = None) -> Dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc).date()
    pull_model = load_pull_rate_model(client)
    set_rows = _paged_select(lambda: client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    era_rows = _paged_select(lambda: client.table("eras").select("id,name"))
    eras = {str(row["id"]): str(row.get("name") or "") for row in era_rows}
    sets_by_id = {
        str(row["id"]): {**row, "era_name": eras.get(str(row.get("era_id") or ""))}
        for row in set_rows
    }
    covered_set_ids = sorted(set(pull_model) & set(sets_by_id))
    cards = load_candidate_cards(client, covered_set_ids)
    prices = load_market_prices(client, covered_set_ids)
    rows, dropped = build_market_rows(
        cards=cards,
        prices=prices,
        pull_model=pull_model,
        sets_by_id=sets_by_id,
        as_of=as_of,
    )
    body = {
        "contractVersion": MARKET_COHORT_VERSION,
        "asOfDate": as_of.isoformat(),
        "sourceTables": [
            "pokemon_set_page_snapshot_latest",
            "pokemon_canonical_cards",
            "pokemon_canonical_card_market_prices_latest",
            "sets",
            "eras",
        ],
        "filters": {
            "catalogRole": "main",
            "openingEligible": True,
            "canonicalReviewStatus": "approved",
            "supertypes": ["Pokemon", "Trainer"],
            "energyIncluded": False,
            "price": "positive latest market price",
            "pullProbability": "modeled rarity-keyed specific-card probability",
        },
        "counts": {
            "pullModelSets": len(pull_model),
            "coveredSets": len(covered_set_ids),
            "candidateCards": len(cards),
            "modeledRows": len(rows),
            "modeledSets": len({row["set_id"] for row in rows}),
            "dropped": dropped,
        },
        "rows": rows,
    }
    body["cohortFingerprint"] = canonical_hash({key: value for key, value in body.items() if key != "cohortFingerprint"})
    return body


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def validate_frozen_input(payload: Mapping[str, Any]) -> List[ComponentSpec]:
    """Validate the handoff boundary from corrected V6 into this harness."""
    if payload.get("contractVersion") != INPUT_CONTRACT_VERSION:
        raise ValueError(f"expected {INPUT_CONTRACT_VERSION}")
    freeze = payload.get("freeze")
    if not isinstance(freeze, Mapping) or freeze.get("status") != "frozen":
        raise ValueError("Collector Appeal validation input must explicitly be frozen")
    if freeze.get("priceInputExcluded") is not True:
        raise ValueError("market validation is circular unless priceInputExcluded=true")
    if not freeze.get("modelVersion") or not freeze.get("formulaFingerprint"):
        raise ValueError("frozen input must pin modelVersion and formulaFingerprint")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("frozen input must declare at least one component")
    specs: List[ComponentSpec] = []
    seen = set()
    for raw in components:
        if not isinstance(raw, Mapping):
            raise ValueError("component definitions must be objects")
        name = str(raw.get("name") or "")
        score_key = str(raw.get("scoreKey") or "")
        if not name or not score_key:
            raise ValueError("component name and scoreKey must be non-empty")
        subject_types = tuple(str(value) for value in (raw.get("subjectTypes") or []))
        spec = ComponentSpec(
            name=name,
            column=f"appeal::{score_key}",
            subject_types=subject_types,
            role=str(raw.get("role") or "candidate"),
            cross_bucket_comparable=raw.get("crossBucketComparable") is True,
            interaction_with_scarcity=raw.get("interactionWithScarcity") is not False,
        )
        spec.validate()
        if name in seen or score_key in seen:
            raise ValueError(f"duplicate component name/scoreKey: {name}/{score_key}")
        seen.update({name, score_key})
        specs.append(spec)
    if not isinstance(payload.get("rows"), list):
        raise ValueError("frozen input rows must be an array")
    return specs


def merge_frozen_appeal(
    market_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    specs: Sequence[ComponentSpec],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Join by canonical card id; no fuzzy card/name matching is allowed."""
    appeal_by_card: Dict[str, Mapping[str, Any]] = {}
    duplicates = 0
    for raw in payload.get("rows") or []:
        if not isinstance(raw, Mapping):
            continue
        card_id = str(raw.get("canonical_card_id") or raw.get("pokemon_canonical_card_id") or "")
        if not card_id:
            continue
        if card_id in appeal_by_card:
            duplicates += 1
        appeal_by_card[card_id] = raw
    if duplicates:
        raise ValueError(f"frozen appeal input contains {duplicates} duplicate canonical card ids")

    merged: List[Dict[str, Any]] = []
    unmatched_market = 0
    matched_appeal_ids = set()
    for market in market_rows:
        card_id = str(market.get("card_id") or "")
        appeal = appeal_by_card.get(card_id)
        if appeal is None:
            unmatched_market += 1
            continue
        scores = appeal.get("scores") if isinstance(appeal.get("scores"), Mapping) else appeal
        subject_type = str(appeal.get("subject_type") or appeal.get("subject_policy") or "")
        subject_cluster_key = (
            appeal.get("subject_cluster_key")
            or appeal.get("subjectClusterKey")
            or appeal.get("subject_identity")
            or appeal.get("subjectIdentity")
        )
        row = {**market, "subject_type": subject_type, "subject_cluster_key": subject_cluster_key}
        found = False
        for spec in specs:
            score_key = spec.column.split("appeal::", 1)[1]
            value = _finite(scores.get(score_key) if isinstance(scores, Mapping) else None)
            row[spec.column] = value
            found = found or value is not None
        if found:
            merged.append(row)
            matched_appeal_ids.add(card_id)
    diagnostics = {
        "marketRows": len(market_rows),
        "appealRows": len(appeal_by_card),
        "mergedRowsWithAnyComponent": len(merged),
        "marketRowsWithoutAppealRow": unmatched_market,
        "appealRowsOutsideMarketCohort": len(set(appeal_by_card) - matched_appeal_ids),
        "joinKey": "canonical card id exact match",
    }
    return merged, diagnostics


def build_waiting_report(market: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "harnessVersion": HARNESS_VERSION,
        "status": "READY_AWAITING_FROZEN_V6",
        "evaluationPerformed": False,
        "reason": "No explicit frozen Collector Appeal validation input was supplied.",
        "marketCohortFingerprint": market.get("cohortFingerprint"),
        "marketCounts": market.get("counts"),
        "guardrails": {
            "readsCurrentCollectorPointer": False,
            "acceptsUnfrozenModel": False,
            "requiresPriceInputExcluded": True,
            "tunesCollectorAppeal": False,
            "transfersPriceCoefficientsToRip": False,
        },
    }


def evaluate_frozen(market: Mapping[str, Any], frozen: Mapping[str, Any], *, bootstrap_draws: int) -> Dict[str, Any]:
    specs = validate_frozen_input(frozen)
    merged, join = merge_frozen_appeal(market.get("rows") or [], frozen, specs)
    comparison = compare_components(merged, specs, bootstrap_draws=bootstrap_draws)
    freeze = frozen["freeze"]
    return {
        "harnessVersion": HARNESS_VERSION,
        "status": "EVALUATED_FROZEN_INPUT",
        "evaluationPerformed": True,
        "marketCohortFingerprint": market.get("cohortFingerprint"),
        "collectorModel": {
            "modelVersion": freeze["modelVersion"],
            "formulaFingerprint": freeze["formulaFingerprint"],
            "asOfDate": freeze.get("asOfDate"),
            "priceInputExcluded": True,
        },
        "joinDiagnostics": join,
        "analysis": comparison,
        "interpretationBoundary": (
            "This report validates market association/incremental information only. "
            "It does not tune Collector Appeal, choose V6 weights, or authorize RIP/publication changes."
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-cohort-input", type=Path, help="Reuse an exact previously extracted market cohort")
    parser.add_argument("--market-cohort-output", type=Path, default=DEFAULT_MARKET_OUTPUT)
    parser.add_argument("--frozen-appeal-artifact", type=Path, help="Explicit frozen validation input; omitted means NO evaluation")
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=400)
    args = parser.parse_args()
    if args.bootstrap_draws < 0:
        parser.error("--bootstrap-draws must be >= 0")

    if args.market_cohort_input:
        market = _read_json(args.market_cohort_input)
        if market.get("contractVersion") != MARKET_COHORT_VERSION:
            raise ValueError(f"expected market cohort {MARKET_COHORT_VERSION}")
    else:
        load_dotenv(ROOT / "backend/.env", override=False)
        from backend.db.clients.supabase_client import service_read_client
        market = extract_market_cohort(service_read_client)
        _write_json(args.market_cohort_output, market)

    if args.frozen_appeal_artifact is None:
        report = build_waiting_report(market)
    else:
        frozen = _read_json(args.frozen_appeal_artifact)
        report = evaluate_frozen(market, frozen, bootstrap_draws=args.bootstrap_draws)
    _write_json(args.report_output, report)
    print(json.dumps({key: value for key, value in report.items() if key != "analysis"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
