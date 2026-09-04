"""Filter-first behaviour of the Market Explorer card query engine.

These tests exist to prove the properties that distinguish the ACCEPTED chase
model from the REJECTED one. A naive implementation that ranked globally and
then filtered, or that reserved a slot per set, would still produce a ten-row
basket -- so "the basket has ten cards" proves nothing. Each test below fails
loudly under exactly one wrong construction.
"""

from __future__ import annotations

import pytest

from backend.db.services import pokemon_market_explorer_query_service as svc
from backend.db.services.market_explorer_query_planner import resolve_canonical_through
from backend.domain.pokemon.market_explorer_query import normalize_query_spec
from backend.domain.pokemon.market_explorer_query import MODE_ALL, MODE_CHASE

SV_ERA = "era-sv"
SWSH_ERA = "era-swsh"

# Two sets in Scarlet & Violet, one in Sword & Shield.
SETS = [
    {"id": "set-ah", "era_id": SV_ERA, "name": "Ascended Heroes", "release_date": "2025-12-01"},
    {"id": "set-pe", "era_id": SV_ERA, "name": "Prismatic Evolutions", "release_date": "2025-01-01"},
    {"id": "set-ev", "era_id": SWSH_ERA, "name": "Evolving Skies", "release_date": "2021-08-27"},
]


def _card(card_id, set_id, rarity, name=None):
    return {"id": card_id, "set_id": set_id, "name": name or card_id,
            "rarity": rarity, "number": "1", "image_small_url": f"http://img/{card_id}"}


CARDS = [
    # Ascended Heroes: 5 expensive SIRs -- deliberately enough to dominate a
    # global top ten on its own (section 40).
    *[_card(f"ah-sir-{i}", "set-ah", "Special Illustration Rare") for i in range(5)],
    # Prismatic Evolutions: 6 mid-priced SIRs.
    *[_card(f"pe-sir-{i}", "set-pe", "Special Illustration Rare") for i in range(6)],
    # Evolving Skies (a DIFFERENT era) holds the single most expensive SIR.
    _card("ev-sir-0", "set-ev", "Special Illustration Rare"),
    # The most expensive card in the whole universe is NOT an SIR.
    _card("ah-hyper-0", "set-ah", "Hyper Rare"),
]

# Prices are chosen so each filter dimension changes the answer visibly.
PRICES = {
    "ah-hyper-0": 5000.0,   # most expensive card overall, wrong rarity
    "ev-sir-0": 3000.0,     # most expensive SIR, wrong era for an SV query
    **{f"ah-sir-{i}": 900.0 - i for i in range(5)},
    **{f"pe-sir-{i}": 500.0 - i for i in range(6)},
}

DATES = ["2026-01-01", "2026-01-02"]


class _Query:
    """Minimal PostgREST-shaped query recorder."""

    def __init__(self, rows, filters=None):
        self._rows = rows
        self._filters = filters or []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        return _Query(self._rows, self._filters + [(column, "eq", value)])

    def in_(self, column, values):
        return _Query(self._rows, self._filters + [(column, "in", list(values))])

    def order(self, column, desc=False):
        # Real paging depends on a deterministic order, so the double must sort
        # too: a fake that ignored `order` would let a paging bug pass here and
        # only surface against the live database.
        return _Query(self._rows, self._filters + [(column, "order", bool(desc))])

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, count):
        self._range = (0, count - 1)
        return self

    def execute(self):
        rows = self._rows
        orderings = []
        for column, op, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if str(row.get(column)) == str(value)]
            elif op == "order":
                orderings.append((column, value))
            else:
                wanted = {str(item) for item in value}
                rows = [row for row in rows if str(row.get(column)) in wanted]
        for column, desc in reversed(orderings):
            rows = sorted(rows, key=lambda row: str(row.get(column) or ""), reverse=desc)
        start, end = getattr(self, "_range", (0, 999))
        return type("Result", (), {"data": rows[start:end + 1]})()


def _panel(prices, set_ids, card_ids):
    """The card-date panel the batched constituent RPC would return."""
    allowed_sets = {str(value) for value in set_ids}
    allowed_cards = None if card_ids is None else {str(value) for value in card_ids}
    rows = []
    for card in CARDS:
        if card["set_id"] not in allowed_sets:
            continue
        if allowed_cards is not None and card["id"] not in allowed_cards:
            continue
        for market_date in DATES:
            price = prices.get(card["id"])
            if isinstance(price, dict):
                price = price.get(market_date)
            if price is None:
                continue
            rows.append({"card_variant_id": f"variant-{card['id']}",
                         "canonical_card_id": card["id"], "legacy_card_id": f"legacy-{card['id']}",
                         "set_id": card["set_id"], "card_name": card["name"],
                         "card_number": card["number"], "rarity": card["rarity"],
                         "edition": None, "printing_type": "holo", "special_type": None,
                         "image_url": card["image_small_url"],
                         "market_date": market_date, "market_price": price})
    return rows


