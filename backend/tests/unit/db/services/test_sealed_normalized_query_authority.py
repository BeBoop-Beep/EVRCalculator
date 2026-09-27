from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_sealed_market_explorer_query_service as svc
from backend.domain.pokemon.market_explorer_query import MarketExplorerQueryError
from backend.domain.pokemon.sealed_market_segments import (
    resolve_sealed_family_selection,
    sealed_selection_vocabulary,
)

SET_A, SET_B, ERA = "set-a", "set-b", "era-1"


def meta(pid, family, set_id=SET_A, parent=True, price=100):
    return {"sealed_product_id": pid, "set_id": set_id, "era_id": ERA, "name": pid,
            "set_name": "Set " + set_id, "era_name": "Era", "product_family": family,
            "product_family_label": family.title(), "variant_label": None,
            "parent_membership": parent, "image_small_url": None, "image_large_url": None,
            "latest_market_date": "2026-09-24", "latest_market_price": price}


def daily(pid, day, price, set_id=SET_A, family="booster_box", parent=True):
    return {"sealed_product_id": pid, "market_date": day, "market_price": price,
            "set_id": set_id, "era_id": ERA, "product_family": family, "parent_membership": parent}


class Q:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_a):
        return self

    def eq(self, k, v):
        self.rows = [r for r in self.rows if r.get(k) == v]
        return self

    def in_(self, k, vs):
        self.rows = [r for r in self.rows if r.get(k) in list(vs)]
        return self

    def gte(self, k, v):
        self.rows = [r for r in self.rows if str(r.get(k)) >= str(v)]
        return self

    def lte(self, k, v):
        self.rows = [r for r in self.rows if str(r.get(k)) <= str(v)]
        return self

    def order(self, *_a):
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def range(self, a, b):
        self.rows = self.rows[a:b + 1]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        if name not in self.tables:
            raise RuntimeError("relation does not exist")
        return Q(self.tables[name])


def world():
    days = ["2026-09-22", "2026-09-23", "2026-09-24"]
    products = [("bb1", "booster_box", SET_A, True), ("bb2", "booster_box", SET_B, True),
                ("etb1", "elite_trainer_box", SET_A, True), ("case1", "case", SET_A, False)]
    tables = {
        svc.NORMALIZED_METADATA_TABLE: [meta(p, f, s, par) for p, f, s, par in products],
        svc.NORMALIZED_DAILY_TABLE: [daily(p, d, 100 + i + n, s, f, par)
                                     for n, (p, f, s, par) in enumerate(products) for i, d in enumerate(days)],
        "sets": [{"id": SET_A, "release_date": "2020-01-01"}, {"id": SET_B, "release_date": "2021-01-01"}],
    }
    return Client(tables)


def run(client, **kw):
    args = dict(mode="all", start_date="2026-09-01", end_date="2026-09-24")
    args.update(kw)
    return svc.run_sealed_market_explorer_query(client, **args)


def ids(result):
    return {c["sealedProductId"] for c in result["currentConstituents"]}


def test_legacy_segment_maps_to_canonical_family_membership():
    assert resolve_sealed_family_selection(["boosterBox"]) == frozenset({"booster_box"})
    assert resolve_sealed_family_selection(["packs"]) == frozenset({"loose_booster_pack", "sleeved_booster_pack"})
    assert resolve_sealed_family_selection(["pokemonCenterEliteTrainerBox"]) == frozenset({"pokemon_center_elite_trainer_box"})
    assert resolve_sealed_family_selection(["case", "display"]) == frozenset({"case", "display"})
    assert resolve_sealed_family_selection([]) is None
    with pytest.raises(ValueError):
        resolve_sealed_family_selection(["nope"])
    assert {"boosterBox", "case", "fun_pack", "packs"} <= sealed_selection_vocabulary()


def test_legacy_and_canonical_selection_yield_identical_market():
    legacy = run(world(), segment_ids=["boosterBox"])
    canonical = run(world(), segment_ids=["booster_box"])
    assert ids(legacy) == ids(canonical) == {"bb1", "bb2"}
    assert legacy["trackedValue"] == canonical["trackedValue"]
    assert legacy["metadata"]["seriesPath"] == "normalizedSealedAuthority"


def test_no_family_selection_is_parent_membership_and_excludes_bulk_container():
    assert ids(run(world())) == {"bb1", "bb2", "etb1"}


def test_case_is_buildable_as_its_own_family():
    assert ids(run(world(), segment_ids=["case"])) == {"case1"}


def test_set_and_era_scope_and_single_identity():
    assert ids(run(world(), set_ids=[SET_B])) == {"bb2"}
    assert ids(run(world(), era_ids=[ERA], segment_ids=["boosterBox"])) == {"bb1", "bb2"}


def test_top_n_and_exact_membership():
    top = run(world(), mode="chase", top_n=10, segment_ids=["booster_box"])
    assert len(top["currentConstituents"]) == 2 and top["reconciliation"]["belowRequestedTopN"] is True
    exact = run(world(), membership_mode="explicit", instrument_ids=["etb1", "case1"])
    assert ids(exact) == {"etb1", "case1"}


def test_price_segment_filter_uses_normalized_prices():
    from backend.domain.pokemon.market_explorer_query import price_segment_for
    seg = price_segment_for("sealed", 100)
    other = next(x for x in ("obtainable", "intermediate", "premium") if x != seg)
    assert run(world(), price_segment_ids=[seg])["currentConstituents"]
    with pytest.raises(svc.SealedMarketExplorerQueryUnavailable):
        run(world(), price_segment_ids=[other])


def test_images_stay_null_never_fabricated():
    assert all(c["imageUrl"] is None for c in run(world())["currentConstituents"])


def test_unknown_family_rejected_by_spec():
    with pytest.raises(MarketExplorerQueryError):
        run(world(), segment_ids=["jumboCollection"])


def test_absent_normalized_authority_uses_legacy_path_probe():
    assert svc.normalized_authority_available(Client({})) is False
    assert svc.normalized_authority_available(Client({svc.NORMALIZED_METADATA_TABLE: []})) is False
    assert svc.normalized_authority_available(world()) is True
