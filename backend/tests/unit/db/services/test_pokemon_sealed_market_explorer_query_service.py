"""The sealed Explorer query engine's methodology guarantees.

These are not "does it return a number" tests. Each one pins a property whose
loss would produce a plausible-looking but wrong market:

  * filter FIRST, rank SECOND -- an expensive product outside the selected era
    or family must be gone before ranking, not ranked and then hidden;
  * no set quota -- one set may own every slot;
  * per-date membership -- today's winners are never projected backward;
  * roster swaps cannot move the index, only Tracked Value;
  * families are read from the published taxonomy, never re-decided here.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_sealed_market_explorer_query_service import (
    SEALED_ID_FIELD,
    SealedMarketExplorerQueryUnavailable,
    build_sealed_price_panel,
    build_sealed_query_series,
    describe_sealed_query,
    families_for_segments,
    filter_products_by_family,
    resolve_sealed_scope_set_ids,
    run_sealed_market_explorer_query,
)
from backend.domain.pokemon.market_explorer_query import (
    ASSET_SEALED,
    MODE_ALL,
    MODE_CHASE,
    MarketExplorerQueryError,
    normalize_query_spec,
)

DATES = ["2026-01-01", "2026-01-02", "2026-01-03"]


def product(product_id, family, prices, *, name=None, set_id="set-a"):
    """One prepared sealed product, in the shape the snapshots publish."""
    return {
        SEALED_ID_FIELD: product_id,
        "name": name or f"{product_id} product",
        "productFamily": family,
        "productFamilyLabel": family.replace("_", " ").title(),
        "variantLabel": None,
        "setId": set_id,
        "history": [
            {"date": date, "marketPrice": price, "isObserved": True}
            for date, price in zip(DATES, prices) if price is not None
        ],
    }


def panel(products, start=DATES[0], end=DATES[-1]):
    return build_sealed_price_panel(products, start_date=start, end_date=end)


def metadata(products):
    return {
        str(item[SEALED_ID_FIELD]): {
            "productName": item["name"],
            "setId": item.get("setId"),
            "setName": "Set A",
            "productFamily": item["productFamily"],
            "productFamilyLabel": item["productFamilyLabel"],
        }
        for item in products
    }


# ---------------------------------------------------------------------------
# Family filter (section 7, 50)
# ---------------------------------------------------------------------------

def test_families_come_from_the_published_taxonomy():
    assert families_for_segments(["boosterBox"]) == frozenset({"booster_box"})
    assert families_for_segments(["eliteTrainerBox"]) == frozenset({"elite_trainer_box"})
    assert families_for_segments(["pokemonCenterEliteTrainerBox"]) == frozenset(
        {"pokemon_center_elite_trainer_box"}
    )
    assert families_for_segments(["boosterBundle"]) == frozenset({"booster_bundle"})


def test_packs_is_the_declared_composite_and_nothing_more():
    assert families_for_segments(["packs"]) == frozenset(
        {"loose_booster_pack", "sleeved_booster_pack"}
    )


def test_no_segment_selection_means_every_eligible_product():
    assert families_for_segments([]) is None


def test_an_unknown_family_is_rejected_rather_than_ignored():
    with pytest.raises(MarketExplorerQueryError):
        families_for_segments(["jumboCollection"])


def test_pokemon_center_etbs_are_never_folded_into_standard_etbs():
    products = [
        product("etb", "elite_trainer_box", [50, 50, 50]),
        product("pc-etb", "pokemon_center_elite_trainer_box", [5000, 5000, 5000]),
    ]
    kept = filter_products_by_family(products, families_for_segments(["eliteTrainerBox"]))
    assert [row[SEALED_ID_FIELD] for row in kept] == ["etb"]


def test_half_and_enhanced_booster_boxes_stay_out_of_booster_boxes():
    products = [
        product("bb", "booster_box", [300, 300, 300]),
        product("half", "half_booster_box", [900, 900, 900]),
        product("enhanced", "enhanced_booster_box", [900, 900, 900]),
    ]
    kept = filter_products_by_family(products, families_for_segments(["boosterBox"]))
    assert [row[SEALED_ID_FIELD] for row in kept] == ["bb"]


# ---------------------------------------------------------------------------
# Filter first, rank second (sections 48-50)
# ---------------------------------------------------------------------------

def test_a_family_filter_applies_before_ranking():
    # The PC ETB is by far the most expensive product. If ranking happened
    # first it would take slot 1 of a standard-ETB Top 2 and then be hidden.
    products = [
        product("pc-etb", "pokemon_center_elite_trainer_box", [5000, 5000, 5000]),
        product("etb-a", "elite_trainer_box", [90, 90, 90]),
        product("etb-b", "elite_trainer_box", [80, 80, 80]),
    ]
    eligible = filter_products_by_family(products, families_for_segments(["eliteTrainerBox"]))
    series = build_sealed_query_series(
        panel(eligible), metadata(products), mode=MODE_CHASE, top_n=2,
    )
    ids = [row[SEALED_ID_FIELD] for row in series["currentConstituents"]]
    assert ids == ["etb-a", "etb-b"]
    assert "pc-etb" not in ids


def test_a_set_filter_applies_before_ranking():
    # The out-of-scope box is the most expensive in the world; scoping to set-a
    # must remove it from the universe, not rank it and then drop it.
    in_scope = [product("bb-a", "booster_box", [300, 300, 300], set_id="set-a")]
    out_of_scope = [product("bb-z", "booster_box", [9000, 9000, 9000], set_id="set-z")]
    series = build_sealed_query_series(
        panel(in_scope), metadata(in_scope + out_of_scope), mode=MODE_CHASE, top_n=10,
    )
    ids = [row[SEALED_ID_FIELD] for row in series["currentConstituents"]]
    assert ids == ["bb-a"]
    assert series["reconciliation"]["eligibleUniverseCount"] == 1


def test_fewer_than_ten_is_reported_not_padded():
    products = [product(f"bb-{i}", "booster_box", [100 + i, 100 + i, 100 + i]) for i in range(7)]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=10,
    )
    assert len(series["currentConstituents"]) == 7
    assert series["reconciliation"]["requestedTopN"] == 10
    assert series["reconciliation"]["actualConstituentCount"] == 7
    assert series["reconciliation"]["belowRequestedTopN"] is True


# ---------------------------------------------------------------------------
# No set quota (section 51)
# ---------------------------------------------------------------------------

def test_one_set_may_own_every_slot_in_a_top_basket():
    dominant = [
        product(f"a-{i}", "booster_box", [1000 - i, 1000 - i, 1000 - i], set_id="set-a")
        for i in range(4)
    ]
    others = [
        product("b-1", "booster_box", [50, 50, 50], set_id="set-b"),
        product("c-1", "booster_box", [40, 40, 40], set_id="set-c"),
    ]
    products = dominant + others
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=4,
    )
    ids = [row[SEALED_ID_FIELD] for row in series["currentConstituents"]]
    assert ids == ["a-0", "a-1", "a-2", "a-3"], "no slot is reserved for a set"
    assert series["metadata"]["representedSetCount"] == 1


# ---------------------------------------------------------------------------
# Dynamic historical membership (sections 13, 52)
# ---------------------------------------------------------------------------

def test_membership_is_re_ranked_on_every_date():
    products = [
        product("a", "booster_box", [100, 100, 100]),
        product("b", "booster_box", [50, 200, 200]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=1,
    )
    by_date = {row["marketDate"]: row["constituentIds"] for row in series["membershipByDate"]}
    assert by_date["2026-01-01"] == ["a"], "A led on day one and history must say so"
    assert by_date["2026-01-02"] == ["b"], "B overtook A on day two"
    assert by_date["2026-01-03"] == ["b"]


def test_todays_winner_is_never_projected_backward():
    # If the engine resolved today's top product and fetched its history, day
    # one would name B. It must name A.
    products = [
        product("a", "booster_box", [100, 10, 10]),
        product("b", "booster_box", [1, 500, 500]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=1,
    )
    assert series["membershipByDate"][0]["constituentIds"] == ["a"]
    assert series["currentConstituents"][0][SEALED_ID_FIELD] == "b"


# ---------------------------------------------------------------------------
# Index vs Tracked Value on a roster swap (sections 14, 53)
# ---------------------------------------------------------------------------

def test_a_roster_swap_moves_tracked_value_but_not_the_index():
    # Common constituents are flat across the swap. A leaves and B enters at a
    # different price level: Tracked Value must move, the index must not.
    products = [
        product("common-1", "booster_box", [100, 100, 100]),
        product("common-2", "booster_box", [100, 100, 100]),
        product("leaver", "booster_box", [80, None, None]),
        product("joiner", "booster_box", [None, 300, 300]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_ALL, top_n=None,
    )
    index_by_date = {date: value for date, value in series["trend"]}
    tracked = {row["date"]: row["value"] for row in series["trackedValueHistory"]}

    assert index_by_date["2026-01-01"] == pytest.approx(100.0)
    assert index_by_date["2026-01-02"] == pytest.approx(100.0), (
        "the common cohort was flat, so a roster replacement must contribute no return"
    )
    assert tracked["2026-01-01"] == pytest.approx(280.0)
    assert tracked["2026-01-02"] == pytest.approx(500.0), (
        "Tracked Value is the literal basket and is allowed to move on a swap"
    )


def test_the_index_measures_common_product_price_movement():
    products = [
        product("a", "booster_box", [100, 110, 110]),
        product("b", "booster_box", [100, 110, 110]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_ALL, top_n=None,
    )
    index_by_date = {date: value for date, value in series["trend"]}
    assert index_by_date["2026-01-02"] == pytest.approx(110.0)


def test_a_zero_price_is_dropped_rather_than_read_as_a_collapse():
    products = [
        product("a", "booster_box", [100, 0, 100]),
        product("b", "booster_box", [100, 100, 100]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_ALL, top_n=None,
    )
    index_by_date = {date: value for date, value in series["trend"]}
    assert index_by_date["2026-01-02"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Constituent contract (sections 17, 19)
# ---------------------------------------------------------------------------

def test_sealed_constituents_carry_product_identity_not_card_fields():
    products = [product("bb-a", "booster_box", [300, 300, 300], name="Surging Sparks Booster Box")]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=10,
    )
    row = series["currentConstituents"][0]
    assert row[SEALED_ID_FIELD] == "bb-a"
    assert row["productName"] == "Surging Sparks Booster Box"
    assert row["productFamily"] == "booster_box"
    assert row["productFamilyLabel"] == "Booster Box"
    assert row["setName"] == "Set A"
    assert row["marketPrice"] == pytest.approx(300.0)
    assert row["rank"] == 1
    assert row["asOf"] == "2026-01-03"
    assert "canonicalCardId" not in row, "no fake card fields to force one row shape"
    assert "rarity" not in row


def test_all_mode_ranks_by_current_price_for_display():
    products = [
        product("cheap", "booster_box", [10, 10, 10]),
        product("dear", "booster_box", [900, 900, 900]),
        product("mid", "booster_box", [100, 100, 100]),
    ]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_ALL, top_n=None,
    )
    ids = [row[SEALED_ID_FIELD] for row in series["currentConstituents"]]
    assert ids == ["dear", "mid", "cheap"]
    assert series["currentConstituents"][0]["queryMembershipReason"].startswith("eligible product")


def test_top_mode_states_the_membership_reason_as_a_rank():
    products = [product(f"bb-{i}", "booster_box", [100 - i, 100 - i, 100 - i]) for i in range(3)]
    series = build_sealed_query_series(
        panel(products), metadata(products), mode=MODE_CHASE, top_n=2,
    )
    assert series["currentConstituents"][0]["queryMembershipReason"] == (
        "rank 1 by market price within the filtered universe"
    )


# ---------------------------------------------------------------------------
# Labels and identity (sections 4, 34)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("segments", "mode", "top_n", "expected"),
    [
        ((), MODE_ALL, None, "Global · All Sealed Products · All"),
        (("eliteTrainerBox",), MODE_ALL, None, "Global · Elite Trainer Boxes · All"),
        (("boosterBox",), MODE_CHASE, 10, "Global · Booster Boxes · Top 10"),
    ],
)
def test_global_sealed_labels(segments, mode, top_n, expected):
    spec = normalize_query_spec(
        mode=mode, asset=ASSET_SEALED, segment_ids=segments, top_n=top_n,
    )
    assert describe_sealed_query(spec) == expected


def test_a_scoped_sealed_label_names_the_era():
    spec = normalize_query_spec(
        mode=MODE_ALL, asset=ASSET_SEALED, era_ids=["era-sv"], segment_ids=["eliteTrainerBox"],
    )
    assert describe_sealed_query(spec, era_names={"era-sv": "Scarlet & Violet"}) == (
        "Scarlet & Violet · Elite Trainer Boxes · All"
    )


def test_a_named_set_wins_over_its_era_in_the_label():
    spec = normalize_query_spec(
        mode=MODE_CHASE, asset=ASSET_SEALED, era_ids=["era-sv"], set_ids=["set-ah"],
        segment_ids=["pokemonCenterEliteTrainerBox"], top_n=10,
    )
    label = describe_sealed_query(
        spec, era_names={"era-sv": "Scarlet & Violet"}, set_names={"set-ah": "Ascended Heroes"},
    )
    assert label == "Ascended Heroes · Pokémon Center ETBs · Top 10"


# ---------------------------------------------------------------------------
# Scope resolution and failure modes
# ---------------------------------------------------------------------------

class _FakeClient:
    """Minimal PostgREST double: prepared sealed snapshots and set/era rows."""

    def __init__(self, *, sealed_set_ids, sets_by_era=None, snapshots=None, eras=None):
        self._sealed_set_ids = list(sealed_set_ids)
        self._sets_by_era = sets_by_era or {}
        self._snapshots = snapshots or {}
        self._eras = eras or {}

    def table(self, name):
        return _FakeTable(self, name)


class _FakeTable:
    def __init__(self, client, name):
        self.client, self.name, self._filters = client, name, {}

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, column, values):
        self._filters[column] = list(values)
        return self

    def range(self, start, end):
        self._filters["range"] = (start, end)
        return self

    def execute(self):
        if self.name == "pokemon_set_sealed_market_snapshot_latest":
            if "set_id" in self._filters:
                rows = [
                    {"set_id": set_id, "market_date": "2026-01-03",
                     "payload_json": self.client._snapshots.get(set_id, {})}
                    for set_id in self._filters["set_id"]
                    if set_id in self.client._snapshots
                ]
            else:
                rows = [{"set_id": set_id} for set_id in self.client._sealed_set_ids]
                start, end = self._filters.get("range", (0, 999))
                rows = rows[start:end + 1]
            return _Result(rows)
        if self.name == "sets":
            era_ids = self._filters.get("era_id", [])
            rows = [
                {"id": set_id, "era_id": era_id}
                for era_id in era_ids
                for set_id in self.client._sets_by_era.get(era_id, [])
            ]
            return _Result(rows)
        if self.name == "eras":
            return _Result([
                {"id": era_id, "name": self.client._eras.get(era_id, "")}
                for era_id in self._filters.get("id", [])
            ])
        return _Result([])


class _Result:
    def __init__(self, data):
        self.data = data


def snapshot_payload(set_id, set_name, products):
    return {"set": {"id": set_id, "name": set_name}, "products": products, "marketDate": "2026-01-03"}


def test_scope_intersects_era_and_set_filters():
    client = _FakeClient(
        sealed_set_ids=["set-a", "set-b", "set-z"],
        sets_by_era={"era-sv": ["set-a", "set-b"]},
    )
    # set-z is named explicitly but sits outside the selected era: both filters
    # must hold, so it is dropped rather than silently honoured.
    assert resolve_sealed_scope_set_ids(
        client, era_ids=["era-sv"], set_ids=["set-a", "set-z"],
    ) == ["set-a"]


def test_a_scope_with_no_prepared_snapshot_is_refused_rather_than_empty():
    client = _FakeClient(sealed_set_ids=["set-a"], sets_by_era={"era-x": ["set-q"]})
    with pytest.raises(SealedMarketExplorerQueryUnavailable):
        run_sealed_market_explorer_query(
            client, mode=MODE_ALL, era_ids=["era-x"],
            start_date="2026-01-01", end_date="2026-01-03",
        )


def test_end_to_end_sealed_query_through_prepared_snapshots():
    products = [
        product("bb-a", "booster_box", [300, 310, 320], name="Set A Booster Box", set_id="set-a"),
        product("etb-a", "elite_trainer_box", [50, 52, 54], name="Set A ETB", set_id="set-a"),
        product("pc-a", "pokemon_center_elite_trainer_box", [900, 900, 900],
                name="Set A PC ETB", set_id="set-a"),
    ]
    client = _FakeClient(
        sealed_set_ids=["set-a"],
        sets_by_era={"era-sv": ["set-a"]},
        snapshots={"set-a": snapshot_payload("set-a", "Set A", products)},
        eras={"era-sv": "Scarlet & Violet"},
    )
    result = run_sealed_market_explorer_query(
        client, mode=MODE_ALL, era_ids=["era-sv"], segment_ids=["eliteTrainerBox"],
        start_date="2026-01-01", end_date="2026-01-03",
    )
    assert result["spec"]["asset"] == ASSET_SEALED
    assert result["displayLabel"] == "Scarlet & Violet · Elite Trainer Boxes · All"
    assert result["queryKey"].startswith("sealed|")
    assert [row[SEALED_ID_FIELD] for row in result["currentConstituents"]] == ["etb-a"]
    assert result["currentConstituents"][0]["setName"] == "Set A"
    assert result["scope"]["eligibleProductCount"] == 1
    assert result["metadata"]["seriesPath"] == "preparedSealedSnapshots"
    assert result["indexValue"] == pytest.approx(108.0)


def test_a_card_rarity_cannot_be_requested_as_a_sealed_query():
    client = _FakeClient(sealed_set_ids=["set-a"])
    with pytest.raises(MarketExplorerQueryError):
        run_sealed_market_explorer_query(
            client, mode=MODE_ALL, segment_ids=["specialIllustrationRare"],
            start_date="2026-01-01", end_date="2026-01-03",
        )
