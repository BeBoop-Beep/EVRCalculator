"""Freeze D3-v4. After this runs, no matcher-logic changes are permitted
before the new blind cohort is captured and its labels frozen (Phase I).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.index_fair_value_ebay_evidence_quality import EvidenceQuality  # noqa: F401  (version anchor)

MATCHER_SOURCE = Path(v4.__file__)
DEVELOPMENT_STUDY = OUT / "ebay_d3_v4_development_study.json"
VALIDATION_PASS = OUT / "ebay_d3_v4_validation_pass.json"

EVIDENCE_QUALITY_VERSION = "ebay_evidence_quality_contract_v1"
CERTIFICATION_SCRIPT_VERSION = "certify_ebay_d3_v3_v1"  # certification tool itself is unchanged; reused for v4 later


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> dict:
    development_study = json.loads(DEVELOPMENT_STUDY.read_text(encoding="utf-8"))
    validation_pass = json.loads(VALIDATION_PASS.read_text(encoding="utf-8"))
    if validation_pass["decision"]["validation_pass_result"] != "PASS":
        raise RuntimeError("REFUSING_FREEZE: validation pass did not PASS -- another held-out stage is required")

    manifest = {
        "version": "ebay_d3_v4_freeze_manifest_v1",
        "matcher_version": v4.MATCHER_VERSION,
        "matcher_fingerprint": v4.rule_fingerprint(),
        "matcher_source_sha256": file_hash(MATCHER_SOURCE),
        "query_strategy_version": v4.QUERY_CONTRACT_VERSION,
        "number_guard_version": v4.NUMBER_GUARD_VERSION,
        "multi_fraction_guard_version": v4.MULTI_FRACTION_GUARD_VERSION,
        "sealed_extension_version": v4.SEALED_ONTOLOGY_EXTENSION_VERSION,
        "evidence_quality_version": EVIDENCE_QUALITY_VERSION,
        "certification_script_version": CERTIFICATION_SCRIPT_VERSION,
        "development_corpus_fingerprint": development_study["development_corpus_fingerprint"],
        "development_study_result": {
            "v3_precision": development_study["v3_metrics"]["precision"],
            "v4_precision": development_study["v4_metrics"]["precision"],
            "newly_rejected_legitimate_count": development_study["newly_rejected_legitimate_count"],
        },
        "validation_pass_result": validation_pass["decision"]["validation_pass_result"],
        "validation_row_count": validation_pass["validation_row_count"],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "logic_frozen": True,
        "production_authority": False,
        "certified_against_new_blind": False,
        "historical_blind_used_for_tuning": False,
    }
    manifest["manifest_fingerprint"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (OUT / "ebay_d3_v4_freeze_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
