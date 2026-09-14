"""EBAY_E2_6 historical post-hoc diagnostic runner for IMAGE-v1.

NON-CERTIFYING. Refuses to run unless a frozen verifier manifest exists
(ebay_image_identity_verifier_v1_freeze_manifest.json) -- this script exists
so that IF a future candidate image guard is frozen, its behavior against
the four already-consumed image-only-identity-risk rows (D4-0375, D5-0054,
D5-0224, D5-0378) and their legitimate sibling true accepts can be recorded
for documentation. It NEVER feeds back into threshold selection: running
this script after freeze must never be followed by re-editing
ebay_image_identity_verifier.py's thresholds.

As of the E2.6 pass, NO verifier has been frozen (see
EBAY_E2_6_IMAGE_IDENTITY_VERIFICATION_FEASIBILITY.md) -- naive ORB+RANSAC
feature matching produced an unacceptable false-MATCH rate on the
development hard-negative set, so this script is expected to refuse to run
via DiagnosticBlocked until a viable candidate exists.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_image_identity_verifier import source_sha256, verify_image_identity

FREEZE_MANIFEST_PATH = OUT / "ebay_image_identity_verifier_v1_freeze_manifest.json"
DIAGNOSTIC_OUTPUT_PATH = OUT / "ebay_image_identity_v1_historical_post_hoc_diagnostic.json"

NON_CERTIFYING_LABEL = "NON_CERTIFYING_HISTORICAL_POST_HOC_DIAGNOSTIC"

# The four consumed image-only-identity-risk rows this diagnostic exists to
# document -- never used to select or adjust IMAGE-v1's thresholds.
HISTORICAL_FAILURE_ROWS: dict[str, dict[str, str]] = {
    "D4-0375": {"benchmark": "V4", "canonical_image_url": "", "listing_image_url": ""},
    "D5-0054": {"benchmark": "V5", "canonical_image_url": "", "listing_image_url": ""},
    "D5-0224": {"benchmark": "V5", "canonical_image_url": "", "listing_image_url": ""},
    "D5-0378": {"benchmark": "V5", "canonical_image_url": "", "listing_image_url": ""},
}


class DiagnosticBlocked(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _load_freeze_manifest() -> dict[str, Any]:
    if not FREEZE_MANIFEST_PATH.exists():
        raise DiagnosticBlocked(
            "EBAY_IMAGE_V1_DIAGNOSTIC_BLOCKED_NOT_FROZEN",
            "no frozen IMAGE-v1 candidate exists; see EBAY_E2_6_IMAGE_IDENTITY_VERIFICATION_FEASIBILITY.md",
        )
    manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded_hash = manifest.get("verifier_source_sha256")
    current_hash = source_sha256()
    if recorded_hash != current_hash:
        raise DiagnosticBlocked(
            "EBAY_IMAGE_V1_DIAGNOSTIC_BLOCKED_SOURCE_HASH_MISMATCH",
            f"recorded={recorded_hash} current={current_hash}",
        )
    return manifest


def main(row_urls: dict[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    manifest = _load_freeze_manifest()
    row_urls = row_urls or {}

    results = {}
    for row_id in HISTORICAL_FAILURE_ROWS:
        if row_id not in row_urls:
            results[row_id] = {"skipped": True, "reason": "no image URLs supplied for this row"}
            continue
        canonical_url, listing_url = row_urls[row_id]
        results[row_id] = verify_image_identity(canonical_url, listing_url).to_dict()

    output = {
        "label": NON_CERTIFYING_LABEL,
        "verifier_manifest_version": manifest.get("version"),
        "verifier_source_sha256": manifest.get("verifier_source_sha256"),
        "results": results,
        "note": "This diagnostic is informational only. It never certifies IMAGE-v1 and "
                "must never be used to re-tune thresholds after freeze.",
    }
    DIAGNOSTIC_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