class _RpcResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeClient:
    def __init__(self, prices=None):
        self.prices = prices if prices is not None else PRICES

    def rpc(self, name, payload):
        """Reproduce the two server-side RPCs against the fixture panel.

        The cohort aggregation mirrors the SQL: rank within each date, apply the
        chase cutoff PER DATE, then sum the day's basket and the cohort common
        with the previous observed day.
        """
        rows = _panel(self.prices, payload["p_set_ids"], payload.get("p_card_ids"))
        start, end = payload["p_start_date"], payload["p_end_date"]
        rows = [row for row in rows if start <= row["market_date"] <= end]

        if name == "get_pokemon_cards_daily_constituents":
            return _RpcResult(rows)

        if name in (svc.FILTERED_COHORT_RPC, svc.DAILY_PROJECTION_RPC):
            segment_ids = set(payload.get("p_segment_ids") or [])
            price_segments = set(payload.get("p_price_segment_ids") or [])
            release_cohorts = set(payload.get("p_release_age_cohort_ids") or [])
            releases = {row["id"]: row["release_date"] for row in SETS}
            normalized = []
            for row in rows:
                card = next(card for card in CARDS if card["id"] == row["canonical_card_id"])
                segment = ("specialIllustrationRare"
                           if card["rarity"] == "Special Illustration Rare"
                           else "hyperRare" if card["rarity"] == "Hyper Rare" else None)
                price = float(row["market_price"])
                price_segment = "obtainable" if price < 10 else "intermediate" if price < 100 else "premium"
                age = (__import__("datetime").date.fromisoformat(row["market_date"]) - __import__("datetime").date.fromisoformat(releases[row["set_id"]])).days
                release = "new" if age <= 180 else "recent" if age <= 730 else "established" if age <= 1825 else "legacy"
                if (not segment_ids or segment in segment_ids) and (not price_segments or price_segment in price_segments) and (not release_cohorts or release in release_cohorts):
                    normalized.append(row)
            by_date = {}
            for row in normalized:
                by_date.setdefault(row["market_date"], []).append(row)
            output, previous = [], None
            for market_date in sorted(by_date):
                universe = sorted(by_date[market_date], key=lambda row: (-float(row["market_price"]), row["card_variant_id"]))
                selected = universe[:payload["p_top_n"]] if payload.get("p_top_n") else universe
                current = {row["card_variant_id"]: float(row["market_price"]) for row in selected}
                common = set() if previous is None else previous.keys() & current.keys()
                output.append({"market_date": market_date, "constituent_count": len(current), "eligible_universe_count": len(universe), "basket_value": sum(current.values()), "common_count": len(common), "common_current_value": sum(current[key] for key in common), "common_previous_value": sum(previous[key] for key in common) if previous else 0, "current_constituents": [{**row, "rank": rank} for rank, row in enumerate(selected, 1)]})
                previous = current
            return _RpcResult(output)

        assert name == "get_pokemon_market_explorer_daily_cohort", name
        top_n = payload.get("p_top_n")
        by_date = {}
        for row in rows:
            by_date.setdefault(row["market_date"], []).append(row)

        output, previous = [], None
        for market_date in sorted(by_date):
            universe = sorted(by_date[market_date],
                              key=lambda row: (-float(row["market_price"]), row["card_variant_id"]))
            selected = universe[:top_n] if top_n else universe
            current = {row["card_variant_id"]: float(row["market_price"]) for row in selected}
            common = set() if previous is None else previous.keys() & current.keys()
            output.append({
                "market_date": market_date,
                "constituent_count": len(current),
                "eligible_universe_count": len(universe),
                "basket_value": round(sum(current.values()), 2),
                "common_count": len(common),
                "common_current_value": round(sum(current[key] for key in common), 2),
                "common_previous_value": round(sum(previous[key] for key in common), 2) if previous else 0.0,
            })
            previous = current
        return _RpcResult(output)

    def table(self, name):
        if name == "pokemon_set_value_daily_history_coverage":
            return _Query([{"set_id": row["id"], "has_history": True,
                            "first_snapshot_date": DATES[0],
                            "latest_snapshot_date": DATES[-1]} for row in SETS])
        if name == "pokemon_market_date_quality":
            return _Query([
                {"market_date": market_date, "tcg": "pokemon", "status": "READY"}
                for market_date in DATES
            ])
        if name == "sets":
            return _Query(SETS)
        if name == "eras":
            return _Query([
                {"id": SV_ERA, "name": "Scarlet & Violet", "sort_order": 1},
                {"id": SWSH_ERA, "name": "Sword & Shield", "sort_order": 2},
            ])
        if name == "pokemon_canonical_cards":
            return _Query(CARDS)
        raise AssertionError(f"unexpected table read: {name}")


