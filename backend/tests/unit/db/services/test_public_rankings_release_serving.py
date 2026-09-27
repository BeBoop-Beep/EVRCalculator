"""Public Product Rankings selects its ranking/Best-Open method through the active release."""
from backend.db.services import public_overall_product_rankings_service as service
from backend.db.services import rip_release as rr
from backend.tests.unit.db.services.test_best_open_price_public_projection import (
    IDENTITIES, PREPARED, PRESENTATION, RAW_ROW, SNAPSHOT,
)

V2 = rr.RELEASES[next(k for k in rr.RELEASES if rr.RELEASES[k].requires_v5_schema)].ranking_method_version
V14 = next(b for b in rr.RELEASES.values() if b.requires_v5_schema)
V12 = next(b for b in rr.RELEASES.values() if not b.requires_v5_schema)


def _install(monkeypatch, *, ranking_version, best_open_available=True):
    seen = {"ranking": [], "best_open": []}

    def latest(_client, **kw):
        seen["ranking"].append(kw.get("ranking_method_version", "<default>"))
        return dict(SNAPSHOT, ranking_method_version=ranking_version)

    def best_open(_client, **kw):
        v = kw["best_open_price_method_version"]
        seen["best_open"].append(v)
        return dict(PREPARED, methodVersion=v) if best_open_available and v == V14.best_open_method_versions[0] else {"available": False, "reason": "none"}

    monkeypatch.setattr(service, "load_latest_snapshot", latest)
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _c, **_k: {"rows": [dict(RAW_ROW)], "authority": {}})
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _r, _s: dict(PRESENTATION))
    monkeypatch.setattr(service, "load_best_open_price_ranking", best_open)
    return seen


def test_v14_release_reads_ranking_v2_and_best_open_v3_only(monkeypatch):
    seen = _install(monkeypatch, ranking_version=V14.ranking_method_version)
    out = service.read_public_overall_product_rankings("full_market", product_family_rankings=IDENTITIES,
                                                       client=object(), release=V14)
    assert out["available"] is True and seen["ranking"] == [V14.ranking_method_version]
    assert seen["best_open"] == list(V14.best_open_method_versions) and len(seen["best_open"]) == 1
    assert out["bestOpenPrice"]["methodVersion"] == V14.best_open_method_versions[0]


def test_v14_release_never_falls_back_to_best_open_v2_or_v1(monkeypatch):
    seen = _install(monkeypatch, ranking_version=V14.ranking_method_version, best_open_available=False)
    out = service.read_public_overall_product_rankings("full_market", product_family_rankings=IDENTITIES,
                                                       client=object(), release=V14)
    assert out["available"] is True and out["bestOpenPrice"]["available"] is False
    assert seen["best_open"] == [V14.best_open_method_versions[0]]     # nothing older was even asked for


def test_v14_release_refuses_a_v1_ranking_snapshot(monkeypatch):
    _install(monkeypatch, ranking_version=V12.ranking_method_version)
    out = service.read_public_overall_product_rankings("full_market", product_family_rankings=IDENTITIES,
                                                       client=object(), release=V14)
    assert out["available"] is False and out["reason"] == "ranking_method_mismatch" and out["rows"] == []


def test_v14_release_without_a_ranking_v2_publication_is_truthfully_unavailable(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _c, **_k: None)
    out = service.read_public_overall_product_rankings("full_market", product_family_rankings=IDENTITIES,
                                                       client=object(), release=V14)
    assert out["available"] is False and out["reason"] == "no_published_authority"


def test_v12_release_keeps_default_ranking_read_and_v2_then_v1_best_open(monkeypatch):
    seen = _install(monkeypatch, ranking_version=V12.ranking_method_version, best_open_available=False)
    service.read_public_overall_product_rankings("full_market", product_family_rankings=IDENTITIES,
                                                 client=object(), release=V12)
    assert seen["ranking"] == ["<default>"] and seen["best_open"] == list(V12.best_open_method_versions)
