"""Stage 1 sealed-product RIP: composition, distribution, discovery, scoring."""

from unittest.mock import patch

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.sealed_product_distribution import (
    DEFAULT_CHUNK_SIZE,
    STAGE1_DISTRIBUTION_MODEL_VERSION,
    build_stage1_product_distributions,
    extract_pack_outcome_vector,
    stage1_distribution_seed,
)
from backend.db.services import sealed_product_rip_service as service
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.desirability.scoring_config import OVERALL_RIP_V9_VERSION
from backend.desirability.weighted_rip import compute_overall_rip_v9
from backend.domain.pokemon import sealed_product_stage2_composition as stage2
from backend.domain.pokemon.sealed_product_composition import (
    STAGE1_COMPOSITION_VERSION,
    SUPPORTED_STAGE1_FAMILIES,
    resolve_stage1_composition,
)

RUNS = 20_000  # above FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT (10_000)


def _pack_vector(n: int = RUNS) -> np.ndarray:
    """A synthetic but realistically skewed pack distribution."""
    rng = np.random.default_rng(20260815)
    base = rng.lognormal(mean=0.5, sigma=0.9, size=n)
    hits = rng.random(n) < 0.01
    base[hits] += rng.lognormal(mean=3.5, sigma=0.8, size=int(hits.sum()))
    return np.round(base, 4)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "family,expected",
    [
        ("loose_booster_pack", 1),
        ("sleeved_booster_pack", 1),
        ("booster_bundle", 6),
        ("half_booster_box", 18),
        ("booster_box", 36),
    ],
)
def test_stage1_supported_families_resolve_to_their_pack_counts(family, expected):
    composition = resolve_stage1_composition(family)
    assert composition is not None
    assert composition.pack_count == expected
    assert composition.product_family == family
    assert composition.source_set_mode == "same_set"
    assert composition.guaranteed_card_components == ()
    assert composition.composition_version == STAGE1_COMPOSITION_VERSION


@pytest.mark.parametrize(
    "family",
    [
        "enhanced_booster_box",
        "elite_trainer_box",
        "pokemon_center_elite_trainer_box",
        "three_pack_blister",
        "collection_product",
        "case",
        "display",
        "other",
        "",
        None,
        "totally_unknown_family",
    ],
)
def test_out_of_scope_families_are_unsupported(family):
    assert resolve_stage1_composition(family) is None


def test_supported_family_set_is_exactly_five():
    assert SUPPORTED_STAGE1_FAMILIES == {
        "loose_booster_pack",
        "sleeved_booster_pack",
        "booster_bundle",
        "half_booster_box",
        "booster_box",
    }


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def test_sleeved_booster_reuses_the_original_pack_vector_unchanged():
    x = _pack_vector(5_000)
    built = build_stage1_product_distributions(x, pack_counts=[1], canonical_set_key="setA")
    np.testing.assert_array_equal(built["distributions"][1], x)


def test_loose_pack_reuses_exact_pack_vector_without_a_new_simulation():
    x = _pack_vector(5_000)
    with patch("numpy.random.default_rng") as rng:
        built = build_stage1_product_distributions(x, pack_counts=[1], canonical_set_key="setA")
    rng.assert_not_called()
    np.testing.assert_array_equal(built["distributions"][1], x)


def test_pack_vector_is_never_mutated():
    x = _pack_vector(5_000)
    before = x.copy()
    build_stage1_product_distributions(x, pack_counts=[1, 6, 36], canonical_set_key="setA")
    np.testing.assert_array_equal(x, before)


def test_product_vectors_have_exactly_len_x_outcomes():
    x = _pack_vector(5_000)
    built = build_stage1_product_distributions(x, pack_counts=[6, 36], canonical_set_key="setA")
    assert built["distributions"][6].shape == (5_000,)
    assert built["distributions"][36].shape == (5_000,)
    assert built["meta"]["productRunCount"] == 5_000


def test_distributions_are_deterministic_for_fixed_input_and_seed_identity():
    x = _pack_vector(4_000)
    first = build_stage1_product_distributions(x, pack_counts=[6, 36], canonical_set_key="setA")
    second = build_stage1_product_distributions(x, pack_counts=[6, 36], canonical_set_key="setA")
    np.testing.assert_array_equal(first["distributions"][6], second["distributions"][6])
    np.testing.assert_array_equal(first["distributions"][36], second["distributions"][36])
    assert first["meta"]["seed"] == second["meta"]["seed"]