@pytest.fixture(autouse=True)
def _stub_constituent_rpc(monkeypatch):
    """Serve the per-card daily panel from the fixture price table."""

    def _load(set_id, start, end, client=None):
        prices = getattr(client, "prices", PRICES)
        rows = []
        for card in CARDS:
            if card["set_id"] != set_id:
                continue
            for market_date in DATES:
                price = prices.get(card["id"])
                if isinstance(price, dict):
                    price = price.get(market_date)
                if price is None:
                    continue
                rows.append({"card_variant_id": f"variant-{card['id']}",
                             "canonical_card_id": card["id"], "market_date": market_date,
                             "market_price": price})
        return rows

    monkeypatch.setattr(svc, "load_card_constituent_rows", _load)


def _run(**kwargs):
    kwargs.setdefault("start_date", DATES[0])
    kwargs.setdefault("end_date", DATES[-1])
    return svc.run_market_explorer_query(kwargs.pop("client", FakeClient()), **kwargs)


def _ids(result):
    return [row["canonicalCardId"] for row in result["currentConstituents"]]


def test_cards_cohort_max_date_matches_publication_watermark():
    client = FakeClient()
    spec = normalize_query_spec(asset="cards", mode=MODE_ALL, set_ids=["set-ah"])
    result = _run(client=client, mode=MODE_ALL, set_ids=["set-ah"])
    assert result["asOf"] == resolve_canonical_through(client, spec) == DATES[-1]


def test_unknown_pokemon_id_fails_before_any_market_history_is_loaded():
    class PokemonClient(FakeClient):
        def table(self, name):
            if name == "pokemon_reference":
                return _Query([{"id": "149", "display_name": "Dragonite"}])
            return super().table(name)

    with pytest.raises(svc.MarketExplorerQueryError, match="unknown Pokemon id"):
        svc.resolve_pokemon_card_ids(PokemonClient(), ["9999"])


# ---------------------------------------------------------------------------
# Section 47 -- rarity filter is applied BEFORE ranking
# ---------------------------------------------------------------------------

def test_expensive_wrong_rarity_card_cannot_enter_a_sir_chase():
    result = _run(mode=MODE_CHASE, segment_ids=["specialIllustrationRare"], top_n=10)
    assert "ah-hyper-0" not in _ids(result)
    # ...and it really is the most expensive card in the unfiltered universe.
    unfiltered = _run(mode=MODE_CHASE, top_n=10)
    assert _ids(unfiltered)[0] == "ah-hyper-0"


# ---------------------------------------------------------------------------
# Section 45 -- era filter is applied BEFORE ranking
# ---------------------------------------------------------------------------

def test_era_scoped_chase_differs_from_global_chase():
    global_chase = _run(mode=MODE_CHASE, segment_ids=["specialIllustrationRare"], top_n=10)
    sv_chase = _run(mode=MODE_CHASE, era_ids=[SV_ERA],
                    segment_ids=["specialIllustrationRare"], top_n=10)
    # The single most valuable SIR lives in Sword & Shield: it tops the global
    # basket and must be absent from the Scarlet & Violet one.
    assert _ids(global_chase)[0] == "ev-sir-0"
    assert "ev-sir-0" not in _ids(sv_chase)
    assert _ids(global_chase) != _ids(sv_chase)


# ---------------------------------------------------------------------------
# Section 46 -- set filter is applied BEFORE ranking
# ---------------------------------------------------------------------------

def test_set_scoped_chase_contains_only_that_set():
    result = _run(mode=MODE_CHASE, set_ids=["set-ah"],
                  segment_ids=["specialIllustrationRare"], top_n=10)
    assert {row["setId"] for row in result["currentConstituents"]} == {"set-ah"}


def test_era_and_set_together_must_both_be_satisfied():
    """A set outside the selected era is dropped, not silently honoured."""
    with pytest.raises(svc.MarketExplorerQueryUnavailable):
        _run(mode=MODE_ALL, era_ids=[SV_ERA], set_ids=["set-ev"])


# ---------------------------------------------------------------------------
# Sections 40/41 -- no set quota
# ---------------------------------------------------------------------------

def test_one_set_may_occupy_multiple_chase_positions():
    result = _run(mode=MODE_CHASE, era_ids=[SV_ERA],
                  segment_ids=["specialIllustrationRare"], top_n=10)
    from collections import Counter
    per_set = Counter(row["setId"] for row in result["currentConstituents"])
    assert per_set["set-ah"] == 5, "all five Ascended Heroes SIRs must survive"
    assert per_set["set-pe"] == 5


def test_a_set_below_the_cutoff_contributes_nothing():
    result = _run(mode=MODE_CHASE, era_ids=[SV_ERA],
                  segment_ids=["specialIllustrationRare"], top_n=5)
    assert {row["setId"] for row in result["currentConstituents"]} == {"set-ah"}


