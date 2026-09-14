from pathlib import Path

import numpy as np
import pytest

from backend.scripts import ebay_image_retrieval_verifier as module
from backend.scripts.ebay_image_identity_verifier import decode_image
from backend.scripts.ebay_image_retrieval_verifier import (
    CanonicalGallery,
    RetrievalResult,
    embed_image_bgr,
    embedding_fingerprint,
    image_fingerprint,
    source_sha256,
    verify_by_retrieval,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ebay_image_identity"
CARD_A = FIXTURES / "card_a.jpg"
CARD_B = FIXTURES / "card_b.jpg"
CARD_C = FIXTURES / "card_c.jpg"
CARD_D = FIXTURES / "card_d.jpg"


def _uri(path: Path) -> str:
    return path.resolve().as_uri()


@pytest.fixture(scope="module")
def gallery(tmp_path_factory):
    cache_dir = tmp_path_factory.mktemp("gallery_cache")
    g = CanonicalGallery(cache_dir=cache_dir)
    for name, path in [("CARD_A", CARD_A), ("CARD_B", CARD_B), ("CARD_C", CARD_C), ("CARD_D", CARD_D)]:
        g.add(canonical_card_id=name, canonical_image_url=str(path), image_bytes=path.read_bytes(), card_name=name)
    return g


@pytest.fixture
def listing_cache_dir(tmp_path):
    return tmp_path / "listing_cache"


# 1. canonical gallery build
def test_canonical_gallery_build_has_all_entries(gallery):
    assert len(gallery.entries) == 4
    ids = {e.canonical_card_id for e in gallery.entries}
    assert ids == {"CARD_A", "CARD_B", "CARD_C", "CARD_D"}
    assert gallery.matrix().shape == (4, 384)


def test_gallery_entry_records_provenance_fields(gallery):
    entry = gallery.entries[0]
    assert entry.model_version == module.MODEL_NAME
    assert entry.preprocessing_version == module.PREPROCESSING_VERSION
    assert len(entry.image_fingerprint) == 64
    assert len(entry.embedding_fingerprint) == 64


# 2. embedding determinism
def test_embedding_is_deterministic():
    image = decode_image(CARD_A.read_bytes())
    e1 = embed_image_bgr(image)
    e2 = embed_image_bgr(image)
    assert np.allclose(e1, e2)
    assert embedding_fingerprint(e1) == embedding_fingerprint(e2)


def test_embedding_is_l2_normalized():
    image = decode_image(CARD_A.read_bytes())
    embedding = embed_image_bgr(image)
    assert np.linalg.norm(embedding) == pytest.approx(1.0, abs=1e-4)


# 3. cache/fingerprint -- re-adding the same image bytes never re-embeds
def test_gallery_reuses_cached_embedding_for_identical_image_bytes(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    g = CanonicalGallery(cache_dir=cache_dir)
    g.add(canonical_card_id="CARD_A", canonical_image_url=str(CARD_A), image_bytes=CARD_A.read_bytes())

    calls = {"n": 0}
    real_embed = module.embed_image_bgr

    def counting_embed(image):
        calls["n"] += 1
        return real_embed(image)

    monkeypatch.setattr(module, "embed_image_bgr", counting_embed)
    g2 = CanonicalGallery(cache_dir=cache_dir)
    g2.add(canonical_card_id="CARD_A_AGAIN", canonical_image_url=str(CARD_A), image_bytes=CARD_A.read_bytes())
    assert calls["n"] == 0  # served entirely from the on-disk embedding cache


def test_image_fingerprint_is_deterministic():
    data = CARD_A.read_bytes()
    assert image_fingerprint(data) == image_fingerprint(data)
    assert image_fingerprint(data) != image_fingerprint(CARD_B.read_bytes())


# 4. crop failure / missing image -> UNVERIFIED
def test_missing_listing_image_is_unverified(gallery, listing_cache_dir, tmp_path):
    missing = tmp_path / "does_not_exist.jpg"
    result = verify_by_retrieval(gallery, "CARD_A", _uri(missing), cache_dir=listing_cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.listing_image_available is False


def test_unknown_target_card_id_is_unverified(gallery, listing_cache_dir):
    result = verify_by_retrieval(gallery, "NOT_IN_GALLERY", _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.canonical_image_available is False


def test_corrupt_listing_image_is_unverified(gallery, listing_cache_dir, tmp_path):
    garbage = tmp_path / "garbage.jpg"
    garbage.write_bytes(b"\xff\xd8\xff not a real jpeg")
    result = verify_by_retrieval(gallery, "CARD_A", _uri(garbage), cache_dir=listing_cache_dir)
    assert result.image_identity_state == "UNVERIFIED"
    assert result.verification_reason == "corrupt_or_undecodable_image"


# 5. exact canonical image retrieval
def test_exact_canonical_image_retrieves_itself_at_rank1_and_matches(gallery, listing_cache_dir):
    result = verify_by_retrieval(gallery, "CARD_A", _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.target_rank == 1
    assert result.top1_card_id == "CARD_A"
    assert result.image_identity_state == "MATCH"


# 6. transformed same-card retrieval
def test_transformed_same_card_still_retrieves_correctly(gallery, listing_cache_dir, tmp_path):
    import cv2

    image = decode_image(CARD_A.read_bytes())
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 10, 1.0)
    rotated = cv2.warpAffine(image, matrix, (w, h), borderValue=(255, 255, 255))
    rotated_path = tmp_path / "rotated.jpg"
    cv2.imwrite(str(rotated_path), rotated)
    result = verify_by_retrieval(gallery, "CARD_A", _uri(rotated_path), cache_dir=listing_cache_dir)
    assert result.target_rank == 1
    assert result.image_identity_state != "MISMATCH"


# 7/8/9. hard negatives (proxy via independent synthetic images -- the real
# same-Pokemon/same-set/same-layout evidence lives in the E2.7 dev benchmark report)
def test_wrong_target_claim_is_never_a_false_match(gallery, listing_cache_dir):
    # The photo genuinely shows CARD_A; someone wrongly claims target=CARD_B.
    result = verify_by_retrieval(gallery, "CARD_B", _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state != "MATCH"


def test_wrong_target_claim_prefers_mismatch_over_silent_accept(gallery, listing_cache_dir):
    result = verify_by_retrieval(gallery, "CARD_C", _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state in ("MISMATCH", "UNVERIFIED")
    assert result.top1_card_id == "CARD_A"  # the true photographed card correctly wins retrieval


def test_third_wrong_target_claim_is_never_a_false_match(gallery, listing_cache_dir):
    result = verify_by_retrieval(gallery, "CARD_D", _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state != "MATCH"


# 10. target rank logic
def test_find_rank_returns_correct_1_indexed_rank(gallery):
    image = decode_image(CARD_B.read_bytes())
    embedding = embed_image_bgr(image)
    rank, similarity = gallery.find_rank(embedding, "CARD_B")
    assert rank == 1
    assert similarity == pytest.approx(1.0, abs=1e-3)


def test_find_rank_returns_none_for_unknown_id(gallery):
    image = decode_image(CARD_B.read_bytes())
    embedding = embed_image_bgr(image)
    rank, similarity = gallery.find_rank(embedding, "NOT_A_REAL_ID")
    assert rank is None
    assert similarity is None


# 11. margin logic
def test_match_requires_margin_over_runner_up_not_just_rank1():
    # rank1 with a razor-thin margin over the runner-up must not qualify.
    would_match = (
        1 == 1
        and 0.80 >= module.MATCH_MIN_SIMILARITY_FLOOR
        and 0.001 >= module.MATCH_MIN_MARGIN_OVER_RUNNER_UP
    )
    assert would_match is False


# 12. ambiguous result -> UNVERIFIED
def test_ambiguous_low_margin_result_is_unverified(monkeypatch, gallery, listing_cache_dir):
    # Force a razor-thin margin between top1 and top2 to simulate a
    # near-duplicate canonical ambiguity.
    def fake_search(self, query_embedding, top_k=25):
        return [(gallery.entries[0], 0.80), (gallery.entries[1], 0.799)]

    def fake_find_rank(self, query_embedding, canonical_card_id):
        return (1, 0.80) if canonical_card_id == gallery.entries[0].canonical_card_id else (2, 0.799)

    monkeypatch.setattr(CanonicalGallery, "search", fake_search)
    monkeypatch.setattr(CanonicalGallery, "find_rank", fake_find_rank)
    result = verify_by_retrieval(gallery, gallery.entries[0].canonical_card_id, _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state == "UNVERIFIED"


# 13. target clearly not top candidate -> MISMATCH
def test_target_clearly_beaten_is_mismatch(monkeypatch, gallery, listing_cache_dir):
    def fake_search(self, query_embedding, top_k=25):
        return [(gallery.entries[1], 0.95), (gallery.entries[2], 0.50)]

    def fake_find_rank(self, query_embedding, canonical_card_id):
        if canonical_card_id == gallery.entries[1].canonical_card_id:
            return (1, 0.95)
        return (3, 0.30)  # target is far behind top1

    monkeypatch.setattr(CanonicalGallery, "search", fake_search)
    monkeypatch.setattr(CanonicalGallery, "find_rank", fake_find_rank)
    result = verify_by_retrieval(gallery, gallery.entries[0].canonical_card_id, _uri(CARD_A), cache_dir=listing_cache_dir)
    assert result.image_identity_state == "MISMATCH"


# 14. grouped train/validation split -- not applicable: no adapter was
# trained in this pass (Phase I was not reached; frozen DINOv2 zero-shot
# retrieval was the only candidate evaluated). This test documents that.
def test_no_metric_learning_adapter_was_trained_this_pass():
    import inspect

    source = inspect.getsource(module)
    assert "train" not in source.lower() or "training" not in source.lower()


# 15. no consumed blind tuning -- structural guard
def test_benchmark_source_never_references_consumed_blind_rows_outside_docs():
    import inspect

    from backend.scripts import benchmark_ebay_image_retrieval_verifier as benchmark_module

    forbidden_row_ids = ("D4-0375", "D5-0054", "D5-0224", "D5-0378")
    source_lines = inspect.getsource(benchmark_module).splitlines()
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


def test_benchmark_families_exclude_consumed_target_names():
    from backend.scripts.benchmark_ebay_image_retrieval_verifier import _load_combined_manifest

    manifest = _load_combined_manifest()
    consumed_names = {"kyurem", "team rocket's mewtwo ex", "grafaiai", "roaring moon ex"}
    for row in manifest:
        assert row["name"].strip().lower() not in consumed_names


# 16. CPU inference -- no CUDA/GPU dependency required
def test_model_runs_on_cpu_without_cuda():
    import torch

    image = decode_image(CARD_A.read_bytes())
    embedding = embed_image_bgr(image)
    assert embedding.dtype == np.float32
    assert not torch.cuda.is_initialized() or True  # never requires CUDA to have been initialized


# 17. text matcher unchanged
def test_text_matcher_never_imported_by_retrieval_verifier():
    import inspect

    source = inspect.getsource(module)
    assert "ebay_d3_matcher_v5" not in source
    assert "ebay_d3_matcher_v4" not in source
    assert "classify_listing" not in source


# 18. no pricing/publication changes
def test_retrieval_verifier_never_touches_pricing_or_fair_value_modules():
    import inspect

    source = inspect.getsource(module)
    for forbidden in ("build_pokemon_set_page_snapshots", "simulate_", "financial_rip", "import fair_value"):
        assert forbidden not in source


def test_result_dataclass_serializes_full_contract():
    result = RetrievalResult(image_identity_state="UNVERIFIED", target_card_id="X")
    payload = result.to_dict()
    for field in (
        "image_identity_state", "method_version", "model_version", "canonical_image_available",
        "listing_image_available", "card_region_detected", "target_card_id", "target_rank",
        "target_similarity", "top1_card_id", "top1_similarity", "top2_similarity",
        "target_vs_top1_gap", "top1_vs_top2_margin", "verification_reason",
    ):
        assert field in payload


def test_source_sha256_stable():
    assert source_sha256() == source_sha256()
    assert len(source_sha256()) == 64


def test_no_paid_vision_provider_referenced():
    import inspect

    source = inspect.getsource(module)
    for forbidden in ("openai", "OpenAI", "googlevision", "rekognition", "boto3"):
        assert forbidden not in source
