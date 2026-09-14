"""IMAGE-v2 (research candidate): exact-card visual identity via RETRIEVAL,
not pairwise template matching (EBAY_E2_7).

E2.6 rejected pairwise ORB+RANSAC-homography matching
(EBAY_IMAGE_VERIFICATION_NOT_VIABLE_HARD_NEGATIVE_FALSE_MATCH_RATE) because
shared card-frame/border/holo-pattern template features produced spurious
geometric agreement between DIFFERENT printed cards. This module reframes
the problem as RETRIEVAL: embed the listing photo with a general-purpose,
frozen, local vision backbone (DINOv2-small, Apache 2.0, Meta AI), search a
precomputed canonical-card gallery by cosine similarity, and require the
CLAIMED target identity to be the clear winner among ALL competing
canonical identities -- not merely "similar enough" to the target alone.

100% local / free / CPU-capable for production inference. No paid vision
API of any kind. DINOv2-small (facebook/dinov2-small on HuggingFace,
Apache 2.0 license) runs a single forward pass per image on ordinary CPU.

FAIL-CLOSED: MATCH requires the target to win rank 1 AND clear a
development-supported similarity floor AND a margin over the runner-up.
Any of: crop failure, missing canonical image, weak margin, or an ambiguous
near-duplicate canonical -> UNVERIFIED, never a guessed MATCH.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from backend.scripts.ebay_image_identity_verifier import (
    decode_image,
    detect_card_region,
    fetch_image_bytes,
    upgrade_ebay_image_url,
)

METHOD_VERSION = "ebay_image_retrieval_verifier_v2"
MODEL_NAME = "facebook/dinov2-small"
MODEL_LICENSE = "Apache-2.0"  # https://huggingface.co/facebook/dinov2-small (Meta AI, DINOv2)
PREPROCESSING_VERSION = "dinov2_small_default_processor_v1"

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "backend/artifacts/index_fair_value/ebay_image_identity_cache"
GALLERY_EMBEDDING_CACHE_DIR = ROOT / "backend/artifacts/index_fair_value/ebay_image_retrieval_embedding_cache"

_MODEL_STATE: dict[str, Any] = {}


def _lazy_load_model():
    if "processor" in _MODEL_STATE:
        return _MODEL_STATE["processor"], _MODEL_STATE["model"]
    import torch
    from transformers import AutoImageProcessor, AutoModel

    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()
    torch.set_grad_enabled(False)
    _MODEL_STATE["processor"] = processor
    _MODEL_STATE["model"] = model
    _MODEL_STATE["torch"] = torch
    return processor, model


def image_fingerprint(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def embed_image_bgr(image_bgr: np.ndarray) -> np.ndarray:
    """Runs the frozen DINOv2-small backbone on a BGR numpy image (OpenCV
    convention, matching ebay_image_identity_verifier.decode_image) and
    returns an L2-normalized embedding vector (CLS token, 384-dim for
    dinov2-small). Deterministic: no dropout/augmentation at inference.
    """
    import cv2

    processor, model = _lazy_load_model()
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    inputs = processor(images=rgb, return_tensors="pt")
    outputs = model(**inputs)
    cls_embedding = outputs.last_hidden_state[:, 0, :].detach().numpy()[0]
    norm = np.linalg.norm(cls_embedding)
    if norm > 0:
        cls_embedding = cls_embedding / norm
    return cls_embedding.astype(np.float32)


def embedding_fingerprint(embedding: np.ndarray) -> str:
    return hashlib.sha256(np.round(embedding, 6).tobytes()).hexdigest()


# --------------------------------------------------------------------------
# Canonical gallery
# --------------------------------------------------------------------------


@dataclass
class GalleryEntry:
    canonical_card_id: str
    card_variant_id: Optional[str]
    set_id: Optional[str]
    card_name: str
    collector_number: Optional[str]
    treatment: Optional[str]
    canonical_image_url: str
    image_fingerprint: str
    embedding_fingerprint: str
    model_version: str
    preprocessing_version: str


class CanonicalGallery:
    """A precomputed, cached gallery of canonical-card embeddings. Embeddings
    are computed ONCE per distinct canonical image (keyed by image
    fingerprint) and cached to disk -- re-embedding the same canonical
    image for every listing candidate never happens.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or GALLERY_EMBEDDING_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[GalleryEntry] = []
        self.embeddings: list[np.ndarray] = []

    def _embedding_cache_path(self, image_fp: str) -> Path:
        return self.cache_dir / f"{image_fp}.npy"

    def add(
        self, canonical_card_id: str, canonical_image_url: str, image_bytes: bytes,
        card_name: str = "", collector_number: Optional[str] = None, treatment: Optional[str] = None,
        card_variant_id: Optional[str] = None, set_id: Optional[str] = None,
    ) -> GalleryEntry:
        image_fp = image_fingerprint(image_bytes)
        cache_path = self._embedding_cache_path(image_fp)
        if cache_path.exists():
            embedding = np.load(cache_path)
        else:
            image = decode_image(image_bytes)
            if image is None:
                raise ValueError(f"undecodable canonical image for {canonical_card_id}")
            embedding = embed_image_bgr(image)
            np.save(cache_path, embedding)

        entry = GalleryEntry(
            canonical_card_id=canonical_card_id, card_variant_id=card_variant_id, set_id=set_id,
            card_name=card_name, collector_number=collector_number, treatment=treatment,
            canonical_image_url=canonical_image_url, image_fingerprint=image_fp,
            embedding_fingerprint=embedding_fingerprint(embedding), model_version=MODEL_NAME,
            preprocessing_version=PREPROCESSING_VERSION,
        )
        self.entries.append(entry)
        self.embeddings.append(embedding)
        return entry

    def matrix(self) -> np.ndarray:
        return np.vstack(self.embeddings) if self.embeddings else np.zeros((0, 384), dtype=np.float32)

    def search(self, query_embedding: np.ndarray, top_k: int = 25) -> list[tuple[GalleryEntry, float]]:
        if not self.entries:
            return []
        sims = self.matrix() @ query_embedding
        order = np.argsort(-sims)[:top_k]
        return [(self.entries[i], float(sims[i])) for i in order]

    def find_rank(self, query_embedding: np.ndarray, canonical_card_id: str) -> tuple[Optional[int], Optional[float]]:
        """Full-gallery rank (1-indexed) and similarity of the FIRST entry
        matching canonical_card_id -- never limited to top_k, since the
        retrieval contract needs the target's true rank even when it falls
        outside the top-K window.
        """
        if not self.entries:
            return None, None
        sims = self.matrix() @ query_embedding
        order = np.argsort(-sims)
        for rank, idx in enumerate(order, start=1):
            if self.entries[idx].canonical_card_id == canonical_card_id:
                return rank, float(sims[idx])
        return None, None


