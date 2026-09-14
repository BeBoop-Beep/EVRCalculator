"""Freeze D3-v5. After this runs, no matcher-logic changes are permitted
before the new blind cohort is captured and its labels frozen.

Unlike v4's freeze, this does NOT gate on a "validation pass" -- the
VALIDATION partition was already consumed during v4's development (E2.1)
and is not eligible to be treated as fresh for v5. v5's only formal
held-out check is the post-freeze, clearly-labeled, non-certifying
historical diagnostic against the (now-consumed) V4 420-row blind cohort.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.index_fair_value_ebay_evidence_quality import EvidenceQuality  # noqa: F401  (version anchor)

MATCHER_SOURCE = Path(v5.__file__)
DEVELOPMENT_STUDY = OUT / "ebay_d3_v5_development_study.json"

EVIDENCE_QUALITY_VERSION = "ebay_evidence_quality_contract_v1"
CERTIFICATION_SCRIPT_VERSION = "certify_ebay_d3_v3_v1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> dict:
    development_study = json.loads(DEVELOPMENT_STUDY.read_text(encoding="utf-8"))
    if development_study["newly_rejected_legitimate_count"] > 0:
        raise RuntimeError(
            "REFUSING_FREEZE: v5 rejected legitimate development listings v4 accepted -- "
            "this must be diagnosed before freezing, not silently frozen"
        )

    manifest = {
        "version": "ebay_d3_v5_freeze_manifest_v1",
        "matcher_version": v5.MATCHER_VERSION,
        "matcher_fingerprint": v5.rule_fingerprint(),
        "matcher_source_sha256": file_hash(MATCHER_SOURCE),
        "query_strategy_version": v5.QUERY_CONTRACT_VERSION,
        "altered_autograph_guard_version": v5.ALTERED_OR_AUTOGRAPH_GUARD_VERSION,
        "evidence_quality_version": EVIDENCE_QUALITY_VERSION,
        "certification_script_version": CERTIFICATION_SCRIPT_VERSION,
        "development_corpus_fingerprint": development_study["development_corpus_fingerprint"],
        "development_study_result": {
            "v4_precision": development_study["v4_metrics"]["precision"],
            "v5_precision": development_study["v5_metrics"]["precision"],
            "v4_recall": development_study["v4_metrics"]["recall"],
            "v5_recall": development_study["v5_metrics"]["recall"],
            "newly_rejected_legitimate_count": development_study["newly_rejected_legitimate_count"],
        },
        "validation_pass_result": "NOT_ELIGIBLE_ALREADY_CONSUMED_BY_V4",
        "v4_blind_cohort_status": "CONSUMED_HISTORICAL_DIAGNOSTIC_ONLY",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "logic_frozen": True,
        "production_authority": False,
        "certified_against_new_blind": False,
        "historical_blind_used_for_tuning": False,
    }
    manifest["manifest_fingerprint"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (OUT / "ebay_d3_v5_freeze_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