# ---------------------------------------------------------------------------
# Section 42 -- fewer than N
# ---------------------------------------------------------------------------

def test_fewer_than_requested_returns_what_exists_and_reports_it():
    result = _run(mode=MODE_CHASE, set_ids=["set-ah"],
                  segment_ids=["specialIllustrationRare"], top_n=10)
    reconciliation = result["reconciliation"]
    assert reconciliation["requestedTopN"] == 10
    assert reconciliation["actualConstituentCount"] == 5
    assert reconciliation["belowRequestedTopN"] is True
    assert len(result["currentConstituents"]) == 5


# ---------------------------------------------------------------------------
# Sections 14/15/43/44 -- dynamic membership and entry/exit neutrality
# ---------------------------------------------------------------------------

def _reference_series(prices, *, set_ids, card_ids, mode, top_n):
    """Build the series through the REFERENCE row-based path.

    The served path aggregates per date inside the database and therefore
    transports only today's constituent identities. Per-date membership is still
    computed correctly there -- the cutoff is applied per date before
    aggregation -- but the ids do not travel, so the two guarantees below are
    asserted where the identities exist. `build_query_series` and
    `build_query_series_from_cohorts` are held to the same numbers by
    test_served_and_reference_paths_agree.
    """
    rows = [
        {"card_variant_id": row["card_variant_id"],
         "canonical_card_id": row["canonical_card_id"], "market_date": row["market_date"],
         "market_price": row["market_price"]}
        for row in _panel(prices, set_ids, card_ids)
    ]
    metadata = {f"variant-{card['id']}": {"canonicalCardId": card["id"],
                "setId": card["set_id"], "cardName": card["name"],
                "rarity": card["rarity"]} for card in CARDS}
    return svc.build_query_series(rows, metadata, mode=mode, top_n=top_n)


SV_SIR_CARD_IDS = [card["id"] for card in CARDS
                   if card["set_id"] in {"set-ah", "set-pe"}
                   and card["rarity"] == "Special Illustration Rare"]
SV_SET_IDS = ["set-ah", "set-pe"]


def test_membership_changes_between_days_without_rewriting_history():
    """Section 43. pe-sir-0 overtakes ah-sir-0 on day two only."""
    prices = dict(PRICES)
    prices["pe-sir-0"] = {DATES[0]: 500.0, DATES[1]: 5000.0}
    series = _reference_series(prices, set_ids=SV_SET_IDS, card_ids=SV_SIR_CARD_IDS,
                               mode=MODE_CHASE, top_n=1)
    day_one, day_two = [entry["constituentIds"] for entry in series["membershipByDate"]]
    # Today's champion is NOT projected backward: on day one pe-sir-0 was worth
    # 500 and ah-sir-0 was the top SIR, and the history says exactly that.
    assert day_one == ["variant-ah-sir-0"]
    assert day_two == ["variant-pe-sir-0"]


def test_a_pure_roster_swap_does_not_move_the_index():
    """Section 44. Card B replaces Card A, entering far above the leaver.

    The four surviving constituents are all flat, so the ONLY thing that changed
    between the two days is the swap. A construction that measured basket against
    basket would report a large gain here; the chain-linked index must report none.
    """
    prices = dict(PRICES)
    prices["ah-sir-4"] = {DATES[0]: 896.0}          # priced day one only
    prices["pe-sir-0"] = {DATES[1]: 4000.0}         # priced day two only
    series = _reference_series(prices, set_ids=SV_SET_IDS, card_ids=SV_SIR_CARD_IDS,
                               mode=MODE_CHASE, top_n=5)

    day_one, day_two = [entry["constituentIds"] for entry in series["membershipByDate"]]
    assert "variant-ah-sir-4" in day_one and "variant-ah-sir-4" not in day_two
    assert "variant-pe-sir-0" in day_two and "variant-pe-sir-0" not in day_one

    index_day_one, index_day_two = (point[1] for point in series["trend"])
    assert index_day_two == pytest.approx(index_day_one)
    tracked = [row["value"] for row in series["trackedValueHistory"]]
    assert tracked[1] > tracked[0], "Tracked Value is expected to move on a swap"


def test_served_and_reference_paths_agree():
    """The fast served path must not be a second, subtly different index.

    Same query, same fixtures, two independent implementations: the database
    cohort aggregation feeding build_query_series_from_cohorts, and the full
    card-date panel feeding build_query_series.
    """
    served = _run(mode=MODE_CHASE, era_ids=[SV_ERA],
                  segment_ids=["specialIllustrationRare"], top_n=5)
    reference = _reference_series(PRICES, set_ids=SV_SET_IDS, card_ids=SV_SIR_CARD_IDS,
                                  mode=MODE_CHASE, top_n=5)

    assert served["asOf"] == reference["asOf"]
    assert served["trackedValue"] == pytest.approx(reference["trackedValue"])
    assert served["indexValue"] == pytest.approx(reference["indexValue"])
    assert [point[1] for point in served["trend"]] == pytest.approx(
        [point[1] for point in reference["trend"]]
    )
    assert [row["cardVariantId"] for row in served["currentConstituents"]] == [row["cardVariantId"] for row in reference["currentConstituents"]]
    assert (served["reconciliation"]["actualConstituentCount"]
            == reference["reconciliation"]["actualConstituentCount"])


