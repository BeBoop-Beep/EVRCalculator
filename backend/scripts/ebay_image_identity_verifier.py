"""IMAGE-v1: local, free, CPU-only image identity verifier (EBAY_E2_6).

Compares a canonical target-card image against an eBay listing image and
decides whether they visually depict the SAME printed card (exact
card/collector-number/treatment identity), returning one of:

    MATCH        -- strong visual evidence of the same physical card
    MISMATCH     -- strong visual evidence of a DIFFERENT physical card
    UNVERIFIED   -- insufficient evidence either way (never a guess)

This module is an ADDITIONAL identity guard layered AFTER the D3-v5 text
matcher -- it never replaces text matching, and it must never be confused
with a "D3-v6" text-rule revision (there is none; D3-v5 is untouched).

COST: 100% local/open-source, CPU-only. No paid vision API, no billing
service of any kind is called. Dependencies: opencv-python-headless (BSD),
numpy, Pillow -- all free, already-installable OSS.

FAIL-CLOSED DESIGN: precision on MATCH dominates coverage. A wrong physical
card classified MATCH is the catastrophic error this module exists to
avoid; an ambiguous pair reported UNVERIFIED is always preferred over a
guessed MATCH. Thresholds are frozen (see
ebay_image_identity_verifier_v1_freeze_manifest.json) from a development
dataset that deliberately excludes every consumed V4/V5 blind-cohort row --
see backend/scripts/build_ebay_image_identity_dev_dataset.py.
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - environment guard, not a code path under test
    raise RuntimeError(
        "ebay_image_identity_verifier requires opencv-python-headless (free/local/BSD). "
        "Install with: pip install opencv-python-headless"
    ) from exc

from PIL import Image, UnidentifiedImageError

METHOD_VERSION = "ebay_image_identity_verifier_v1"

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "backend/artifacts/index_fair_value/ebay_image_identity_cache"

# --------------------------------------------------------------------------
# Bounded fetch/cache layer
# --------------------------------------------------------------------------

FETCH_TIMEOUT_SECONDS = 10
MAX_IMAGE_BYTES = 8_000_000  # 8 MB hard cap -- refuse anything larger, no streaming re-attempt
ALLOWED_CONTENT_TYPE_PREFIXES = ("image/jpeg", "image/png", "image/webp", "image/jpg")
USER_AGENT = "Mozilla/5.0 (inDex-image-identity-verifier/1.0)"

# eBay's own CDN accepts a same-image, higher-resolution filename swap with
# zero extra API calls (s-l225.jpg -> s-l1600.jpg is the SAME photo at
# ~4-6x the linear resolution). Verified during E2.6 audit: a 225px
# thumbnail (bounded to ~20KB) upgrades to a ~1000x1400px, ~450-700KB image
# via this swap alone. This is the single highest-leverage, zero-cost change
# available -- ORB feature matching is far more reliable against real
# resolution than a 225px thumbnail.
EBAY_THUMBNAIL_SUFFIXES = ("s-l225.jpg", "s-l300.jpg", "s-l400.jpg", "s-l500.jpg", "s-l64.jpg")
EBAY_HIRES_SUFFIX = "s-l1600.jpg"


def upgrade_ebay_image_url(url: str) -> str:
    """Swap a known eBay CDN thumbnail suffix for the same photo's
    high-resolution variant. Any URL not matching a known thumbnail suffix
    (including non-eBay URLs) passes through unchanged.
    """
    for suffix in EBAY_THUMBNAIL_SUFFIXES:
        if url.endswith(suffix):
            return url[: -len(suffix)] + EBAY_HIRES_SUFFIX
    return url


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def fetch_image_bytes(url: str, cache_dir: Optional[Path] = None) -> Optional[bytes]:
    """Bounded, cached, single-attempt fetch. NEVER raises -- any failure
    (timeout, HTTP error, oversized body, wrong content-type, network error)
    returns None, which downstream becomes UNVERIFIED. No infinite retry: at
    most one network attempt per call.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{_cache_key(url)}.bin"
    if cache_path.exists():
        data = cache_path.read_bytes()
        return data if data else None
    marker_path = cache_dir / f"{_cache_key(url)}.failed"
    if marker_path.exists():
        return None  # a prior fetch failed -- do not repeatedly retry the same URL

    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            if not any(content_type.startswith(p) for p in ALLOWED_CONTENT_TYPE_PREFIXES):
                marker_path.write_text(f"bad_content_type:{content_type}", encoding="utf-8")
                return None
            body = response.read(MAX_IMAGE_BYTES + 1)
            if len(body) > MAX_IMAGE_BYTES:
                marker_path.write_text("oversized", encoding="utf-8")
                return None
    except (URLError, HTTPError, TimeoutError, OSError, ValueError):
        marker_path.write_text("fetch_error", encoding="utf-8")
        return None

    cache_path.write_bytes(body)
    return body