def test_seed_excludes_price_and_sku_but_tracks_set_and_size():
    a = stage1_distribution_seed(canonical_set_key="setA", outcome_count=1000)
    b = stage1_distribution_seed(canonical_set_key="setA", outcome_count=1000)
    assert a == b
    assert a != stage1_distribution_seed(canonical_set_key="setB", outcome_count=1000)
    assert a != stage1_distribution_seed(canonical_set_key="setA", outcome_count=1001)


def test_bundle_and_box_means_track_linear_scaling_of_the_pack_mean():
    x = _pack_vector(60_000)
    built = build_stage1_product_distributions(x, pack_counts=[6, 36], canonical_set_key="setA")
    pack_mean = float(x.mean())
    # Monte Carlo tolerance: sd of the mean of k i.i.d. draws over n runs.
    for count in (6, 36):
        y = built["distributions"][count]
        tolerance = 5.0 * np.sqrt(count / y.size) * float(x.std())
        assert float(y.mean()) == pytest.approx(count * pack_mean, abs=tolerance)


def test_bundle_and_half_box_are_leading_draws_of_the_box_common_random_numbers():
    x = _pack_vector(3_000)
    built = build_stage1_product_distributions(x, pack_counts=[6, 18, 36], canonical_set_key="setA")
    # The 36-pack sum must always be at least the 6-pack sum drawn alongside it,
    # which is only true when they share the same leading draws (values > 0).
    assert bool(np.all(built["distributions"][36] >= built["distributions"][6] - 1e-9))
    assert bool(np.all(built["distributions"][36] >= built["distributions"][18] - 1e-9))


def test_generation_is_chunked_and_never_allocates_the_full_n_by_36_matrix(monkeypatch):
    x = _pack_vector(5_000)
    shapes = []
    real_default_rng = np.random.default_rng

    class _SpyRng:
        def __init__(self, inner):
            self._inner = inner

        def integers(self, *args, **kwargs):
            shapes.append(kwargs.get("size"))
            return self._inner.integers(*args, **kwargs)

    monkeypatch.setattr(
        np.random, "default_rng", lambda seed=None: _SpyRng(real_default_rng(seed))
    )
    build_stage1_product_distributions(
        x, pack_counts=[6, 36], canonical_set_key="setA", chunk_size=1_000
    )
    assert len(shapes) == 5
    assert all(shape == (1_000, 36) for shape in shapes)
    assert DEFAULT_CHUNK_SIZE <= 50_000


def test_extract_prefers_the_numpy_distribution_over_the_list_form():
    array = np.array([1.0, 2.0, 3.0])
    extracted = extract_pack_outcome_vector({"distribution": array, "values": [9.0, 9.0, 9.0]})
    np.testing.assert_array_equal(extracted, array)
    fallback = extract_pack_outcome_vector({"values": [4.0, 5.0]})
    np.testing.assert_array_equal(fallback, np.array([4.0, 5.0]))


@pytest.mark.parametrize("bad", [[], [1.0, float("nan")], [1.0, float("inf")]])
def test_invalid_pack_vectors_are_rejected(bad):
    with pytest.raises(ValueError):
        build_stage1_product_distributions(bad, pack_counts=[6], canonical_set_key="setA")


# ---------------------------------------------------------------------------
# Product discovery
# ---------------------------------------------------------------------------

def _snapshot(products):
    return {"set": {"id": "set-uuid"}, "products": products}


def test_only_exact_stage1_families_are_selected_and_enhanced_box_is_excluded():
    payload = _snapshot(
        [
            {"sealedProductId": "1", "name": "X Booster Box", "productFamily": "booster_box", "currentPrice": 120.0},
            {"sealedProductId": "2", "name": "X Enhanced Booster Box", "productFamily": "enhanced_booster_box", "currentPrice": 150.0},
            {"sealedProductId": "3", "name": "X Elite Trainer Box", "productFamily": "elite_trainer_box", "currentPrice": 60.0},
            {"sealedProductId": "4", "name": "X Booster Bundle", "productFamily": "booster_bundle", "currentPrice": 25.0},
            {"sealedProductId": "5", "name": "X Sleeved Booster Pack", "productFamily": "sleeved_booster_pack", "currentPrice": 5.5},
            {"sealedProductId": "6", "name": "X Booster Pack", "productFamily": "loose_booster_pack", "currentPrice": 4.5},
        ]
    )
    selection = service.select_stage1_products(payload)
    assert [c["sealed_product_id"] for c in selection["candidates"]] == ["1", "4", "5", "6"]
    excluded = {s["sealedProductId"]: s["reason"] for s in selection["skipped"]}
    assert excluded == {
        "2": service.REASON_UNSUPPORTED_FAMILY,
        "3": service.REASON_UNSUPPORTED_FAMILY,
    }