@pytest.mark.parametrize(
    "query,reference_sets",
    [
        ({"price_segment_ids": ["premium"]}, [row["id"] for row in SETS]),
        ({"release_age_cohort_ids": ["recent"]}, ["set-pe"]),
        ({"price_segment_ids": ["premium"], "segment_ids": ["specialIllustrationRare"]}, [row["id"] for row in SETS]),
        ({"release_age_cohort_ids": ["new"], "segment_ids": ["specialIllustrationRare"]}, ["set-ah"]),
    ],
)
def test_filtered_database_cohort_matches_legacy_row_path(query, reference_sets):
    """Pass 4 parity: SQL-side dynamic filtering changes cost, never math."""
    served = _run(mode=MODE_CHASE, top_n=5, **query)
    segment_ids = query.get("segment_ids")
    card_ids = [card["id"] for card in CARDS if card["set_id"] in reference_sets and (
        not segment_ids or card["rarity"] == "Special Illustration Rare"
    )]
    reference = _reference_series(PRICES, set_ids=reference_sets, card_ids=card_ids,
                                  mode=MODE_CHASE, top_n=5)
    assert served["trackedValue"] == pytest.approx(reference["trackedValue"])
    assert served["indexValue"] == pytest.approx(reference["indexValue"])
    assert [point[1] for point in served["trend"]] == pytest.approx([point[1] for point in reference["trend"]])
    assert [row["cardVariantId"] for row in served["currentConstituents"]] == [row["cardVariantId"] for row in reference["currentConstituents"]]


def _ids_by_day(result):
    """Constituent ids per day, from the engine's published membership history."""
    return [entry["constituentIds"] for entry in result["membershipByDate"]]


# ---------------------------------------------------------------------------
# Identity and read-only guarantees
# ---------------------------------------------------------------------------

def test_query_identity_is_published_and_stable():
    result = _run(mode=MODE_CHASE, era_ids=[SV_ERA], segment_ids=["specialIllustrationRare"])
    assert result["queryKey"] == (
        f"cards|era={SV_ERA}|set=all|segment=specialIllustrationRare|pokemon=all|"
        "priceSegment=all|releaseAge=all|mode=chase|topN=10"
    )
    assert len(result["queryFingerprint"]) == 64
    again = _run(mode=MODE_CHASE, era_ids=[SV_ERA], segment_ids=["specialIllustrationRare"])
    assert again["queryFingerprint"] == result["queryFingerprint"]


def test_constituents_publish_the_section_24_contract():
    result = _run(mode=MODE_CHASE, set_ids=["set-ah"],
                  segment_ids=["specialIllustrationRare"], top_n=10)
    row = result["currentConstituents"][0]
    for field in ("rank", "cardVariantId", "canonicalCardId", "cardName", "setId", "setName",
                  "rarity", "marketPrice", "imageUrl", "asOf", "queryMembershipReason"):
        assert field in row, f"missing published constituent field: {field}"
    assert row["setName"] == "Ascended Heroes"


def test_one_canonical_card_can_publish_first_and_unlimited_constituents():
    cohorts = [{"marketDate": "2026-01-01", "constituentCount": 2,
                "eligibleUniverseCount": 2, "basketValue": 600,
                "commonCount": 0, "commonCurrentValue": 0,
                "commonPreviousValue": 0}]
    basket = [
        {"cardVariantId": "dragonite-first", "canonicalCardId": "dragonite-9",
         "legacyCardId": "legacy-dragonite", "setId": "base",
         "cardName": "Dragonite", "edition": "1st-edition",
         "printingType": "holo", "marketPrice": 500, "rank": 1},
        {"cardVariantId": "dragonite-unlimited", "canonicalCardId": "dragonite-9",
         "legacyCardId": "legacy-dragonite", "setId": "base",
         "cardName": "Dragonite", "edition": "unlimited",
         "printingType": "holo", "marketPrice": 100, "rank": 2},
    ]
    series = svc.build_query_series_from_cohorts(
        cohorts, basket, {}, mode=MODE_ALL, top_n=None,
    )
    assert [row["cardVariantId"] for row in series["currentConstituents"]] == [
        "dragonite-first", "dragonite-unlimited",
    ]
    assert [row["canonicalCardId"] for row in series["currentConstituents"]] == [
        "dragonite-9", "dragonite-9",
    ]


