"""Sealed detail + public snapshot judge and read through the active release."""
from backend.db.services import pokemon_public_snapshot_service as snap
from backend.db.services import pokemon_sealed_product_detail_service as detail
from backend.db.services import rip_release as rr

V14 = next(b for b in rr.RELEASES.values() if b.requires_v5_schema)
V12 = next(b for b in rr.RELEASES.values() if not b.requires_v5_schema)


def test_detail_best_open_reads_only_the_release_versions(monkeypatch):
    asked = []

    def load(_c, _pid, *, best_open_price_method_version):
        asked.append(best_open_price_method_version)
        return {"available": False, "reason": "none"}
    monkeypatch.setattr(detail, "load_best_open_price_product", load)
    detail._best_open_price_contract(object(), "p", V14)
    assert asked == list(V14.best_open_method_versions) and len(asked) == 1
    asked.clear()
    detail._best_open_price_contract(object(), "p", V12)
    assert asked == list(V12.best_open_method_versions) and len(asked) == 2


def test_snapshot_currentness_follows_the_active_release_identity(monkeypatch):
    from backend.db.services.public_rip_publication_contract import (
        candidate_publication_identity, canonical_publication_identity)
    v12_payload = {"meta": {"ripWeightsConfig": None}}
    monkeypatch.setattr(snap, "_read_rankings_publication_identity", lambda p: dict(canonical_publication_identity()))
    assert snap._rankings_publication_identity_mismatches({}) == []
    assert snap._rankings_publication_identity_mismatches({}, V14) != []   # a V12-built snapshot is stale under V14
    monkeypatch.setattr(snap, "_read_rankings_publication_identity", lambda p: dict(candidate_publication_identity()))
    assert snap._rankings_publication_identity_mismatches({}, V14) == []
    assert snap._rankings_publication_identity_mismatches({}) != []       # and a V14 snapshot is stale under V12 rollback


def test_v12_release_keeps_the_single_argument_check(monkeypatch):
    calls = []
    monkeypatch.setattr(snap, "_active_release_or_none", lambda: None)
    monkeypatch.setattr(snap, "_rankings_publication_identity_mismatches", lambda p, *a: calls.append(a) or [])
    snap._identity_mismatches_for_active_release({})
    assert calls == [()]