def decode_image(data: bytes) -> Optional[np.ndarray]:
    """Decode bytes to a BGR uint8 numpy array (OpenCV convention). Returns
    None for any corrupt/unreadable/zero-size image -- never raises.
    """
    if not data:
        return None
    try:
        pil_image = Image.open(io.BytesIO(data))
        pil_image = pil_image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    rgb = np.array(pil_image)
    if rgb.size == 0:
        return None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# --------------------------------------------------------------------------
# Card-region detection (best-effort; never blocks the pipeline on failure)
# --------------------------------------------------------------------------


def detect_card_region(image: np.ndarray) -> tuple[Optional[np.ndarray], bool]:
    """Best-effort detection of the largest quadrilateral (the physical
    card) in a listing photo, returning a perspective-rectified crop.
    Returns (None, False) on any failure -- callers fall back to matching
    against the full original image, which ORB handles reasonably for
    moderate backgrounds.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 120)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, False

        image_area = image.shape[0] * image.shape[1]
        best_quad = None
        best_area = 0.0
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) != 4:
                continue
            area = cv2.contourArea(approx)
            if area < 0.25 * image_area:  # card should occupy a meaningful fraction of the photo
                continue
            if area > best_area:
                best_area = area
                best_quad = approx

        if best_quad is None:
            return None, False

        pts = best_quad.reshape(4, 2).astype("float32")
        rect = _order_quad_points(pts)
        (tl, tr, br, bl) = rect
        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = max(int(width_a), int(width_b))
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = max(int(height_a), int(height_b))
        if max_width < 20 or max_height < 20:
            return None, False

        dst = np.array(
            [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
            dtype="float32",
        )
        matrix = cv2.getPerspectiveTransform(rect, dst)
        rectified = cv2.warpPerspective(image, matrix, (max_width, max_height))
        return rectified, True
    except cv2.error:
        return None, False


def _order_quad_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


# --------------------------------------------------------------------------
# Perceptual hash (secondary signal only -- never authoritative alone)
# --------------------------------------------------------------------------


def perceptual_hash(image: np.ndarray, hash_size: int = 8) -> int:
    """dHash (difference hash): robust to minor resize/compression, brittle
    to rotation/perspective -- used only as a secondary diagnostic, never as
    sole MATCH evidence (see module docstring / freeze manifest).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = 0
    for bit in diff.flatten():
        bits = (bits << 1) | int(bit)
    return bits


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# --------------------------------------------------------------------------
# ORB feature matching + RANSAC homography (primary signal)
# --------------------------------------------------------------------------

ORB_N_FEATURES = 2000
RATIO_TEST_THRESHOLD = 0.75
RANSAC_REPROJ_THRESHOLD_PX = 6.0
MIN_GOOD_MATCHES_FOR_HOMOGRAPHY = 8