def test_a_broad_unranked_universe_is_sent_to_the_database():
    """Universe size is not a normal product-level rejection reason."""
    seen = {}

    class Client:
        def rpc(self, name, payload):
            seen["payload"] = payload
            return _RpcResult([])

    oversized = [f"card-{index}" for index in range(5_000)]
    rows = svc.load_daily_cohort_rows(
        Client(), ["set-a"], start_date="2026-01-01", end_date="2026-01-05",
        card_ids=oversized, top_n=None,
    )
    assert rows == []
    assert seen["payload"]["p_card_ids"] == oversized
    assert seen["payload"]["p_top_n"] is None


def test_all_filter_axes_are_sent_to_one_variant_cohort_rpc():
    seen = {}

    class Client:
        def rpc(self, name, payload):
            seen["name"], seen["payload"] = name, payload
            return _RpcResult([])

    svc.load_filtered_daily_cohort_rows(
        Client(), ["set-a", "set-b"], start_date="2026-01-01",
        end_date="2026-01-02", card_ids=None,
        segment_ids=["rareHolo"], pokemon_ids=["149"],
        price_segment_ids=["premium"],
        release_age_cohort_ids=["legacy"], top_n=10,
    )
    assert seen["name"] == svc.FILTERED_COHORT_RPC
    assert seen["payload"] == {
        "p_set_ids": ["set-a", "set-b"], "p_start_date": "2026-01-01",
        "p_end_date": "2026-01-02", "p_card_ids": None,
        "p_segment_ids": ["rareHolo"], "p_pokemon_ids": [149],
        "p_price_segment_ids": ["premium"],
        "p_release_age_cohort_ids": ["legacy"], "p_top_n": 10,
    }


def test_daily_projection_coverage_requires_every_set_and_full_range():
    class Query:
        def select(self, *_args): return self
        def in_(self, *_args): return self
        def execute(self):
            return _RpcResult([
                {"set_id": "set-a", "first_market_date": "2026-04-11", "computed_through": "2026-08-31"},
                {"set_id": "set-b", "first_market_date": "2026-04-11", "computed_through": "2026-08-31"},
            ])
    class Client:
        def table(self, name):
            assert name == "pokemon_market_explorer_card_daily_coverage"
            return Query()
    assert svc.daily_projection_covers(Client(), ["set-a", "set-b"],
        start_date="2026-04-11", end_date="2026-08-31")
    assert not svc.daily_projection_covers(Client(), ["set-a", "set-c"],
        start_date="2026-04-11", end_date="2026-08-31")


def test_daily_projection_coverage_allows_staggered_set_starts():
    class Query:
        def select(self, *_args): return self
        def in_(self, *_args): return self
        def execute(self):
            return _RpcResult([
                {"set_id": "set-a", "first_market_date": "2026-04-11",
                 "computed_through": "2026-08-31"},
                {"set_id": "set-b", "first_market_date": "2026-04-23",
                 "computed_through": "2026-08-31"},
                {"set_id": "set-c", "first_market_date": "2026-08-01",
                 "computed_through": "2026-08-31"},
            ])
    class Client:
        def table(self, _name): return Query()

    assert svc.daily_projection_covers(Client(), ["set-a", "set-b", "set-c"],
        start_date="2026-04-11", end_date="2026-08-31")


def test_daily_projection_coverage_rejects_stale_late_start_set():
    class Query:
        def select(self, *_args): return self
        def in_(self, *_args): return self
        def execute(self):
            return _RpcResult([
                {"set_id": "set-a", "first_market_date": "2026-04-11",
                 "computed_through": "2026-08-31"},
                {"set_id": "set-b", "first_market_date": "2026-04-23",
                 "computed_through": "2026-08-30"},
            ])
    class Client:
        def table(self, _name): return Query()

    assert not svc.daily_projection_covers(Client(), ["set-a", "set-b"],
        start_date="2026-04-11", end_date="2026-08-31")


def test_daily_projection_coverage_failure_falls_back_closed():
    class Client:
        def table(self, _name): raise RuntimeError("controlled coverage failure")
    assert not svc.daily_projection_covers(Client(), ["set-a"],
        start_date="2026-04-11", end_date="2026-08-31")


def test_future_set_fixture_enters_only_on_its_first_market_date():
    """A later release must not invalidate or retroactively change older dates."""
    first_dates = {"set-a": "2026-04-11", "set-b": "2026-04-11",
                   "set-c": "2026-04-21", "set-d": "2026-09-01"}
    requested_dates = [f"2026-04-{day:02d}" for day in range(11, 23)]
    active_counts = [sum(first <= market_date for first in first_dates.values())
                     for market_date in requested_dates]
    assert active_counts == ([2] * 10) + ([3] * 2)
    assert all(first_dates["set-d"] > market_date for market_date in requested_dates)