@pytest.mark.parametrize("price", [None, "", "abc", 0, -1.0, float("nan"), float("inf")])
def test_products_without_a_valid_market_price_are_skipped_with_no_fallback(price):
    payload = _snapshot(
        [{"sealedProductId": "9", "name": "X Booster Bundle", "productFamily": "booster_bundle", "currentPrice": price}]
    )
    selection = service.select_stage1_products(payload)
    assert selection["candidates"] == []
    assert selection["skipped"][0]["reason"] == service.REASON_INVALID_PRICE


def test_multiple_skus_in_one_family_remain_separate_candidates():
    payload = _snapshot(
        [
            {"sealedProductId": "10", "name": "X Sleeved Booster Pack [A]", "productFamily": "sleeved_booster_pack", "currentPrice": 5.0},
            {"sealedProductId": "11", "name": "X Sleeved Booster Pack [B]", "productFamily": "sleeved_booster_pack", "currentPrice": 7.5},
        ]
    )
    selection = service.select_stage1_products(payload)
    assert len(selection["candidates"]) == 2
    assert {c["product_market_cost"] for c in selection["candidates"]} == {5.0, 7.5}


@pytest.mark.parametrize(
    "name,family,reason",
    [
        ("Set Quarter Booster Box", "booster_box", "non_default_pack_count_variant"),
        (
            "Prismatic Evolutions Booster Bundle + Surprise Box Bundle (Sam's Club)",
            "booster_bundle",
            "composite_multi_product_sku",
        ),
    ],
)
def test_real_skus_whose_pack_count_is_not_the_stage1_default_are_refused(name, family, reason):
    payload = _snapshot(
        [{"sealedProductId": "50", "name": name, "productFamily": family, "currentPrice": 200.0}]
    )
    selection = service.select_stage1_products(payload)
    assert selection["candidates"] == []
    assert selection["skipped"][0]["reason"] == reason


@pytest.mark.parametrize(
    "name,family",
    [
        ("Surging Sparks Booster Box", "booster_box"),
        ("Surging Sparks Booster Bundle (Retail)", "booster_bundle"),
        ("Surging Sparks Sleeved Booster Pack", "sleeved_booster_pack"),
    ],
)
def test_ordinary_stage1_skus_are_not_refused_by_the_integrity_guard(name, family):
    payload = _snapshot(
        [{"sealedProductId": "51", "name": name, "productFamily": family, "currentPrice": 30.0}]
    )
    assert len(service.select_stage1_products(payload)["candidates"]) == 1


def test_half_box_uses_its_own_price_and_18_pack_composition_despite_stale_snapshot_family():
    payload = _snapshot(
        [{"sealedProductId": "half", "name": "Surging Sparks Half Booster Box", "productFamily": "booster_box", "currentPrice": 189.81}]
    )
    candidate = service.select_stage1_products(payload)["candidates"][0]
    assert candidate["product_family"] == "half_booster_box"
    assert candidate["composition"].pack_count == 18
    assert candidate["product_market_cost"] == 189.81


def test_family_falls_back_to_the_canonical_classifier_when_absent():
    payload = _snapshot([{"sealedProductId": "12", "name": "Some Set Enhanced Booster Box", "currentPrice": 100.0}])
    selection = service.select_stage1_products(payload)
    assert selection["candidates"] == []
    assert selection["skipped"][0]["productFamily"] == "enhanced_booster_box"


# ---------------------------------------------------------------------------
# Financial RIP / Collector Appeal / Overall RIP
# ---------------------------------------------------------------------------

def _candidates(*specs):
    out = []
    for product_id, family, cost in specs:
        out.append(
            {
                "sealed_product_id": product_id,
                "name": f"product-{product_id}",
                "product_family": family,
                "composition": resolve_stage1_composition(family),
                "product_market_cost": cost,
                "price_as_of": "2026-08-14",
                "price_source": "TCGPLAYER",
            }
        )
    return out


