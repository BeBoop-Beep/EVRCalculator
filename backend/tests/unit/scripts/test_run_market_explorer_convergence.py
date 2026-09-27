from __future__ import annotations

from dataclasses import replace

import backend.scripts.run_market_explorer_convergence as worker


DAY = "2026-09-27"


def snap(**over):
    base = worker.ConvergenceSnapshot(
        target_market_date=DAY,
        tracked_set_count=3,
        stale_card_set_ids=(),
        card_min_through=DAY,
        card_max_through=DAY,
        sealed_daily_through=DAY,
        sealed_metadata_through=DAY,
        rarity_certified_through=DAY,
        prepared_through=DAY,
        surface_v2_through=DAY,
    )
    return replace(base, **over)


def test_choose_stage_is_strict_dependency_order():
    assert worker.choose_stage(snap(stale_card_set_ids=("set-1",))) == "card_v2"
    assert worker.choose_stage(snap(sealed_daily_through="2026-09-26")) == "sealed_daily"
    assert worker.choose_stage(snap(sealed_metadata_through="2026-09-26")) == "sealed_meta"
    assert worker.choose_stage(snap(rarity_certified_through="2026-09-26")) == "rarity"
    assert worker.choose_stage(snap(prepared_through="2026-09-26")) == "prepared"
    assert worker.choose_stage(snap(surface_v2_through="2026-09-26")) == "surface_v2"
    assert worker.choose_stage(snap()) == "current"


def test_card_v2_outranks_every_downstream_gap():
    state = snap(
        stale_card_set_ids=("set-1",),
        sealed_daily_through="2026-09-26",
        sealed_metadata_through="2026-09-26",
        rarity_certified_through="2026-09-26",
        prepared_through="2026-09-26",
        surface_v2_through="2026-09-26",
    )
    assert worker.choose_stage(state) == "card_v2"


def test_dry_run_never_mutates(monkeypatch):
    before = snap(surface_v2_through="2026-09-26")
    monkeypatch.setattr(worker, "load_snapshot", lambda *_a, **_k: before)
    monkeypatch.setattr(
        worker,
        "_run_surface_stage",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("mutated")),
    )
    report = worker.run_convergence(object(), market_date=DAY, commit=False)
    assert report["status"] == "planned"
    assert report["stage"] == "surface_v2"
    assert report["result"] is None


def test_one_invocation_runs_only_selected_stage(monkeypatch):
    states = iter([
        snap(sealed_daily_through="2026-09-26", sealed_metadata_through="2026-09-26"),
        snap(sealed_daily_through=DAY, sealed_metadata_through="2026-09-26"),
    ])
    monkeypatch.setattr(worker, "load_snapshot", lambda *_a, **_k: next(states))
    calls = []
    monkeypatch.setattr(
        worker,
        "_run_sealed_daily_stage",
        lambda *_a, **_k: calls.append("sealed_daily") or {"upsertedRows": 4},
    )
    monkeypatch.setattr(
        worker,
        "_run_sealed_meta_stage",
        lambda *_a, **_k: calls.append("sealed_meta") or {"rows": 4},
    )

    report = worker.run_convergence(object(), market_date=DAY, commit=True)
    assert calls == ["sealed_daily"]
    assert report["stage"] == "sealed_daily"
    assert report["status"] == "advanced"


def test_card_stage_is_bounded_to_configured_set_count(monkeypatch):
    before = snap(stale_card_set_ids=("a", "b", "c", "d"))
    after = snap(stale_card_set_ids=("c", "d"))
    states = iter([before, after])
    monkeypatch.setattr(worker, "load_snapshot", lambda *_a, **_k: next(states))
    seen = []
    monkeypatch.setattr(
        worker,
        "_run_card_stage",
        lambda _client, _snapshot, *, card_set_batch: (
            seen.append(card_set_batch)
            or {"selectedSetCount": min(card_set_batch, 4)}
        ),
    )

    report = worker.run_convergence(
        object(), market_date=DAY, commit=True, card_set_batch=2
    )
    assert seen == [2]
    assert report["stage"] == "card_v2"
    assert report["status"] == "advanced"


def test_final_surface_promotion_runs_only_after_all_prerequisites(monkeypatch):
    before = snap(surface_v2_through="2026-09-26")
    after = snap()
    states = iter([before, after])
    monkeypatch.setattr(worker, "load_snapshot", lambda *_a, **_k: next(states))
    calls = []
    monkeypatch.setattr(
        worker,
        "_run_surface_stage",
        lambda *_a, **_k: calls.append("surface_v2") or {
            "status": "promoted",
            "marketDate": DAY,
        },
    )

    report = worker.run_convergence(object(), market_date=DAY, commit=True)
    assert calls == ["surface_v2"]
    assert report["status"] == "current"


def test_rarity_refresh_starts_after_existing_certification():
    assert worker._next_day("2026-09-26", DAY) == DAY
    assert worker._next_day(None, DAY) == DAY
