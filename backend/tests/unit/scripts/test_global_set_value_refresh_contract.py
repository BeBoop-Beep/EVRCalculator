from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[3] / "scripts" / "refresh_stale_public_snapshots.py").read_text(encoding="utf-8")


def test_global_set_values_refresh_after_per_set_market_and_before_other_globals():
    coordinated = SOURCE.index("_maybe_rebuild_coordinated_market(", SOURCE.index("# Rebuild order for the remaining families"))
    set_values = SOURCE.index("_maybe_rebuild_explore_set_values(", coordinated)
    movers = SOURCE.index("_maybe_rebuild_explore_card_movers(", set_values)
    rankings = SOURCE.index("_maybe_rebuild_rankings(", movers)
    assert coordinated < set_values < movers < rankings


def test_global_set_value_refresh_is_fail_closed():
    function = SOURCE[SOURCE.index("def _maybe_rebuild_explore_set_values("):SOURCE.index("def _maybe_rebuild_set_page(")]
    assert 'summary.global_failed.append("explore_set_values: promoted market date unavailable")' in function
    assert 'summary.global_failed.append(f"explore_set_values: {exc}")' in function
    assert "upsert_explore_set_value_snapshot(candidate" in function


# --------------------------------------------------------------------------
# Behavioral coverage. The contract tests above only prove the SOURCE mentions
# the right calls in the right order; they cannot prove the daily job actually
# publishes, skips, or fails closed. These do.
# --------------------------------------------------------------------------
import types

import pytest

from backend.scripts import refresh_stale_public_snapshots as refresh


CANDIDATE = {
    "tcg": "pokemon",
    "scope": "market",
    "payload_json": {"sets": [{"setId": "set-1"}]},
    "market_date": "2026-08-15",
    "set_count": 1,
    "source_generation_fingerprint": "fingerprint-new",
    "payload_size_bytes": 128,
    "_diagnostics": {},
}


def _summary():
    return refresh.RefreshSummary()


def _patch(monkeypatch, *, candidate, current, upserts):
    def _build(*, client, market_date, commit):
        assert commit is False, "the refresh path must never let the builder write directly"
        if isinstance(candidate, Exception):
            raise candidate
        return candidate

    monkeypatch.setattr(refresh, "build_explore_set_values", _build)
    monkeypatch.setattr(refresh, "_read_snapshot_row", lambda *_a, **_k: current)
    monkeypatch.setattr(
        "backend.db.services.pokemon_explore_set_value_service.upsert_explore_set_value_snapshot",
        lambda row, *, client: upserts.append(row),
    )


def test_a_no_current_snapshot_row_publishes_on_commit(monkeypatch):
    """The exact production state: an empty table must be treated as stale."""
    upserts = []
    _patch(monkeypatch, candidate=CANDIDATE, current=None, upserts=upserts)
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=True, summary=summary
    )

    assert len(upserts) == 1
    assert upserts[0]["source_generation_fingerprint"] == "fingerprint-new"
    assert "explore_set_values" in summary.global_rebuilt
    assert summary.global_failed == []


def test_b_unchanged_fingerprint_writes_nothing(monkeypatch):
    upserts = []
    _patch(
        monkeypatch,
        candidate=CANDIDATE,
        current={"source_generation_fingerprint": "fingerprint-new"},
        upserts=upserts,
    )
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=True, summary=summary
    )

    assert upserts == []
    assert "explore_set_values" not in summary.global_rebuilt
    assert "explore_set_values" not in summary.stale_snapshot_families
    assert summary.global_failed == []


def test_c_changed_fingerprint_writes_the_new_snapshot(monkeypatch):
    """Tomorrow's run: the source generation advances, so the artifact advances."""
    upserts = []
    _patch(
        monkeypatch,
        candidate=CANDIDATE,
        current={"source_generation_fingerprint": "fingerprint-yesterday"},
        upserts=upserts,
    )
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=True, summary=summary
    )

    assert len(upserts) == 1
    assert "explore_set_values" in summary.global_rebuilt
    assert "explore_set_values" in summary.stale_snapshot_families


def test_c_dry_run_detects_staleness_without_writing(monkeypatch):
    upserts = []
    _patch(
        monkeypatch,
        candidate=CANDIDATE,
        current={"source_generation_fingerprint": "fingerprint-yesterday"},
        upserts=upserts,
    )
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=False, summary=summary
    )

    assert upserts == []
    assert "explore_set_values" in summary.stale_snapshot_families
    assert any("explore_set_values" in entry for entry in summary.global_skipped)
    assert summary.global_rebuilt == []


def test_d_failed_validation_leaves_the_known_good_snapshot_untouched(monkeypatch):
    """A candidate that fails validation must not overwrite a good snapshot."""
    from backend.db.services.pokemon_explore_set_value_service import ExploreSetValueUnavailable

    upserts = []
    _patch(
        monkeypatch,
        candidate=ExploreSetValueUnavailable(
            "eligible Market Set Value sources are incomplete or disagree",
            diagnostics={"missingSets": ["set-9"]},
        ),
        current={"source_generation_fingerprint": "fingerprint-known-good"},
        upserts=upserts,
    )
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=True, summary=summary
    )

    assert upserts == [], "the previous known-good snapshot must survive a bad candidate"
    assert summary.global_rebuilt == []
    assert any("explore_set_values" in entry for entry in summary.global_failed)


def test_d_failure_is_recorded_so_publication_cannot_claim_health(monkeypatch):
    """global_failed must be non-empty so the run cannot report success."""
    upserts = []
    _patch(
        monkeypatch,
        candidate=RuntimeError("supabase exploded"),
        current=None,
        upserts=upserts,
    )
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date="2026-08-15", commit=True, summary=summary
    )

    assert upserts == []
    assert summary.global_failed
    assert "supabase exploded" in summary.global_failed[0]


def test_missing_market_date_fails_closed(monkeypatch):
    upserts = []
    _patch(monkeypatch, candidate=CANDIDATE, current=None, upserts=upserts)
    summary = _summary()

    refresh._maybe_rebuild_explore_set_values(
        object(), market_date=None, commit=True, summary=summary
    )

    assert upserts == []
    assert summary.global_failed == ["explore_set_values: promoted market date unavailable"]
