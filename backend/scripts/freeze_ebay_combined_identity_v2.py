"""Freezes COMBINED-IDENTITY-v2's policy semantics (EBAY_E2_9).

Records the policy source hash, the composite policy fingerprint, and the
exact frozen versions/fingerprints of the two layers it consumes (D3-v5 text,
IMAGE-v2 image), plus the historical development fingerprints this policy
was reasoned about against. Writes
backend/artifacts/index_fair_value/ebay_combined_identity_v2_freeze_manifest.json
and must not be re-run with different output after freeze; a changed
`policy_source_sha256` on a later run is a freeze violation, not an update
mechanism (see test_ebay_combined_identity_policy_v2.py::test_no_post_freeze_mutation).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_image_retrieval_verifier as image_v2
from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
from backend.scripts.ebay_gold_access import OUT

FREEZE_OUTPUT_PATH = OUT / "ebay_combined_identity_v2_freeze_manifest.json"


def build_manifest() -> dict:
    text_fingerprint = v5.rule_fingerprint()
    image_fingerprint = image_v2.source_sha256()
    return {
        "version": "ebay_combined_identity_policy_v2",
        "policy_source_sha256": policy_v2.policy_source_hash(),
        "policy_fingerprint": policy_v2.policy_fingerprint(text_fingerprint, image_fingerprint),
        "text_matcher_version": v5.MATCHER_VERSION,
        "text_matcher_fingerprint": text_fingerprint,
        "image_verifier_version": image_v2.METHOD_VERSION,
        "image_verifier_model": image_v2.MODEL_NAME,
        "image_verifier_fingerprint": image_fingerprint,
        "historical_development_fingerprints": {
            "combined_identity_v1_historical_diagnostic": "backend/artifacts/index_fair_value/ebay_combined_identity_v1_historical_post_hoc_diagnostic.json",
            "image_retrieval_verifier_v2_freeze_manifest": "backend/artifacts/index_fair_value/ebay_image_retrieval_verifier_v2_freeze_manifest.json",
        },
        "eligible_states": list(policy_v2.ELIGIBLE_STATES),
        "production_authority": False,
        "shadow_research_only": True,
        "certified_against_new_blind": False,
        "consumed_blind_rows_used_for_tuning": False,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> dict:
    manifest = build_manifest()
    FREEZE_OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
