from backend.db.services import product_family_rankings_service as service
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V10_VERSION,
    canonical_collector_appeal_version,
)


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_a): return self
    def in_(self, _field, values):
        self.rows = [r for r in self.rows if r[_field] in values]
        return self
    def execute(self):
        return type("Result", (), {"data": self.rows})()


class Client:
    def __init__(self, rows, products=None): self.rows = rows; self.products = products or []
    def table(self, name):
        assert name in {"simulation_sealed_product_results", "sealed_products"}
        return Query(list(self.products if name == "sealed_products" else self.rows))


def row(product, family="booster_box", run="current", overall=80, financial=70, chance=.4, price=100, **changes):
    value = {
        "calculation_run_id": run, "sealed_product_id": product, "set_id": "set-1",
        "product_family": family, "product_name": product, "pack_count": 36,
        "product_market_cost": price, "expected_value": 80, "median_value": 55,
        "chance_to_recover_cost": chance,
        # Historical V3/V9 columns. Kept populated so the service can still describe
        # what it read even though canonical selection no longer keys off these.
        "financial_rip_v3_score": financial,
        "financial_rip_v3_version": "financial_rip_v3",
        "overall_rip_score": overall, "overall_rip_version": "overall_rip_v9",
        "overall_rip_rankable": True,
        # Canonical V4/V10 columns.
        "financial_rip_v4_score": financial,
        "financial_rip_v4_version": CANONICAL_FINANCIAL_RIP_VERSION,
        "collector_appeal_score": 60, "collector_appeal_version": canonical_collector_appeal_version(),
        # V10's OWN literal version string - independent of whatever is canonical
        # right now, since V10 stays computable/identifiable as explicit history.
        "overall_rip_v10_score": overall, "overall_rip_v10_version": OVERALL_RIP_V10_VERSION,
        "overall_rip_v10_rankable": True,
        # Canonical (as of the 2026-09-03 cutover, V12) fields - this is what
        # `_rank_key`/`_canonical`/`_project` actually read by default now.
        "overall_rip_v12_score": overall, "overall_rip_v12_version": CANONICAL_OVERALL_RIP_VERSION,
        "overall_rip_v12_rankable": True, "overall_rip_v12_status": "ready",
    }
    value.update(changes)
    return value


def build(monkeypatch, rows):
    return service.build_product_family_rankings(
        Client(rows),
        set_targets=[{"set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current", "name": "Alpha", "logo_image_url": "logo"}],
    )


