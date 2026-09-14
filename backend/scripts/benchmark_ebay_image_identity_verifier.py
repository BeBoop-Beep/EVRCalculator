"""EBAY_E2_6 development benchmark for ebay_image_identity_verifier (IMAGE-v1).

Builds a DEVELOPMENT image-verification dataset from freely-licensed public
Pokemon TCG API card artwork (Charizard ex / Pikachu ex / Gardevoir ex
families -- deliberately NOT overlapping with the three consumed V5
WRONG_SET failure cards or the V4 D4-0375 failure card), then measures
ORB+RANSAC-homography feature-matching performance on:

  - POSITIVE pairs: a canonical image against geometrically-transformed
    copies of ITSELF (rotation, perspective warp, downscale/recompress,
    crop) -- simulating the kinds of distortion a real photographed
    listing introduces while still being the same printed card.
  - HARD NEGATIVE pairs: canonical images of DIFFERENT cards that share the
    same Pokemon name (same Pokemon, different set/number/artwork/treatment)
    -- exactly the "sibling hard negative" class the E2.6 spec requires.
  - EASY NEGATIVE pairs: cross-family (different Pokemon entirely).

This script NEVER reads or references the consumed V4/V5 blind-cohort rows.
Thresholds selected here are what ebay_image_identity_verifier.py freezes;
the historical post-hoc diagnostic (a SEPARATE script) runs strictly after
freeze and never feeds back into these thresholds.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.scripts.ebay_image_identity_verifier import (
    METHOD_VERSION,
    MATCH_MIN_INLIER_COUNT,
    MATCH_MIN_INLIER_RATIO,
    MISMATCH_MAX_INLIER_RATIO,
    MISMATCH_MIN_GOOD_MATCHES,
    decode_image,
    detect_card_region,
    orb_feature_match,
    perceptual_hash,
    hamming_distance,
    source_sha256,
)
from backend.scripts.ebay_gold_access import OUT

DEV_DATASET_DIR = Path(
    r"C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e26_dev_canonical"
)
BENCHMARK_OUTPUT_PATH = OUT / "ebay_image_identity_verifier_v1_dev_benchmark.json"
FREEZE_MANIFEST_PATH = OUT / "ebay_image_identity_verifier_v1_freeze_manifest.json"


def _load_manifest() -> list[dict[str, Any]]:
    manifest_path = DEV_DATASET_DIR / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_image(path: str) -> np.ndarray:
    data = Path(path).read_bytes()
    image = decode_image(data)
    if image is None:
        raise RuntimeError(f"failed to decode dev image {path}")
    return image


def _transform_rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=(255, 255, 255))


def _transform_perspective(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    shift = 0.06
    dst = np.float32([
        [w * shift, h * shift * 0.5], [w * (1 - shift * 0.3), 0],
        [w, h * (1 - shift)], [w * shift * 0.5, h],
    ])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (w, h), borderValue=(255, 255, 255))


def _transform_downscale_recompress(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    small = cv2.resize(image, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    return cv2.resize(decoded, (w, h), interpolation=cv2.INTER_LINEAR)


def _transform_crop(image: np.ndarray, margin: float = 0.08) -> np.ndarray:
    h, w = image.shape[:2]
    y0, y1 = int(h * margin), int(h * (1 - margin))
    x0, x1 = int(w * margin), int(w * (1 - margin))
    return image[y0:y1, x0:x1]


TRANSFORMS = {
    "rotate_8deg": lambda img: _transform_rotate(img, 8),
    "rotate_-12deg": lambda img: _transform_rotate(img, -12),
    "perspective": _transform_perspective,
    "downscale_recompress": _transform_downscale_recompress,
    "crop_8pct": _transform_crop,
}


def _pair_metrics(image_a: np.ndarray, image_b: np.ndarray) -> dict[str, Any]:
    rectified, region_detected = detect_card_region(image_b)
    target = rectified if region_detected else image_b
    match = orb_feature_match(image_a, target)
    phash_dist = hamming_distance(perceptual_hash(image_a), perceptual_hash(target))
    return {
        "card_region_detected": region_detected,
        "good_match_count": match["good_match_count"],
        "homography_inlier_count": match["homography_inlier_count"],
        "homography_inlier_ratio": match["homography_inlier_ratio"],
        "perceptual_hash_distance": phash_dist,
    }


def _classify(metrics: dict[str, Any]) -> str:
    good = metrics["good_match_count"]
    inliers = metrics["homography_inlier_count"]
    ratio = metrics["homography_inlier_ratio"]
    if good >= MATCH_MIN_INLIER_COUNT and inliers >= MATCH_MIN_INLIER_COUNT and ratio >= MATCH_MIN_INLIER_RATIO:
        return "MATCH"
    if good >= MISMATCH_MIN_GOOD_MATCHES and ratio <= MISMATCH_MAX_INLIER_RATIO:
        return "MISMATCH"
    return "UNVERIFIED"


def build_and_run() -> dict[str, Any]:
    manifest = _load_manifest()
    images = {row["id"]: _load_image(row["image_path"]) for row in manifest}
    by_family: dict[str, list[str]] = {}
    for row in manifest:
        by_family.setdefault(row["query_name"], []).append(row["id"])

    positive_results = []
    for card_id, image in images.items():
        for transform_name, transform_fn in TRANSFORMS.items():
            transformed = transform_fn(image)
            metrics = _pair_metrics(image, transformed)
            positive_results.append({
                "pair_type": "POSITIVE_TRANSFORMED", "card_id": card_id, "transform": transform_name,
                "predicted_state": _classify(metrics), **metrics,
            })

    hard_negative_results = []
    for family, ids in by_family.items():
        for id_a, id_b in itertools.combinations(ids, 2):
            metrics = _pair_metrics(images[id_a], images[id_b])
            hard_negative_results.append({
                "pair_type": "HARD_NEGATIVE_SAME_POKEMON", "card_id_a": id_a, "card_id_b": id_b,
                "family": family, "predicted_state": _classify(metrics), **metrics,
            })

    easy_negative_results = []
    families = list(by_family.keys())
    for fam_a, fam_b in itertools.combinations(families, 2):
        id_a = by_family[fam_a][0]
        id_b = by_family[fam_b][0]
        metrics = _pair_metrics(images[id_a], images[id_b])
        easy_negative_results.append({
            "pair_type": "EASY_NEGATIVE_DIFFERENT_POKEMON", "card_id_a": id_a, "card_id_b": id_b,
            "predicted_state": _classify(metrics), **metrics,
        })

    def _rate(results: list[dict[str, Any]], state: str) -> float:
        return round(sum(1 for r in results if r["predicted_state"] == state) / len(results), 6) if results else 0.0

    summary = {
        "method_version": METHOD_VERSION,
        "dev_dataset_card_count": len(images),
        "dev_dataset_families": {k: len(v) for k, v in by_family.items()},
        "positive_pairs": len(positive_results),
        "positive_match_rate": _rate(positive_results, "MATCH"),
        "positive_unverified_rate": _rate(positive_results, "UNVERIFIED"),
        "positive_false_mismatch_rate": _rate(positive_results, "MISMATCH"),
        "hard_negative_pairs": len(hard_negative_results),
        "hard_negative_false_match_rate": _rate(hard_negative_results, "MATCH"),
        "hard_negative_mismatch_rate": _rate(hard_negative_results, "MISMATCH"),
        "hard_negative_unverified_rate": _rate(hard_negative_results, "UNVERIFIED"),
        "easy_negative_pairs": len(easy_negative_results),
        "easy_negative_false_match_rate": _rate(easy_negative_results, "MATCH"),
        "thresholds": {
            "MATCH_MIN_INLIER_COUNT": MATCH_MIN_INLIER_COUNT,
            "MATCH_MIN_INLIER_RATIO": MATCH_MIN_INLIER_RATIO,
            "MISMATCH_MAX_INLIER_RATIO": MISMATCH_MAX_INLIER_RATIO,
            "MISMATCH_MIN_GOOD_MATCHES": MISMATCH_MIN_GOOD_MATCHES,
        },
    }

    detail = {
        "positive_results": positive_results,
        "hard_negative_results": hard_negative_results,
        "easy_negative_results": easy_negative_results,
    }

    return {"summary": summary, "detail": detail, "manifest": manifest}


def dataset_fingerprint(manifest: list[dict[str, Any]]) -> str:
    material = "\n".join(sorted(f"{m['id']}:{Path(m['image_path']).stat().st_size}" for m in manifest))
    return hashlib.sha256(material.encode()).hexdigest()


def main() -> dict[str, Any]:
    result = build_and_run()
    BENCHMARK_OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    output = main()
    print(json.dumps(output["summary"], indent=2))
