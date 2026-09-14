"""Local, blinded, append-only human review server for the D3-v4 fresh blind
cohort (backend/artifacts/index_fair_value/ebay_d3_v4_fresh_blind_queue.csv).

This module NEVER imports ebay_d3_matcher_v4 (or v3/v2/v1) and never computes
or displays any matcher-derived value. It is a dedicated V4 tool, separate
from the older ebay_gold_review_server.py, which is hard-wired to the D2/D3
gold partitions and does not know about this cohort.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/index_fair_value"
QUEUE_PATH = OUT / "ebay_d3_v4_fresh_blind_queue.csv"
MANIFEST_PATH = OUT / "ebay_d3_v4_fresh_blind_manifest.json"
HISTORY_PATH = OUT / "ebay_d3_v4_fresh_blind_review_history.jsonl"
CORRECTION_HISTORY_PATH = OUT / "ebay_d3_v4_fresh_blind_correction_history.jsonl"

CORRECTION_ORDER_SEED = 1337  # fixed, recorded -- review ORDER only, never selection

CORRECTION_DECISIONS = (
    "KEEP_YES", "CHANGE_TO_NO", "UNCERTAIN",
    # Extended decisions for --review-existing (E2.1E), which walks ALL 420
    # rows (not just former-YES ones) and allows changing to any primary.
    "KEEP_CURRENT", "CHANGE_TO_YES", "CHANGE_TO_UNCERTAIN",
)

REVIEWER_PROTOCOL = "SINGLE_REVIEWER_BLIND"
EXPECTED_ROW_COUNT = 420

# The exact enum strings the review UI stores. certify_ebay_d3_v4_fresh_blind.py's
# _human_error_class() accepts these values (verified/aligned, not a new schema).
LABEL_SCHEMA: dict[str, list[str]] = {
    "exact_match_yes_no_uncertain": ["YES", "NO", "UNCERTAIN"],
    "single_card_or_lot": ["SINGLE_CARD", "LOT_OR_BUNDLE", "UNCERTAIN"],
    "raw_or_graded": ["RAW", "GRADED", "UNCERTAIN"],
    "card_or_sealed_nonshcard": ["CARD", "SEALED_OR_NON_CARD", "UNCERTAIN"],
    "collector_number_consistency": ["CONSISTENT", "INCONSISTENT", "NOT_VISIBLE", "UNCERTAIN"],
    "set_consistency": ["CONSISTENT", "INCONSISTENT", "NOT_VISIBLE", "UNCERTAIN"],
    "language": ["ENGLISH", "NON_ENGLISH", "NOT_VISIBLE", "UNCERTAIN"],
    "variant_treatment": ["CONSISTENT", "INCONSISTENT", "NOT_VISIBLE", "UNCERTAIN"],
}
LABEL_FIELDS = tuple(LABEL_SCHEMA)

# The 4 fields certify_ebay_d3_v4_fresh_blind.py's REQUIRED_LABEL_FIELDS
# actually needs (beyond reviewer_id/label_timestamp, tracked separately).
# collector_number_consistency/set_consistency/language/variant_treatment are
# genuinely optional -- the certifier tolerates them blank.
STRUCTURAL_REQUIRED_FIELDS = ("exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard")
ADVANCED_OPTIONAL_FIELDS = ("collector_number_consistency", "set_consistency", "language", "variant_treatment")

PRIMARY_CHOICES = ("YES", "NO", "UNCERTAIN")

# One required reason when the reviewer answers NO. Each maps deterministically
# onto the existing certification taxonomy fields -- never invented, never
# requiring the reviewer to redundantly re-select a field the reason already implies.
NO_REASONS: dict[str, dict[str, str]] = {
    "WRONG_CARD": {},
    "WRONG_CARD_NUMBER": {"collector_number_consistency": "INCONSISTENT"},
    "WRONG_SET": {"set_consistency": "INCONSISTENT"},
    "WRONG_VARIANT_OR_TREATMENT": {"variant_treatment": "INCONSISTENT"},
    "GRADED": {"raw_or_graded": "GRADED"},
    "LOT_OR_BUNDLE": {"single_card_or_lot": "LOT_OR_BUNDLE"},
    "SEALED_OR_NON_CARD": {"card_or_sealed_nonshcard": "SEALED_OR_NON_CARD"},
    "WRONG_LANGUAGE": {"language": "NON_ENGLISH"},
    "OTHER": {},
}

# Fields never allowed to appear in the queue file -- if any of these exist,
# something has (incorrectly) leaked matcher output into the blind cohort.
FORBIDDEN_MATCHER_COLUMNS = frozenset({
    "matcher_version", "matcher_state", "identity_state", "match_status", "confidence",
    "confidence_tier", "score", "accepted", "rejection_reason", "v3_state", "v4_state", "reason",
})

HUMAN_VISIBLE_FIELDS = (
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "listing_title", "condition", "buying_options_json", "image_url", "item_url", "seller_id",
)


class ReviewFrozen(RuntimeError):
    pass


class FreezeRefused(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# --------------------------------------------------------------------------
# Queue loading (read-only; the CSV is not rewritten until --freeze)
# --------------------------------------------------------------------------


def load_queue_rows() -> list[dict[str, Any]]:
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def assert_no_forbidden_columns(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    present = FORBIDDEN_MATCHER_COLUMNS & set(rows[0].keys())
    if present:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_MATCHER_COLUMNS_PRESENT", str(sorted(present)))


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


# --------------------------------------------------------------------------
# Append-only review history + resumable reconstruction
# --------------------------------------------------------------------------


def _read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def is_frozen() -> bool:
    """True once the FIRST-PASS (initial) review history is closed -- i.e.
    the cohort has been materialized with human labels at least once. This
    gate is unaffected by the correction audit; it only ever closes the
    original review file to further first-pass writes.
    """
    return bool(_read_manifest().get("labels_frozen"))


def is_finally_frozen() -> bool:
    """True once the FINAL freeze (post-correction) has happened. Once true,
    neither the first-pass history nor the correction history may be
    appended to again, and the correction audit may not be restarted.
    """
    return "final_human_freeze" in _read_manifest()


def read_history(path: Optional[Path] = None, actions: frozenset = frozenset({"label", "undo"})) -> list[dict[str, Any]]:
    path = path or HISTORY_PATH
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("action") in actions:
                events.append(event)
    return events


def _append(event: Mapping[str, Any], path: Path) -> dict[str, Any]:
    stored = dict(event)
    stored.setdefault("event_id", uuid.uuid4().hex)
    stored.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n")
    return stored


def append_event(event: Mapping[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    """Append to the first-pass review history. Refused once that pass is frozen."""
    path = path or HISTORY_PATH
    if is_frozen():
        raise ReviewFrozen("first-pass labels are frozen; no further review-history writes are permitted")
    return _append(event, path)


def append_correction_event(event: Mapping[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    """Append to the SEPARATE correction-audit history. Refused once the
    final freeze has happened, or before the first-pass freeze has happened
    (there is nothing to correct yet).
    """
    path = path or CORRECTION_HISTORY_PATH
    if not is_frozen():
        raise ReviewFrozen("the correction audit requires a completed first-pass freeze first")
    if is_finally_frozen():
        raise ReviewFrozen("final labels are frozen; no further correction-history writes are permitted")
    return _append(event, path)


def reconstruct_effective_labels(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Latest non-undone label event per benchmark_row_id. Undo never deletes
    history -- it appends an undo event referencing the target event_id.
    """
    by_row: dict[str, list[dict[str, Any]]] = {}
    undone_ids: set[str] = set()
    for event in events:
        if event["action"] == "label":
            by_row.setdefault(event["benchmark_row_id"], []).append(event)
        elif event["action"] == "undo":
            undone_ids.add(event.get("target_event_id"))
    effective: dict[str, dict[str, Any]] = {}
    for row_id, row_events in by_row.items():
        valid = [e for e in row_events if e["event_id"] not in undone_ids]
        if valid:
            effective[row_id] = valid[-1]
    return effective


