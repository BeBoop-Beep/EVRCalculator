from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

from backend.alerts.scrape_alerts import queue_alert
from backend.db.repositories import pokemon_set_onboarding_repository as jobs
from backend.services.tcgplayer_set_catalog_service import (
    ThrottledRequester,
    build_priceguide_urls,
    fetch_global_set_aggregations,
    normalize_name,
    validate_candidate_set_id,
)

SOURCE_SYSTEM = "tcgplayer"
DEFAULT_MIN_CONFIDENCE = 0.90
_SET_ID_RE = re.compile(r"/priceguide/set/(\d+)/")
_ASSIGNMENT_RE = re.compile(r"^\s*SET_NAME\s*=\s*['\"](.+?)['\"]\s*$", re.MULTILINE)


@dataclass
class DiscoverySummary:
    status: str = "ok"
    provider_candidates: int = 0
    candidates_checked: int = 0
    known_provider_ids: int = 0
    detected: int = 0
    manual_review: int = 0
    unchanged: int = 0
    dry_run: bool = True
    error: Optional[str] = None


def parse_tcgplayer_set_id(url: Optional[str]) -> Optional[str]:
    match = _SET_ID_RE.search(url or "")
    return match.group(1) if match else None


def _local_catalog(root: Path) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    names: set[str] = set()
    for path in root.glob("**/*.py"):
        if path.name in {"setMap.py", "baseConfig.py", "__init__.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        ids.update(_SET_ID_RE.findall(text))
        match = _ASSIGNMENT_RE.search(text)
        if match:
            names.add(normalize_name(match.group(1)))
    return ids, names


def _database_catalog() -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    for row in jobs.list_registered_set_urls():
        for key in ("card_details_url", "sealed_details_url"):
            source_id = parse_tcgplayer_set_id(row.get(key))
            if source_id:
                ids.add(source_id)
    return ids, jobs.list_source_identities(SOURCE_SYSTEM)


def discover_new_sets(
    *, commit: bool, min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_new: int = 12, provider_timeout_seconds: float = 10.0,
    max_candidates: int = 100, session: Optional[requests.Session] = None,
    pokemon_root: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = DiscoverySummary(dry_run=not commit)
    root = pokemon_root or Path("backend/constants/tcg/pokemon")
    local_ids, local_names = _local_catalog(root)
    try:
        db_ids, job_ids = _database_catalog()
    except Exception as exc:
        if commit:
            return {**asdict(summary), "status": "retryable_provider_or_database_error", "error": str(exc)}
        db_ids, job_ids = set(), set()

    known_ids = local_ids | db_ids | job_ids
    summary.known_provider_ids = len(known_ids)
    requester = ThrottledRequester(
        session or requests.Session(), timeout_seconds=max(0.1, provider_timeout_seconds)
    )
    cache: Dict[str, Any] = {}
    try:
        aggregations = fetch_global_set_aggregations(requester, cache)
    except Exception as exc:
        return {**asdict(summary), "status": "retryable_provider_error", "error": str(exc)}
    if not aggregations:
        return {**asdict(summary), "status": "retryable_provider_error", "error": "empty setName aggregation"}

    summary.provider_candidates = len(aggregations)
    candidates = [
        item for item in aggregations
        if item.get("value") and normalize_name(str(item["value"])) not in local_names
    ][:max_candidates]
    evidence: list[Dict[str, Any]] = []
    for aggregation in candidates:
        if summary.detected + summary.manual_review >= max_new:
            break
        provider_name = str(aggregation["value"])
        summary.candidates_checked += 1
        set_id, confidence, note = validate_candidate_set_id(
            requester, cache, provider_name, provider_name, provider_name
        )
        item_evidence = {
            "aggregation": aggregation, "source_set_name": provider_name,
            "resolved_set_id": set_id, "confidence": confidence,
            "confidence_threshold": min_confidence, "diagnostic": note,
        }
        evidence.append(item_evidence)
        if set_id is None:
            summary.manual_review += 1
            continue
        source_id = str(set_id)
        if source_id in known_ids:
            summary.unchanged += 1
            continue
        card_url, sealed_url = build_priceguide_urls(set_id)
        status = "detected" if confidence >= min_confidence else "manual_review"
        row = {
            "tcg": "pokemon", "source_system": SOURCE_SYSTEM,
            "source_set_id": source_id, "source_set_name": provider_name,
            "status": status, "current_step": "metadata_resolution",
            "metadata_json": {
                "discovery_evidence": item_evidence,
                "card_details_url": card_url, "sealed_details_url": sealed_url,
            },
        }
        if commit:
            jobs.upsert_discovery(row)
            queue_alert(
                "new_pokemon_set_detected" if status == "detected" else "pokemon_set_onboarding_manual_review",
                f"Pokemon set {provider_name} {'detected' if status == 'detected' else 'needs review'}",
                f"TCGplayer setId {source_id}; confidence {confidence:.3f}.",
                severity="info" if status == "detected" else "warning",
                dedupe_key=f"pokemon-set-onboarding:{source_id}",
                payload=row,
            )
        known_ids.add(source_id)
        if status == "detected":
            summary.detected += 1
        else:
            summary.manual_review += 1
    return {**asdict(summary), "evidence": evidence}
