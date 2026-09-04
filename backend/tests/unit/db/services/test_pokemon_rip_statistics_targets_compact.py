"""Regression tests for the compact `/explore/rip-statistics/targets` reader.

Phase B-E of the 2026-09-04 memory P0 fast-follow: the HEALTHY (non-fallback)
`/explore/rip-statistics/targets` path used to select and materialize the
complete `ranking_payload_json` mega-contract
(`_load_pokemon_explore_rankings_snapshot_row`) on every request, including
the unrelated `productFamilyRankings`/`setRip`/`eraSetStrengthV1` blocks. This
suite exercises the new compact `get_pokemon_rip_statistics_targets_compact`
RPC-backed path added to
`backend/db/services/pokemon_public_snapshot_service.py`, which must be used
for a healthy/enriched publication instead, with an EXPLICIT (never silent)
fallback to the full mega-contract reader for legacy/incomplete publications.
"""

from backend.db.services import pokemon_public_snapshot_service, public_read_retry
from backend.db.services.public_rip_publication_contract import canonical_publication_identity
import pytest


class _Result:
    def __init__(self, data):
        self.data = data


class _TableQuery:
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


class _RpcCall:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return _Result(self._fn())


class _Client:
    """Fake Supabase client supporting both `.table(...)` (full reader) and
    `.rpc(...)` (compact reader) so tests can exercise either path."""

    def __init__(self, table_handlers=None, rpc_handlers=None):
        self.table_handlers = table_handlers or {}
        self.rpc_handlers = rpc_handlers or {}
        self.rpc_calls = []

    def table(self, table_name):
        return _TableQuery(table_name, self.table_handlers)

    def rpc(self, fn_name, params=None):
        self.rpc_calls.append((fn_name, params))
        handler = self.rpc_handlers[fn_name]
        return _RpcCall(lambda: handler(params))


@pytest.fixture(autouse=True)
def _reset_state():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    pokemon_public_snapshot_service._reset_rankings_fallback_cache_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    pokemon_public_snapshot_service._reset_rankings_fallback_cache_for_tests()


def _identity_meta(**extra):
    identity = canonical_publication_identity()
    meta = {
        "ripWeightsConfig": {
            "overallRip": {"version": identity["overallRipVersion"]},
            "financialRip": {"version": identity["financialRipVersion"]},
            "publicContract": {"version": identity["publicRipContractVersion"]},
            "collectorAppeal": {"version": identity["collectorAppealVersion"]},
        }
    }
    meta.update(extra)
    return meta


def _enriched_set_rip(rank=1):
    return {
        "score": 90.0,
        "rank": rank,
        "tier": "S",
        "cohortSize": 3,
        "rankable": True,
        "methodologyVersion": "v1",
        "participatingFamilyCount": 1,
        "participatingFamilies": ["family-1"],
        "skuEvidenceCount": 5,
        "familyScores": [
            {"family": "family-1", "skuCount": 2, "score": 90.0, "rank": 1, "cohortSize": 3}
        ],
    }


def _compact_target(i):
    return {
        "id": f"set-{i}",
        "target_id": f"set-{i}",
        "target_type": "set",
        "name": f"Set {i}",
        "is_opening_set": True,
        "pack_cost": 4.99,
        "p95_value_to_cost_ratio": 3.2,
        "setRipV1": _enriched_set_rip(rank=i + 1),
    }


def _opening_audit(n):
    return {
        "total_raw_pokemon_set_rows": n,
        "opening_set_rows": n,
        "subset_rows": 0,
        "subset_rows_missing_parent_mapping": 0,
        "rollup_parent_rows": 0,
    }


def _compact_rpc_row(n, *, updated_at="2026-09-04T00:00:00+00:00", with_audit=True):
    targets = [_compact_target(i) for i in range(n)]
    meta = _identity_meta()
    if with_audit:
        meta["openingSetAudit"] = _opening_audit(n)
        meta["opening_set_audit"] = _opening_audit(n)
    return {
        "targets": targets,
        "default_target": {"target_id": "set-0", "target_type": "set"},
        "meta": meta,
        "updated_at": updated_at,
    }


