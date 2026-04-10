import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_bootstrap_report.json")
DEFAULT_RESOLUTION_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_tcgplayer_resolution_report.json")
DEFAULT_READINESS_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_readiness_after_tcgplayer_resolution.json")

TCGPLAYER_SEARCH_URL = "https://mp-search-api.tcgplayer.com/v1/search/request"


@dataclass
class ConfigTargets:
    card_details_url: Optional[str]
    sealed_details_url: Optional[str]
    price_endpoints_count: int
    set_name: Optional[str]


def normalize_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def clean_tcg_set_name(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^[A-Z0-9]+:\s*", "", value)
    return value.strip()


def token_set(value: str) -> set:
    return set(normalize_name(value).split())


def token_overlap_score(a: str, b: str) -> float:
    ta = token_set(a)
    tb = token_set(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    return intersection / max(len(ta), len(tb))


def parse_python_literal(value: str) -> Any:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return eval(value, {"__builtins__": {}}, {})
    except Exception:
        return None


def parse_assignment_text(py_text: str, name: str) -> Optional[str]:
    pattern = rf"^\s*{re.escape(name)}\s*=\s*(.+)$"
    m = re.search(pattern, py_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_existing_targets(py_text: str) -> ConfigTargets:
    card_raw = parse_assignment_text(py_text, "CARD_DETAILS_URL")
    sealed_raw = parse_assignment_text(py_text, "SEALED_DETAILS_URL")
    price_raw = parse_assignment_text(py_text, "PRICE_ENDPOINTS")
    set_name_raw = parse_assignment_text(py_text, "SET_NAME")

    card_value = parse_python_literal(card_raw) if card_raw else None
    sealed_value = parse_python_literal(sealed_raw) if sealed_raw else None
    price_value = parse_python_literal(price_raw) if price_raw else {}
    set_name_value = parse_python_literal(set_name_raw) if set_name_raw else None

    if not isinstance(price_value, dict):
        price_value = {}

    return ConfigTargets(
        card_details_url=card_value if isinstance(card_value, str) and card_value.strip() else None,
        sealed_details_url=sealed_value if isinstance(sealed_value, str) and sealed_value.strip() else None,
        price_endpoints_count=len(price_value),
        set_name=set_name_value if isinstance(set_name_value, str) else None,
    )


def build_search_body(query_set_name: Optional[str] = None, size: int = 24) -> Dict[str, Any]:
    term_filters: Dict[str, Any] = {
        "productLineName": ["Pokemon"],
        "productTypeName": ["Cards"],
    }
    if query_set_name:
        term_filters["setName"] = [query_set_name]

    return {
        "algorithm": "sales_dismax",
        "from": 0,
        "size": size,
        "filters": {"term": term_filters},
        "listingSearch": {
            "context": {"cart": {}},
            "filters": {
                "term": {
                    "sellerStatus": "Live",
                    "channelId": 0,
                }
            },
        },
        "settings": {"useFuzzySearch": True},
        "sort": {},
        "context": {"cart": {}, "shippingCountry": "US"},
    }


def fetch_global_set_aggregations(session: requests.Session) -> List[Dict[str, Any]]:
    body = build_search_body(size=0)
    payload = safe_post_search(session=session, query="", body=body)
    results = (payload.get("results") or [{}])[0]
    return (results.get("aggregations") or {}).get("setName") or []


def safe_post_search(session: requests.Session, query: str, body: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    params = {"q": query, "isList": "true"}
    for attempt in range(retries):
        try:
            response = session.post(TCGPLAYER_SEARCH_URL, params=params, json=body, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.5 * (attempt + 1))
                continue
            return {}
        except requests.RequestException:
            time.sleep(0.5 * (attempt + 1))
    return {}


def pick_candidate_set_name(aggregations: List[Dict[str, Any]], target_name: str) -> Tuple[Optional[str], float, str]:
    if not aggregations:
        return None, 0.0, "No setName aggregations returned"

    target_norm = normalize_name(target_name)

    best_value = None
    best_score = 0.0
    best_note = "No candidate"

    for agg in aggregations:
        value = agg.get("value")
        if not value:
            continue

        candidate_clean = clean_tcg_set_name(value)
        candidate_norm = normalize_name(candidate_clean)

        if candidate_norm == target_norm:
            return value, 1.0, "Exact normalized set-name match"

        overlap = token_overlap_score(candidate_clean, target_name)
        contains = 1.0 if target_norm and (target_norm in candidate_norm or candidate_norm in target_norm) else 0.0
        score = (0.7 * overlap) + (0.3 * contains)

        if score > best_score:
            best_score = score
            best_value = value
            best_note = f"Best normalized overlap score={score:.3f}"

    return best_value, best_score, best_note


def validate_candidate_set_id(
    session: requests.Session,
    search_query: str,
    set_name_filter: str,
    expected_set_name: str,
) -> Tuple[Optional[int], float, str]:
    body = build_search_body(query_set_name=set_name_filter, size=24)
    payload = safe_post_search(session, query=search_query, body=body)
    results = (payload.get("results") or [{}])[0]
    items = results.get("results") or []

    if not items:
        return None, 0.0, "Validation returned no product results"

    set_ids = [int(item.get("setId")) for item in items if item.get("setId") is not None]
    set_names = [item.get("setName", "") for item in items if item.get("setName")]
    if not set_ids:
        return None, 0.0, "Validation results missing setId"

    dominant_set_id = max(set(set_ids), key=set_ids.count)
    same_id_ratio = set_ids.count(dominant_set_id) / len(set_ids)

    dominant_set_names = [name for name, sid in zip(set_names, set_ids) if sid == dominant_set_id]
    dominant_name = dominant_set_names[0] if dominant_set_names else ""

    overlap = token_overlap_score(clean_tcg_set_name(dominant_name), expected_set_name)
    name_match = normalize_name(clean_tcg_set_name(dominant_name)) == normalize_name(expected_set_name)

    confidence = (0.6 * same_id_ratio) + (0.4 * overlap)
    if name_match:
        confidence = max(confidence, 0.95)

    note = (
        f"dominant_set_id={dominant_set_id}, same_id_ratio={same_id_ratio:.2f}, "
        f"overlap={overlap:.2f}, dominant_name='{dominant_name}'"
    )
    return dominant_set_id, confidence, note


def build_priceguide_urls(set_id: int) -> Tuple[str, str]:
    card_url = f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}/cards/?rows=5000&productTypeID=1"
    sealed_url = f"https://infinite-api.tcgplayer.com/priceguide/set/{set_id}/cards/?rows=5000&productTypeID=25"
    return card_url, sealed_url


def replace_assignment_line(py_text: str, assignment_name: str, new_value_repr: str) -> Tuple[str, bool]:
    pattern = rf"^(\s*{re.escape(assignment_name)}\s*=\s*)(.+)$"
    m = re.search(pattern, py_text, re.MULTILINE)
    if not m:
        return py_text, False
    replacement = f"{m.group(1)}{new_value_repr}"
    start, end = m.span()
    return py_text[:start] + replacement + py_text[end:], True


def summarize_readiness(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    total = len(rows)
    ready = 0
    for row in rows:
        if row.get("has_card_details_url") or row.get("has_sealed_details_url"):
            ready += 1
    return {
        "total_sets_inspected": total,
        "ready_for_daily_scrape": ready,
        "not_ready": total - ready,
    }


def resolve_single_set(
    session: requests.Session,
    row: Dict[str, Any],
    apply_changes: bool,
    min_confidence: float,
    global_set_aggregations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    config_file = Path(row["local_config_file_path"])
    if not config_file.exists():
        return {
            "resolution_status": "unresolved",
            "confidence": 0.0,
            "validation_notes": "Config file missing",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": 0,
            "existing_card_details_url": None,
            "existing_sealed_details_url": None,
            "existing_price_endpoints_count": 0,
            "notes": "Missing config file",
        }

    py_text = config_file.read_text(encoding="utf-8")
    existing = parse_existing_targets(py_text)

    has_existing_ready = bool(existing.card_details_url or existing.sealed_details_url)
    if has_existing_ready:
        return {
            "resolution_status": "already_ready",
            "confidence": 1.0,
            "validation_notes": "Existing authored target(s) preserved",
            "wrote_changes": False,
            "manual_review_required": False,
            "resolved_card_details_url": existing.card_details_url,
            "resolved_sealed_details_url": existing.sealed_details_url,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "No overwrite performed",
        }

    target_set_name = row.get("set_name") or existing.set_name or row.get("canonical_key") or ""
    best_candidate_name: Optional[str] = None
    best_candidate_score = 0.0
    best_candidate_note = ""

    candidate_name, score, note = pick_candidate_set_name(global_set_aggregations, target_set_name)
    if candidate_name and score > best_candidate_score:
        best_candidate_name = candidate_name
        best_candidate_score = score
        best_candidate_note = f"global_aggregation {note}"

    if best_candidate_score < 1.0:
        staged_queries = [
            target_set_name,
            normalize_name(target_set_name),
            f"pokemon {target_set_name}",
            row.get("canonical_key") or "",
        ]
        for query in staged_queries:
            query = (query or "").strip()
            if not query:
                continue
            body = build_search_body(size=0)
            payload = safe_post_search(session, query=query, body=body)
            results = (payload.get("results") or [{}])[0]
            aggregations = (results.get("aggregations") or {}).get("setName") or []
            candidate_name, score, note = pick_candidate_set_name(aggregations, target_set_name)
            if candidate_name and score > best_candidate_score:
                best_candidate_name = candidate_name
                best_candidate_score = score
                best_candidate_note = f"stage_query='{query}' {note}"
            if score >= 1.0:
                break

    if not best_candidate_name:
        return {
            "resolution_status": "unresolved",
            "confidence": 0.0,
            "validation_notes": "No setName candidate found via search aggregations",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "Aggregation matching failed",
        }

    set_id, confidence, validation_note = validate_candidate_set_id(
        session=session,
        search_query=target_set_name,
        set_name_filter=best_candidate_name,
        expected_set_name=target_set_name,
    )

    if not set_id or confidence < min_confidence:
        return {
            "resolution_status": "validation_failed",
            "confidence": round(confidence, 3),
            "validation_notes": f"{best_candidate_note}; {validation_note}",
            "wrote_changes": False,
            "manual_review_required": True,
            "resolved_card_details_url": None,
            "resolved_sealed_details_url": None,
            "resolved_price_endpoints_count": existing.price_endpoints_count,
            "existing_card_details_url": existing.card_details_url,
            "existing_sealed_details_url": existing.sealed_details_url,
            "existing_price_endpoints_count": existing.price_endpoints_count,
            "notes": "Confidence threshold not met",
        }

    resolved_card_url, resolved_sealed_url = build_priceguide_urls(set_id)

    wrote_changes = False
    patched_text = py_text

    if not existing.card_details_url:
        patched_text, changed = replace_assignment_line(patched_text, "CARD_DETAILS_URL", repr(resolved_card_url))
        wrote_changes = wrote_changes or changed
    if not existing.sealed_details_url:
        patched_text, changed = replace_assignment_line(patched_text, "SEALED_DETAILS_URL", repr(resolved_sealed_url))
        wrote_changes = wrote_changes or changed

    if apply_changes and wrote_changes and patched_text != py_text:
        config_file.write_text(patched_text, encoding="utf-8", newline="\n")

    status = "resolved_automatically"
    if (existing.card_details_url and not existing.sealed_details_url) or (existing.sealed_details_url and not existing.card_details_url):
        status = "partially_resolved"

    return {
        "resolution_status": status,
        "confidence": round(confidence, 3),
        "validation_notes": f"{best_candidate_note}; {validation_note}",
        "wrote_changes": wrote_changes and apply_changes,
        "manual_review_required": False,
        "resolved_card_details_url": existing.card_details_url or resolved_card_url,
        "resolved_sealed_details_url": existing.sealed_details_url or resolved_sealed_url,
        "resolved_price_endpoints_count": existing.price_endpoints_count,
        "existing_card_details_url": existing.card_details_url,
        "existing_sealed_details_url": existing.sealed_details_url,
        "existing_price_endpoints_count": existing.price_endpoints_count,
        "notes": f"Resolved setId={set_id}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve missing Pokemon TCGplayer scrape targets deterministically")
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH), help="Path to pokemon bootstrap report JSON")
    parser.add_argument("--apply", action="store_true", help="Apply validated updates to set config files")
    parser.add_argument("--min-confidence", type=float, default=0.90, help="Minimum confidence to write URLs")
    parser.add_argument("--max-sets", type=int, default=0, help="Optional cap on sets processed from unresolved queue")
    parser.add_argument("--resolution-report", default=str(DEFAULT_RESOLUTION_REPORT_PATH), help="Output resolution report path")
    parser.add_argument("--readiness-report", default=str(DEFAULT_READINESS_REPORT_PATH), help="Output readiness summary report path")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sets = payload.get("sets", [])

    unresolved_queue = [
        row
        for row in sets
        if (not row.get("ready_for_daily_scrape"))
        or (not row.get("has_card_details_url"))
        or (not row.get("has_sealed_details_url"))
        or (not row.get("has_price_endpoints"))
    ]

    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.tcgplayer.com",
        "Referer": "https://www.tcgplayer.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    })

    before_ready = sum(1 for row in sets if row.get("ready_for_daily_scrape"))

    if args.max_sets and args.max_sets > 0:
        unresolved_queue = unresolved_queue[: args.max_sets]

    global_set_aggregations = fetch_global_set_aggregations(session)

    resolution_rows: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {}
    wrote_count = 0

    for row in unresolved_queue:
        resolution = resolve_single_set(
            session=session,
            row=row,
            apply_changes=args.apply,
            min_confidence=args.min_confidence,
            global_set_aggregations=global_set_aggregations,
        )

        status = resolution["resolution_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if resolution.get("wrote_changes"):
            wrote_count += 1

        config_path = row.get("local_config_file_path")
        config_targets_after = ConfigTargets(None, None, 0, None)
        if config_path and Path(config_path).exists():
            config_text_after = Path(config_path).read_text(encoding="utf-8")
            config_targets_after = parse_existing_targets(config_text_after)

        resolution_rows.append(
            {
                "era": row.get("era_name"),
                "canonical_key": row.get("canonical_key"),
                "set_name": row.get("set_name"),
                "config_file_path": row.get("local_config_file_path"),
                "existing_card_details_url": resolution.get("existing_card_details_url"),
                "resolved_card_details_url": resolution.get("resolved_card_details_url"),
                "existing_sealed_details_url": resolution.get("existing_sealed_details_url"),
                "resolved_sealed_details_url": resolution.get("resolved_sealed_details_url"),
                "existing_price_endpoints_count": resolution.get("existing_price_endpoints_count", 0),
                "resolved_price_endpoints_count": resolution.get("resolved_price_endpoints_count", 0),
                "resolution_status": resolution.get("resolution_status"),
                "confidence": resolution.get("confidence", 0.0),
                "validation_notes": resolution.get("validation_notes", ""),
                "wrote_changes": resolution.get("wrote_changes", False),
                "manual_review_required": resolution.get("manual_review_required", False),
                "notes": resolution.get("notes", ""),
                "post_apply_has_card_details_url": bool(config_targets_after.card_details_url),
                "post_apply_has_sealed_details_url": bool(config_targets_after.sealed_details_url),
            }
        )

    refreshed_sets: List[Dict[str, Any]] = []
    for row in sets:
        updated = dict(row)
        config_path = row.get("local_config_file_path")
        if config_path and Path(config_path).exists():
            config_text = Path(config_path).read_text(encoding="utf-8")
            targets = parse_existing_targets(config_text)
            updated["has_card_details_url"] = bool(targets.card_details_url)
            updated["has_sealed_details_url"] = bool(targets.sealed_details_url)
            updated["has_price_endpoints"] = targets.price_endpoints_count > 0
            updated["ready_for_daily_scrape"] = bool(targets.card_details_url or targets.sealed_details_url)
        refreshed_sets.append(updated)

    after_ready = sum(1 for row in refreshed_sets if row.get("ready_for_daily_scrape"))
    readiness_summary = summarize_readiness(refreshed_sets)

    readiness_report = {
        "summary": {
            "source_report": str(report_path).replace("\\", "/"),
            "apply_mode": bool(args.apply),
            "sets_inspected": len(sets),
            "sets_in_resolution_queue": len(unresolved_queue),
            "sets_already_ready_before": before_ready,
            "sets_ready_after": after_ready,
            "sets_newly_resolved": max(after_ready - before_ready, 0),
            "sets_with_file_writes": wrote_count,
            "status_counts": status_counts,
            **readiness_summary,
        },
        "sets": refreshed_sets,
    }

    resolution_report = {
        "summary": {
            "source_report": str(report_path).replace("\\", "/"),
            "apply_mode": bool(args.apply),
            "min_confidence": args.min_confidence,
            "sets_inspected": len(sets),
            "sets_in_resolution_queue": len(unresolved_queue),
            "status_counts": status_counts,
            "writes_applied": wrote_count,
            "sets_already_ready_before": before_ready,
            "sets_ready_after": after_ready,
            "newly_ready": max(after_ready - before_ready, 0),
        },
        "sets": resolution_rows,
    }

    resolution_report_path = Path(args.resolution_report)
    readiness_report_path = Path(args.readiness_report)
    resolution_report_path.write_text(json.dumps(resolution_report, indent=2), encoding="utf-8", newline="\n")
    readiness_report_path.write_text(json.dumps(readiness_report, indent=2), encoding="utf-8", newline="\n")

    print(f"[TCGPLAYER-RESOLVE] sets_inspected={len(sets)}")
    print(f"[TCGPLAYER-RESOLVE] queue={len(unresolved_queue)}")
    print(f"[TCGPLAYER-RESOLVE] ready_before={before_ready} ready_after={after_ready}")
    print(f"[TCGPLAYER-RESOLVE] writes_applied={wrote_count} apply_mode={args.apply}")
    print(f"[TCGPLAYER-RESOLVE] resolution_report={resolution_report_path}")
    print(f"[TCGPLAYER-RESOLVE] readiness_report={readiness_report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