_APPEAL = {"score": 62.5, "version": COLLECTOR_APPEAL_V5_VERSION, "available": True, "reason": None}


def test_sleeved_booster_at_loose_pack_cost_reproduces_the_canonical_pack_v3_result():
    x = _pack_vector()
    cost = 5.25
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(("1", "sleeved_booster_pack", cost)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    product = scored["products"][0]
    canonical = build_financial_rip_v3(x, cost)
    assert product["financial_rip_v3_score"] == canonical["score"]
    assert product["financial_rip_v3_payload"] == canonical
    assert product["financial_rip_v3_version"] == canonical["scoreVersion"]


def test_same_distribution_different_cost_changes_the_score_but_not_the_distribution():
    x = _pack_vector()
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(("1", "sleeved_booster_pack", 4.0), ("2", "sleeved_booster_pack", 9.0)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    cheap, dear = scored["products"]
    assert cheap["expected_value"] == dear["expected_value"]
    assert cheap["median_value"] == dear["median_value"]
    assert cheap["simulation_count"] == dear["simulation_count"]
    assert cheap["financial_rip_v3_score"] > dear["financial_rip_v3_score"]
    assert cheap["chance_to_recover_cost"] > dear["chance_to_recover_cost"]
    assert cheap["total_value_to_cost_ratio"] > dear["total_value_to_cost_ratio"]


def test_bundle_and_box_scores_come_from_composed_vectors_not_scaled_pack_metrics():
    x = _pack_vector()
    pack_cost = 5.0
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(("1", "booster_bundle", 6 * pack_cost), ("2", "booster_box", 36 * pack_cost)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    bundle, box = scored["products"]
    pack_payload = build_financial_rip_v3(x, pack_cost)

    assert bundle["pack_count"] == 6
    assert box["pack_count"] == 36
    # Distributional metrics are NOT k * the pack metric; only the mean is.
    assert bundle["median_value"] != pytest.approx(6 * float(np.median(x)), rel=1e-3)
    assert box["p95_value"] != pytest.approx(36 * float(np.percentile(x, 95)), rel=1e-3)
    assert bundle["financial_rip_v3_score"] != pack_payload["score"]
    assert box["financial_rip_v3_score"] != pack_payload["score"]
    # And each is exactly V3 over its own composed vector.
    built = build_stage1_product_distributions(x, pack_counts=[6, 36], canonical_set_key="setA")
    assert bundle["financial_rip_v3_payload"] == build_financial_rip_v3(built["distributions"][6], 6 * pack_cost)
    assert box["financial_rip_v3_payload"] == build_financial_rip_v3(built["distributions"][36], 36 * pack_cost)


def test_identical_compositions_share_one_generated_distribution():
    x = _pack_vector()
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(("1", "booster_bundle", 24.0), ("2", "booster_bundle", 31.0)),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    a, b = scored["products"]
    assert a["expected_value"] == b["expected_value"]
    assert a["p99_value"] == b["p99_value"]
    assert scored["distributionMeta"]["bootstrapPackCounts"] == [6]
    assert a["product_market_cost"] != b["product_market_cost"]


def test_all_products_inherit_the_same_canonical_collector_appeal_and_overall_version():
    x = _pack_vector()
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(
            ("1", "sleeved_booster_pack", 6.0),
            ("2", "booster_bundle", 28.0),
            ("3", "booster_box", 150.0),
        ),
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    assert {p["collector_appeal_score"] for p in scored["products"]} == {62.5}
    assert {p["collector_appeal_version"] for p in scored["products"]} == {COLLECTOR_APPEAL_V5_VERSION}
    assert {p["overall_rip_version"] for p in scored["products"]} == {OVERALL_RIP_V9_VERSION}
    # Same appeal, different distributions and costs -> different Overall RIP.
    assert len({p["overall_rip_score"] for p in scored["products"]}) == 3
    for product in scored["products"]:
        expected = compute_overall_rip_v9(product["financial_rip_v3_score"], 62.5)
        assert product["overall_rip_payload"] == expected


def test_missing_collector_appeal_keeps_financial_but_makes_overall_unavailable():
    x = _pack_vector()
    scored = service.score_stage1_sealed_products(
        pack_values=x,
        candidates=_candidates(("1", "booster_bundle", 28.0)),
        canonical_set_key="setA",
        collector_appeal={"score": None, "version": None, "available": False, "reason": service.REASON_COLLECTOR_APPEAL_UNAVAILABLE},
    )
    product = scored["products"][0]
    assert product["financial_rip_v3_score"] is not None
    assert product["financial_rip_v3_rankable"] is True
    assert product["collector_appeal_score"] is None
    assert product["overall_rip_score"] is None
    assert product["overall_rip_rankable"] is False
    assert product["overall_rip_version"] == OVERALL_RIP_V9_VERSION


def test_non_canonical_collector_appeal_version_is_refused():
    with patch.object(
        service,
        "resolve_set_collector_appeal",
        wraps=service.resolve_set_collector_appeal,
    ):
        with patch(
            "backend.db.services.collector_appeal_service.get_collector_appeal",
            return_value={"collectorAppeal": {"score": 70.0, "version": "collector-appeal-v3"}},
        ):
            resolved = service.resolve_set_collector_appeal("set-uuid")
    assert resolved["available"] is False
    assert resolved["score"] is None
    assert resolved["reason"] == service.REASON_COLLECTOR_APPEAL_UNAVAILABLE


def test_no_supported_products_returns_a_structured_empty_result():
    scored = service.score_stage1_sealed_products(
        pack_values=_pack_vector(1_000),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=_APPEAL,
    )
    assert scored["status"] == "empty"
    assert scored["reason"] == service.REASON_NO_SUPPORTED_PRODUCTS
    assert scored["products"] == []


# ---------------------------------------------------------------------------
# Orchestration / persistence
# ---------------------------------------------------------------------------

def _run_stage1(products, *, appeal=None, captured=None):
    def _persist(rows):
        if captured is not None:
            captured.extend(rows)
        return rows

    return service.run_stage1_sealed_product_rip(
        sim_results={"distribution": _pack_vector()},
        set_id="set-uuid",
        canonical_set_key="setA",
        calculation_run_id="run-uuid",
        read_snapshot_fn=lambda _set_id: _snapshot(products),
        persist_fn=_persist,
        collector_appeal_fn=lambda _set_id: appeal or _APPEAL,
        # Stage 2 discovery is a real dependency of the orchestrator now. These
        # Stage 1 tests declare "no verified Stage 2 composition exists" the same
        # way they already declare the snapshot and the persistence sink.
        stage2_compositions_fn=lambda _ids: [],
    )


def test_persisted_rows_are_one_per_run_and_product_with_full_provenance():
    captured = []
    summary = _run_stage1(
        [
            {"sealedProductId": "101", "name": "A Booster Box", "productFamily": "booster_box", "currentPrice": 140.0, "priceAsOf": "2026-08-14", "source": "TCGPLAYER"},
            {"sealedProductId": "102", "name": "A Booster Bundle", "productFamily": "booster_bundle", "currentPrice": 26.0, "priceAsOf": "2026-08-14", "source": "TCGPLAYER"},
            {"sealedProductId": "103", "name": "A Enhanced Booster Box", "productFamily": "enhanced_booster_box", "currentPrice": 190.0},
        ],
        captured=captured,
    )

    assert summary["status"] == "ok"
    assert summary["scoredProductCount"] == 2
    assert summary["persistedProductCount"] == 2
    # The Enhanced Booster Box is a STAGE 2 family, so its skip reason is now the
    # specific one ("nobody has verified what is in this SKU") rather than the
    # generic "Stage 1 does not model this family". Stage 2 owning the verdict for
    # its own families is what keeps a SKU from carrying two different reasons.
    assert summary["skippedReasons"] == {stage2.REASON_NO_VERIFIED_COMPOSITION: 1}
    assert len({(r["calculation_run_id"], r["sealed_product_id"]) for r in captured}) == 2

    row = next(r for r in captured if r["sealed_product_id"] == "101")
    assert row["set_id"] == "set-uuid"
    assert row["pack_count"] == 36
    assert row["composition_version"] == STAGE1_COMPOSITION_VERSION
    assert row["distribution_model_version"] == STAGE1_DISTRIBUTION_MODEL_VERSION
    assert row["pack_independence_assumption"] is True
    assert row["product_market_cost"] == 140.0
    assert row["price_as_of"] == "2026-08-14"
    assert row["price_source"] == "TCGPLAYER"
    assert row["simulation_count"] == RUNS
    assert isinstance(row["financial_rip_v3_payload"], dict)
    assert isinstance(row["overall_rip_payload"], dict)
    assert 0.0 <= row["chance_to_recover_cost"] <= 1.0


def test_repeated_skus_share_a_distribution_but_persist_separate_costs_and_scores():
    captured = []
    _run_stage1(
        [
            {"sealedProductId": "201", "name": "A Sleeved Booster Pack [1]", "productFamily": "sleeved_booster_pack", "currentPrice": 5.0},
            {"sealedProductId": "202", "name": "A Sleeved Booster Pack [2]", "productFamily": "sleeved_booster_pack", "currentPrice": 8.0},
        ],
        captured=captured,
    )
    assert len(captured) == 2
    assert {r["expected_value"] for r in captured} == {captured[0]["expected_value"]}
    assert {r["product_market_cost"] for r in captured} == {5.0, 8.0}
    assert captured[0]["financial_rip_v3_score"] != captured[1]["financial_rip_v3_score"]


def test_no_snapshot_and_no_supported_products_are_expected_not_failures():
    no_snapshot = service.run_stage1_sealed_product_rip(
        sim_results={"distribution": _pack_vector(1_000)},
        set_id="set-uuid",
        canonical_set_key="setA",
        calculation_run_id="run-uuid",
        read_snapshot_fn=lambda _set_id: None,
        persist_fn=lambda rows: rows,
        collector_appeal_fn=lambda _set_id: _APPEAL,
    )
    assert no_snapshot["status"] == "skipped"
    assert no_snapshot["reason"] == service.REASON_NO_SEALED_SNAPSHOT

    none_supported = _run_stage1(
        [{"sealedProductId": "301", "name": "A Elite Trainer Box", "productFamily": "elite_trainer_box", "currentPrice": 60.0}]
    )
    assert none_supported["status"] == "skipped"
    assert none_supported["reason"] == service.REASON_NO_SUPPORTED_PRODUCTS


def test_supported_products_cannot_silently_persist_zero_rows():
    with pytest.raises(service.SealedProductCoverageError, match="expected=1 persisted=0"):
        service.run_stage1_sealed_product_rip(
            sim_results={"distribution": _pack_vector()},
            set_id="set-uuid",
            canonical_set_key="whiteFlareLike",
            calculation_run_id="new-run",
            read_snapshot_fn=lambda _set_id: _snapshot([
                {"sealedProductId": "bundle", "name": "White Flare Booster Bundle",
                 "productFamily": "booster_bundle", "currentPrice": 80.0}
            ]),
            persist_fn=lambda _rows: [],
            collector_appeal_fn=lambda _set_id: _APPEAL,
            stage2_compositions_fn=lambda _ids: [],
        )


def test_prior_run_rows_cannot_satisfy_new_run_coverage():
    captured = []

    def _persist(rows):
        captured.extend(rows)
        return [{**row, "calculation_run_id": "old-run"} for row in rows]

    with pytest.raises(service.SealedProductCoverageError, match="matched=0"):
        service.run_stage1_sealed_product_rip(
            sim_results={"distribution": _pack_vector()},
            set_id="set-uuid",
            canonical_set_key="setA",
            calculation_run_id="new-run",
            read_snapshot_fn=lambda _set_id: _snapshot([
                {"sealedProductId": "bundle", "name": "A Booster Bundle",
                 "productFamily": "booster_bundle", "currentPrice": 30.0}
            ]),
            persist_fn=_persist,
            collector_appeal_fn=lambda _set_id: _APPEAL,
            stage2_compositions_fn=lambda _ids: [],
        )
    assert captured[0]["calculation_run_id"] == "new-run"


def test_summary_is_compact_and_never_carries_raw_vectors():
    summary = _run_stage1(
        [{"sealedProductId": "401", "name": "A Booster Bundle", "productFamily": "booster_bundle", "currentPrice": 26.0}]
    )
    assert summary["packOutcomeCount"] == RUNS
    assert summary["requiredPackCounts"] == [6]
    assert summary["generatedDistributionCount"] == 1
    assert summary["collectorAppealVersion"] == COLLECTOR_APPEAL_V5_VERSION
    assert isinstance(summary["elapsedMs"], float)
    for product in summary["products"]:
        assert set(product).isdisjoint({"financial_rip_v3_payload", "overall_rip_payload"})