def _full_row(n, *, updated_at="2026-09-04T00:00:00+00:00", with_mega_contract=True):
    targets = [_compact_target(i) for i in range(n)]
    payload = {"targets": targets, "meta": _identity_meta()}
    if with_mega_contract:
        payload["productFamilyRankings"] = {"families": {"family-1": {"score": 1}}}
        payload["setRip"] = {"weights": {"a": 1}}
        payload["eraSetStrengthV1"] = {"eras": [{"era": "e1"}]}
    return [
        {
            "updated_at": updated_at,
            "ranking_payload_json": payload,
            "default_target_json": {"target_id": "set-0", "target_type": "set"},
        }
    ]


def _patch_compact_client(monkeypatch, rpc_row, *, table_rows=None):
    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: table_rows or []},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: rpc_row},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )
    return client


def test_healthy_publication_uses_compact_reader_not_mega_contract(monkeypatch):
    """The RPC client is used, and the table (full mega-contract) reader is
    never called for a healthy, enriched, audited publication."""
    rpc_row = _compact_rpc_row(5)
    table_calls = []

    def _record_table(_q):
        table_calls.append(_q)
        return []

    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": _record_table},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: rpc_row},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=5)

    assert len(result["targets"]) == 5
    assert client.rpc_calls and client.rpc_calls[0][0] == "get_pokemon_rip_statistics_targets_compact"
    assert not table_calls, "healthy compact path must never read the table/mega-contract"


def test_compact_response_excludes_product_family_rankings(monkeypatch):
    rpc_row = _compact_rpc_row(4)
    _patch_compact_client(monkeypatch, rpc_row)

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=4)

    assert "productFamilyRankings" not in result
    assert "setRip" not in result
    assert "eraSetStrengthV1" not in result


def test_compact_response_preserves_persisted_opening_audit_unchanged(monkeypatch):
    rpc_row = _compact_rpc_row(6)
    _patch_compact_client(monkeypatch, rpc_row)

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=6)

    assert result["meta"]["openingSetAudit"] == _opening_audit(6)
    assert result["meta"]["opening_set_audit"] == _opening_audit(6)


def test_compact_response_respects_request_limit_and_ordering(monkeypatch):
    rpc_row = _compact_rpc_row(10)
    _patch_compact_client(monkeypatch, rpc_row)

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=3)

    assert [t["id"] for t in result["targets"]] == ["set-0", "set-1", "set-2"]


def test_compact_response_keeps_full_set_rip_object(monkeypatch):
    """Plus fields (setRipV1.familyScores etc.) must survive the compact
    projection unmodified -- Set RIP / Overall RIP parity."""
    rpc_row = _compact_rpc_row(2)
    _patch_compact_client(monkeypatch, rpc_row)

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=2)

    assert result["targets"][0]["setRipV1"] == _enriched_set_rip(rank=1)


def test_legacy_incomplete_set_rip_falls_back_to_full_reader(monkeypatch):
    """A publication whose Set RIP contract isn't fully enriched must fall
    back explicitly to the full mega-contract reader, never be silently
    served as-is from the compact path."""
    incomplete_target = {
        "id": "set-0",
        "target_id": "set-0",
        "target_type": "set",
        "name": "Set 0",
        "is_opening_set": True,
        "setRipV1": {"rankable": True, "cohortSize": None},  # incomplete
    }
    rpc_row = {
        "targets": [incomplete_target],
        "default_target": None,
        "meta": _identity_meta(),
        "updated_at": "2026-09-04T00:00:00+00:00",
    }
    full_rows = _full_row(3, with_mega_contract=True)
    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: full_rows},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: rpc_row},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=3)

    # Served from the full reader: 3 targets (the compact row only had 1),
    # and the full reader's own audit-rebuild ran (meta carries the key).
    assert len(result["targets"]) == 3
    assert "openingSetAudit" in result["meta"]


