"""Human-only consistency audit and freeze helpers for fresh D3 gold."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS

PARTITION = "D3_BLIND_REVIEW"
REVIEW_QUEUE = OUT / "ebay_d3_blind_review_queue.csv"
FROZEN_CAPTURE = OUT / "ebay_d3_fresh_blind_manifest.json"
AUDIT_HISTORY = OUT / "ebay_d3_fresh_gold_audit_history.jsonl"
GOLD_MANIFEST = OUT / "ebay_d3_fresh_human_gold_manifest.json"
EDGE_LABELS = frozenset({
    "RELATED_BUT_WRONG_VARIANT", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY",
    "WRONG_SET", "WRONG_LANGUAGE",
})
TAXONOMY_VERSION = "ebay_d3_fresh_human_gold_taxonomy_v1"
GRADE_TEXT_RE = re.compile(
    r"\b(?:PSA|BGS|CGC|SGC|TAG|ACE)(?:\s*(?:[1-9](?:\.5)?|10))?\b|"
    r"\bgraded\b|\bslab(?:bed)?\b|\bgrade\s*(?:[1-9](?:\.5)?|10)\b|"
    r"\bcertification(?: number)?\b", re.I,
)
GRADE_ASPECT_KEYS = frozenset({
    "grader", "grading company", "professional grader", "grade", "card grade",
    "certification number", "certification", "graded",
})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aspects(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, str):
        try: value = json.loads(value)
        except (json.JSONDecodeError, TypeError): return []
    result = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping): continue
            key = item.get("name") or item.get("localizedName") or item.get("key") or ""
            values = item.get("values") or item.get("localizedValues") or item.get("value") or []
            if not isinstance(values, list): values = [values]
            result.extend((str(key), str(entry)) for entry in values)
    elif isinstance(value, Mapping):
        for key, values in value.items():
            if not isinstance(values, list): values = [values]
            result.extend((str(key), str(entry)) for entry in values)
    return result


def has_human_visible_graded_evidence(row: Mapping[str, Any]) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("listing_title", "subtitle", "condition", "category_id"))
    if GRADE_TEXT_RE.search(text): return True
    if str(row.get("condition_id") or "") == "2750" or str(row.get("condition") or "").lower() in {"graded", "bewertet"}: return True
    for key, value in _aspects(row.get("localized_aspects_json")):
        if key.strip().lower() in GRADE_ASPECT_KEYS and value.strip().lower() not in {"", "no", "none", "not graded", "ungraded", "false", "0"}:
            return True
    return False


def build_audit_queue(rows: Iterable[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for raw in rows:
        row = dict(raw); row_id = str(row["benchmark_row_id"]); label = str(labels[row_id]["label"])
        reason = f"EDGE_IDENTITY_LABEL:{label}" if label in EDGE_LABELS else None
        if label == "GRADED" and not has_human_visible_graded_evidence(row):
            reason = "IMAGE_ONLY_GRADED_CANDIDATE"
        if reason:
            row["current_human_label"] = label; row["human_only_audit_reason"] = reason; queue.append(row)
    return queue


def read_audit_history(path: Path = AUDIT_HISTORY) -> list[dict[str, Any]]:
    if not path.exists(): return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try: event = json.loads(line)
            except (json.JSONDecodeError, TypeError): continue
            if isinstance(event, dict):
                event = dict(event); event["_event_id"] = str(event.get("event_id") or f"legacy:{line_number}"); events.append(event)
    return events


def applicable_decisions(events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str]) -> list[dict[str, Any]]:
    valid_ids = set(row_ids); decisions = []; undone = set()
    for raw in events:
        event = dict(raw)
        if event.get("partition") != PARTITION or event.get("reviewer_id") != reviewer: continue
        event_id = str(event.get("_event_id") or event.get("event_id") or "")
        if event.get("action") == "audit_undo":
            target = str(event.get("reverses_event_id") or "")
            if any(item["_event_id"] == target for item in decisions): undone.add(target)
            continue
        if (str(event.get("row_id", "")) in valid_ids
                and event.get("action") in {"audit_keep", "audit_replace"}
                and event.get("original_label") in LABELS
                and (event.get("action") == "audit_keep" or event.get("replacement_label") in LABELS)):
            event["_event_id"] = event_id; decisions.append(event)
    return [event for event in decisions if event["_event_id"] not in undone]


def reconstruct_audit_state(events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str]) -> dict[str, Any]:
    ids = set(row_ids); actions = applicable_decisions(events, reviewer, ids)
    decisions = {str(event["row_id"]): event for event in actions}
    return {"decisions": decisions, "unreviewed": ids - set(decisions), "actions": actions}


def build_undo(events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str]) -> dict[str, str] | None:
    actions = applicable_decisions(events, reviewer, row_ids)
    if not actions: return None
    target = actions[-1]
    return {"partition":PARTITION, "reviewer_id":reviewer, "row_id":str(target["row_id"]),
            "action":"audit_undo", "reverses_event_id":str(target["_event_id"]),
            "reverses_action":str(target["action"])}


def append_audit_event(event: Mapping[str, Any], path: Path = AUDIT_HISTORY) -> dict[str, Any]:
    if path == AUDIT_HISTORY and GOLD_MANIFEST.exists(): raise PermissionError("fresh D3 human gold is frozen")
    stored = {key:value for key,value in dict(event).items() if not key.startswith("_")}
    stored.setdefault("event_id", str(uuid.uuid4())); stored["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n")
    return stored


def effective_labels(base: Mapping[str, Mapping[str, Any]], audit_state: Mapping[str, Any]) -> dict[str, str]:
    labels = {row_id:str(event["label"]) for row_id,event in base.items()}
    for row_id,event in audit_state["decisions"].items():
        if event["action"] == "audit_replace": labels[row_id] = str(event["replacement_label"])
    return labels


def effective_gold_fingerprint(labels: Mapping[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{row_id}:{labels[row_id]}" for row_id in sorted(labels)).encode()).hexdigest()


def summary(base: Mapping[str, Mapping[str, Any]], state: Mapping[str, Any], total: int) -> dict[str, Any]:
    labels = effective_labels(base, state); changed = sum(event["action"] == "audit_replace" and event["replacement_label"] != event["original_label"] for event in state["decisions"].values())
    return {"effective_count":len(labels), "label_breakdown":dict(sorted(Counter(labels.values()).items())),
            "audit_row_count":total, "audit_reviewed_count":len(state["decisions"]),
            "audit_remaining_count":total-len(state["decisions"]), "changed_label_count":changed}


def freeze_gold(rows: list[Mapping[str, Any]], base: Mapping[str, Mapping[str, Any]], state: Mapping[str, Any], reviewer: str) -> dict[str, Any]:
    capture = json.loads(FROZEN_CAPTURE.read_text(encoding="utf-8"))
    if sha256_file(REVIEW_QUEUE) != capture["review_queue_fingerprint"]: raise RuntimeError("REVIEW_QUEUE_FINGERPRINT_MISMATCH")
    if len(base) != 704 or state["unreviewed"]: raise RuntimeError("D3_FRESH_GOLD_AUDIT_INCOMPLETE")
    labels = effective_labels(base, state)
    image_only = sum(row["human_only_audit_reason"] == "IMAGE_ONLY_GRADED_CANDIDATE" for row in build_audit_queue(rows, base))
    manifest = {"version":"ebay_d3_fresh_human_gold_manifest_v1", "effective_row_count":len(labels),
                "label_breakdown":dict(sorted(Counter(labels.values()).items())),
                "original_review_queue_fingerprint":capture["review_queue_fingerprint"],
                "review_history_fingerprint":sha256_file(OUT/"ebay_gold_review_history.jsonl"),
                "audit_history_fingerprint":sha256_file(AUDIT_HISTORY),
                "effective_human_gold_fingerprint":effective_gold_fingerprint(labels),
                "reviewer_id":reviewer, "taxonomy_version":TAXONOMY_VERSION,
                "audit_cohort_size":len(state["decisions"]), "image_only_graded_candidate_count":image_only,
                "matcher_predictions_consulted":False}
    GOLD_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