# --------------------------------------------------------------------------
# Retrieval contract + decision policy
# --------------------------------------------------------------------------

# FROZEN THRESHOLDS -- selected via the E2.7 development dataset only (see
# benchmark_ebay_image_retrieval_verifier.py), never via the consumed V4/V5
# blind failure rows. See ebay_image_retrieval_verifier_v2_freeze_manifest.json
# for the frozen record (present only if a candidate was actually frozen).
MATCH_MIN_SIMILARITY_FLOOR = 0.75
MATCH_MIN_MARGIN_OVER_RUNNER_UP = 0.05
MISMATCH_MIN_TOP1_ADVANTAGE_OVER_TARGET = 0.05


@dataclass
class RetrievalResult:
    image_identity_state: str  # MATCH | MISMATCH | UNVERIFIED
    method_version: str = METHOD_VERSION
    model_version: str = MODEL_NAME
    canonical_image_available: bool = False
    listing_image_available: bool = False
    card_region_detected: bool = False
    target_card_id: str = ""
    target_rank: Optional[int] = None
    target_similarity: Optional[float] = None
    top1_card_id: Optional[str] = None
    top1_similarity: Optional[float] = None
    top2_similarity: Optional[float] = None
    target_vs_top1_gap: Optional[float] = None
    top1_vs_top2_margin: Optional[float] = None
    verification_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_by_retrieval(
    gallery: CanonicalGallery, target_card_id: str, listing_image_url: str, cache_dir: Optional[Path] = None,
) -> RetrievalResult:
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    listing_url = upgrade_ebay_image_url(listing_image_url) if listing_image_url else None
    listing_bytes = fetch_image_bytes(listing_url, cache_dir) if listing_url else None
    listing_available = listing_bytes is not None
    canonical_available = any(e.canonical_card_id == target_card_id for e in gallery.entries)

    if not listing_available or not canonical_available:
        return RetrievalResult(
            image_identity_state="UNVERIFIED", target_card_id=target_card_id,
            canonical_image_available=canonical_available, listing_image_available=listing_available,
            verification_reason="canonical_or_listing_image_unavailable",
        )

    listing_image = decode_image(listing_bytes)
    if listing_image is None:
        return RetrievalResult(
            image_identity_state="UNVERIFIED", target_card_id=target_card_id,
            canonical_image_available=canonical_available, listing_image_available=listing_available,
            verification_reason="corrupt_or_undecodable_image",
        )

    rectified, region_detected = detect_card_region(listing_image)
    match_target = rectified if region_detected else listing_image

    query_embedding = embed_image_bgr(match_target)
    top_matches = gallery.search(query_embedding, top_k=25)
    if not top_matches:
        return RetrievalResult(
            image_identity_state="UNVERIFIED", target_card_id=target_card_id,
            canonical_image_available=canonical_available, listing_image_available=listing_available,
            card_region_detected=region_detected, verification_reason="empty_gallery",
        )

    target_rank, target_similarity = gallery.find_rank(query_embedding, target_card_id)
    top1_entry, top1_similarity = top_matches[0]
    top2_similarity = top_matches[1][1] if len(top_matches) > 1 else None
    target_vs_top1_gap = (top1_similarity - target_similarity) if target_similarity is not None else None
    top1_vs_top2_margin = (top1_similarity - top2_similarity) if top2_similarity is not None else None

    result_kwargs = dict(
        target_card_id=target_card_id, canonical_image_available=canonical_available,
        listing_image_available=listing_available, card_region_detected=region_detected,
        target_rank=target_rank, target_similarity=target_similarity,
        top1_card_id=top1_entry.canonical_card_id, top1_similarity=top1_similarity,
        top2_similarity=top2_similarity, target_vs_top1_gap=target_vs_top1_gap,
        top1_vs_top2_margin=top1_vs_top2_margin,
    )

    if (
        target_rank == 1
        and target_similarity is not None and target_similarity >= MATCH_MIN_SIMILARITY_FLOOR
        and top1_vs_top2_margin is not None and top1_vs_top2_margin >= MATCH_MIN_MARGIN_OVER_RUNNER_UP
    ):
        return RetrievalResult(image_identity_state="MATCH", verification_reason="target_rank1_with_sufficient_margin", **result_kwargs)

    if (
        target_rank != 1
        and target_vs_top1_gap is not None and target_vs_top1_gap >= MISMATCH_MIN_TOP1_ADVANTAGE_OVER_TARGET
    ):
        return RetrievalResult(image_identity_state="MISMATCH", verification_reason="another_identity_clearly_preferred_over_target", **result_kwargs)

    return RetrievalResult(image_identity_state="UNVERIFIED", verification_reason="insufficient_rank_or_margin_evidence", **result_kwargs)


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


if __name__ == "__main__":
    import sys

    print("This module is a library; use benchmark_ebay_image_retrieval_verifier.py to run research.", file=sys.stderr)
    raise SystemExit(2)
