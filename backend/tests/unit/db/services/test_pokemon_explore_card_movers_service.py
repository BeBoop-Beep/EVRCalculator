import pytest
from postgrest.exceptions import APIError

from backend.db.services import pokemon_explore_card_movers_service as svc
from backend.db.services import public_read_retry
from backend.db.services.pokemon_explore_card_movers_service import (
    ExploreCardMoversUnavailable,
    build_global_card_movers_row,
    build_global_raw_card_movers_row,
    build_global_mixed_movers_row,
    read_explore_card_movers_snapshot,
)
from backend.db.services.pokemon_card_market_delta_contract import WINDOW_CONVENTION


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()


def movement(card_id, percent, amount, **extra):
    return {"canonicalCardId": card_id, "cardVariantId": "v", "conditionId": "nm",
            "name": card_id, "changePercent": percent, "changeAmount": amount, **extra}


def snapshot(set_id, rows, date="2026-08-01", version="pokemon_card_movement_v1", top_cards=None):
    top_cards = rows[:10] if top_cards is None else top_cards
    return {"set_id": set_id, "latest_market_date": date, "updated_at": f"{date}T12:00:00Z",
            "payload_json": {"topChaseCards": top_cards,
                "marketMoversByWindow": {"7D": {"all": rows}}, "meta": {
                "movementContractVersion": version, "windowConvention": WINDOW_CONVENTION,
                "movementGenerationId": f"generation-{set_id}"}}}


def test_aggregates_deduplicates_sorts_and_adds_cross_set_identity():
    sets = [{"id": "a", "name": "Alpha", "canonical_key": "alpha"},
            {"id": "b", "name": "Beta", "canonical_key": "beta"}]
    row = build_global_card_movers_row(
        sets, [snapshot("a", [movement("positive", 10, 50), movement("duplicate", -20, -1)]),
               snapshot("b", [movement("negative", -30, -2), movement("duplicate", -20, -1)])],
        target_market_date="2026-08-01",
    )
    cards = row["payload_json"]["marketMovers"]["all"]
    assert [card["canonicalCardId"] for card in cards] == ["negative", "duplicate", "positive"]
    assert cards[0]["setName"] == "Beta"
    assert "setSlug" not in cards[0]
    assert len([card for card in cards if card["canonicalCardId"] == "duplicate"]) == 1
    assert row["payload_json"]["meta"]["coverage"]["candidateCardCount"] == 4


def test_excludes_non_public_sets_and_caps_each_set_at_ten_candidates():
    sets = [{"id": "a", "name": "Alpha"}, {"id": "hidden", "name": "Sword and Shield",
             "era": "Sword and Shield"}]
    rows = [movement(f"c{i:02}", i, i) for i in range(40)]
    row = build_global_card_movers_row(
        sets, [snapshot("a", rows, top_cards=rows[10:40])], target_market_date="2026-08-01"
    )
    assert row["eligible_set_count"] == 1
    assert row["card_count"] == 10
    assert row["payload_json"]["marketMovers"]["all"][0]["canonicalCardId"] == "c19"


def test_only_current_top_ten_per_set_enter_global_candidate_pool():
    sets = [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]
    alpha_top = [movement(f"a{i}", i, i) for i in range(10)]
    beta_top = [movement(f"b{i}", i + 20, i + 20) for i in range(4)]
    noisy_outside_top_ten = movement("cheap-noise", 999, 0.01)
    row = build_global_card_movers_row(
        sets,
        [
            snapshot("a", [noisy_outside_top_ten, *alpha_top], top_cards=alpha_top),
            snapshot("b", beta_top, top_cards=beta_top),
        ],
        target_market_date="2026-08-01",
    )
    cards = row["payload_json"]["marketMovers"]["all"]
    assert "cheap-noise" not in [card["canonicalCardId"] for card in cards]
    assert cards[0]["canonicalCardId"] == "b3"
    coverage = row["payload_json"]["meta"]["coverage"]
    assert coverage["topChaseCandidateCardCount"] == 14
    assert coverage["candidateCardCount"] == 14
    assert coverage["participatingSetCount"] == 2


@pytest.mark.parametrize("sources", [[], [snapshot("a", [], date="2026-07-31")],
                                        [snapshot("a", [], version="wrong")]])
def test_incoherent_source_blocks_publication(sources):
    with pytest.raises(ExploreCardMoversUnavailable):
        build_global_card_movers_row([{"id": "a", "name": "Alpha"}], sources,
                                     target_market_date="2026-08-01")


