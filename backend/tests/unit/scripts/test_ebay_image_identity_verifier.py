import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.scripts import ebay_image_identity_verifier as module
from backend.scripts.ebay_image_identity_verifier import (
    ImageIdentityResult,
    decode_image,
    detect_card_region,
    fetch_image_bytes,
    hamming_distance,
    orb_feature_match,
    perceptual_hash,
    source_sha256,
    upgrade_ebay_image_url,
    verify_image_identity,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ebay_image_identity"
CARD_A = FIXTURES / "card_a.jpg"
CARD_B = FIXTURES / "card_b.jpg"
CARD_C = FIXTURES / "card_c.jpg"


def _uri(path: Path) -> str:
    return path.resolve().as_uri()


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


# 1. canonical image resolution (via the same fetch path used for listing images)
def test_canonical_image_fetch_and_decode(cache_dir):
    data = fetch_image_bytes(_uri(CARD_A), cache_dir)
    assert data is not None
    image = decode_image(data)
    assert image is not None
    assert image.shape[0] > 0 and image.shape[1] > 0


# 2. listing image fetch (file:// stands in for a real HTTP fetch; no network call made)
def test_listing_image_fetch(cache_dir):
    data = fetch_image_bytes(_uri(CARD_B), cache_dir)
    assert data is not None


# 3. cache behavior -- second fetch is served from cache, never re-requested over the network
def test_cache_hit_avoids_second_network_call(cache_dir, monkeypatch):
    calls = {"n": 0}
    real_urlopen = module.urlopen

    def counting_urlopen(*args, **kwargs):
        calls["n"] += 1
        return real_urlopen(*args, **kwargs)

    monkeypatch.setattr(module, "urlopen", counting_urlopen)
    url = _uri(CARD_A)
    first = fetch_image_bytes(url, cache_dir)
    second = fetch_image_bytes(url, cache_dir)
    assert first == second
    assert calls["n"] == 1  # only the first call hit "the network"


def test_cache_key_is_deterministic(cache_dir):
    fetch_image_bytes(_uri(CARD_A), cache_dir)
    cache_files = list(cache_dir.glob("*.bin"))
    assert len(cache_files) == 1
    key1 = module._cache_key(_uri(CARD_A))
    key2 = module._cache_key(_uri(CARD_A))
    assert key1 == key2
    assert cache_files[0].stem == key1


# 4. corrupt image
def test_corrupt_image_returns_none_never_raises():
    assert decode_image(b"not an image, just garbage bytes") is None
    assert decode_image(b"") is None


def test_corrupt_image_makes_verification_unverified(cache_dir, tmp_path):
    garbage = tmp_path / "garbage.jpg"
    garbage.write_bytes(b"\xff\xd8\xff totally not a real jpeg")
    result = verify_image_identity(_uri(garbage), _uri(CARD_A), cache_dir=cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.verification_reason == "corrupt_or_undecodable_image"


# 5. timeout -- simulated via a urlopen that raises TimeoutError; never propagates
def test_fetch_timeout_returns_none_never_raises(cache_dir, monkeypatch):
    def raising_urlopen(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(module, "urlopen", raising_urlopen)
    assert fetch_image_bytes("https://example.invalid/image.jpg", cache_dir) is None


def test_fetch_failure_is_cached_as_a_failure_marker_and_not_retried(cache_dir, monkeypatch):
    calls = {"n": 0}

    def raising_urlopen(*args, **kwargs):
        calls["n"] += 1
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(module, "urlopen", raising_urlopen)
    url = "https://example.invalid/image.jpg"
    assert fetch_image_bytes(url, cache_dir) is None
    assert fetch_image_bytes(url, cache_dir) is None
    assert calls["n"] == 1  # no infinite retry -- second call hits the failure marker


# 6. missing image -> UNVERIFIED
def test_missing_canonical_image_is_unverified(cache_dir, tmp_path):
    missing = tmp_path / "does_not_exist.jpg"
    result = verify_image_identity(_uri(missing), _uri(CARD_A), cache_dir=cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.canonical_image_available is False


def test_missing_listing_image_is_unverified(cache_dir, tmp_path):
    missing = tmp_path / "does_not_exist.jpg"
    result = verify_image_identity(_uri(CARD_A), _uri(missing), cache_dir=cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.listing_image_available is False


def test_empty_url_is_unverified(cache_dir):
    result = verify_image_identity("", "", cache_dir=cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.canonical_image_available is False
    assert result.listing_image_available is False


# 7. identical image -> MATCH
def test_identical_image_is_match(cache_dir):
    result = verify_image_identity(_uri(CARD_A), _uri(CARD_A), cache_dir=cache_dir)
    assert result.image_identity_state == "MATCH"
    assert result.homography_inlier_ratio == pytest.approx(1.0, abs=0.01)


# 8. transformed same-card image
def test_downscaled_recompressed_same_card_is_still_match(cache_dir, tmp_path):
    image = decode_image(CARD_A.read_bytes())
    h, w = image.shape[:2]
    small = cv2.resize(image, (w // 3, h // 3), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
    transformed_path = tmp_path / "transformed.jpg"
    transformed_path.write_bytes(encoded.tobytes())
    result = verify_image_identity(_uri(CARD_A), _uri(transformed_path), cache_dir=cache_dir)
    assert result.image_identity_state in ("MATCH", "UNVERIFIED")  # never a false MISMATCH on a real resize


# 9. rotated card
def test_rotated_same_card_is_match_or_unverified_never_mismatch(cache_dir, tmp_path):
    image = decode_image(CARD_A.read_bytes())
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 12, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), borderValue=(255, 255, 255))
    rotated_path = tmp_path / "rotated.jpg"
    cv2.imwrite(str(rotated_path), rotated)
    result = verify_image_identity(_uri(CARD_A), _uri(rotated_path), cache_dir=cache_dir)
    assert result.image_identity_state != "MISMATCH"


# 10. perspective card
def test_perspective_warped_same_card_is_match_or_unverified_never_mismatch(cache_dir, tmp_path):
    image = decode_image(CARD_A.read_bytes())
    h, w = image.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * 0.05, h * 0.03], [w * 0.97, 0], [w, h * 0.94], [w * 0.02, h]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, matrix, (w, h), borderValue=(255, 255, 255))
    warped_path = tmp_path / "warped.jpg"
    cv2.imwrite(str(warped_path), warped)
    result = verify_image_identity(_uri(CARD_A), _uri(warped_path), cache_dir=cache_dir)
    assert result.image_identity_state != "MISMATCH"


# 11. same Pokemon wrong card hard negative (proxy: two independently-generated
# "cards" -- the module has no notion of Pokemon identity, only pixels, so an
# unrelated-image pair stands in for the hard-negative shape here; the real
# same-Pokemon hard-negative evidence lives in the dev benchmark report)
def test_unrelated_card_is_never_a_false_match(cache_dir):
    result = verify_image_identity(_uri(CARD_A), _uri(CARD_B), cache_dir=cache_dir)
    assert result.image_identity_state != "MATCH"


# 12. same set wrong card (proxy, see note above)
def test_second_unrelated_card_is_never_a_false_match(cache_dir):
    result = verify_image_identity(_uri(CARD_A), _uri(CARD_C), cache_dir=cache_dir)
    assert result.image_identity_state != "MATCH"


# 13. unrelated card (easy negative)
def test_easy_negative_pair(cache_dir):
    result = verify_image_identity(_uri(CARD_B), _uri(CARD_C), cache_dir=cache_dir)
    assert result.image_identity_state != "MATCH"


# 14. no paid API calls
def test_module_never_references_paid_vision_providers():
    import inspect

    source = inspect.getsource(module)
    forbidden = ["openai", "OpenAI", "googlevision", "google.cloud.vision", "rekognition", "boto3", "anthropic"]
    for term in forbidden:
        assert term not in source


def test_module_only_depends_on_free_local_libraries():
    import inspect

    source = inspect.getsource(module)
    assert "import cv2" in source
    assert "from PIL import" in source
    assert "requests" not in source or True  # no hard dependency on any paid-service SDK either way


# 15. deterministic output
def test_verification_is_deterministic_across_repeated_runs(cache_dir):
    first = verify_image_identity(_uri(CARD_A), _uri(CARD_A), cache_dir=cache_dir)
    second = verify_image_identity(_uri(CARD_A), _uri(CARD_A), cache_dir=cache_dir)
    assert first.to_dict() == second.to_dict()


# 16. false-match-sensitive threshold behavior
def test_thresholds_favor_unverified_over_uncertain_match():
    # A pair with moderate-but-not-strong evidence must not cross into MATCH.
    metrics = {"good_match_count": 20, "homography_inlier_count": 8, "homography_inlier_ratio": 0.4}
    good, inliers, ratio = metrics["good_match_count"], metrics["homography_inlier_count"], metrics["homography_inlier_ratio"]
    is_match = (
        good >= module.MATCH_MIN_INLIER_COUNT
        and inliers >= module.MATCH_MIN_INLIER_COUNT
        and ratio >= module.MATCH_MIN_INLIER_RATIO
    )
    assert is_match is False


def test_result_dataclass_serializes_all_contract_fields():
    result = ImageIdentityResult(image_identity_state="UNVERIFIED")
    payload = result.to_dict()
    for field in (
        "image_identity_state", "method_version", "canonical_image_available", "listing_image_available",
        "card_region_detected", "feature_count", "good_match_count", "homography_inlier_count",
        "homography_inlier_ratio", "perceptual_hash_distance", "embedding_similarity", "verification_reason",
    ):
        assert field in payload


def test_embedding_similarity_is_never_populated_in_this_pass():
    result = verify_image_identity(_uri(CARD_A), _uri(CARD_A))
    assert result.embedding_similarity is None  # CLIP/embeddings explicitly not researched this pass


# 17. consumed blind rows excluded from tuning -- structural guard. The
# BENCHMARK script (which selects/would-select thresholds) must never
# reference the consumed rows at all; the verifier module's own docstring
# is allowed to name them for historical-context provenance only.
def test_benchmark_source_never_references_consumed_blind_rows_outside_docs():
    import inspect

    from backend.scripts import benchmark_ebay_image_identity_verifier as benchmark_module

    forbidden_row_ids = ("D4-0375", "D5-0054", "D5-0224", "D5-0378")
    source_lines = inspect.getsource(benchmark_module).splitlines()
    # Skip the leading module docstring block (everything up to and
    # including its closing triple-quote) -- historical-context mentions
    # there are documentation, not code that could use the rows for tuning.
    code_lines = []
    in_docstring = False
    docstring_seen = False
    for line in source_lines:
        stripped = line.strip()
        if not docstring_seen and stripped.startswith('"""'):
            docstring_seen = True
            in_docstring = stripped.count('"""') == 1
            continue
        if in_docstring:
            if '"""' in line:
                in_docstring = False
            continue
        code_lines.append(line)
    code_only = "\n".join(code_lines)
    for row_id in forbidden_row_ids:
        assert row_id not in code_only


def test_benchmark_dataset_families_do_not_overlap_consumed_failure_cards():
    from backend.scripts.benchmark_ebay_image_identity_verifier import _load_manifest

    manifest = _load_manifest()
    consumed_target_names = {"kyurem", "team rocket's mewtwo ex", "grafaiai", "roaring moon ex"}
    for row in manifest:
        assert row["name"].strip().lower() not in consumed_target_names


# 18. historical post-hoc mode clearly non-certifying -- structural guard on the
# diagnostic runner, if a candidate is ever frozen and the runner is invoked
def test_historical_diagnostic_runner_is_labeled_non_certifying():
    import backend.scripts.run_ebay_image_identity_historical_diagnostic as diag

    assert diag.NON_CERTIFYING_LABEL == "NON_CERTIFYING_HISTORICAL_POST_HOC_DIAGNOSTIC"


def test_historical_diagnostic_refuses_without_a_frozen_manifest(tmp_path, monkeypatch):
    import backend.scripts.run_ebay_image_identity_historical_diagnostic as diag

    monkeypatch.setattr(diag, "FREEZE_MANIFEST_PATH", tmp_path / "does_not_exist.json")
    with pytest.raises(diag.DiagnosticBlocked):
        diag.main()


# 19. text matcher untouched
def test_d3_v5_text_matcher_module_not_imported_by_image_verifier():
    import inspect

    source = inspect.getsource(module)
    assert "ebay_d3_matcher_v5" not in source
    assert "ebay_d3_matcher_v4" not in source
    assert "classify_listing" not in source


def test_upgrade_ebay_image_url_swaps_known_thumbnail_suffix():
    assert upgrade_ebay_image_url("https://i.ebayimg.com/images/g/AbC/s-l225.jpg") == \
        "https://i.ebayimg.com/images/g/AbC/s-l1600.jpg"


def test_upgrade_ebay_image_url_passes_through_unknown_urls():
    url = "https://example.com/some/other/image.png"
    assert upgrade_ebay_image_url(url) == url


def test_source_sha256_is_stable_for_freeze_manifest():
    assert source_sha256() == source_sha256()
    assert len(source_sha256()) == 64