def test_uncovered_range_uses_bounded_interval_fallback(monkeypatch):
    seen = []
    original = svc.load_filtered_daily_cohort_rows

    def recording_loader(*args, **kwargs):
        seen.append(kwargs.get("rpc_name"))
        return original(*args, **kwargs)

    monkeypatch.setattr(svc, "daily_projection_covers", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(svc, "load_filtered_daily_cohort_rows", recording_loader)
    result = _run(mode=MODE_ALL, set_ids=["set-ah"])

    assert result["diagnostics"]["executionEngine"] == "interval_fallback"
    assert seen == [svc.FILTERED_COHORT_RPC]
    assert [row[0] for row in result["trend"]] == DATES


def test_filtered_cohort_chunks_overlap_once_without_dropping_dates():
    calls = []

    class Client:
        def rpc(self, _name, payload):
            calls.append((payload["p_start_date"], payload["p_end_date"]))
            from datetime import date, timedelta
            cursor, end = date.fromisoformat(payload["p_start_date"]), date.fromisoformat(payload["p_end_date"])
            rows = []
            while cursor <= end:
                rows.append({"market_date": cursor.isoformat(), "constituent_count": 1,
                             "eligible_universe_count": 1, "basket_value": 10,
                             "common_count": 1 if rows else 0,
                             "common_current_value": 10 if rows else 0,
                             "common_previous_value": 10 if rows else 0,
                             "current_constituents": [{"card_variant_id": "variant-a",
                                "canonical_card_id": "card-a", "legacy_card_id": "legacy-a",
                                "set_id": "set-a", "market_date": cursor.isoformat(),
                                "market_price": 10, "rank": 1}]})
                cursor += timedelta(days=1)
            return _RpcResult(rows)

    cohorts, basket = svc.load_filtered_daily_cohort_rows(
        Client(), ["set-a"], start_date="2026-01-01", end_date="2026-01-05",
        card_ids=None, chunk_days=2,
    )
    assert calls == [("2026-01-01", "2026-01-02"),
                     ("2026-01-02", "2026-01-04"),
                     ("2026-01-04", "2026-01-05")]
    assert [row["marketDate"] for row in cohorts] == [
        "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
    ]
    assert basket[0]["cardVariantId"] == "variant-a"


def test_a_statement_timeout_remains_plan_evidence_not_a_size_rejection():

    class Timeout(Exception):
        code = "57014"

    class Client:
        def rpc(self, *_args, **_kwargs):
            raise Timeout("canceling statement due to statement timeout")

    with pytest.raises(Timeout):
        svc.load_daily_cohort_rows(
            Client(), ["set-a"], start_date="2026-01-01", end_date="2026-01-05",
            card_ids=["card-1"], top_n=None,
        )


# ---------------------------------------------------------------------------
# Root cause 1 -- tracked-set resolution excludes catalog-only sets
# ---------------------------------------------------------------------------

def test_resolve_tracked_set_ids_excludes_catalog_only_sets():
    """169 history-tracked sets, 4 catalog-only, must resolve to 165."""
    history_ids = [f"set-{index}" for index in range(169)]
    catalog_only_ids = set(history_ids[:4])

    class Client:
        def table(self, name):
            if name == "pokemon_set_value_daily_history_coverage":
                return _Query([{"set_id": sid, "has_history": True} for sid in history_ids])
            if name == "sets":
                return _Query([
                    {"id": sid, "catalog_only": sid in catalog_only_ids}
                    for sid in history_ids
                ])
            raise AssertionError(f"unexpected table read: {name}")

    result = svc.resolve_tracked_set_ids(Client())
    assert len(result) == 165
    assert catalog_only_ids.isdisjoint(result)
    assert set(result) == set(history_ids) - catalog_only_ids


def test_resolve_tracked_set_ids_keeps_a_normal_tracked_set():
    class Client:
        def table(self, name):
            if name == "pokemon_set_value_daily_history_coverage":
                return _Query([{"set_id": "set-normal", "has_history": True}])
            if name == "sets":
                return _Query([{"id": "set-normal", "catalog_only": False}])
            raise AssertionError(f"unexpected table read: {name}")

    assert svc.resolve_tracked_set_ids(Client()) == ["set-normal"]


def test_resolve_tracked_set_ids_is_an_intersection_not_a_union():
    """A catalog_only=false set with no tracked history stays untracked --
    the contract is history INTERSECT non-catalog-only, not "every
    non-catalog-only set"."""

    class Client:
        def table(self, name):
            if name == "pokemon_set_value_daily_history_coverage":
                return _Query([{"set_id": "set-tracked", "has_history": True}])
            if name == "sets":
                return _Query([
                    {"id": "set-tracked", "catalog_only": False},
                    {"id": "set-untracked-no-history", "catalog_only": False},
                ])
            raise AssertionError(f"unexpected table read: {name}")

    assert svc.resolve_tracked_set_ids(Client()) == ["set-tracked"]


def test_resolve_tracked_set_ids_treats_missing_catalog_only_as_false():
    """A `sets` row missing the column entirely must not be excluded --
    `catalog_only` defaults FALSE in the schema."""

    class Client:
        def table(self, name):
            if name == "pokemon_set_value_daily_history_coverage":
                return _Query([{"set_id": "set-legacy-row", "has_history": True}])
            if name == "sets":
                return _Query([{"id": "set-legacy-row"}])  # no catalog_only key
            raise AssertionError(f"unexpected table read: {name}")

    assert svc.resolve_tracked_set_ids(Client()) == ["set-legacy-row"]


def test_filter_options_publication_excludes_catalog_only_sets(monkeypatch):
    """The filter panel's set list must inherit the same exclusion --
    it is built from `resolve_tracked_set_ids`, not a separate query."""

    monkeypatch.setattr(svc, "resolve_tracked_set_ids", lambda _client: ["set-ah", "set-pe"])

    class Client(FakeClient):
        def table(self, name):
            if name == "pokemon_card_desirability_links":
                return _Query([])
            if name == "pokemon_set_sealed_market_snapshot_latest":
                return _Query([])
            return super().table(name)

    options = svc.build_market_explorer_filter_options(Client())
    set_ids = {row["id"] for row in options["sets"]}
    assert set_ids == {"set-ah", "set-pe"}
    assert "set-ev" not in set_ids  # would appear if the raw SETS fixture leaked through


# ---------------------------------------------------------------------------
# Root cause 2 -- same-day queries must use daily projection when covered
# ---------------------------------------------------------------------------

def test_covered_same_day_query_uses_daily_projection(monkeypatch):
    seen = []
    original = svc.load_filtered_daily_cohort_rows

    def recording_loader(*args, **kwargs):
        seen.append(kwargs.get("rpc_name"))
        return original(*args, **kwargs)

    monkeypatch.setattr(svc, "daily_projection_covers", lambda *_a, **_k: True)
    monkeypatch.setattr(svc, "load_filtered_daily_cohort_rows", recording_loader)

    result = _run(mode=MODE_ALL, set_ids=["set-ah"],
                  start_date=DATES[0], end_date=DATES[0])

    assert result["diagnostics"]["executionEngine"] == "daily_projection"
    assert seen == [svc.DAILY_PROJECTION_RPC]


def test_uncovered_same_day_query_preserves_interval_current(monkeypatch):
    seen = []
    original = svc.load_filtered_daily_cohort_rows

    def recording_loader(*args, **kwargs):
        seen.append(kwargs.get("rpc_name"))
        return original(*args, **kwargs)

    monkeypatch.setattr(svc, "daily_projection_covers", lambda *_a, **_k: False)
    monkeypatch.setattr(svc, "load_filtered_daily_cohort_rows", recording_loader)

    result = _run(mode=MODE_ALL, set_ids=["set-ah"],
                  start_date=DATES[0], end_date=DATES[0])

    assert result["diagnostics"]["executionEngine"] == "interval_current"
    assert seen == [svc.FILTERED_COHORT_RPC]


def test_covered_multi_day_query_remains_daily_projection(monkeypatch):
    seen = []
    original = svc.load_filtered_daily_cohort_rows

    def recording_loader(*args, **kwargs):
        seen.append(kwargs.get("rpc_name"))
        return original(*args, **kwargs)

    monkeypatch.setattr(svc, "daily_projection_covers", lambda *_a, **_k: True)
    monkeypatch.setattr(svc, "load_filtered_daily_cohort_rows", recording_loader)

    result = _run(mode=MODE_ALL, set_ids=["set-ah"],
                  start_date=DATES[0], end_date=DATES[-1])

    assert result["diagnostics"]["executionEngine"] == "daily_projection"
    assert seen == [svc.DAILY_PROJECTION_RPC]


def test_uncovered_multi_day_query_remains_interval_fallback():
    """Same assertion as test_uncovered_range_uses_bounded_interval_fallback,
    named explicitly for the corrected same-day/multi-day contract matrix."""
    result = _run(mode=MODE_ALL, set_ids=["set-ah"],
                  start_date=DATES[0], end_date=DATES[-1])
    assert result["diagnostics"]["executionEngine"] == "interval_fallback"


def test_an_unrelated_database_error_still_propagates():
    """Only 57014 is reclassified; a real fault must not be mistaken for size."""

    class Boom(Exception):
        code = "42P01"

    class Client:
        def rpc(self, *_args, **_kwargs):
            raise Boom("relation does not exist")

    try:
        svc.load_daily_cohort_rows(
            Client(), ["set-a"], start_date="2026-01-01", end_date="2026-01-05",
            card_ids=["card-1"], top_n=None,
        )
    except Boom:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected the original error to propagate")
