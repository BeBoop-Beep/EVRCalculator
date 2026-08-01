from __future__ import annotations

import json
import hashlib
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
# Terminal, non-runnable status used only by the one-time catalog baseline.
BASELINE_STATUS = "ignored"
BASELINE_STEP = "catalog_baseline"
BASELINE_REASON = (
    "Captured during initial TCGplayer catalog baseline; this provider set already existed "
    "in the catalog before new-set discovery was enabled and was NOT onboarded. "
    "It exists solely so normal discovery treats it as known."
)
_SET_ID_RE = re.compile(r"/priceguide/set/(\d+)/")
_ASSIGNMENT_RE = re.compile(r"^\s*SET_NAME\s*=\s*['\"](.+?)['\"]\s*$", re.MULTILINE)


@dataclass
class DiscoverySummary:
    status: str = "ok"
    mode: str = "discovery"
    provider_candidates: int = 0
    candidates_checked: int = 0
    known_provider_ids: int = 0
    baseline_ignored_known: int = 0
    detected: int = 0
    manual_review: int = 0
    unchanged: int = 0
    dry_run: bool = True
    error: Optional[str] = None


@dataclass
class BaselineSummary:
    """One-time catalog baseline: records pre-existing provider identities as non-runnable."""

    status: str = "ok"
    mode: str = "baseline"
    provider_candidates: int = 0
    candidates_checked: int = 0
    known_provider_ids: int = 0
    already_baselined: int = 0
    known_skipped: int = 0
    unresolved: int = 0
    would_baseline: int = 0
    baselined: int = 0
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


def _database_catalog() -> tuple[set[str], set[str], set[str]]:
    """Returns (public.sets ids, all onboarding job identities, baseline-ignored identities)."""
    ids: set[str] = set()
    for row in jobs.list_registered_set_urls():
        for key in ("card_details_url", "sealed_details_url"):
            source_id = parse_tcgplayer_set_id(row.get(key))
            if source_id:
                ids.add(source_id)
    identities = jobs.list_source_identity_statuses(SOURCE_SYSTEM)
    ignored = {key for key, status in identities.items() if status == BASELINE_STATUS}
    return ids, set(identities), ignored


def _classify_known(
    source_id: str, *, local_ids: set[str], db_ids: set[str],
    ignored_ids: set[str], job_ids: set[str],
) -> Optional[str]:
    """Why an already-known provider identity is known, or None when it is genuinely new."""
    if source_id in local_ids:
        return "known_local"
    if source_id in db_ids:
        return "known_database"
    if source_id in ignored_ids:
        return "baseline_ignored"
    if source_id in job_ids:
        return "known_job"
    return None