def test_missing_persisted_audit_falls_back_to_full_reader(monkeypatch):
    rpc_row = _compact_rpc_row(2, with_audit=False)
    full_rows = _full_row(2, with_mega_contract=True)
    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: full_rows},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: rpc_row},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=2)
    assert "openingSetAudit" in result["meta"]


def test_compact_rpc_unavailable_falls_back_to_full_reader(monkeypatch):
    """A rolling deploy where application code arrives before the migration:
    the compact RPC call itself fails. Never fatal -- explicit fallback."""
    full_rows = _full_row(2, with_mega_contract=True)

    def _raise_rpc(_params):
        raise RuntimeError("function get_pokemon_rip_statistics_targets_compact does not exist")

    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: full_rows},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": _raise_rpc},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    monkeypatch.setattr(
        pokemon_public_snapshot_service,
        "_enrich_rankings_payload_with_checklist_set_values",
        lambda payload: payload,
    )

    result = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=2)
    assert len(result["targets"]) == 2


def test_compact_publication_identity_mismatch_fails_closed(monkeypatch):
    stale_meta = _identity_meta()
    stale_meta["ripWeightsConfig"]["overallRip"] = {"version": "not-current"}
    stale_meta["openingSetAudit"] = _opening_audit(2)
    stale_meta["opening_set_audit"] = _opening_audit(2)
    rpc_row = {
        "targets": [_compact_target(0), _compact_target(1)],
        "default_target": None,
        "meta": stale_meta,
        "updated_at": "2026-09-04T00:00:00+00:00",
    }
    client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": lambda _q: []},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": lambda _params: rpc_row},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )

    with pytest.raises(pokemon_public_snapshot_service.ExploreRipStatisticsTargetsError) as raised:
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=2)
    assert raised.value.status_code == 503
    assert raised.value.code == "RIP_STATISTICS_TARGETS_PUBLICATION_SUPERSEDED"


def test_compact_populates_fallback_cache_from_compact_slot(monkeypatch):
    """Phase D: after a healthy compact-path request, the (single-slot)
    fallback cache is populated from the compact contract, not any lingering
    full-publication reference."""
    rpc_row = _compact_rpc_row(4)
    _patch_compact_client(monkeypatch, rpc_row)

    pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=4)
    cache = pokemon_public_snapshot_service._RANKINGS_FALLBACK_CACHE

    assert cache["base_payload"] == {}
    assert len(cache["raw_targets"]) == 4
    assert "productFamilyRankings" not in (cache["base_payload"] or {})

    def _raise_rpc(_params):
        raise RuntimeError("transient")

    from postgrest.exceptions import APIError

    def fail(_q):
        raise APIError({"message": "unavailable", "code": "PGRST002", "hint": None, "details": None})

    failing_client = _Client(
        table_handlers={"pokemon_explore_rankings_snapshot_latest": fail},
        rpc_handlers={"get_pokemon_rip_statistics_targets_compact": _raise_rpc},
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", failing_client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: failing_client
    )

    fallback = pokemon_public_snapshot_service.get_pokemon_explore_rankings_snapshot_payload(limit=2)
    assert len(fallback["targets"]) == 2
    assert fallback["meta"]["snapshot"]["isStaleFallback"] is True


def test_sets_lens_rpc_name_unchanged(monkeypatch):
    """`/explore/rankings/lens/sets` must keep calling
    `get_pokemon_rankings_sets_lens`, unaffected by this refactor."""
    calls = []

    def _sets_lens(_params):
        calls.append(_params)
        return {"targets": [], "default_target": None, "meta": {}}

    client = _Client(rpc_handlers={"get_pokemon_rankings_sets_lens": _sets_lens})
    monkeypatch.setattr(pokemon_public_snapshot_service, "service_read_client", client)
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "create_short_timeout_service_client", lambda: client
    )
    with pytest.raises(pokemon_public_snapshot_service.ExploreRipStatisticsTargetsError):
        # Empty targets -> RANKINGS_LENS_INCOMPLETE, but proves the sets lens
        # RPC name/path is untouched by the new compact targets RPC.
        pokemon_public_snapshot_service.get_pokemon_explore_rankings_lens_payload("sets", limit=10)
    assert calls
