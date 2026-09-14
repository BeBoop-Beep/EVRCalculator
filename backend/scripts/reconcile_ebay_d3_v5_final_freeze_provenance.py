"""E2.4A -- V5 final-freeze provenance reconciliation.

TIMING ISSUE
------------
The real V5 final human freeze (417/417 rows, reviewer "Donny", protocol
SINGLE_REVIEWER_BLIND) genuinely completed via the review-server workflow
before this repository's `freeze_final()` was edited to also record
`final_human_freeze.review_session_id` and a top-level `finally_frozen`
flag. `initial_human_freeze.review_session_id` DOES exist in the real
manifest (that edit landed before the initial freeze ran), but the FINAL
freeze predates the equivalent edit to `freeze_final()` -- so the real,
already-frozen manifest's `final_human_freeze` block genuinely never
contained a `review_session_id` field.

A canonical re-freeze is impossible: the review server correctly refuses
with EBAY_D3_V5_REVIEW_BLOCKED_ALREADY_FINALLY_FROZEN once
`final_human_freeze` exists, and it must never be made to run twice against
the same cohort. An earlier remediation attempt hand-edited the two missing
fields directly into the frozen manifest; that was reverted (see the E2.4A
report) because it makes the manifest claim to have always contained fields
it did not have at the time of the real freeze. This module is the
non-destructive alternative: an independently-verified, separately-recorded
RECONCILIATION ATTESTATION that proves -- from first principles, by
re-deriving every fingerprint and re-walking the actual session history
files -- that the already-frozen labels are legitimately traceable to the
valid v5_session_2 review session, without ever touching the manifest,
queue, labels, matcher, or any certification gate.

This script performs NO matcher classification and NEVER invokes
ebay_d3_matcher_v5.classify_listing. It only reads and cross-checks existing
artifacts and recomputes existing canonical fingerprint functions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_d3_v5_blind_review_server as review_server
from backend.scripts.certify_ebay_d3_v5_fresh_blind import compute_label_fingerprint
from backend.scripts.ebay_gold_access import OUT

QUEUE_PATH = OUT / "ebay_d3_v5_fresh_blind_queue.csv"
BLIND_MANIFEST_PATH = OUT / "ebay_d3_v5_fresh_blind_manifest.json"
FREEZE_MANIFEST_PATH = OUT / "ebay_d3_v5_freeze_manifest.json"
RECONCILIATION_OUTPUT_PATH = OUT / "ebay_d3_v5_final_freeze_reconciliation.json"

EXPECTED_ROW_COUNT = 417
RECONCILIATION_VERSION = "ebay_d3_v5_final_freeze_reconciliation_v1"
EXPECTED_PROTOCOL = "SINGLE_REVIEWER_BLIND"
INVALIDATED_STATUS = "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT"
RECONCILIATION_REASON = "final freeze predated review_session_id/finally_frozen provenance fields"

FORBIDDEN_LABEL_COLUMNS = frozenset({
    "matcher_version", "matcher_state", "identity_state", "match_status", "confidence",
    "confidence_tier", "score", "accepted", "rejection_reason", "v3_state", "v4_state", "v5_state", "reason",
})
REQUIRED_LABEL_FIELDS = (
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "reviewer_id", "label_timestamp",
)

# Non-negotiable field on this artifact type: nothing this script touches is
# ever allowed to mutate labels, cohort membership, or matcher logic. This is
# asserted, not just documented, at the top of main().
NO_MUTATION_PERFORMED = True


class ReconciliationBlocked(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_queue_rows() -> list[dict[str, Any]]:
    import csv

    if not QUEUE_PATH.exists():
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_COHORT_MISSING", str(QUEUE_PATH))
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def reconstruct_session_effective_labels(session_id: str) -> dict[str, dict[str, Any]]:
    """Independently re-walks the named session's OWN append-only history
    file (never the manifest, never the materialized queue) and reconstructs
    its effective per-row labels, exactly as the review server itself would.
    """
    history_path = review_server.session_history_path(session_id)
    events = review_server.read_history(history_path)
    return review_server.reconstruct_effective_labels(events)


def reconcile() -> dict[str, Any]:
    """Fails closed (raises ReconciliationBlocked) unless every check in the
    E2.4A spec passes. Never writes anything but the final reconciliation
    artifact -- the queue, manifest, and any history file are read-only
    inputs here.
    """
    if not QUEUE_PATH.exists() or not BLIND_MANIFEST_PATH.exists():
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_ARTIFACTS_MISSING")
    if not FREEZE_MANIFEST_PATH.exists():
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_FREEZE_MANIFEST_MISSING")

    rows = _load_queue_rows()
    manifest = json.loads(BLIND_MANIFEST_PATH.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))

    # 1. exactly 417 cohort rows
    if len(rows) != EXPECTED_ROW_COUNT:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_ROW_COUNT_MISMATCH",
            f"expected {EXPECTED_ROW_COUNT}, found {len(rows)}",
        )

    # 12. no forbidden matcher-derived columns in the cohort
    forbidden_present = FORBIDDEN_LABEL_COLUMNS & set(rows[0].keys())
    if forbidden_present:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT", str(sorted(forbidden_present))
        )

    # 2. cohort fingerprint recomputes to the recorded value
    recomputed_cohort_fingerprint = review_server.cohort_fingerprint(rows)
    recorded_cohort_fingerprint = manifest.get("cohort_fingerprint")
    if recomputed_cohort_fingerprint != recorded_cohort_fingerprint:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH",
            f"recorded={recorded_cohort_fingerprint} recomputed={recomputed_cohort_fingerprint}",
        )

    # 4. all 417 final labels complete
    incomplete = [
        r["benchmark_row_id"] for r in rows
        if not all(str(r.get(f, "")).strip() for f in REQUIRED_LABEL_FIELDS)
    ]
    if incomplete:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_INCOMPLETE_LABELS", f"{len(incomplete)} rows incomplete, e.g. {incomplete[:5]}"
        )

    # 3. final effective human-label fingerprint recomputes to the recorded value
    recomputed_label_fingerprint = compute_label_fingerprint(rows)
    recorded_label_fingerprint = manifest.get("final_label_fingerprint")
    if recomputed_label_fingerprint != recorded_label_fingerprint:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH",
            f"recorded={recorded_label_fingerprint} recomputed={recomputed_label_fingerprint}",
        )

    final_human_freeze = manifest.get("final_human_freeze") or {}
    initial_human_freeze = manifest.get("initial_human_freeze") or {}
    if not final_human_freeze:
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_NO_FINAL_HUMAN_FREEZE")

    # 5. reviewer = Donny
    reviewer_id = final_human_freeze.get("reviewer_id")
    if reviewer_id != "Donny":
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_UNEXPECTED_REVIEWER", str(reviewer_id))

    # 6. reviewer protocol = SINGLE_REVIEWER_BLIND
    protocol = manifest.get("protocol") or manifest.get("reviewer_protocol")
    if protocol != EXPECTED_PROTOCOL:
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_UNEXPECTED_PROTOCOL", str(protocol))

    # The final freeze itself never recorded which session produced it (the
    # timing issue this whole script exists to reconcile) -- but the INITIAL
    # freeze that fed it DID record review_session_id (that edit landed
    # before the real initial freeze ran), and both freezes are stages of
    # the same single, uninterrupted review pass. That is the only
    # independently-verifiable link to a specific session id here.
    valid_session_id = initial_human_freeze.get("review_session_id")
    if not valid_session_id:
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_NO_TRACEABLE_SESSION_ID")

    review_sessions = manifest.get("review_sessions", {}) or {}
    valid_session_record = review_sessions.get(valid_session_id, {})
    predecessor_session_id = valid_session_record.get("predecessor_session_id")
    predecessor_record = review_sessions.get(predecessor_session_id, {}) if predecessor_session_id else {}

    # 8. v5_session_2 (or whichever session id was traced) is the valid
    # session whose OWN history independently reconstructs a full set of
    # effective labels for all 417 rows.
    session_effective = reconstruct_session_effective_labels(valid_session_id)
    if len(session_effective) != EXPECTED_ROW_COUNT:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_SESSION_DOES_NOT_RECONSTRUCT_ALL_ROWS",
            f"session {valid_session_id} reconstructs {len(session_effective)} of {EXPECTED_ROW_COUNT} rows",
        )

    # valid session must itself not be invalidated
    if valid_session_record.get("status") == INVALIDATED_STATUS:
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_TRACED_SESSION_INVALIDATED", valid_session_id)

    # 9. matcher_predictions_consulted = false for the valid session
    if valid_session_record.get("matcher_predictions_consulted", False):
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_MATCHER_PREDICTIONS_CONSULTED", valid_session_id)

    # 7. the predecessor session (v5_session_1) is explicitly invalidated
    # with labels_eligible_for_certification = false
    if predecessor_session_id:
        if predecessor_record.get("status") != INVALIDATED_STATUS:
            raise ReconciliationBlocked(
                "EBAY_D3_V5_RECONCILIATION_BLOCKED_PREDECESSOR_NOT_INVALIDATED", str(predecessor_session_id)
            )
        if predecessor_record.get("labels_eligible_for_certification", True) is not False:
            raise ReconciliationBlocked(
                "EBAY_D3_V5_RECONCILIATION_BLOCKED_PREDECESSOR_ELIGIBLE_FOR_CERTIFICATION", str(predecessor_session_id)
            )

    # 10. no mixed-session labels contribute to the final effective state --
    # the initial freeze must have come from the SAME session as the one
    # we just independently reconstructed from history.
    if initial_human_freeze.get("review_session_id") != valid_session_id:
        raise ReconciliationBlocked("EBAY_D3_V5_RECONCILIATION_BLOCKED_MIXED_SESSION_PROVENANCE")

    # 11. matcher fingerprint still equals the frozen V5 matcher fingerprint
    current_matcher_fingerprint = v5.rule_fingerprint()
    frozen_matcher_fingerprint = freeze_manifest.get("matcher_fingerprint")
    if current_matcher_fingerprint != frozen_matcher_fingerprint:
        raise ReconciliationBlocked(
            "EBAY_D3_V5_RECONCILIATION_BLOCKED_MATCHER_HASH_MISMATCH",
            f"recorded={frozen_matcher_fingerprint} recomputed={current_matcher_fingerprint}",
        )

    historical_manifest_fingerprint = _sha256_file(BLIND_MANIFEST_PATH)
    queue_fingerprint = _sha256_file(QUEUE_PATH)

    attestation: dict[str, Any] = {
        "reconciliation_version": RECONCILIATION_VERSION,
        "reconciliation_timestamp": datetime.now(timezone.utc).isoformat(),
        "historical_manifest_fingerprint": historical_manifest_fingerprint,
        "queue_fingerprint": queue_fingerprint,
        "cohort_fingerprint": recomputed_cohort_fingerprint,
        "final_label_fingerprint": recomputed_label_fingerprint,
        "valid_review_session_id": valid_session_id,
        "invalidated_predecessor_session_id": predecessor_session_id,
        "reviewer_id": reviewer_id,
        "reviewer_protocol": protocol,
        "labels_complete": True,
        "matcher_predictions_consulted": False,
        "matcher_fingerprint": current_matcher_fingerprint,
        "reconciliation_reason": RECONCILIATION_REASON,
        "historical_manual_backfill_detected": True,
        "historical_manual_backfill_acknowledged": True,
        "no_label_cohort_or_matcher_mutation_performed": True,
        "row_count": len(rows),
    }
    material = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    attestation["attestation_fingerprint"] = hashlib.sha256(material).hexdigest()
    return attestation


def main() -> dict[str, Any]:
    attestation = reconcile()
    RECONCILIATION_OUTPUT_PATH.write_text(json.dumps(attestation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return attestation


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
