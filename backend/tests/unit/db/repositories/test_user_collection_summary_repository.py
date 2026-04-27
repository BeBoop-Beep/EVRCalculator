from types import SimpleNamespace
from unittest.mock import MagicMock

import backend.db.repositories.user_collection_summary_repository as repo


def test_get_nightly_snapshot_pricing_freshness_returns_rpc_payload(monkeypatch):
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value = SimpleNamespace(
        data={
            "snapshot_date": "2026-04-25",
            "status": "ok",
            "check_completed": True,
            "is_fresh": True,
            "held_asset_counts": {"cards": 1, "sealed": 1, "graded": 1},
            "fresh_asset_counts": {"cards": 1, "sealed": 1, "graded": 1},
            "missing_asset_counts": {"cards": 0, "sealed": 0, "graded": 0, "total": 0},
            "missing_assets_sample": [],
            "warning": None,
            "timings_ms": {
                "held_asset_load_ms": 1.0,
                "card_freshness_check_ms": 2.0,
                "sealed_freshness_check_ms": 3.0,
                "graded_freshness_check_ms": 4.0,
                "total_ms": 10.0,
            },
            "query_path": {"uses_distinct_held_assets": True},
        }
    )

    mock_supabase = MagicMock()
    mock_supabase.rpc.return_value = mock_rpc
    monkeypatch.setattr(repo, "supabase", mock_supabase)

    result = repo.get_nightly_snapshot_pricing_freshness("2026-04-25")

    mock_supabase.rpc.assert_called_once_with(
        "get_nightly_snapshot_pricing_freshness",
        {"p_snapshot_date": "2026-04-25", "p_sample_limit": 25},
    )
    assert result["is_fresh"] is True
    assert result["status"] == "ok"
    assert result["query_path"] == {"uses_distinct_held_assets": True}


def test_get_nightly_snapshot_pricing_freshness_normalizes_list_rpc_payload(monkeypatch):
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value = SimpleNamespace(
        data=[
            {
                "snapshot_date": "2026-04-25",
                "status": "skipped",
                "check_completed": True,
                "is_fresh": False,
                "held_asset_counts": {"cards": 2, "sealed": 0, "graded": 0},
                "fresh_asset_counts": {"cards": 1, "sealed": 0, "graded": 0},
                "missing_asset_counts": {"cards": 1, "sealed": 0, "graded": 0, "total": 1},
                "missing_assets_sample": [],
                "warning": "Pricing freshness incomplete for snapshot_date=2026-04-25; missing_or_stale_assets=1. Nightly snapshot skipped.",
                "timings_ms": {"total_ms": 8.0},
            }
        ]
    )

    mock_supabase = MagicMock()
    mock_supabase.rpc.return_value = mock_rpc
    monkeypatch.setattr(repo, "supabase", mock_supabase)

    result = repo.get_nightly_snapshot_pricing_freshness("2026-04-25")

    assert result["status"] == "skipped"
    assert result["check_completed"] is True
    assert result["missing_asset_counts"]["total"] == 1


def test_get_nightly_snapshot_pricing_freshness_returns_incomplete_when_rpc_fails(monkeypatch):
    mock_supabase = MagicMock()
    mock_supabase.rpc.side_effect = RuntimeError("query failed")
    monkeypatch.setattr(repo, "supabase", mock_supabase)

    result = repo.get_nightly_snapshot_pricing_freshness("2026-04-25")

    assert result["status"] == "incomplete"
    assert result["check_completed"] is False
    assert result["is_fresh"] is False
    assert result["warning"] == (
        "Pricing freshness check could not complete for snapshot_date=2026-04-25; "
        "nightly snapshot skipped."
    )
    assert result["error"] == {
        "type": "RuntimeError",
        "message": "query failed",
    }