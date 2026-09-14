"""EBAY_E2_7 historical post-hoc diagnostic for the FROZEN IMAGE-v2
retrieval verifier.

NON-CERTIFYING. Refuses to run (DiagnosticBlocked) unless
ebay_image_retrieval_verifier_v2_freeze_manifest.json exists and the
verifier's source hash matches what was frozen. Runs the frozen candidate
once against the four already-consumed image-only-identity-risk rows
(D4-0375, D5-0054, D5-0224, D5-0378) plus their legitimate sibling true
accepts, using REAL eBay listing photo URLs and REAL canonical Pokemon TCG
API images. Never used to re-tune thresholds afterward.
"""
from __future__ import annotations

import json
from typing import Any

from backend.scripts.benchmark_ebay_image_retrieval_verifier import _load_combined_manifest, build_gallery
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_image_retrieval_verifier import source_sha256, verify_by_retrieval

FREEZE_MANIFEST_PATH = OUT / "ebay_image_retrieval_verifier_v2_freeze_manifest.json"
DIAGNOSTIC_OUTPUT_PATH = OUT / "ebay_image_retrieval_v2_historical_post_hoc_diagnostic.json"

NON_CERTIFYING_LABEL = "NON_CERTIFYING_HISTORICAL_POST_HOC_DIAGNOSTIC"

# Real, publicly-fetchable canonical images for the three consumed V5
# target cards that have a distinct Pokemon TCG API entry (Roaring Moon ex,
# the D4-0375/V4 case, is not evaluated here -- out of scope for this V5-era
# pass; V4 evidence is a separate benchmark generation).
HISTORICAL_ROWS: dict[str, dict[str, str]] = {
    "D5-0054": {
        "target_card_id": "TARGET-Kyurem165",
        "canonical_image_url": "https://images.pokemontcg.io/zsv10pt5/165_hires.png",
        "listing_image_url": "https://i.ebayimg.com/images/g/X6YAAeSwdSZqftE9/s-l225.jpg",
        "sibling_true_accept_listing_url": "https://i.ebayimg.com/images/g/SrkAAeSwHKFqLXwx/s-l225.jpg",
        "sibling_true_accept_row": "D5-0056",
    },
    "D5-0224": {
        "target_card_id": "TARGET-Mewtwo231",
        "canonical_image_url": "https://images.pokemontcg.io/sv10/231_hires.png",
        "listing_image_url": "https://i.ebayimg.com/images/g/UkMAAeSwHPVqpXTU/s-l225.jpg",
        "sibling_true_accept_listing_url": "https://i.ebayimg.com/images/g/xigAAeSwuxVqho2k/s-l225.jpg",
        "sibling_true_accept_row": "D5-0219",
    },
    "D5-0378": {
        "target_card_id": "TARGET-Grafaiai223",
        "canonical_image_url": "https://images.pokemontcg.io/sv2/223_hires.png",
        "listing_image_url": "https://i.ebayimg.com/images/g/h-cAAeSw1clqgmds/s-l225.jpg",
        "sibling_true_accept_listing_url": "https://i.ebayimg.com/images/g/GMIAAOSwlc5n7afv/s-l225.jpg",
        "sibling_true_accept_row": "D5-0375",
    },
}


class DiagnosticBlocked(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _load_freeze_manifest() -> dict[str, Any]:
    if not FREEZE_MANIFEST_PATH.exists():
        raise DiagnosticBlocked(
            "EBAY_IMAGE_V2_DIAGNOSTIC_BLOCKED_NOT_FROZEN",
            "no frozen IMAGE-v2 candidate exists",
        )
    manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded_hash = manifest.get("verifier_source_sha256")
    current_hash = source_sha256()
    if recorded_hash != current_hash:
        raise DiagnosticBlocked(
            "EBAY_IMAGE_V2_DIAGNOSTIC_BLOCKED_SOURCE_HASH_MISMATCH",
            f"recorded={recorded_hash} current={current_hash}",
        )
    return manifest


def main() -> dict[str, Any]:
    manifest = _load_freeze_manifest()

    dev_manifest = _load_combined_manifest()
    gallery = build_gallery(dev_manifest)

    results: dict[str, Any] = {}
    for row_id, spec in HISTORICAL_ROWS.items():
        target_id = spec["target_card_id"]
        import urllib.request

        req = urllib.request.Request(spec["canonical_image_url"], headers={"User-Agent": "Mozilla/5.0"})
        canonical_bytes = urllib.request.urlopen(req, timeout=15).read()
        gallery.add(canonical_card_id=target_id, canonical_image_url=spec["canonical_image_url"], image_bytes=canonical_bytes)

        catastrophic_result = verify_by_retrieval(gallery, target_id, spec["listing_image_url"])
        sibling_result = verify_by_retrieval(gallery, target_id, spec["sibling_true_accept_listing_url"])

        results[row_id] = {
            "catastrophic_false_accept": catastrophic_result.to_dict(),
            "sibling_true_accept_row": spec["sibling_true_accept_row"],
            "sibling_true_accept_result": sibling_result.to_dict(),
        }

    output = {
        "label": NON_CERTIFYING_LABEL,
        "verifier_manifest_version": manifest.get("version"),
        "verifier_source_sha256": manifest.get("verifier_source_sha256"),
        "results": results,
        "note": "Informational only. Never certifies IMAGE-v2 and must never be used to re-tune thresholds after freeze.",
    }
    DIAGNOSTIC_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