def test_overall_rip_v12_payload_passes_through_as_shadow_field_without_affecting_rank(monkeypatch):
    """`overall_rip_v12_payload` (written by
    `sealed_product_rip_finalization_service._overall_rip_v12_for`) is
    surfaced as a pure, additive `overallRipV12` passthrough on each product
    row - it must never influence `_rank_key`/`_canonical`, which stay keyed
    on the V10/V4 columns exactly as before this change."""
    v12_payload = {
        "score": 55.0, "version": "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
        "status": "ready", "rankable": True, "components": {}, "missingInputs": [],
        "weights": {"financial_rip": 0.86, "chase_accessibility": 0.04, "collector_appeal": 0.10},
    }
    # "low" has the HIGHER V12 score but the LOWER V10 score - family order
    # must still follow V10 (leader = "high"), proving V12 is shadow-only.
    rows = [
        row("high", overall=90, overall_rip_v12_payload={**v12_payload, "score": 10.0}),
        row("low", overall=50, overall_rip_v12_payload=v12_payload),
        row("no-shadow", overall=70),
    ]
    payload = build(None, rows)
    products = payload["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["high", "no-shadow", "low"]
    assert products[0]["overallRipV12"]["score"] == 10.0
    assert products[1]["overallRipV12"] is None
    assert products[2]["overallRipV12"]["score"] == 55.0


def test_current_canonical_rows_only_and_deferred_products_are_not_fabricated(monkeypatch):
    payload = build(monkeypatch, [row("ranked"), row("historical", run="old")])
    products = payload["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["ranked"]
    assert payload["partialToCurrentlyScoredProducts"] is True


def _ev_representativeness(run_id="current", pack_count=420):
    return {
        "contractVersion": "ev_representativeness_public_v1",
        "methodVersion": "ev_representativeness_v1",
        "calculationRunId": run_id,
        "realizationHorizon": {"targetEvRatio": .80, "openerProbability": .80, "packCount": pack_count, "status": "confirmed"},
    }


def test_product_rows_inherit_the_set_evRepresentativeness_only_from_the_same_run():
    """Every product in a set carries that SAME set's confirmed EV
    realization headline - not a new per-product calculation - and only
    when the set target's evRepresentativeness matches the exact run this
    product family ranking was built from."""
    payload = service.build_product_family_rankings(
        Client([row("ranked")]),
        set_targets=[{
            "set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current",
            "name": "Alpha", "logo_image_url": "logo",
            "evRepresentativeness": _ev_representativeness(),
        }],
    )
    product = payload["families"]["booster_box"]["products"][0]
    assert product["setEvRepresentativeness"]["calculationRunId"] == "current"
    assert product["setEvRepresentativeness"]["realizationHorizon"]["packCount"] == 420
    # Compact: no curve/history array copied onto every product row.
    assert set(product["setEvRepresentativeness"]) == {"contractVersion", "methodVersion", "calculationRunId", "realizationHorizon"}


def test_product_rows_omit_set_evRepresentativeness_from_a_different_run():
    payload = service.build_product_family_rankings(
        Client([row("ranked")]),
        set_targets=[{
            "set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current",
            "name": "Alpha", "logo_image_url": "logo",
            "evRepresentativeness": _ev_representativeness(run_id="stale-run"),
        }],
    )
    product = payload["families"]["booster_box"]["products"][0]
    assert product["setEvRepresentativeness"] is None


def test_product_rows_omit_set_evRepresentativeness_when_absent():
    payload = build(None, [row("ranked")])
    product = payload["families"]["booster_box"]["products"][0]
    assert product["setEvRepresentativeness"] is None


def test_versions_and_rankable_flag_gate_rankings(monkeypatch):
    rows = [row("good"), row("old-ca", collector_appeal_version="v4"), row("old-overall", overall_rip_v12_version="v8"), row("not-rankable", overall_rip_v12_rankable=False)]
    family = build(monkeypatch, rows)["families"]["booster_box"]
    assert family["currentlyScoredCount"] == 4
    assert family["currentlyRankableCount"] == family["count"] == 1


def test_collector_appeal_gate_uses_the_canonical_selector(monkeypatch):
    sentinel = "collector_appeal_future_canonical"
    monkeypatch.setattr(service, "canonical_collector_appeal_version", lambda: sentinel)
    rows = [
        row("canonical", collector_appeal_version=sentinel, overall=90),
        row("superseded", collector_appeal_version="collector_appeal_v4_superseded", overall=99),
    ]
    family = build(monkeypatch, rows)["families"]["booster_box"]
    assert family["currentlyScoredCount"] == 2
    assert family["currentlyRankableCount"] == family["count"] == 1
    assert [product["sealedProductId"] for product in family["products"]] == ["canonical"]


def test_families_are_isolated_and_ties_are_deterministic(monkeypatch):
    rows = [row("b", price=90), row("a", price=90), row("half", family="half_booster_box"), row("etb", family="elite_trainer_box"), row("pc", family="pokemon_center_elite_trainer_box")]
    families = build(monkeypatch, rows)["families"]
    assert [p["sealedProductId"] for p in families["booster_box"]["products"]] == ["a", "b"]
    assert families["booster_box"]["products"][1]["familyRank"] == 2
    assert families["booster_box"]["products"][0]["familySize"] == 2
    assert set(families) >= {"booster_box", "half_booster_box", "elite_trainer_box", "pokemon_center_elite_trainer_box"}
    assert all(p["productFamily"] == f for f, block in families.items() for p in block["products"])
    assert "products" not in {k: v for k, v in families.items() if k == "all"}


def test_new_score_automatically_appears_on_next_build(monkeypatch):
    rows = [row("existing")]
    assert build(monkeypatch, rows)["families"]["booster_box"]["count"] == 1
    rows.append(row("newly-scored", overall=90))
    products = build(monkeypatch, rows)["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["newly-scored", "existing"]
    assert "all" not in build(monkeypatch, rows)["families"]


def test_loose_pack_uses_canonical_product_art_and_other_families_do_not():
    client = Client(
        [row("pack", family="loose_booster_pack"), row("box")],
        products=[{"id": "pack", "image_small_url": "https://img/pack.png", "image_large_url": None}],
    )
    payload = service.build_product_family_rankings(
        client,
        set_targets=[{"set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current"}],
    )
    assert payload["families"]["loose_booster_pack"]["products"][0]["productImageUrl"] == "https://img/pack.png"
    assert payload["families"]["booster_box"]["products"][0]["productImageUrl"] is None


def test_public_scores_follow_the_family_leader_curve_and_preserve_relative_fields(monkeypatch):
    products = build(monkeypatch, [row("leader", overall=42.8172), row("next", overall=42.2344)])["families"]["booster_box"]["products"]
    assert products[0]["overallRipLeaderScore"] == 100.0
    assert products[1]["overallRipLeaderScore"] == 98.64
    assert products[0]["overallRipRelativeScore"] == 100.0
    assert products[1]["overallRipRelativeScore"] == 0.0


def test_mixed_date_target_runs_are_exact_authority_and_old_run_is_excluded():
    rows = [
        row("a-old", run="run-A-old", set_id="set-a"),
        row("a-new", run="run-A-new", set_id="set-a"),
        row("b-current", run="run-B-current", set_id="set-b"),
    ]
    targets = [
        {"set_id": "set-a", "canonical_key": "alpha", "calculation_run_id": "run-A-new", "market_date": "D2"},
        {"set_id": "set-b", "canonical_key": "beta", "calculation_run_id": "run-B-current", "market_date": "D1"},
    ]
    payload = service.build_product_family_rankings(Client(rows), set_targets=targets)
    products = payload["families"]["booster_box"]["products"]
    assert {product["sealedProductId"] for product in products} == {"a-new", "b-current"}
    assert {product["calculationRunId"] for product in products} == {"run-A-new", "run-B-current"}
    assert payload["runAuthority"] == "set_targets.calculation_run_id"


def test_every_product_run_matches_owning_target_across_families():
    targets = [
        {"set_id": "set-a", "canonical_key": "alpha", "calculation_run_id": "run-a"},
        {"set_id": "set-b", "canonical_key": "beta", "calculation_run_id": "run-b"},
    ]
    rows = [
        row("a-box", run="run-a", set_id="set-a"),
        row("a-bundle", family="booster_bundle", run="run-a", set_id="set-a"),
        row("b-etb", family="elite_trainer_box", run="run-b", set_id="set-b"),
    ]
    payload = service.build_product_family_rankings(Client(rows), set_targets=targets)
    authority = {target["set_id"]: target["calculation_run_id"] for target in targets}
    for block in payload["families"].values():
        for product in block["products"]:
            assert product["calculationRunId"] == authority[product["setId"]]


def test_conflicting_target_run_authority_fails_closed():
    targets = [
        {"set_id": "set-a", "canonical_key": "alpha", "calculation_run_id": "run-a"},
        {"set_id": "set-a", "canonical_key": "alpha", "calculation_run_id": "run-b"},
    ]
    import pytest
    with pytest.raises(ValueError, match="conflicting calculation_run_id authority"):
        service.build_product_family_rankings(Client([]), set_targets=targets)


def test_canonical_checks_v4_v10_columns_not_the_legacy_v3_v9_columns():
    v4_v10_row = row("has-v4-v10")
    assert service._canonical(v4_v10_row) is True

    # A row that ONLY carries legacy V3/V9 columns -- even if those legacy columns
    # happen to equal what the OLD canonical selection used to require -- must not
    # be treated as canonical now that canonical selection is V4/V10.
    v3_v9_only_row = dict(v4_v10_row)
    v3_v9_only_row.pop("financial_rip_v4_version")
    v3_v9_only_row.pop("overall_rip_v10_version")
    v3_v9_only_row.pop("overall_rip_v10_rankable")
    assert service._canonical(v3_v9_only_row) is False


def test_rank_key_and_project_read_the_v4_v10_fields_not_v3_v9():
    canonical_row = row("x", overall=42, financial=17)
    # _rank_key must sort on the V10/V4 columns.
    assert service._rank_key(canonical_row)[0] == -42
    assert service._rank_key(canonical_row)[1] == -17

    # Even if the legacy V3/V9 columns disagree with the V4/V10 columns, _project
    # must publish the V4/V10 values as "the" score/version.
    diverging_row = row("y", overall=42, financial=17)
    diverging_row["overall_rip_score"] = 999
    diverging_row["financial_rip_v3_score"] = 999
    diverging_row["overall_rip_version"] = "overall_rip_v9"
    diverging_row["financial_rip_v3_version"] = "financial_rip_v3"
    projected = service._project(diverging_row, {}, 1, 1)
    assert projected["overallRipScore"] == 42
    assert projected["financialRipScore"] == 17
    assert projected["overallRipVersion"] == CANONICAL_OVERALL_RIP_VERSION
    assert projected["financialRipVersion"] == CANONICAL_FINANCIAL_RIP_VERSION


def test_public_tier_uses_leader_score_while_absolute_model_tiers_are_preserved():
    from backend.desirability.composite import assign_composite_tier

    for overall_score in (95, 80, 60, 40, 20, 5):
        projected = service._project(row("x", overall=overall_score), {}, 1, 1, 5, 20, 63, 25)
        assert projected["familyTier"] == assign_composite_tier(overall_score)
        assert projected["publicTier"] == "D"
        assert projected["modelTier"] == assign_composite_tier(overall_score)

    # Tier is derived from the SAME overall_rip_v10_score that produced the
    # rank -- never the legacy v9 column, even when they disagree.
    diverging_row = row("y", overall=90)
    diverging_row["overall_rip_score"] = 5
    projected = service._project(diverging_row, {}, 1, 1, 5, 10, 98.36, 25)
    assert projected["familyTier"] == assign_composite_tier(90)
    assert projected["publicTier"] == "S"


def test_collector_appeal_tier_uses_absolute_composite_scale_not_public_leader_scale():
    projected = service._project(
        row("collector-scale", collector_appeal_score=80), {}, 1, 1,
        overall_leader=90, financial_leader=90,
    )
    assert projected["collectorAppealScore"] == 80
    assert projected["collectorAppealTier"] == "A"
    # The same numeric value interpreted as a leader score would be B (8.0/10).
    assert service.public_leader_rip_tier(80) == "B"


def test_missing_target_run_authority_fails_closed():
    import pytest
    with pytest.raises(ValueError, match="calculation_run_id is missing"):
        service.build_product_family_rankings(
            Client([]), set_targets=[{"set_id": "set-a", "canonical_key": "alpha"}]
        )


def test_canonical_overall_rip_version_flip_to_v12_reranks_on_v12_fields(monkeypatch):
    """If CANONICAL_OVERALL_RIP_VERSION is ever flipped to V12, `_rank_key`/
    `_canonical`/`_project` must key off the v12 score/version/rankable
    columns instead of v10 - proving the family-ranking service is genuinely
    version-generic, not hardcoded to V10, ahead of any real cutover."""
    from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION

    monkeypatch.setattr(service, "CANONICAL_OVERALL_RIP_VERSION", OVERALL_RIP_V12_VERSION)
    rows_in = [
        row(
            "low-v10-high-v12", overall=10,
            overall_rip_v12_score=95, overall_rip_v12_version=OVERALL_RIP_V12_VERSION,
            overall_rip_v12_rankable=True,
        ),
        row(
            "high-v10-low-v12", overall=90,
            overall_rip_v12_score=5, overall_rip_v12_version=OVERALL_RIP_V12_VERSION,
            overall_rip_v12_rankable=True,
        ),
    ]
    result = build(monkeypatch, rows_in)
    products = result["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["low-v10-high-v12", "high-v10-low-v12"]
    assert products[0]["overallRipScore"] == 95
    assert products[0]["overallRipVersion"] == OVERALL_RIP_V12_VERSION
    assert products[0]["familyRank"] == 1


def test_canonical_overall_rip_version_flip_to_v12_excludes_wrong_version_rows(monkeypatch):
    """A row whose v12 version/rankable is not aligned is excluded from the
    V12-canonical cohort even if its v10 fields look fine - `_canonical` must
    gate on the SAME field triple `_rank_key` sorts on, never a mismatched
    pair."""
    from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION

    monkeypatch.setattr(service, "CANONICAL_OVERALL_RIP_VERSION", OVERALL_RIP_V12_VERSION)
    rows_in = [
        row("v12-ready", overall_rip_v12_score=50, overall_rip_v12_version=OVERALL_RIP_V12_VERSION,
            overall_rip_v12_rankable=True),
        row("v12-not-rankable", overall_rip_v12_score=99, overall_rip_v12_version=OVERALL_RIP_V12_VERSION,
            overall_rip_v12_rankable=False),
        row("v12-wrong-version", overall_rip_v12_score=99, overall_rip_v12_version="overall_rip_v12_stale",
            overall_rip_v12_rankable=True),
    ]
    result = build(monkeypatch, rows_in)
    products = result["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["v12-ready"]
