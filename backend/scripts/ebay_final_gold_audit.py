"""Matcher-blind, append-only consistency audit for Final Blind human gold."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.prepare_ebay_d2h_benchmark import LABELS

AUDIT_HISTORY = OUT / "ebay_final_blind_gold_audit_history_v1.jsonl"
GOLD_MANIFEST = OUT / "ebay_final_blind_gold_manifest_v1.json"
AUDIT_LABELS = frozenset({
    "RELATED_BUT_WRONG_VARIANT", "AMBIGUOUS", "LOT_OR_BUNDLE",
    "SEALED_OR_ACCESSORY",
})
NOTE_TERMS = frozenset({
    "identity", "variant", "printing", "parallel", "finish", "stamp",
    "accessory", "holder", "case", "multi-selection", "choose", "pick",
    "bundle", "lot",
})
TAXONOMY_VERSION = "ebay_final_blind_gold_taxonomy_v1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_audit_history(path: Path = AUDIT_HISTORY) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(event, dict):
                event = dict(event)
                event["_event_id"] = str(event.get("event_id") or f"legacy:{line_number}")
                events.append(event)
    return events


def relevant_note_row_ids(
    review_events: Iterable[Mapping[str, Any]], reviewer: str,
) -> set[str]:
    result = set()
    for event in review_events:
        if (event.get("partition") != "FINAL_BLIND_TEST"
                or event.get("reviewer_id") != reviewer
                or event.get("action") != "note"):
            continue
        note = str(event.get("note", "")).lower()
        if any(term in note for term in NOTE_TERMS):
            result.add(str(event.get("row_id", "")))
    return result


def build_audit_queue(
    rows: Iterable[Mapping[str, Any]], labels: Mapping[str, Mapping[str, Any]],
    review_events: Iterable[Mapping[str, Any]], reviewer: str,
) -> list[dict[str, Any]]:
    note_ids = relevant_note_row_ids(review_events, reviewer)
    queue = []
    for raw in rows:
        row = dict(raw)
        row_id = str(row["benchmark_row_id"])
        event = labels.get(row_id)
        if event and (event.get("label") in AUDIT_LABELS or row_id in note_ids):
            row["current_human_label"] = str(event["label"])
            queue.append(row)
    return queue


def applicable_audit_decisions(
    events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str],
) -> list[dict[str, Any]]:
    valid_ids = set(row_ids)
    decisions: list[dict[str, Any]] = []
    undone: set[str] = set()
    for raw in events:
        event = dict(raw)
        if event.get("partition") != "FINAL_BLIND_TEST" or event.get("reviewer_id") != reviewer:
            continue
        event_id = str(event.get("_event_id") or event.get("event_id") or "")
        if event.get("action") == "audit_undo":
            target = str(event.get("reverses_event_id") or "")
            if any(item["_event_id"] == target for item in decisions):
                undone.add(target)
            continue
        valid = (
            str(event.get("row_id", "")) in valid_ids
            and event.get("action") in {"audit_keep", "audit_replace"}
            and event.get("original_label") in LABELS
            and (event.get("action") == "audit_keep" or event.get("replacement_label") in LABELS)
        )
        if valid:
            event["_event_id"] = event_id
            decisions.append(event)
    return [event for event in decisions if event["_event_id"] not in undone]


def reconstruct_audit_state(
    events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str],
) -> dict[str, Any]:
    ids = set(row_ids)
    decisions = applicable_audit_decisions(events, reviewer, ids)
    latest = {str(event["row_id"]): event for event in decisions}
    return {"decisions": latest, "unreviewed": ids - set(latest), "actions": decisions}


def build_audit_undo(
    events: Iterable[Mapping[str, Any]], reviewer: str, row_ids: Iterable[str],
) -> dict[str, str] | None:
    actions = applicable_audit_decisions(events, reviewer, row_ids)
    if not actions:
        return None
    target = actions[-1]
    return {
        "partition": "FINAL_BLIND_TEST", "reviewer_id": reviewer,
        "row_id": str(target["row_id"]), "action": "audit_undo",
        "reverses_event_id": str(target["_event_id"]),
        "reverses_action": str(target["action"]),
    }


def append_audit_event(event: Mapping[str, Any], path: Path = AUDIT_HISTORY) -> dict[str, Any]:
    if path == AUDIT_HISTORY and GOLD_MANIFEST.exists():
        raise PermissionError("Final Blind gold is frozen")
    stored = {key: value for key, value in dict(event).items() if not key.startswith("_")}
    stored.setdefault("event_id", str(uuid.uuid4()))
    stored["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n")
    return stored


def effective_labels(
    base_labels: Mapping[str, Mapping[str, Any]], audit_state: Mapping[str, Any],
) -> dict[str, str]:
    result = {row_id: str(event["label"]) for row_id, event in base_labels.items()}
    for row_id, decision in audit_state["decisions"].items():
        if decision["action"] == "audit_replace":
            result[row_id] = str(decision["replacement_label"])
    return result


def effective_gold_fingerprint(labels: Mapping[str, str]) -> str:
    material = "\n".join(f"{row_id}:{labels[row_id]}" for row_id in sorted(labels))
    return hashlib.sha256(material.encode()).hexdigest()


def audit_summary(
    base_labels: Mapping[str, Mapping[str, Any]], audit_state: Mapping[str, Any],
    audit_total: int,
) -> dict[str, Any]:
    labels = effective_labels(base_labels, audit_state)
    changed = sum(e["action"] == "audit_replace" for e in audit_state["decisions"].values())
    reviewed = len(audit_state["decisions"])
    return {
        "effective_count": len(labels),
        "label_breakdown": dict(sorted(Counter(labels.values()).items())),
        "changed_row_count": changed,
        "unchanged_row_count": reviewed - changed,
        "audit_row_count": audit_total,
        "audit_reviewed_count": reviewed,
        "audit_remaining_count": audit_total - reviewed,
    }


def freeze_gold(
    rows: list[Mapping[str, Any]], base_labels: Mapping[str, Mapping[str, Any]],
    audit_state: Mapping[str, Any], reviewer: str,
    review_history_path: Path, audit_history_path: Path = AUDIT_HISTORY,
    output_path: Path = GOLD_MANIFEST,
) -> dict[str, Any]:
    if len(base_labels) != len(rows):
        raise ValueError("Final Blind human labels are incomplete")
    if audit_state["unreviewed"]:
        raise ValueError("Final Blind gold audit is incomplete")
    labels = effective_labels(base_labels, audit_state)
    manifest = {
        "version": "ebay_final_blind_gold_manifest_v1",
        "effective_row_count": len(labels),
        "label_counts": dict(sorted(Counter(labels.values()).items())),
        "ambiguous_count": sum(label == "AMBIGUOUS" for label in labels.values()),
        "partition_fingerprint": sha256_file(OUT / "ebay_gold_final_blind.csv"),
        "review_history_fingerprint": sha256_file(review_history_path),
        "audit_history_fingerprint": sha256_file(audit_history_path),
        "effective_gold_fingerprint": effective_gold_fingerprint(labels),
        "reviewer_id": reviewer,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