def build_label_event_from_fields(row_id: str, reviewer_id: str, fields: Mapping[str, str], note: str = "") -> dict[str, Any]:
    """Low-level event builder taking a fully-specified field dict. Prefer
    `build_label_event()` for the normal YES/NO/UNCERTAIN review workflow --
    this stays available for direct/advanced overrides and tests.
    """
    return {
        "action": "label", "benchmark_row_id": row_id, "reviewer_id": reviewer_id,
        "fields": {k: str(fields.get(k, "")).strip().upper() for k in LABEL_FIELDS},
        "note": note,
    }


def derive_fields(primary: str, no_reason: Optional[str] = None, advanced: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Deterministic, non-inventing derivation of the full 8-field label
    schema from the single primary answer (+ one required reason if NO).

    YES  -> single_card_or_lot=SINGLE_CARD, raw_or_graded=RAW, card_or_sealed_nonshcard=CARD
    UNCERTAIN -> those three fields = UNCERTAIN (per spec)
    NO   -> same SINGLE_CARD/RAW/CARD defaults (a wrong card is still
            observably one raw single card, unless the reason says otherwise),
            overridden by the reason's specific structural implication.
    Advanced overrides (explicit reviewer observations from the collapsed
    "Advanced details" section) always win over any derived default.
    """
    primary = str(primary or "").strip().upper()
    if primary not in PRIMARY_CHOICES:
        raise ValueError(f"unknown primary answer: {primary!r}")
    fields: dict[str, str] = {f: "" for f in LABEL_FIELDS}
    fields["exact_match_yes_no_uncertain"] = primary
    if primary == "UNCERTAIN":
        fields["single_card_or_lot"] = "UNCERTAIN"
        fields["raw_or_graded"] = "UNCERTAIN"
        fields["card_or_sealed_nonshcard"] = "UNCERTAIN"
    else:
        fields["single_card_or_lot"] = "SINGLE_CARD"
        fields["raw_or_graded"] = "RAW"
        fields["card_or_sealed_nonshcard"] = "CARD"
        if primary == "NO":
            reason = str(no_reason or "").strip().upper()
            if reason not in NO_REASONS:
                raise ValueError(f"NO requires one of {sorted(NO_REASONS)}, got {no_reason!r}")
            fields.update(NO_REASONS[reason])
    for key, value in (advanced or {}).items():
        value = str(value or "").strip().upper()
        if value and key in ADVANCED_OPTIONAL_FIELDS:
            fields[key] = value
    return fields


def build_label_event(
    row_id: str, reviewer_id: str, primary: str, no_reason: Optional[str] = None,
    advanced: Optional[Mapping[str, str]] = None, note: str = "",
) -> dict[str, Any]:
    """The normal review-workflow event builder: one primary answer, one
    reason if NO, optional advanced overrides. Produces the exact same
    `fields` shape build_label_event_from_fields() would, so freeze/
    materialization and the certifier need no special-casing.
    """
    fields = derive_fields(primary, no_reason, advanced)
    event = build_label_event_from_fields(row_id, reviewer_id, fields, note)
    event["primary"] = str(primary).strip().upper()
    if primary.strip().upper() == "NO":
        event["no_reason"] = str(no_reason or "").strip().upper()
    return event


def build_undo_event(events: list[dict[str, Any]], row_id: str, reviewer_id: str) -> Optional[dict[str, Any]]:
    """Undo the latest non-undone label for a SPECIFIC row."""
    effective = reconstruct_effective_labels(events)
    target = effective.get(row_id)
    if target is None:
        return None
    return {"action": "undo", "benchmark_row_id": row_id, "reviewer_id": reviewer_id, "target_event_id": target["event_id"]}


def build_undo_last_label_event(events: list[dict[str, Any]], reviewer_id: str) -> Optional[dict[str, Any]]:
    """Undo the single most recently RECORDED label event across the WHOLE
    history, regardless of which row is currently on screen.

    This is the fix for the reported "Undo did not work reliably" bug: the
    UI's "Undo Previous" button previously sent the row_id of the row
    CURRENTLY on screen (the next, not-yet-reviewed row the page had already
    advanced to), not the row the reviewer actually just labeled -- so the
    undo silently targeted the wrong (usually unlabeled) row and did nothing.
    Undoing "the last thing I did" only ever makes sense in terms of global
    append order, never the currently displayed row.
    """
    undone_ids = {e.get("target_event_id") for e in events if e["action"] == "undo"}
    label_events = [e for e in events if e["action"] == "label" and e["event_id"] not in undone_ids]
    if not label_events:
        return None
    target = label_events[-1]
    return {
        "action": "undo", "benchmark_row_id": target["benchmark_row_id"], "reviewer_id": reviewer_id,
        "target_event_id": target["event_id"],
    }


def next_unreviewed_index(rows: list[dict[str, Any]], effective: Mapping[str, dict[str, Any]], after: int = -1) -> Optional[int]:
    n = len(rows)
    for offset in range(1, n + 1):
        i = (after + offset) % n
        if rows[i]["benchmark_row_id"] not in effective:
            return i
    return None


# --------------------------------------------------------------------------
# Correction audit -- second, human-only pass over current-YES rows.
#
# Uses a SEPARATE append-only history file. Never touches, rewrites, or
# deletes the first-pass ebay_d3_v4_fresh_blind_review_history.jsonl.
# --------------------------------------------------------------------------


def current_effective_primary_label(row: Mapping[str, Any]) -> str:
    """Reads the CURRENT first-pass effective label directly off the
    already-materialized queue CSV (this is only ever called after the
    first-pass freeze, at which point the CSV *is* the first-pass record).
    """
    return str(row.get("exact_match_yes_no_uncertain", "")).strip().upper()


def build_correction_queue(rows: list[dict[str, Any]], seed: int = CORRECTION_ORDER_SEED) -> list[str]:
    """ALL rows whose current effective first-pass label is YES -- never
    selected or filtered by any matcher output. Order is a deterministic
    shuffle from a fixed, recorded seed (selection itself is untouched by
    the shuffle: it is still exactly the set of current-YES rows).
    """
    import random

    yes_ids = sorted(row["benchmark_row_id"] for row in rows if current_effective_primary_label(row) == "YES")
    rng = random.Random(seed)
    order = list(yes_ids)
    rng.shuffle(order)
    return order


def reconstruct_correction_state(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_row: dict[str, list[dict[str, Any]]] = {}
    undone_ids: set[str] = set()
    for event in events:
        if event["action"] == "correction":
            by_row.setdefault(event["benchmark_row_id"], []).append(event)
        elif event["action"] == "undo_correction":
            undone_ids.add(event.get("target_event_id"))
    effective: dict[str, dict[str, Any]] = {}
    for row_id, row_events in by_row.items():
        valid = [e for e in row_events if e["event_id"] not in undone_ids]
        if valid:
            effective[row_id] = valid[-1]
    return effective


def build_correction_event(
    row_id: str, reviewer_id: str, decision: str, no_reason: Optional[str] = None, note: str = "",
    current_fields: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """`current_fields` is required only for decision="KEEP_CURRENT" (used by
    --review-existing to re-affirm a row's current effective label -- whatever
    it currently is, including a NO reason -- without inventing a new
    observation). All other decisions derive fields exactly as the primary
    review workflow does.
    """
    decision = str(decision or "").strip().upper()
    if decision not in CORRECTION_DECISIONS:
        raise ValueError(f"decision must be one of {CORRECTION_DECISIONS}, got {decision!r}")
    if decision in ("KEEP_YES", "CHANGE_TO_YES"):
        fields = derive_fields("YES")
    elif decision in ("UNCERTAIN", "CHANGE_TO_UNCERTAIN"):
        fields = derive_fields("UNCERTAIN")
    elif decision == "CHANGE_TO_NO":
        fields = derive_fields("NO", no_reason)
    else:  # KEEP_CURRENT
        if current_fields is None:
            raise ValueError("KEEP_CURRENT requires current_fields")
        fields = {k: str(current_fields.get(k, "")).strip().upper() for k in LABEL_FIELDS}
    event: dict[str, Any] = {
        "action": "correction", "benchmark_row_id": row_id, "reviewer_id": reviewer_id,
        "decision": decision, "fields": fields, "note": note,
    }
    if decision == "CHANGE_TO_NO":
        event["no_reason"] = str(no_reason or "").strip().upper()
    return event


def build_undo_correction_event(events: list[dict[str, Any]], row_id: str, reviewer_id: str) -> Optional[dict[str, Any]]:
    effective = reconstruct_correction_state(events)
    target = effective.get(row_id)
    if target is None:
        return None
    return {"action": "undo_correction", "benchmark_row_id": row_id, "reviewer_id": reviewer_id, "target_event_id": target["event_id"]}


def build_undo_last_correction_event(events: list[dict[str, Any]], reviewer_id: str) -> Optional[dict[str, Any]]:
    undone_ids = {e.get("target_event_id") for e in events if e["action"] == "undo_correction"}
    correction_events = [e for e in events if e["action"] == "correction" and e["event_id"] not in undone_ids]
    if not correction_events:
        return None
    target = correction_events[-1]
    return {
        "action": "undo_correction", "benchmark_row_id": target["benchmark_row_id"], "reviewer_id": reviewer_id,
        "target_event_id": target["event_id"],
    }


def correction_summary(reviewer_id: str) -> dict[str, Any]:
    rows = load_queue_rows()
    queue = build_correction_queue(rows)
    effective = reconstruct_correction_state(read_history(CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"})))
    decision_counts: dict[str, int] = {}
    for event in effective.values():
        decision_counts[event["decision"]] = decision_counts.get(event["decision"], 0) + 1
    return {
        "yes_rows_total": len(queue), "corrected_rows": len(effective),
        "remaining_rows": len(queue) - len(effective), "reviewer_id": reviewer_id,
        "decision_counts": decision_counts, "correction_order_seed": CORRECTION_ORDER_SEED,
        "finally_frozen": is_finally_frozen(),
    }


def next_uncorrected_index(queue: list[str], effective: Mapping[str, dict[str, Any]], after: int = -1) -> Optional[int]:
    n = len(queue)
    if n == 0:
        return None
    for offset in range(1, n + 1):
        i = (after + offset) % n
        if queue[i] not in effective:
            return i
    return None


def current_effective_fields(row: Mapping[str, Any], corrections: Mapping[str, dict[str, Any]]) -> dict[str, str]:
    """The CURRENT effective label fields for any row: a correction-history
    override if one exists, otherwise whatever is already materialized in
    the (first-pass-frozen) queue CSV. Never reads or infers from a matcher.
    """
    correction = corrections.get(row["benchmark_row_id"])
    if correction is not None:
        return dict(correction["fields"])
    return {f: row.get(f, "") for f in LABEL_FIELDS}


def _clamped_index(index: int, n: int) -> int:
    if n <= 0:
        return 0
    return max(0, min(n - 1, index))


def _position_of(ordered_ids: list[str], row_id: Optional[str]) -> Optional[int]:
    if row_id is None:
        return None
    try:
        return ordered_ids.index(row_id)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Summary (read-only; never touches the matcher)
# --------------------------------------------------------------------------


def summary(reviewer_id: str) -> dict[str, Any]:
    rows = load_queue_rows()
    effective = reconstruct_effective_labels(read_history())
    primary_counts: dict[str, int] = {}
    for event in effective.values():
        value = event["fields"].get("exact_match_yes_no_uncertain", "")
        primary_counts[value] = primary_counts.get(value, 0) + 1
    result = {
        "total_rows": len(rows),
        "reviewed_rows": len(effective),
        "remaining_rows": len(rows) - len(effective),
        "reviewer_id": reviewer_id,
        "primary_label_counts": primary_counts,
        "frozen": is_frozen(),
        "finally_frozen": is_finally_frozen(),
    }
    if is_frozen():
        result["correction_audit"] = correction_summary(reviewer_id)
    return result


# --------------------------------------------------------------------------
# Freeze
# --------------------------------------------------------------------------


def _row_is_complete(event: Optional[dict[str, Any]]) -> bool:
    """Matches certify_ebay_d3_v4_fresh_blind.py's REQUIRED_LABEL_FIELDS
    exactly: the 4 structural fields + reviewer_id + timestamp. The 4
    ADVANCED_OPTIONAL_FIELDS may legitimately stay blank -- the certifier
    tolerates that (they are its DETERMINABLE_WHEN_PRESENT_FIELDS, not
    required), and the simplified review UX never forces the reviewer to
    fill them for a normal row.
    """
    if event is None:
        return False
    fields = event.get("fields", {})
    return (
        all(str(fields.get(f, "")).strip() for f in STRUCTURAL_REQUIRED_FIELDS)
        and bool(event.get("reviewer_id")) and bool(event.get("timestamp"))
    )


def _canonical_label_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Delegates to certify_ebay_d3_v4_fresh_blind.compute_label_fingerprint --
    THE single canonical implementation. Never reimplemented here.
    """
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import compute_label_fingerprint

    return compute_label_fingerprint(rows)


def _materialize(rows: list[dict[str, Any]], fields_by_row: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    materialized = []
    for row in rows:
        event = fields_by_row[row["benchmark_row_id"]]
        merged = dict(row)
        merged.update(event["fields"])
        merged["reviewer_id"] = event["reviewer_id"]
        merged["label_timestamp"] = event["timestamp"]
        merged["review_note"] = event.get("note", "")
        merged["adjudicated_result"] = ""  # never fabricated -- single reviewer only
        materialized.append(merged)
    return materialized


def _write_queue(rows: list[dict[str, Any]], materialized_rows: list[dict[str, Any]]) -> None:
    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(materialized_rows)


def freeze_initial(reviewer_id: str) -> dict[str, Any]:
    """The original single-pass freeze. Refused if already run."""
    if is_frozen():
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_ALREADY_FROZEN")

    rows = load_queue_rows()
    if len(rows) != EXPECTED_ROW_COUNT:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_ROW_COUNT_MISMATCH", f"expected {EXPECTED_ROW_COUNT}, found {len(rows)}")
    assert_no_forbidden_columns(rows)

    if not MANIFEST_PATH.exists():
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_MANIFEST_MISSING")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded_fingerprint = manifest.get("cohort_fingerprint")
    recomputed_fingerprint = cohort_fingerprint(rows)
    if recorded_fingerprint != recomputed_fingerprint:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_COHORT_FINGERPRINT_MISMATCH",
                             f"recorded={recorded_fingerprint} recomputed={recomputed_fingerprint}")

    effective = reconstruct_effective_labels(read_history())
    incomplete = [r["benchmark_row_id"] for r in rows if not _row_is_complete(effective.get(r["benchmark_row_id"]))]
    if incomplete:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_INCOMPLETE_LABELS", f"{len(incomplete)} rows incomplete, e.g. {incomplete[:5]}")

    materialized_rows = _materialize(rows, effective)
    _write_queue(rows, materialized_rows)
    label_fingerprint = _canonical_label_fingerprint(materialized_rows)
    freeze_timestamp = datetime.now(timezone.utc).isoformat()

    manifest["labels_exist"] = True
    manifest["labels_frozen"] = True
    manifest["reviewer_protocol"] = REVIEWER_PROTOCOL
    manifest["reviewer_id"] = reviewer_id
    manifest["freeze_timestamp"] = freeze_timestamp
    manifest["label_fingerprint"] = label_fingerprint  # legacy key, retained for provenance only
    manifest["cohort_fingerprint"] = recorded_fingerprint  # explicitly preserved, unchanged
    manifest["initial_human_freeze"] = {
        "label_fingerprint": label_fingerprint, "freeze_timestamp": freeze_timestamp, "reviewer_id": reviewer_id,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "stage": "initial_human_freeze", "rows_materialized": len(materialized_rows),
        "label_fingerprint": label_fingerprint, "cohort_fingerprint": recorded_fingerprint,
        "reviewer_protocol": REVIEWER_PROTOCOL, "reviewer_id": reviewer_id,
    }


def freeze_final(reviewer_id: str) -> dict[str, Any]:
    """Incorporates the correction audit and produces the certification-ready
    final label state. Requires the initial freeze to have happened, the
    correction audit to be COMPLETE (every current-YES row has a decision),
    and refuses if a final freeze already happened.
    """
    if not is_frozen():
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_NO_INITIAL_FREEZE")
    if is_finally_frozen():
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_ALREADY_FINALLY_FROZEN")

    rows = load_queue_rows()
    if len(rows) != EXPECTED_ROW_COUNT:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_ROW_COUNT_MISMATCH", f"expected {EXPECTED_ROW_COUNT}, found {len(rows)}")
    assert_no_forbidden_columns(rows)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded_fingerprint = manifest.get("cohort_fingerprint")
    recomputed_fingerprint = cohort_fingerprint(rows)
    if recorded_fingerprint != recomputed_fingerprint:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_COHORT_FINGERPRINT_MISMATCH",
                             f"recorded={recorded_fingerprint} recomputed={recomputed_fingerprint}")

    queue = build_correction_queue(rows)
    correction_events = read_history(CORRECTION_HISTORY_PATH, actions=frozenset({"correction", "undo_correction"}))
    corrections = reconstruct_correction_state(correction_events)
    missing = [row_id for row_id in queue if row_id not in corrections]
    if missing:
        raise FreezeRefused("EBAY_D3_V4_REVIEW_BLOCKED_CORRECTION_AUDIT_INCOMPLETE",
                             f"{len(missing)} of {len(queue)} current-YES rows have no correction decision, e.g. {missing[:5]}")

    now = datetime.now(timezone.utc).isoformat()
    corrected_fields_by_row: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row["benchmark_row_id"]
        correction = corrections.get(row_id)
        if correction is None:
            # not a YES row -- carry the (already materialized) first-pass fields forward unchanged
            corrected_fields_by_row[row_id] = {
                "fields": {f: row.get(f, "") for f in LABEL_FIELDS},
                "reviewer_id": row.get("reviewer_id") or reviewer_id,
                "timestamp": row.get("label_timestamp") or now,
                "note": row.get("review_note", ""),
            }
        else:
            corrected_fields_by_row[row_id] = {
                "fields": correction["fields"], "reviewer_id": correction["reviewer_id"],
                "timestamp": correction["timestamp"], "note": correction.get("note", ""),
            }

    materialized_rows = _materialize(rows, corrected_fields_by_row)
    _write_queue(rows, materialized_rows)
    final_label_fingerprint = _canonical_label_fingerprint(materialized_rows)
    correction_history_fingerprint = hashlib.sha256(
        "\n".join(sorted(f"{e['event_id']}:{e['action']}" for e in correction_events)).encode()
    ).hexdigest()

    manifest.setdefault("initial_human_freeze", {
        "label_fingerprint": manifest.get("label_fingerprint"),
        "freeze_timestamp": manifest.get("freeze_timestamp"), "reviewer_id": manifest.get("reviewer_id"),
    })
    manifest["correction_audit"] = {
        "performed": True, "corrected_row_count": len(corrections), "yes_row_count": len(queue),
        "correction_order_seed": CORRECTION_ORDER_SEED, "correction_history_fingerprint": correction_history_fingerprint,
        "decision_counts": _decision_counts(corrections),
    }
    manifest["final_human_freeze"] = {
        "label_fingerprint": final_label_fingerprint, "freeze_timestamp": now, "reviewer_id": reviewer_id,
    }
    manifest["final_label_fingerprint"] = final_label_fingerprint
    manifest["reviewer_protocol"] = REVIEWER_PROTOCOL
    manifest["matcher_predictions_consulted"] = False
    manifest["certification_not_yet_run"] = True
    manifest["cohort_fingerprint"] = recorded_fingerprint  # unchanged, always
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "stage": "final_human_freeze", "rows_materialized": len(materialized_rows),
        "final_label_fingerprint": final_label_fingerprint, "cohort_fingerprint": recorded_fingerprint,
        "correction_history_fingerprint": correction_history_fingerprint, "corrected_row_count": len(corrections),
        "reviewer_protocol": REVIEWER_PROTOCOL, "reviewer_id": reviewer_id,
    }