def discover_new_sets(
    *, commit: bool, min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_new: int = 12, provider_timeout_seconds: float = 10.0,
    max_candidates: int = 100, max_same_name_audits: int = 10,
    session: Optional[requests.Session] = None,
    pokemon_root: Optional[Path] = None,
) -> Dict[str, Any]:
    summary = DiscoverySummary(dry_run=not commit)
    root = pokemon_root or Path("backend/constants/tcg/pokemon")
    local_ids, local_names = _local_catalog(root)
    try:
        db_ids, job_ids, ignored_ids = _database_catalog()
    except Exception as exc:
        if commit:
            return {**asdict(summary), "status": "retryable_provider_or_database_error", "error": str(exc)}
        db_ids, job_ids, ignored_ids = set(), set(), set()

    # Baseline-ignored identities are part of job_ids and therefore already known; they are
    # tracked separately only so evidence can attribute the disposition.
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
    named = [item for item in aggregations if item.get("value")]
    tier_1 = [
        item for item in named
        if normalize_name(str(item["value"])) not in local_names
    ]
    tier_2 = [
        item for item in named
        if normalize_name(str(item["value"])) in local_names
    ]
    # Unknown names receive the main budget regardless of their provider order.
    # Same-name/new-ID detection remains available through a separate bounded audit.
    candidates = tier_1[:max_candidates] + tier_2[:max(0, max_same_name_audits)]
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
            provisional = "unresolved:" + hashlib.sha256(
                json.dumps(item_evidence, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if provisional in job_ids:
                item_evidence["disposition"] = (
                    "baseline_ignored" if provisional in ignored_ids else "known_job"
                )
                summary.unchanged += 1
                continue
            item_evidence["disposition"] = "manual_review"
            row = {
                "tcg": "pokemon", "source_system": SOURCE_SYSTEM,
                "source_set_id": provisional, "source_set_name": provider_name,
                "status": "manual_review", "current_step": "metadata_resolution",
                "metadata_json": {"discovery_evidence": item_evidence, "provisional_identity": True},
            }
            if commit:
                jobs.upsert_discovery(row)
                queue_alert(
                    "pokemon_set_onboarding_manual_review",
                    f"Pokemon provider candidate {provider_name} needs stable-ID review",
                    "TCGplayer validation did not resolve a stable setId; evidence was persisted.",
                    severity="warning", dedupe_key=f"pokemon-set-onboarding:{provisional}",
                    payload=row,
                )
            job_ids.add(provisional)
            summary.manual_review += 1
            continue
        source_id = str(set_id)
        known_reason = _classify_known(
            source_id, local_ids=local_ids, db_ids=db_ids,
            ignored_ids=ignored_ids, job_ids=job_ids,
        )
        if known_reason is not None:
            item_evidence["disposition"] = known_reason
            if known_reason == "baseline_ignored":
                summary.baseline_ignored_known += 1
            summary.unchanged += 1
            continue
        card_url, sealed_url = build_priceguide_urls(set_id)
        status = "detected" if confidence >= min_confidence else "manual_review"
        item_evidence["disposition"] = status
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
        # job_ids feeds _classify_known, so two provider names resolving to the same new
        # setId inside one run collapse to a single detection rather than double-counting.
        known_ids.add(source_id)
        job_ids.add(source_id)
        if status == "detected":
            summary.detected += 1
        else:
            summary.manual_review += 1
    return {
        **asdict(summary),
        "dispositions": _disposition_counts(evidence),
        "evidence": evidence,
    }


def _disposition_counts(evidence: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in evidence:
        key = str(item.get("disposition") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def baseline_current_catalog(
    *, commit: bool, provider_timeout_seconds: float = 10.0,
    session: Optional[requests.Session] = None,
    pokemon_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """One-time baseline: record the pre-existing provider catalog as non-runnable identities.

    Never creates detected/ready/retry jobs, never alerts, and never triggers any
    downstream onboarding (no PRs, no card scrapes, no image sync).
    """
    summary = BaselineSummary(dry_run=not commit)
    root = pokemon_root or Path("backend/constants/tcg/pokemon")
    local_ids, _local_names = _local_catalog(root)
    try:
        db_ids, job_ids, ignored_ids = _database_catalog()
    except Exception as exc:
        return {**asdict(summary), "status": "retryable_provider_or_database_error", "error": str(exc)}

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
    evidence: list[Dict[str, Any]] = []
    # The baseline intentionally walks the COMPLETE provider catalog with no max_new budget:
    # a partial baseline would leave historical products to resurface as false detections.
    for aggregation in aggregations:
        if not aggregation.get("value"):
            continue
        provider_name = str(aggregation["value"])
        summary.candidates_checked += 1
        set_id, confidence, note = validate_candidate_set_id(
            requester, cache, provider_name, provider_name, provider_name
        )
        item_evidence: Dict[str, Any] = {
            "aggregation": aggregation, "source_set_name": provider_name,
            "resolved_set_id": set_id, "confidence": confidence, "diagnostic": note,
        }
        evidence.append(item_evidence)
        if set_id is None:
            # Unresolvable identities are left alone: no provisional rows, no manual_review.
            item_evidence["disposition"] = "unresolved"
            summary.unresolved += 1
            continue
        source_id = str(set_id)
        known_reason = _classify_known(
            source_id, local_ids=local_ids, db_ids=db_ids,
            ignored_ids=ignored_ids, job_ids=job_ids,
        )
        if known_reason is not None:
            item_evidence["disposition"] = known_reason
            if known_reason == "baseline_ignored":
                summary.already_baselined += 1
            else:
                summary.known_skipped += 1
            continue
        item_evidence["disposition"] = "baseline_ignored"
        summary.would_baseline += 1
        if not commit:
            continue
        jobs.upsert_discovery({
            "tcg": "pokemon", "source_system": SOURCE_SYSTEM,
            "source_set_id": source_id, "source_set_name": provider_name,
            "status": BASELINE_STATUS, "current_step": BASELINE_STEP,
            "metadata_json": {
                "baseline_reason": BASELINE_REASON,
                "captured_by": "discover_new_pokemon_sets.py --baseline-current",
                "onboarded": False,
                "discovery_evidence": item_evidence,
            },
        })
        # Keep in-run state consistent so a duplicate provider name cannot double-write.
        job_ids.add(source_id)
        ignored_ids.add(source_id)
        known_ids.add(source_id)
        summary.baselined += 1
    return {
        **asdict(summary),
        "dispositions": _disposition_counts(evidence),
        "evidence": evidence,
    }
