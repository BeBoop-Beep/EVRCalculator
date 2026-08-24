"""Top Chase validates the FINAL response candidate, not the stored row.

The defect this pins: ``get_pokemon_set_top_chase_snapshot_payload`` scored the
chosen stored row and raised ``POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE``
BEFORE reaching the scoped ``card_variant_price_observations`` hydration
fallback. A row with cards but empty stored histories therefore 503'd even
though the recovery path would have produced a complete answer.

Required order (asserted below):
  1. select the freshest/best stored row
  2. slice stored histories
  3. hydrate from scoped observations only if stored histories are missing
  4. build the final cards + histories candidate
  5. validate the FINAL candidate
  6. 503 only when it is still structurally incomplete
"""

from __future__ import annotations

import pytest

from backend.db.services import pokemon_public_snapshot_service as svc
from backend.db.services.pokemon_set_market_service import PokemonSetMarketError

SET_ID = "11111111-2222-3333-4444-555555555555"
LATEST = "2026-08-03"
PRIOR = "2026-08-02"


def _card(key, price=10.0):
    return {"cardVariantId": key, "name": f"Card {key}", "marketPrice": price}


def _history(*dates):
    return [{"date": day, "marketPrice": 10.0} for day in dates]


def _row(window, *, cards, histories, latest_date=LATEST, set_id=SET_ID):
    return {
        "set_id": set_id,
        "window_key": window,
        "top_chase_cards_json": cards,
        "top_chase_card_histories_json": histories,
        "latest_market_date": latest_date,
        "updated_at": f"{latest_date}T12:00:00+00:00",
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Only the dashboard-row read is exercised through the client here; the
    observation hydration is stubbed so the test asserts *whether* it ran."""

    def __init__(self, rows_by_window, raise_on_read=None):
        self.rows_by_window = rows_by_window
        self.raise_on_read = raise_on_read
        self.eq_filters = {}

    def select(self, _fields):
        return self

    def eq(self, field, value):
        self.eq_filters[field] = value
        return self

    def limit(self, _value):
        return self

    def order(self, _field, desc=False):
        return self

    def execute(self):
        if self.raise_on_read is not None:
            raise self.raise_on_read
        row = self.rows_by_window.get(self.eq_filters.get("window_key"))
        return _Result([row] if row else [])


class _Client:
    def __init__(self, rows_by_window, raise_on_read=None):
        self.rows_by_window = rows_by_window
        self.raise_on_read = raise_on_read

    def table(self, name):
        assert name == "pokemon_set_market_dashboard_snapshot_latest", name
        return _Query(self.rows_by_window, self.raise_on_read)


@pytest.fixture
def harness(monkeypatch):
    """Wire the snapshot service to in-memory rows and a recording hydrator."""

    calls = {"hydrations": []}

    def install(rows_by_window, *, observation_histories=None, raise_on_read=None):
        monkeypatch.setattr(
            svc, "service_read_client", _Client(rows_by_window, raise_on_read)
        )
        monkeypatch.setattr(
            svc, "_read_peer_movement_snapshot_meta", lambda *a, **k: ({}, False)
        )

        def _fake_hydrate(*, set_id, cards, variant_ids, latest_date_key, window_days):
            calls["hydrations"].append(
                {
                    "set_id": set_id,
                    "variant_ids": list(variant_ids),
                    "window_days": window_days,
                }
            )
            return dict(observation_histories or {})

        monkeypatch.setattr(svc, "_load_top_chase_observation_histories", _fake_hydrate)
        return calls

    return install


def test_complete_stored_histories_skip_observation_hydration(harness):
    """Step 3 must not run when the stored histories already satisfy step 2."""
    calls = harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(PRIOR, LATEST), "v1": _history(PRIOR, LATEST)},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        }
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert calls["hydrations"] == []
    assert payload["meta"]["topChaseCompleteness"]["status"] == "complete"
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is False
    assert len(payload["topChaseCards"]) == 2


def test_empty_stored_histories_recovered_by_scoped_observations_return_200(harness):
    """The regression: this used to 503 before hydration could run."""
    calls = harness(
        {
            "30d": _row("30d", cards=[_card("v0"), _card("v1")], histories={}),
            "365d": _row("365d", cards=[_card("v0"), _card("v1")], histories={}),
        },
        observation_histories={
            "v0": _history(PRIOR, LATEST),
            "v1": _history(PRIOR, LATEST),
        },
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    # Hydration ran, and stayed scoped to the selected cards' variant IDs.
    assert len(calls["hydrations"]) == 1
    assert sorted(calls["hydrations"][0]["variant_ids"]) == ["v0", "v1"]
    assert payload["meta"]["topChaseCompleteness"]["status"] == "complete"
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is True
    assert payload["topChaseCardHistories"]["v0"]


def test_absent_stored_and_observation_histories_raise_structured_503(harness):
    harness(
        {
            "30d": _row("30d", cards=[_card("v0"), _card("v1")], histories={}),
            "365d": _row("365d", cards=[_card("v0"), _card("v1")], histories={}),
        },
        observation_histories={},
    )

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE"


def test_one_point_new_set_is_a_settled_insufficient_history_answer(harness):
    """A brand-new set with a single observation is truthful, not a 503 loop."""
    harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(LATEST), "v1": _history(LATEST)},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        }
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    completeness = payload["meta"]["topChaseCompleteness"]
    assert completeness["status"] == "insufficient_history"
    assert completeness["retryable"] is False
    assert completeness["maxUsablePoints"] == 1
    assert any("too new for a trend" in warning for warning in payload["meta"]["warnings"])


def test_partial_candidate_raises_retryable_503(harness):
    """ATOMIC: a partially renderable candidate is not a successful answer.

    It used to return 200, so the section settled on a half-populated grid and
    the cards without history sat on "Awaiting trend" with no retry.
    """
    harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(PRIOR, LATEST)},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        },
        observation_histories={},
    )

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE"


def test_identity_mismatch_raises_retryable_503(harness):
    harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0")],
                histories={"v0": _history(PRIOR, LATEST)},
                set_id="99999999-0000-0000-0000-000000000000",
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        }
    )

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE"


# --- Correction 1: per-card partial hydration --------------------------------
def test_only_the_deficient_cards_are_hydrated_and_the_result_becomes_complete(harness):
    """8/10 stored complete, 2/10 missing: query only the missing two."""
    cards = [_card(f"v{index}") for index in range(10)]
    histories = {f"v{index}": _history(PRIOR, LATEST) for index in range(8)}
    calls = harness(
        {
            "30d": _row("30d", cards=cards, histories=histories),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        },
        observation_histories={
            "v8": _history(PRIOR, LATEST),
            "v9": _history(PRIOR, LATEST),
        },
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    # Scope: exactly the two deficient variants were queried, not all ten.
    assert len(calls["hydrations"]) == 1
    assert sorted(calls["hydrations"][0]["variant_ids"]) == ["v8", "v9"]

    completeness = payload["meta"]["topChaseCompleteness"]
    assert completeness["status"] == "complete"
    assert completeness["renderableCards"] == 10
    assert completeness["pricedCards"] == 10
    assert payload["meta"]["topChaseHistoryHydratedFromObservations"] is True


def test_a_poorer_observation_history_never_replaces_a_richer_stored_one(harness):
    """The merge must fill gaps, never downgrade a healthy card."""
    # v0 is deficient (1 point) and drives the hydration call; the loader also
    # returns a thin series for the healthy v1, which must be ignored.
    calls = harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={
                    "v0": _history(LATEST),
                    "v1": _history("2026-08-01", PRIOR, LATEST),
                },
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        },
        observation_histories={
            "v0": _history(PRIOR, LATEST),
            "v1": _history(LATEST),
        },
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    # Only the deficient card was in scope.
    assert sorted(calls["hydrations"][0]["variant_ids"]) == ["v0"]
    # v1 kept its richer stored 3-point series.
    assert len(payload["topChaseCardHistories"]["v1"]) == 3
    assert len(payload["topChaseCardHistories"]["v0"]) == 2
    assert payload["meta"]["topChaseCompleteness"]["status"] == "complete"


def test_hydration_does_not_run_when_every_card_is_already_renderable(harness):
    calls = harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(PRIOR, LATEST), "v1": _history(PRIOR, LATEST)},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        }
    )

    svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert calls["hydrations"] == []


# --- Correction 3: read failures are not empty success -----------------------
def test_read_exception_raises_retryable_503_not_empty_success(harness):
    harness({}, raise_on_read=RuntimeError("PostgREST connection reset"))

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_READ_FAILED"


def test_successful_read_with_no_row_raises_snapshot_missing_503(harness):
    """A read that returns nothing is an unpublished snapshot, not an empty set."""
    harness({}, observation_histories={})

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_MISSING"


def test_equally_fresh_canonical_row_with_history_beats_incomplete_requested_row(harness):
    """Step 1 still prefers the structurally better row at equal freshness."""
    calls = harness(
        {
            "30d": _row("30d", cards=[_card("v0")], histories={}),
            "365d": _row(
                "365d",
                cards=[_card("v0")],
                histories={"v0": _history(PRIOR, LATEST)},
            ),
        }
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert payload["meta"]["snapshot"]["usedFallbackWindow"] is True
    assert payload["meta"]["snapshot"]["fallbackReason"] == "requested_window_row_incomplete"
    # The canonical row already had history, so no observation read was needed.
    assert calls["hydrations"] == []
    assert payload["meta"]["topChaseCompleteness"]["status"] == "complete"
    # The response still echoes the window the caller asked for.
    assert payload["window"] == "30d"


def test_no_priced_cards_is_a_settled_empty_answer(harness):
    harness(
        {
            "30d": _row("30d", cards=[_card("v0", price=0)], histories={}),
            "365d": _row("365d", cards=[_card("v0", price=0)], histories={}),
        },
        observation_histories={},
    )

    payload = svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    completeness = payload["meta"]["topChaseCompleteness"]
    assert completeness["status"] == "empty"
    assert completeness["retryable"] is False


# --- Correction 4: insufficient history must be PROVEN CURRENT ---------------
def test_one_stale_point_is_incomplete_not_a_new_set(harness):
    """A single point that does not reach latest_market_date is a stalled feed."""
    harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(PRIOR), "v1": _history(PRIOR)},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date="2026-08-01"),
        },
        observation_histories={},
    )

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE"


def test_one_point_on_some_cards_only_is_incomplete(harness):
    harness(
        {
            "30d": _row(
                "30d",
                cards=[_card("v0"), _card("v1")],
                histories={"v0": _history(LATEST), "v1": []},
            ),
            "365d": _row("365d", cards=[], histories={}, latest_date=PRIOR),
        },
        observation_histories={},
    )

    with pytest.raises(PokemonSetMarketError) as excinfo:
        svc.get_pokemon_set_top_chase_snapshot_payload(SET_ID, window="30d")

    assert excinfo.value.code == "POKEMON_SET_TOP_CHASE_SNAPSHOT_INCOMPLETE"


# --- classifier unit coverage ------------------------------------------------
def test_classifier_flags_identity_mismatch():
    verdict = svc._classify_top_chase_candidate(
        [_card("v0")],
        {"v0": _history(PRIOR, LATEST)},
        requested_set_id=SET_ID,
        row_set_id="99999999-0000-0000-0000-000000000000",
    )
    assert verdict["status"] == "identity_mismatch"
    assert verdict["retryable"] is True


def test_classifier_flags_a_card_naming_a_foreign_set():
    card = {**_card("v0"), "setId": "99999999-0000-0000-0000-000000000000"}
    verdict = svc._classify_top_chase_candidate(
        [card],
        {"v0": _history(PRIOR, LATEST)},
        requested_set_id=SET_ID,
        row_set_id=SET_ID,
        latest_market_date=LATEST,
    )
    assert verdict["status"] == "identity_mismatch"


def test_classifier_rejects_a_point_dated_after_the_market_date():
    verdict = svc._classify_top_chase_candidate(
        [_card("v0")],
        {"v0": _history(LATEST, "2026-08-04")},
        requested_set_id=SET_ID,
        row_set_id=SET_ID,
        latest_market_date=LATEST,
    )
    assert verdict["status"] == "incomplete"


def test_classifier_requires_a_market_date_for_insufficient_history():
    """Without a declared market date, currency cannot be proven."""
    verdict = svc._classify_top_chase_candidate(
        [_card("v0")],
        {"v0": _history(LATEST)},
        requested_set_id=SET_ID,
        row_set_id=SET_ID,
        latest_market_date=None,
    )
    assert verdict["status"] == "incomplete"


def test_classifier_accepts_a_current_one_point_new_set():
    verdict = svc._classify_top_chase_candidate(
        [_card("v0"), _card("v1")],
        {"v0": _history(LATEST), "v1": _history(LATEST)},
        requested_set_id=SET_ID,
        row_set_id=SET_ID,
        latest_market_date=LATEST,
    )
    assert verdict["status"] == "insufficient_history"
    assert verdict["retryable"] is False


# --- merge helper -------------------------------------------------------------
def test_richer_history_wins_and_ties_break_on_freshness():
    poor = _history(LATEST)
    rich = _history(PRIOR, LATEST)
    assert svc._pick_richer_top_chase_history(rich, poor) is rich
    assert svc._pick_richer_top_chase_history(poor, rich) is rich

    stale_pair = _history("2026-08-01", PRIOR)
    fresh_pair = _history(PRIOR, LATEST)
    assert svc._pick_richer_top_chase_history(stale_pair, fresh_pair) is fresh_pair
    assert svc._pick_richer_top_chase_history(fresh_pair, stale_pair) is fresh_pair
