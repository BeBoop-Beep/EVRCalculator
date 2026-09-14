"""EBAY_E2_7 development benchmark for ebay_image_retrieval_verifier (IMAGE-v2).

Builds a large (171-card), diverse canonical gallery from freely-licensed
public Pokemon TCG API artwork across 30 Pokemon-name families --
deliberately excluding Kyurem, Team Rocket's Mewtwo ex, Grafaiai, and
Roaring Moon ex (the four consumed V4/V5 blind-cohort failure cards).
Reuses the 30-card E2.6 gallery as a subset for continuity.

Measures, entirely on this development gallery (never the consumed rows):

  - Top-1/Top-3/Top-5 RETRIEVAL accuracy: does the transformed query image
    of card X actually retrieve card X's own canonical embedding within
    the top-K, among all 171 competing canonical identities?
  - FALSE TARGET MATCH RATE: if someone WRONGLY claims a photo shows card
    B when it actually shows card A (a same-Pokemon-family sibling), does
    the retrieval+margin policy correctly refuse MATCH for B?

Thresholds selected here are what ebay_image_retrieval_verifier.py
freezes (if any). The historical post-hoc diagnostic against the four
consumed failure rows is a SEPARATE script/step that only runs after a
freeze, and never feeds back into these thresholds.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from backend.scripts.benchmark_ebay_image_identity_verifier import TRANSFORMS
from backend.scripts.ebay_image_identity_verifier import decode_image
from backend.scripts.ebay_image_retrieval_verifier import (
    METHOD_VERSION,
    MODEL_NAME,
    MODEL_LICENSE,
    PREPROCESSING_VERSION,
    MATCH_MIN_SIMILARITY_FLOOR,
    MATCH_MIN_MARGIN_OVER_RUNNER_UP,
    MISMATCH_MIN_TOP1_ADVANTAGE_OVER_TARGET,
    CanonicalGallery,
    embed_image_bgr,
    image_fingerprint,
)
from backend.scripts.ebay_gold_access import OUT

GALLERY_DIR_E26 = Path(
    r"C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e26_dev_canonical"
)
GALLERY_DIR_E27 = Path(
    r"C:\Users\Owner\AppData\Local\Temp\claude\d--EVRCalculator\ab525fb1-3a68-4190-b321-235965717bad\scratchpad\e27_gallery"
)
BENCHMARK_OUTPUT_PATH = OUT / "ebay_image_retrieval_verifier_v2_dev_benchmark.json"
FREEZE_MANIFEST_PATH = OUT / "ebay_image_retrieval_verifier_v2_freeze_manifest.json"

# A small subset of transforms (of the full E2.6 TRANSFORMS dict) to keep
# CPU wall-clock reasonable while still covering rotation, perspective, and
# resize/recompress distortion classes.
BENCHMARK_TRANSFORM_NAMES = ["rotate_-12deg", "perspective", "downscale_recompress"]


# The four consumed V4/V5 blind-cohort failure cards' EXACT canonical
# identities. A broad name-family fetch ("Mewtwo ex") can incidentally pull
# in a card that IS one of these (discovered: card sv10-231 -- the literal
# canonical identity one of the four consumed blind-cohort target rows
# refers to -- was present in the raw fetched gallery under the "Mewtwo ex"
# query family). Excluded here, unconditionally, so no consumed target
# identity ever participates in threshold selection.
CONSUMED_TARGET_NAMES = {"kyurem", "team rocket's mewtwo ex", "grafaiai", "roaring moon ex"}


def _load_combined_manifest() -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    combined: list[dict[str, Any]] = []
    for gallery_dir in (GALLERY_DIR_E26, GALLERY_DIR_E27):
        manifest_path = gallery_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        for row in json.loads(manifest_path.read_text(encoding="utf-8")):
            if row["id"] in seen_ids:
                continue
            if row["name"].strip().lower() in CONSUMED_TARGET_NAMES:
                continue
            seen_ids.add(row["id"])
            combined.append(row)
    return combined


def build_gallery(manifest: list[dict[str, Any]]) -> CanonicalGallery:
    gallery = CanonicalGallery()
    for row in manifest:
        image_bytes = Path(row["image_path"]).read_bytes()
        gallery.add(
            canonical_card_id=row["id"], canonical_image_url=row["image_path"], image_bytes=image_bytes,
            card_name=row["name"], collector_number=row.get("number"), set_id=row.get("set_id"),
        )
    return gallery


def run_benchmark() -> dict[str, Any]:
    manifest = _load_combined_manifest()
    by_family: dict[str, list[str]] = {}
    for row in manifest:
        by_family.setdefault(row["query_name"], []).append(row["id"])

    t0 = time.time()
    gallery = build_gallery(manifest)
    gallery_build_seconds = time.time() - t0

    images = {row["id"]: decode_image(Path(row["image_path"]).read_bytes()) for row in manifest}

    # One embedding per (card, transform) -- reused for BOTH the retrieval-
    # accuracy measurement (does it retrieve itself?) AND the false-target-
    # match measurement (does a WRONG sibling claim get rejected?).
    query_embeddings: dict[tuple[str, str], np.ndarray] = {}
    t0 = time.time()
    for card_id, image in images.items():
        for transform_name in BENCHMARK_TRANSFORM_NAMES:
            transformed = TRANSFORMS[transform_name](image)
            query_embeddings[(card_id, transform_name)] = embed_image_bgr(transformed)
    query_embedding_seconds = time.time() - t0

    retrieval_results = []
    for (card_id, transform_name), embedding in query_embeddings.items():
        matches = gallery.search(embedding, top_k=5)
        ranked_ids = [m[0].canonical_card_id for m in matches]
        top1_sim = matches[0][1] if matches else None
        target_rank, target_sim = gallery.find_rank(embedding, card_id)
        retrieval_results.append({
            "card_id": card_id, "transform": transform_name,
            "top1_correct": ranked_ids[:1] == [card_id],
            "top3_correct": card_id in ranked_ids[:3],
            "top5_correct": card_id in ranked_ids[:5],
            "target_rank": target_rank, "target_similarity": target_sim, "top1_similarity": top1_sim,
        })

    false_target_match_results = []
    for family, ids in by_family.items():
        for true_id, claimed_id in itertools.permutations(ids, 2):
            for transform_name in BENCHMARK_TRANSFORM_NAMES:
                embedding = query_embeddings[(true_id, transform_name)]
                matches = gallery.search(embedding, top_k=5)
                top1_entry, top1_sim = matches[0]
                top2_sim = matches[1][1] if len(matches) > 1 else None
                claimed_rank, claimed_sim = gallery.find_rank(embedding, claimed_id)
                margin = (top1_sim - top2_sim) if top2_sim is not None else None
                gap = (top1_sim - claimed_sim) if claimed_sim is not None else None

                would_match = (
                    claimed_rank == 1
                    and claimed_sim is not None and claimed_sim >= MATCH_MIN_SIMILARITY_FLOOR
                    and margin is not None and margin >= MATCH_MIN_MARGIN_OVER_RUNNER_UP
                )
                false_target_match_results.append({
                    "true_card_id": true_id, "falsely_claimed_target_id": claimed_id, "family": family,
                    "transform": transform_name, "claimed_rank": claimed_rank, "claimed_similarity": claimed_sim,
                    "top1_card_id": top1_entry.canonical_card_id, "top1_similarity": top1_sim,
                    "would_emit_match": would_match,
                })
            # keep runtime bounded -- one true/claimed pair per family per
            # unordered combination is already the full same-family hard-
            # negative universe; permutations covers both directions.

    def _rate(results: list[dict[str, Any]], key: str) -> float:
        return round(sum(1 for r in results if r[key]) / len(results), 6) if results else 0.0

    summary = {
        "method_version": METHOD_VERSION,
        "model_version": MODEL_NAME,
        "model_license": MODEL_LICENSE,
        "preprocessing_version": PREPROCESSING_VERSION,
        "gallery_size": len(manifest),
        "gallery_families": {k: len(v) for k, v in by_family.items()},
        "gallery_build_seconds": round(gallery_build_seconds, 3),
        "query_embedding_seconds_total": round(query_embedding_seconds, 3),
        "query_embedding_seconds_per_image": round(query_embedding_seconds / max(len(query_embeddings), 1), 4),
        "retrieval_queries": len(retrieval_results),
        "top1_accuracy": _rate(retrieval_results, "top1_correct"),
        "top3_accuracy": _rate(retrieval_results, "top3_correct"),
        "top5_accuracy": _rate(retrieval_results, "top5_correct"),
        "false_target_match_pairs": len(false_target_match_results),
        "false_target_match_rate": _rate(false_target_match_results, "would_emit_match"),
        "thresholds": {
            "MATCH_MIN_SIMILARITY_FLOOR": MATCH_MIN_SIMILARITY_FLOOR,
            "MATCH_MIN_MARGIN_OVER_RUNNER_UP": MATCH_MIN_MARGIN_OVER_RUNNER_UP,
            "MISMATCH_MIN_TOP1_ADVANTAGE_OVER_TARGET": MISMATCH_MIN_TOP1_ADVANTAGE_OVER_TARGET,
        },
    }

    return {
        "summary": summary,
        "detail": {"retrieval_results": retrieval_results, "false_target_match_results": false_target_match_results},
        "manifest": manifest,
    }


def dataset_fingerprint(manifest: list[dict[str, Any]]) -> str:
    material = "\n".join(sorted(f"{m['id']}:{Path(m['image_path']).stat().st_size}" for m in manifest))
    return hashlib.sha256(material.encode()).hexdigest()


def main() -> dict[str, Any]:
    result = run_benchmark()
    BENCHMARK_OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    output = main()
    print(json.dumps(output["summary"], indent=2))