def orb_feature_match(image_a: np.ndarray, image_b: np.ndarray) -> dict[str, Any]:
    orb = cv2.ORB_create(nfeatures=ORB_N_FEATURES)
    kp_a, des_a = orb.detectAndCompute(image_a, None)
    kp_b, des_b = orb.detectAndCompute(image_b, None)

    result: dict[str, Any] = {
        "feature_count_a": len(kp_a) if kp_a else 0,
        "feature_count_b": len(kp_b) if kp_b else 0,
        "good_match_count": 0,
        "homography_inlier_count": 0,
        "homography_inlier_ratio": 0.0,
    }
    if des_a is None or des_b is None or len(des_a) < 2 or len(des_b) < 2:
        return result

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(des_a, des_b, k=2)
    good_matches = [m for pair in raw_matches if len(pair) == 2 for m, n in [pair] if m.distance < RATIO_TEST_THRESHOLD * n.distance]
    result["good_match_count"] = len(good_matches)
    if len(good_matches) < MIN_GOOD_MATCHES_FOR_HOMOGRAPHY:
        return result

    src_pts = np.float32([kp_a[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_b[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD_PX)
    if mask is None:
        return result
    inliers = int(mask.sum())
    result["homography_inlier_count"] = inliers
    result["homography_inlier_ratio"] = round(inliers / len(good_matches), 6) if good_matches else 0.0
    return result


# --------------------------------------------------------------------------
# Decision thresholds -- FROZEN. Selected via the development dataset
# (build_ebay_image_identity_dev_dataset.py / benchmark_ebay_image_identity_verifier.py),
# NEVER via D4-0375/D5-0054/D5-0224/D5-0378 (the consumed blind rows this
# module exists to eventually help catch). See
# ebay_image_identity_verifier_v1_freeze_manifest.json for the frozen record.
# --------------------------------------------------------------------------

MATCH_MIN_INLIER_COUNT = 12
MATCH_MIN_INLIER_RATIO = 0.45
MISMATCH_MAX_INLIER_RATIO = 0.15
MISMATCH_MIN_GOOD_MATCHES = MIN_GOOD_MATCHES_FOR_HOMOGRAPHY


@dataclass
class ImageIdentityResult:
    image_identity_state: str  # MATCH | MISMATCH | UNVERIFIED
    method_version: str = METHOD_VERSION
    canonical_image_available: bool = False
    listing_image_available: bool = False
    card_region_detected: bool = False
    feature_count: int = 0
    good_match_count: int = 0
    homography_inlier_count: int = 0
    homography_inlier_ratio: float = 0.0
    perceptual_hash_distance: Optional[int] = None
    embedding_similarity: Optional[float] = None  # not researched in this pass -- always None
    verification_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_image_identity(
    canonical_image_url: str, listing_image_url: str, cache_dir: Optional[Path] = None,
) -> ImageIdentityResult:
    """The public entrypoint. Never raises. Always returns a fully-populated
    ImageIdentityResult, defaulting to UNVERIFIED on any missing/undecodable
    input -- this is the fail-closed contract.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR

    canonical_bytes = fetch_image_bytes(canonical_image_url, cache_dir) if canonical_image_url else None
    listing_url = upgrade_ebay_image_url(listing_image_url) if listing_image_url else None
    listing_bytes = fetch_image_bytes(listing_url, cache_dir) if listing_url else None

    canonical_available = canonical_bytes is not None
    listing_available = listing_bytes is not None

    if not canonical_available or not listing_available:
        return ImageIdentityResult(
            image_identity_state="UNVERIFIED",
            canonical_image_available=canonical_available,
            listing_image_available=listing_available,
            verification_reason="canonical_or_listing_image_unavailable",
        )

    canonical_image = decode_image(canonical_bytes)
    listing_image = decode_image(listing_bytes)
    if canonical_image is None or listing_image is None:
        return ImageIdentityResult(
            image_identity_state="UNVERIFIED",
            canonical_image_available=canonical_available,
            listing_image_available=listing_available,
            verification_reason="corrupt_or_undecodable_image",
        )

    rectified, region_detected = detect_card_region(listing_image)
    match_target = rectified if region_detected else listing_image

    match = orb_feature_match(canonical_image, match_target)
    phash_distance = hamming_distance(perceptual_hash(canonical_image), perceptual_hash(match_target))

    feature_count = min(match["feature_count_a"], match["feature_count_b"])
    good_matches = match["good_match_count"]
    inlier_count = match["homography_inlier_count"]
    inlier_ratio = match["homography_inlier_ratio"]

    if good_matches >= MATCH_MIN_INLIER_COUNT and inlier_count >= MATCH_MIN_INLIER_COUNT and inlier_ratio >= MATCH_MIN_INLIER_RATIO:
        state = "MATCH"
        reason = "sufficient_ransac_inliers"
    elif good_matches >= MISMATCH_MIN_GOOD_MATCHES and inlier_ratio <= MISMATCH_MAX_INLIER_RATIO:
        state = "MISMATCH"
        reason = "low_inlier_ratio_despite_sufficient_candidate_matches"
    else:
        state = "UNVERIFIED"
        reason = "insufficient_feature_evidence_for_a_confident_decision"

    return ImageIdentityResult(
        image_identity_state=state,
        canonical_image_available=canonical_available,
        listing_image_available=listing_available,
        card_region_detected=region_detected,
        feature_count=feature_count,
        good_match_count=good_matches,
        homography_inlier_count=inlier_count,
        homography_inlier_ratio=inlier_ratio,
        perceptual_hash_distance=phash_distance,
        embedding_similarity=None,
        verification_reason=reason,
    )


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: python -m backend.scripts.ebay_image_identity_verifier <canonical_url> <listing_url>")
        raise SystemExit(2)
    print(json.dumps(verify_image_identity(sys.argv[1], sys.argv[2]).to_dict(), indent=2))
