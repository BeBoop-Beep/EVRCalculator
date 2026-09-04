"""Regression tests for the P0 2026-09-04 rankings fallback cache fix.

Prior behaviour: `_LAST_SUCCESSFUL_RANKINGS_PAYLOADS` was a `Dict[int, ...]`
keyed by every distinct `limit` a caller passed, and EVERY successful call to
`get_pokemon_explore_rankings_snapshot_payload` wrote a `deepcopy()` of the
entire resolved mega-contract payload into it, with no eviction. That is an
unbounded-memory cache on two axes (key count, and per-entry deep-copy cost)
and was a material contributor to the production OOM restart documented in
docs/PRODUCTION_BACKEND_MEMORY_P0_2026-09-04.md.

These tests exercise the real reader function (not a mock of it) against the
actual `_RANKINGS_FALLBACK_CACHE` single-slot cache introduced to replace it,
using the module's CURRENT client attribute names (`service_read_client`,
`create_short_timeout_service_client`).
"""

from backend.db.services import pokemon_public_snapshot_service, public_read_retry
from backend.db.services.public_rip_publication_contract import canonical_publication_identity
import pytest


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def limit(self, _value):
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


@pytest.fixture(autouse=True)
def _reset_state():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    pokemon_public_snapshot_service._reset_rankings_fallback_cache_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    pokemon_public_snapshot_service._reset_rankings_fallback_cache_for_tests()


def _identity_meta():
    identity = canonical_publication_identity()
    return {
        "ripWeightsConfig": {
            "overallRip": {"version": identity["overallRipVersion"]},
            "financialRip": {"version": identity["financialRipVersion"]},
            "publicContract": {"version": identity["publicRipContractVersion"]},
            "collectorAppeal": {"version": identity["collectorAppealVersion"]},
        }
    }


def _rows(n, *, updated_at="2026-09-04T00:00:00+00:00"):
    targets = [
        {
            "id": f"set-{i}",
            "target_id": f"set-{i}",
            "target_type": "set",
            "name": f"Set {i}",
            "is_opening_set": True,
        }
        for i in range(n)
    ]
    return [
        {
            "updated_at": updated_at,
            "ranking_payload_json": {"targets": targets, "meta": _identity_meta()},
            "default_target_json": {"target_id": "set-0", "target_type": "set"},
        }
    ]


def _patch_healthy_reader(monkeypatch, rows):
    client = _Client({"pokemon_explore_rankings_snapshot_latest": lambda _q: rows})
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )


def test_cache_stays_single_slot_across_many_distinct_limits(monkeypatch):
    """An unbounded per-limit cache used to grow one full copy per distinct
    `limit`. The replacement is a single slot regardless of how many distinct
    limits are requested."""
    _patch_healthy_reader(monkeypatch, _rows(50))

    for limit in range(1, 40):
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=limit)

    cache = pokemon_public_snapshot_service._RANKINGS_FALLBACK_CACHE
    assert set(cache.keys()) == {
        "identity_key",
        "raw_targets",
        "base_payload",
        "meta",
        "default_target",
    }
    # Single slot: the cache dict itself never grows a key per limit.
    assert len(cache) == 5


def test_healthy_requests_do_not_deep_copy_the_payload(monkeypatch):
    """The cached `base_payload`/`raw_targets` must be the SAME objects the
    reader already built for this request, not a `deepcopy()` of them —
    deep-copying the whole mega-contract on every healthy request was the
    other unbounded-memory axis of the old design."""
    rows = _rows(10)
    _patch_healthy_reader(monkeypatch, rows)

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)
    cache = pokemon_public_snapshot_service._RANKINGS_FALLBACK_CACHE

    # The served payload's own target dicts are the identical objects (by
    # `id()`) as the cached ones -- proof no deep copy separated them.
    assert result["targets"][0] is cache["raw_targets"][0]


def test_repeated_identical_requests_do_not_replace_the_cache_slot(monkeypatch):
    """Cache updates only on publication identity/content change (here,
    `updated_at`), not on every successful read."""
    rows = _rows(5)
    _patch_healthy_reader(monkeypatch, rows)

    pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=5)
    cache = pokemon_public_snapshot_service._RANKINGS_FALLBACK_CACHE
    first_base_payload_id = id(cache["base_payload"])

    for _ in range(20):
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=5)

    assert id(cache["base_payload"]) == first_base_payload_id


def test_stale_fallback_slices_cached_cohort_per_requested_limit(monkeypatch):
    """A fallback for `limit=3` must return exactly 3 targets even though the
    cache holds the full cohort, mirroring the healthy-path slicing."""
    rows = _rows(20)
    _patch_healthy_reader(monkeypatch, rows)
    pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=20)

    from postgrest.exceptions import APIError

    def fail(_q):
        raise APIError({"message": "unavailable", "code": "PGRST002", "hint": None, "details": None})

    failing_client = _Client({"pokemon_explore_rankings_snapshot_latest": fail})
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", failing_client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: failing_client
    )

    fallback = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=3)
    assert len(fallback["targets"]) == 3
    assert fallback["meta"]["snapshot"]["isStaleFallback"] is True
    assert fallback["meta"]["snapshot"]["fallbackReason"] == "transient_data_service_failure"


def test_no_cached_entry_still_raises_503_on_transient_failure(monkeypatch):
    from postgrest.exceptions import APIError

    def fail(_q):
        raise APIError({"message": "unavailable", "code": "PGRST002", "hint": None, "details": None})

    client = _Client({"pokemon_explore_rankings_snapshot_latest": fail})
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client)

    with pytest.raises(pokemon_public_snapshot_service.ExploreRipStatisticsTargetsError) as raised:
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=10)
    assert raised.value.status_code == 503