def test_valid_empty_all_array_is_included_not_malformed():
    row = build_global_card_movers_row(
        [{"id": "a", "name": "Alpha", "canonical_key": "alpha"}],
        [snapshot("a", [])],
        target_market_date="2026-08-01",
    )
    assert row["eligible_set_count"] == 1
    assert row["card_count"] == 0
    assert row["_diagnostics"]["includedSetCount"] == 1


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return _Result(self.rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows
    def table(self, _name): return _Query(self.rows)


def test_read_service_serves_only_prepared_snapshot_and_caps_limit_at_fifty():
    payload = {"marketMovers": {"window": "7D", "all": [movement(str(i), i, i) for i in range(55)]},
               "meta": {"snapshot": {"marketDate": "2026-08-01"}}}
    result = read_explore_card_movers_snapshot(client=_Client([{"payload_json": payload}]), limit=99)
    assert result["marketMovers"]["window"] == "7D"
    assert len(result["marketMovers"]["all"]) == 50


def _transient_error(code="PGRST002"):
    return APIError({"message": "schema cache unavailable", "code": code, "hint": None, "details": None})


class _FlakyOnceClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def table(self, _name):
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        self.calls += 1
        if self.calls == 1:
            raise _transient_error()
        return _Result(self.rows)


def test_no_client_path_retries_a_transient_failure_and_recovers(monkeypatch):
    """D/B: no-client path wraps the read in run_public_read_with_retry; a first
    transient failure is retried on a fresh client and the retry succeeds."""
    payload = {"marketMovers": {"window": "7D", "all": [movement("a", 1, 1)]}, "meta": {}}
    flaky = _FlakyOnceClient([{"payload_json": payload}])
    monkeypatch.setattr(svc, "service_read_client", flaky)
    real_retry = public_read_retry.run_public_read_with_retry
    monkeypatch.setattr(
        svc, "run_public_read_with_retry",
        lambda op, **kwargs: real_retry(op, client_factory=lambda: flaky, **kwargs),
    )
    result = read_explore_card_movers_snapshot()
    assert result["marketMovers"]["window"] == "7D"
    assert flaky.calls == 2


def test_no_client_path_does_not_retry_missing_snapshot():
    """E: ExploreCardMoversUnavailable is a semantic/non-transient failure and
    must not be retried."""
    empty = _Client([])
    with pytest.raises(ExploreCardMoversUnavailable):
        read_explore_card_movers_snapshot(client=empty)



def raw_authority(*, market_date="2026-09-29", universe="serving_raw_exact_variant_v1"):
    return {
        "status": "READY",
        "marketDate": market_date,
        "generationId": "surface-generation",
        "window": "7D",
        "windowDays": 7,
        "movementContractVersion": "pokemon_card_movement_v1",
        "windowConvention": WINDOW_CONVENTION,
        "universeContractVersion": universe,
        "rankingMethodology": "market_movement_score_v1",
        "priceBasis": "serving_raw_current_plus_exact_nm_tcgplayer_observation_baseline_v1",
        "baselineQualityGuardVersion": "target_baseline_reversion_guard_v1",
        "baselineTransientExcludedCount": 1,
        "rawConstituentCount": 20315,
        "rawRootCount": 155,
        "rawMarketCount": 159,
        "scopedConstituentCount": 1264,
        "baselineCoveredCount": 20090,
        "eligibleCandidateCount": 2370,
        "scopedCandidateCount": 247,
        "publishedCount": 2,
        "movements": [
            {
                "canonicalCardId": "same-card",
                "cardVariantId": "unlimited-variant",
                "conditionId": "nm",
                "setId": "neo",
                "setName": "Neo Destiny",
                "marketScope": "unlimited",
                "edition": "unlimited",
                "name": "Shining Tyranitar",
                "changeAmount": -317.25,
                "changePercent": -47.9,
                "movementScore": -274.6961,
            },
            {
                "canonicalCardId": "same-card",
                "cardVariantId": "first-edition-variant",
                "conditionId": "nm",
                "setId": "neo",
                "setName": "Neo Destiny",
                "marketScope": "first_edition",
                "edition": "1st-edition",
                "name": "Shining Tyranitar",
                "changeAmount": -100,
                "changePercent": -10,
                "movementScore": -90,
            },
        ],
    }


def test_raw_authority_snapshot_is_market_wide_and_preserves_exact_variants():
    row = build_global_raw_card_movers_row(
        raw_authority(), target_market_date="2026-09-29"
    )
    cards = row["payload_json"]["marketMovers"]["all"]
    assert [card["cardVariantId"] for card in cards] == [
        "unlimited-variant",
        "first-edition-variant",
    ]
    assert [card["marketScope"] for card in cards] == ["unlimited", "first_edition"]
    assert row["eligible_set_count"] == 155
    coverage = row["payload_json"]["meta"]["coverage"]
    assert coverage["rawConstituentCount"] == 20315
    assert coverage["rawMarketCount"] == 159
    assert coverage["scopedConstituentCount"] == 1264
    assert coverage["candidateCardCount"] == 2370
    assert coverage["baselineTransientExcludedCount"] == 1
    assert row["payload_json"]["meta"]["baselineQualityGuardVersion"] == "target_baseline_reversion_guard_v1"
    assert row["payload_json"]["meta"]["builder"] == "pokemon_raw_market_seven_day_movers_v2"


@pytest.mark.parametrize(
    "authority",
    [
        raw_authority(market_date="2026-09-28"),
        raw_authority(universe="legacy_top_chase_subset"),
        {**raw_authority(), "status": "BLOCKED"},
    ],
)
def test_raw_authority_snapshot_fails_closed_on_incoherent_authority(authority):
    with pytest.raises(ExploreCardMoversUnavailable):
        build_global_raw_card_movers_row(
            authority, target_market_date="2026-09-29"
        )



def mixed_authority(*, market_date="2026-09-29", universe="serving_cards_and_sealed_exact_instruments_v1"):
    return {
        "status": "READY",
        "marketDate": market_date,
        "generationId": "surface-generation",
        "window": "7D",
        "windowDays": 7,
        "movementContractVersion": "pokemon_card_movement_v1",
        "windowConvention": WINDOW_CONVENTION,
        "universeContractVersion": universe,
        "rankingMethodology": "market_movement_score_v1",
        "baselineQualityGuardVersion": "target_baseline_reversion_guard_v1",
        "marketSetCount": 208,
        "cardRootCount": 155,
        "cardMarketCount": 159,
        "cardConstituentCount": 20315,
        "cardCandidateCount": 2370,
        "cardTransientExcludedCount": 1,
        "sealedSetCount": 167,
        "sealedConstituentCount": 1377,
        "sealedCurrentEndpointCount": 1321,
        "sealedBaselineCoveredCount": 1341,
        "sealedCandidateCount": 419,
        "sealedTransientExcludedCount": 1,
        "publishedCount": 3,
        "publishedCardCount": 2,
        "publishedSealedCount": 1,
        "movements": [
            {
                "asset": "cards",
                "canonicalCardId": "card-a",
                "cardVariantId": "variant-a",
                "conditionId": "nm",
                "name": "Card A",
                "movementScore": 200,
                "changeAmount": 150,
                "changePercent": 20,
            },
            {
                "asset": "sealed",
                "sealedProductId": "product-a",
                "instrumentId": "product-a",
                "id": "product-a",
                "name": "Booster Box A",
                "movementScore": 180,
                "changeAmount": 130,
                "changePercent": 5,
            },
            {
                "asset": "cards",
                "canonicalCardId": "card-b",
                "cardVariantId": "variant-b",
                "conditionId": "nm",
                "name": "Card B",
                "movementScore": -170,
                "changeAmount": -120,
                "changePercent": -25,
            },
        ],
    }


def test_mixed_snapshot_preserves_authoritative_cross_asset_order_and_counts():
    row = build_global_mixed_movers_row(
        mixed_authority(), target_market_date="2026-09-29"
    )
    movers = row["payload_json"]["marketMovers"]["all"]
    assert [item["asset"] for item in movers] == ["cards", "sealed", "cards"]
    assert movers[1]["sealedProductId"] == "product-a"
    coverage = row["payload_json"]["meta"]["coverage"]
    assert coverage["cardConstituentCount"] == 20315
    assert coverage["sealedConstituentCount"] == 1377
    assert coverage["candidateInstrumentCount"] == 2789
    assert coverage["publishedCardCount"] == 2
    assert coverage["publishedSealedCount"] == 1
    assert coverage["publishedInstrumentCount"] == 3
    assert row["card_count"] == 3
    assert row["eligible_set_count"] == 208
    assert row["payload_json"]["meta"]["builder"] == "pokemon_mixed_market_seven_day_movers_v3"


@pytest.mark.parametrize(
    "authority",
    [
        mixed_authority(market_date="2026-09-28"),
        mixed_authority(universe="cards_only"),
        {**mixed_authority(), "sealedCandidateCount": 0},
        {**mixed_authority(), "publishedSealedCount": 2},
    ],
)
def test_mixed_snapshot_fails_closed_on_incoherent_cross_asset_authority(authority):
    with pytest.raises(ExploreCardMoversUnavailable):
        build_global_mixed_movers_row(
            authority, target_market_date="2026-09-29"
        )