def _decision_counts(corrections: Mapping[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in corrections.values():
        counts[event["decision"]] = counts.get(event["decision"], 0) + 1
    return counts


def freeze(reviewer_id: str) -> dict[str, Any]:
    """Auto-selects the correct stage: initial freeze if none has happened
    yet, otherwise the final (post-correction) freeze.
    """
    if not is_frozen():
        return freeze_initial(reviewer_id)
    return freeze_final(reviewer_id)


def run_precondition_check_only() -> dict[str, Any]:
    """Reuses certify_ebay_d3_v4_fresh_blind.check_preconditions(), which
    never classifies a single listing -- it only hashes/compares fingerprints
    and inspects label completeness. No matcher prediction is computed.
    """
    from backend.scripts.certify_ebay_d3_v4_fresh_blind import check_preconditions

    return check_preconditions()


# --------------------------------------------------------------------------
# HTML rendering -- human-observable fields ONLY
# --------------------------------------------------------------------------


NO_REASON_SHORTCUTS = {str(i + 1): reason for i, reason in enumerate(NO_REASONS)}


def _advanced_select(field: str) -> str:
    options = LABEL_SCHEMA[field]
    opts = "".join(f'<option value="{o}">{html.escape(o)}</option>' for o in options)
    return f'<label>{html.escape(field)}<br><select name="{field}"><option value="">(leave derived)</option>{opts}</select></label>'


def page(row: Mapping[str, Any], reviewed: int, total: int) -> str:
    e = html.escape
    reason_buttons = "".join(
        f'<button type="button" class="reason" data-reason="{reason}">{i + 1}: {reason.replace("_", " ")}</button>'
        for i, reason in enumerate(NO_REASONS)
    )
    advanced_controls = "".join(f"{_advanced_select(f)}<br>" for f in ADVANCED_OPTIONAL_FIELDS)
    return f"""<!doctype html><meta charset="utf-8"><title>D3-v4 Fresh Blind Review</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}img{{max-height:360px;max-width:480px}}
label{{display:block;margin:6px 0}}button{{padding:10px 16px;margin:4px 6px 4px 0;font-size:16px}}
.cols{{display:flex;gap:30px}}.primary{{padding:18px 28px;font-size:20px}}
#yesBtn{{background:#d7f5d0}}#noBtn{{background:#f5d0d0}}#uncertainBtn{{background:#f0e6c0}}
#reasonBar{{display:none;margin-top:10px}}details{{margin-top:14px}}</style>
<h1>D3-v4 fresh blind review &mdash; SINGLE_REVIEWER_BLIND</h1>
<p>{reviewed} / {total} reviewed &middot; {total - reviewed} remaining</p>
<div class="cols">
<section><h2>Target instrument</h2>
<p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>
#{e(str(row['target_card_number']))}<br>Treatment: {e(str(row['target_treatment']))}</p></section>
<section><h2>eBay listing</h2>
<p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>
Buying options: {e(str(row.get('buying_options_json') or ''))}<br>Seller: {e(str(row.get('seller_id') or ''))}</p>
<img src="{e(str(row.get('image_url') or ''))}"><p><a href="{e(str(row.get('item_url') or ''))}" target="_blank">Open listing on eBay</a></p></section>
</div>
<p><b>Is this one raw single-card listing for the exact target instrument?</b></p>
<p>
<button type="button" class="primary" id="yesBtn">YES (Y)</button>
<button type="button" class="primary" id="noBtn">NO (N)</button>
<button type="button" class="primary" id="uncertainBtn">UNCERTAIN (U)</button>
</p>
<div id="reasonBar"><b>Why is this NOT the target?</b><br>{reason_buttons}</div>
<details><summary>Advanced details (optional)</summary>{advanced_controls}
<label>Note (optional)<br><input type="text" id="note" style="width:100%"></label></details>
<p><button type="button" id="undo">Undo Previous</button></p>
<script>
const rowId={json.dumps(row['benchmark_row_id'])};
function advancedFields(){{const out={{}};document.querySelectorAll('#detailsForm select,details select').forEach(s=>{{if(s.value)out[s.name]=s.value;}});return out;}}
function submitLabel(primary,reason){{
  const body={{row_id:rowId,primary,note:(document.getElementById('note')||{{}}).value||''}};
  if(reason)body.no_reason=reason;
  const advanced=advancedFields();for(const k in advanced)body['advanced_'+k]=advanced[k];
  fetch('/label',{{method:'POST',body:new URLSearchParams(body)}}).then(()=>location.reload());
}}
yesBtn.onclick=()=>submitLabel('YES');
uncertainBtn.onclick=()=>submitLabel('UNCERTAIN');
noBtn.onclick=()=>{{document.getElementById('reasonBar').style.display='block';}};
document.querySelectorAll('.reason').forEach(b=>b.onclick=()=>submitLabel('NO',b.dataset.reason));
undo.onclick=()=>fetch('/undo',{{method:'POST',body:new URLSearchParams({{}})}}).then(()=>location.reload());
const reasonKeys={json.dumps(NO_REASON_SHORTCUTS)};
onkeydown=function(ev){{
  const k=ev.key.toLowerCase();
  if(document.getElementById('reasonBar').style.display==='block' && reasonKeys[ev.key]){{submitLabel('NO',reasonKeys[ev.key]);return;}}
  if(k==='y')submitLabel('YES');else if(k==='u')submitLabel('UNCERTAIN');else if(k==='n')noBtn.click();
}};
</script>"""


def _current_decision_line(current: Optional[dict[str, Any]]) -> str:
    if current is None:
        return "No decision recorded yet for this row."
    label = current["fields"].get("exact_match_yes_no_uncertain", "")
    reason = current.get("no_reason")
    return f"Current decision: <b>{html.escape(str(current['decision']))}</b> (effective label: {html.escape(str(label))}{f', reason: {html.escape(str(reason))}' if reason else ''})"


def correction_page(row: Mapping[str, Any], reviewed: int, total: int, current: Optional[dict[str, Any]] = None) -> str:
    e = html.escape
    reason_buttons = "".join(
        f'<button type="button" class="reason" data-reason="{reason}">{i + 1}: {reason.replace("_", " ")}</button>'
        for i, reason in enumerate(NO_REASONS)
    )
    return f"""<!doctype html><meta charset="utf-8"><title>D3-v4 YES-Label Correction Audit</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}img{{max-height:360px;max-width:480px}}
button{{padding:10px 16px;margin:4px 6px 4px 0;font-size:16px}}.cols{{display:flex;gap:30px}}
.primary{{padding:18px 28px;font-size:20px}}#keepBtn{{background:#d7f5d0}}#changeBtn{{background:#f5d0d0}}#uncertainBtn2{{background:#f0e6c0}}
#reasonBar2{{display:none;margin-top:10px}}</style>
<h1>D3-v4 YES-label correction audit &mdash; SINGLE_REVIEWER_BLIND</h1>
<p>This row's first-pass human label was <b>YES</b>. Re-examine only the human-visible evidence below.</p>
<p>{reviewed} / {total} corrected &middot; {total - reviewed} remaining</p>
<p>{_current_decision_line(current)}</p>
<div class="cols">
<section><h2>Target instrument</h2>
<p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>
#{e(str(row['target_card_number']))}<br>Treatment: {e(str(row['target_treatment']))}</p></section>
<section><h2>eBay listing</h2>
<p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>
Buying options: {e(str(row.get('buying_options_json') or ''))}<br>Seller: {e(str(row.get('seller_id') or ''))}</p>
<img src="{e(str(row.get('image_url') or ''))}"><p><a href="{e(str(row.get('item_url') or ''))}" target="_blank">Open listing on eBay</a></p></section>
</div>
<p>
<button type="button" class="primary" id="keepBtn">KEEP YES (K)</button>
<button type="button" class="primary" id="changeBtn">CHANGE TO NO (C)</button>
<button type="button" class="primary" id="uncertainBtn2">UNCERTAIN (U)</button>
</p>
<div id="reasonBar2"><b>Why is this NOT the target?</b><br>{reason_buttons}</div>
<p>
<button type="button" id="prevBtn">&larr; Previous (B)</button>
<button type="button" id="nextBtn">Next (N)</button>
<button type="button" id="undo2">Undo Last Action</button>
</p>
<script>
const rowId={json.dumps(row['benchmark_row_id'])};
function submitCorrection(decision,reason){{
  const body={{row_id:rowId,decision}};if(reason)body.no_reason=reason;
  fetch('/correction',{{method:'POST',body:new URLSearchParams(body)}}).then(()=>location.reload());
}}
keepBtn.onclick=()=>submitCorrection('KEEP_YES');
uncertainBtn2.onclick=()=>submitCorrection('UNCERTAIN');
changeBtn.onclick=()=>{{document.getElementById('reasonBar2').style.display='block';}};
document.querySelectorAll('.reason').forEach(b=>b.onclick=()=>submitCorrection('CHANGE_TO_NO',b.dataset.reason));
undo2.onclick=()=>fetch('/undo_correction',{{method:'POST',body:new URLSearchParams({{}})}}).then(()=>location.reload());
prevBtn.onclick=()=>fetch('/previous_correction',{{method:'POST'}}).then(()=>location.reload());
nextBtn.onclick=()=>fetch('/next_correction',{{method:'POST'}}).then(()=>location.reload());
const reasonKeys={json.dumps(NO_REASON_SHORTCUTS)};
onkeydown=function(ev){{
  const k=ev.key.toLowerCase();
  if(k==='b'){{prevBtn.click();return;}}
  if(document.getElementById('reasonBar2').style.display==='block' && reasonKeys[ev.key]){{submitCorrection('CHANGE_TO_NO',reasonKeys[ev.key]);return;}}
  if(k==='k')submitCorrection('KEEP_YES');else if(k==='u')submitCorrection('UNCERTAIN');else if(k==='c')changeBtn.click();
}};
</script>"""


def correction_complete_page() -> bytes:
    return b"<!doctype html><h1>Correction audit complete</h1><p>All current-YES rows reviewed. Stop the server and run --freeze.</p>"


def review_existing_page(row: Mapping[str, Any], current_fields: Mapping[str, str], position: int, total: int) -> str:
    """Final human-only cleanup pass over ALL 420 rows' CURRENT effective
    labels. Shows only human-observable evidence plus the current human
    label/reason -- never any matcher field.
    """
    e = html.escape
    reason_buttons = "".join(
        f'<button type="button" class="reason" data-reason="{reason}">{i + 1}: {reason.replace("_", " ")}</button>'
        for i, reason in enumerate(NO_REASONS)
    )
    current_label = current_fields.get("exact_match_yes_no_uncertain", "")
    current_reason = ""
    for field, value in current_fields.items():
        if field != "exact_match_yes_no_uncertain" and value and value not in ("SINGLE_CARD", "RAW", "CARD"):
            current_reason = f"{field}={value}"
            break
    return f"""<!doctype html><meta charset="utf-8"><title>D3-v4 Review Existing Labels</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:30px auto}}img{{max-height:360px;max-width:480px}}
button{{padding:10px 16px;margin:4px 6px 4px 0;font-size:16px}}.cols{{display:flex;gap:30px}}
.primary{{padding:18px 28px;font-size:20px}}#keepBtn3{{background:#d7f5d0}}#reasonBar3{{display:none;margin-top:10px}}</style>
<h1>D3-v4 review-existing cleanup &mdash; SINGLE_REVIEWER_BLIND</h1>
<p>{position} / {total}</p>
<p>CURRENT HUMAN LABEL: <b>{e(str(current_label))}</b>{f' &mdash; CURRENT HUMAN NO REASON: <b>{e(current_reason)}</b>' if current_reason else ''}</p>
<div class="cols">
<section><h2>Target instrument</h2>
<p><b>{e(str(row['target_card_name']))}</b><br>{e(str(row['target_set_name']))}<br>
#{e(str(row['target_card_number']))}<br>Treatment: {e(str(row['target_treatment']))}</p></section>
<section><h2>eBay listing</h2>
<p><b>{e(str(row['listing_title']))}</b><br>Condition: {e(str(row['condition']))}<br>
Buying options: {e(str(row.get('buying_options_json') or ''))}<br>Seller: {e(str(row.get('seller_id') or ''))}</p>
<img src="{e(str(row.get('image_url') or ''))}"><p><a href="{e(str(row.get('item_url') or ''))}" target="_blank">Open listing on eBay</a></p></section>
</div>
<p>
<button type="button" class="primary" id="keepBtn3">KEEP (K)</button>
<button type="button" class="primary" id="changeYesBtn">CHANGE TO YES</button>
<button type="button" class="primary" id="changeNoBtn">CHANGE TO NO</button>
<button type="button" class="primary" id="changeUncertainBtn">CHANGE TO UNCERTAIN</button>
</p>
<div id="reasonBar3"><b>Why is this NOT the target?</b><br>{reason_buttons}</div>
<p>
<button type="button" id="prevBtn3">&larr; Previous (B)</button>
<button type="button" id="nextBtn3">Next (N)</button>
<button type="button" id="undo3">Undo Last Action</button>
</p>
<script>
const rowId={json.dumps(row['benchmark_row_id'])};
function submitReview(decision,reason){{
  const body={{row_id:rowId,decision}};if(reason)body.no_reason=reason;
  fetch('/review_existing',{{method:'POST',body:new URLSearchParams(body)}}).then(()=>location.reload());
}}
keepBtn3.onclick=()=>submitReview('KEEP_CURRENT');
changeYesBtn.onclick=()=>submitReview('CHANGE_TO_YES');
changeUncertainBtn.onclick=()=>submitReview('CHANGE_TO_UNCERTAIN');
changeNoBtn.onclick=()=>{{document.getElementById('reasonBar3').style.display='block';}};
document.querySelectorAll('.reason').forEach(b=>b.onclick=()=>submitReview('CHANGE_TO_NO',b.dataset.reason));
undo3.onclick=()=>fetch('/undo_review_existing',{{method:'POST'}}).then(()=>location.reload());
prevBtn3.onclick=()=>fetch('/previous_review_existing',{{method:'POST'}}).then(()=>location.reload());
nextBtn3.onclick=()=>fetch('/next_review_existing',{{method:'POST'}}).then(()=>location.reload());
const reasonKeys={json.dumps(NO_REASON_SHORTCUTS)};
onkeydown=function(ev){{
  const k=ev.key.toLowerCase();
  if(k==='b'){{prevBtn3.click();return;}}
  if(document.getElementById('reasonBar3').style.display==='block' && reasonKeys[ev.key]){{submitReview('CHANGE_TO_NO',reasonKeys[ev.key]);return;}}
  if(k==='k')submitReview('KEEP_CURRENT');else if(k==='n')nextBtn3.click();
}};
</script>"""


def review_existing_complete_page() -> bytes:
    return b"<!doctype html><h1>Review-existing cleanup complete</h1><p>You have reached the end of the list. Use Previous to revisit any row, or stop the server and run --freeze.</p>"


def complete_page() -> bytes:
    return b"<!doctype html><h1>Review complete</h1><p>All rows reviewed. Stop the server and run --freeze.</p>"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--audit-yes-labels", action="store_true", help="Second-pass correction audit over current-YES rows.")
    parser.add_argument("--review-existing", action="store_true", help="Final cleanup pass over ALL current effective labels.")
    return parser


def _run_primary_review(reviewer_id: str, port: int) -> None:
    if is_frozen():
        raise SystemExit("Labels are already frozen; review is closed. Use --summary to inspect the frozen state.")

    rows = load_queue_rows()
    if len(rows) != EXPECTED_ROW_COUNT:
        raise SystemExit(f"Expected {EXPECTED_ROW_COUNT} rows, found {len(rows)} -- refusing to serve a mutated cohort.")
    assert_no_forbidden_columns(rows)
    row_ids = [r["benchmark_row_id"] for r in rows]

    lock = threading.Lock()
    cursor: dict[str, Optional[int]] = {"index": None}

    def refresh(after: int = -1) -> dict[str, dict[str, Any]]:
        effective = reconstruct_effective_labels(read_history())
        cursor["index"] = next_unreviewed_index(rows, effective, after)
        return effective

    refresh()
    print(json.dumps(summary(reviewer_id), indent=2, sort_keys=True))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                prior = (cursor["index"] - 1) if cursor["index"] is not None else -1
                state = refresh(prior)
                index = cursor["index"]
                body = complete_page() if index is None else page(rows[index], len(state), len(rows)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            with lock:
                try:
                    if self.path == "/undo":
                        # Global "undo my last action" -- never the row_id of
                        # whatever the page has already advanced to.
                        event = build_undo_last_label_event(read_history(), reviewer_id)
                        if event:
                            append_event(event)
                    elif self.path == "/label" and data.get("row_id") in row_ids:
                        advanced = {
                            key[len("advanced_"):]: value
                            for key, value in data.items()
                            if key.startswith("advanced_") and key[len("advanced_"):] in ADVANCED_OPTIONAL_FIELDS
                        }
                        event = build_label_event(
                            data["row_id"], reviewer_id, data.get("primary", ""),
                            no_reason=data.get("no_reason"), advanced=advanced, note=data.get("note", ""),
                        )
                        append_event(event)
                except ReviewFrozen:
                    self.send_response(423)
                    self.end_headers()
                    return
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass

    url = f"http://127.0.0.1:{port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


CORRECTION_ACTIONS = frozenset({"correction", "undo_correction"})


def _read_correction_events() -> list[dict[str, Any]]:
    return read_history(CORRECTION_HISTORY_PATH, actions=CORRECTION_ACTIONS)


def _run_correction_audit(reviewer_id: str, port: int) -> None:
    if not is_frozen():
        raise SystemExit("The correction audit requires a completed first-pass freeze first.")
    if is_finally_frozen():
        raise SystemExit("Final labels are already frozen; the correction audit is closed.")

    rows = load_queue_rows()
    by_id = {r["benchmark_row_id"]: r for r in rows}
    queue = build_correction_queue(rows)

    lock = threading.Lock()
    cursor: dict[str, Optional[int]] = {
        "index": next_uncorrected_index(queue, reconstruct_correction_state(_read_correction_events()), -1)
    }
    print(json.dumps(correction_summary(reviewer_id), indent=2, sort_keys=True))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                effective = reconstruct_correction_state(_read_correction_events())
                index = cursor["index"]
                if index is None:
                    body = correction_complete_page()
                else:
                    row_id = queue[index]
                    body = correction_page(by_id[row_id], len(effective), len(queue), current=effective.get(row_id)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            with lock:
                try:
                    if self.path == "/previous_correction":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) - 1, len(queue))
                    elif self.path == "/next_correction":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) + 1, len(queue))
                    elif self.path == "/undo_correction":
                        # Global "undo my last action" -- never derived from
                        # the currently displayed row. Navigates the UI to
                        # whichever row was actually affected.
                        event = build_undo_last_correction_event(_read_correction_events(), reviewer_id)
                        if event:
                            append_correction_event(event)
                            affected = _position_of(queue, event["benchmark_row_id"])
                            if affected is not None:
                                cursor["index"] = affected
                    elif self.path == "/correction" and data.get("row_id") in queue:
                        event = build_correction_event(
                            data["row_id"], reviewer_id, data.get("decision", ""),
                            no_reason=data.get("no_reason"), note=data.get("note", ""),
                        )
                        append_correction_event(event)
                        effective = reconstruct_correction_state(_read_correction_events())
                        current_index = _position_of(queue, data["row_id"])
                        next_index = next_uncorrected_index(queue, effective, current_index if current_index is not None else -1)
                        cursor["index"] = next_index if next_index is not None else current_index
                except ReviewFrozen:
                    self.send_response(423)
                    self.end_headers()
                    return
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass

    url = f"http://127.0.0.1:{port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def _run_review_existing(reviewer_id: str, port: int) -> None:
    """--review-existing: one final human-only cleanup pass over ALL 420
    rows' CURRENT effective labels (first-pass, possibly corrected). Uses the
    SAME append-only correction history/stream as --audit-yes-labels -- it is
    not a separate stage, just a broader, optional pass over any row.
    """
    if not is_frozen():
        raise SystemExit("Review-existing requires a completed first-pass freeze first.")
    if is_finally_frozen():
        raise SystemExit("Final labels are already frozen; review-existing is closed.")

    rows = load_queue_rows()
    ordered_ids = [r["benchmark_row_id"] for r in rows]
    by_id = {r["benchmark_row_id"]: r for r in rows}

    lock = threading.Lock()
    cursor: dict[str, Optional[int]] = {"index": 0 if rows else None}
    print(json.dumps({"total_rows": len(rows), "reviewer_id": reviewer_id, "mode": "review_existing"}, indent=2, sort_keys=True))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                effective = reconstruct_correction_state(_read_correction_events())
                index = cursor["index"]
                if index is None:
                    body = review_existing_complete_page()
                else:
                    row = by_id[ordered_ids[index]]
                    fields = current_effective_fields(row, effective)
                    body = review_existing_page(row, fields, index + 1, len(ordered_ids)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            with lock:
                try:
                    if self.path == "/previous_review_existing":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) - 1, len(ordered_ids))
                    elif self.path == "/next_review_existing":
                        cursor["index"] = _clamped_index((cursor["index"] or 0) + 1, len(ordered_ids))
                    elif self.path == "/undo_review_existing":
                        event = build_undo_last_correction_event(_read_correction_events(), reviewer_id)
                        if event:
                            append_correction_event(event)
                            affected = _position_of(ordered_ids, event["benchmark_row_id"])
                            if affected is not None:
                                cursor["index"] = affected
                    elif self.path == "/review_existing" and data.get("row_id") in by_id:
                        row_id = data["row_id"]
                        decision = data.get("decision", "")
                        if decision == "KEEP_CURRENT":
                            effective = reconstruct_correction_state(_read_correction_events())
                            current_fields = current_effective_fields(by_id[row_id], effective)
                            event = build_correction_event(row_id, reviewer_id, "KEEP_CURRENT", current_fields=current_fields)
                        else:
                            event = build_correction_event(row_id, reviewer_id, decision, no_reason=data.get("no_reason"), note=data.get("note", ""))
                        append_correction_event(event)
                        current_index = _position_of(ordered_ids, row_id)
                        if current_index is not None:
                            cursor["index"] = _clamped_index(current_index + 1, len(ordered_ids))
                except ReviewFrozen:
                    self.send_response(423)
                    self.end_headers()
                    return
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            pass

    url = f"http://127.0.0.1:{port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.summary:
        print(json.dumps(summary(args.reviewer), indent=2, sort_keys=True))
        return

    if args.freeze:
        result = freeze(args.reviewer)
        print(json.dumps(result, indent=2, sort_keys=True))
        precondition_report = run_precondition_check_only()
        print(json.dumps({"post_freeze_precondition_check": precondition_report}, indent=2, sort_keys=True, default=str))
        return

    if args.audit_yes_labels:
        _run_correction_audit(args.reviewer, args.port)
        return

    if args.review_existing:
        _run_review_existing(args.reviewer, args.port)
        return

    _run_primary_review(args.reviewer, args.port)


if __name__ == "__main__":
    main()
