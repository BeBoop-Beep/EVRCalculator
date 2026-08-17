from backend.db.services import product_family_rankings_service as service
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_a): return self
    def in_(self, _field, values):
        self.rows = [r for r in self.rows if r["calculation_run_id"] in values]
        return self
    def execute(self):
        return type("Result", (), {"data": self.rows})()


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name):
        assert name == "simulation_sealed_product_results"
        return Query(list(self.rows))


def row(product, family="booster_box", run="current", overall=80, financial=70, chance=.4, price=100, **changes):
    value = {
        "calculation_run_id": run, "sealed_product_id": product, "set_id": "set-1",
        "product_family": family, "product_name": product, "pack_count": 36,
        "product_market_cost": price, "expected_value": 80, "median_value": 55,
        "chance_to_recover_cost": chance, "financial_rip_v3_score": financial,
        "financial_rip_v3_version": CANONICAL_FINANCIAL_RIP_VERSION,
        "collector_appeal_score": 60, "collector_appeal_version": canonical_collector_appeal_version(),
        "overall_rip_score": overall, "overall_rip_version": CANONICAL_OVERALL_RIP_VERSION,
        "overall_rip_rankable": True,
    }
    value.update(changes)
    return value


def build(monkeypatch, rows):
    return service.build_product_family_rankings(
        Client(rows),
        set_targets=[{"set_id": "set-1", "canonical_key": "alpha", "calculation_run_id": "current", "name": "Alpha", "logo_image_url": "logo"}],
    )


def test_current_canonical_rows_only_and_deferred_products_are_not_fabricated(monkeypatch):
    payload = build(monkeypatch, [row("ranked"), row("historical", run="old")])
    products = payload["families"]["booster_box"]["products"]
    assert [p["sealedProductId"] for p in products] == ["ranked"]
    assert payload["partialToCurrentlyScoredProducts"] is True


def test_versions_and_rankable_flag_gate_rankings(monkeypatch):
    rows = [row("good"), row("old-ca", collector_appeal_version="v4"), row("old-overall", overall_rip_version="v8"), row("not-rankable", overall_rip_rankable=False)]
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


def test_missing_target_run_authority_fails_closed():
    import pytest
    with pytest.raises(ValueError, match="calculation_run_id is missing"):
        service.build_product_family_rankings(
            Client([]), set_targets=[{"set_id": "set-a", "canonical_key": "alpha"}]
        )
