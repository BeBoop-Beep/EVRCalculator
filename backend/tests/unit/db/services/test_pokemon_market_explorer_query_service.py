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
from backend.domain.pokemon.market_explorer_query import MODE_ALL, MODE_CHASE

SV_ERA = "era-sv"
SWSH_ERA = "era-swsh"

# Two sets in Scarlet & Violet, one in Sword & Shield.
SETS = [
    {"id": "set-ah", "era_id": SV_ERA, "name": "Ascended Heroes"},
    {"id": "set-pe", "era_id": SV_ERA, "name": "Prismatic Evolutions"},
    {"id": "set-ev", "era_id": SWSH_ERA, "name": "Evolving Skies"},
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

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = self._rows
        for column, op, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if str(row.get(column)) == str(value)]
            else:
                wanted = {str(item) for item in value}
                rows = [row for row in rows if str(row.get(column)) in wanted]
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
            rows.append({"canonical_card_id": card["id"], "set_id": card["set_id"],
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

        assert name == "get_pokemon_market_explorer_daily_cohort", name
        top_n = payload.get("p_top_n")
        by_date = {}
        for row in rows:
            by_date.setdefault(row["market_date"], []).append(row)

        output, previous = [], None
        for market_date in sorted(by_date):
            universe = sorted(by_date[market_date],
                              key=lambda row: (-float(row["market_price"]), row["canonical_card_id"]))
            selected = universe[:top_n] if top_n else universe
            current = {row["canonical_card_id"]: float(row["market_price"]) for row in selected}
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
                rows.append({"canonical_card_id": card["id"], "market_date": market_date,
                             "market_price": price})
        return rows

    monkeypatch.setattr(svc, "load_card_constituent_rows", _load)


def _run(**kwargs):
    kwargs.setdefault("start_date", DATES[0])
    kwargs.setdefault("end_date", DATES[-1])
    return svc.run_market_explorer_query(kwargs.pop("client", FakeClient()), **kwargs)


def _ids(result):
    return [row["canonicalCardId"] for row in result["currentConstituents"]]


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
        {"canonical_card_id": row["canonical_card_id"], "market_date": row["market_date"],
         "market_price": row["market_price"]}
        for row in _panel(prices, set_ids, card_ids)
    ]
    metadata = {card["id"]: {"setId": card["set_id"], "cardName": card["name"],
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
    assert day_one == ["ah-sir-0"]
    assert day_two == ["pe-sir-0"]


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
    assert "ah-sir-4" in day_one and "ah-sir-4" not in day_two
    assert "pe-sir-0" in day_two and "pe-sir-0" not in day_one

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
    assert _ids(served) == [row["canonicalCardId"] for row in reference["currentConstituents"]]
    assert (served["reconciliation"]["actualConstituentCount"]
            == reference["reconciliation"]["actualConstituentCount"])


def _ids_by_day(result):
    """Constituent ids per day, from the engine's published membership history."""
    return [entry["constituentIds"] for entry in result["membershipByDate"]]


# ---------------------------------------------------------------------------
# Identity and read-only guarantees
# ---------------------------------------------------------------------------

def test_query_identity_is_published_and_stable():
    result = _run(mode=MODE_CHASE, era_ids=[SV_ERA], segment_ids=["specialIllustrationRare"])
    assert result["queryKey"] == (
        f"cards|era={SV_ERA}|set=all|segment=specialIllustrationRare|mode=chase|topN=10"
    )
    assert len(result["queryFingerprint"]) == 64
    again = _run(mode=MODE_CHASE, era_ids=[SV_ERA], segment_ids=["specialIllustrationRare"])
    assert again["queryFingerprint"] == result["queryFingerprint"]


def test_constituents_publish_the_section_24_contract():
    result = _run(mode=MODE_CHASE, set_ids=["set-ah"],
                  segment_ids=["specialIllustrationRare"], top_n=10)
    row = result["currentConstituents"][0]
    for field in ("rank", "canonicalCardId", "cardName", "setId", "setName",
                  "rarity", "marketPrice", "imageUrl", "asOf", "queryMembershipReason"):
        assert field in row, f"missing published constituent field: {field}"
    assert row["setName"] == "Ascended Heroes"
