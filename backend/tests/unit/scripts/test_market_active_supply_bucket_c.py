from __future__ import annotations

from pathlib import Path

import pytest

from backend.scripts.check_market_active_supply_health import evaluate
from backend.scripts.run_market_active_supply_snapshot import preflight

ROOT = Path(__file__).resolve().parents[4]


def test_dry_run_is_zero_cost_and_recurring_panel_stays_disabled():
    out = preflight(target_limit=10, offer_limit=19, credit_cap=300)
    assert out["target_count"] == 10
    assert out["projected_max_credits"] == 200
    assert out["provider_requests"] == out["provider_credits_used"] == 0
    assert out["database_writes"] == 0
    assert out["recurring_full_panel_enabled"] is False


@pytest.mark.parametrize("targets,offers,credits", [(11, 19, 300), (10, 20, 300), (10, 19, 301), (10, 19, 100)])
def test_launch_bounds_fail_closed(targets, offers, credits):
    with pytest.raises(ValueError):
        preflight(target_limit=targets, offer_limit=offers, credit_cap=credits)


def test_health_distinguishes_missing_run_from_zero_supply():
    missing = evaluate([], expected_date="2026-09-29")
    assert missing["state"] == "RUN_MISSING" and missing["healthy"] is False
    empty_but_observed = evaluate([{
        "run_id": "r", "expected_observation_date": "2026-09-29",
        "status": "COMPLETE", "target_count": 1, "observed_target_count": 1,
    }], expected_date="2026-09-29")
    assert empty_but_observed["healthy"] is True


def test_migration_is_mirrored_and_enforces_hashed_sellers():
    relative = "20260930010000_market_active_supply_bucket_c_v1.sql"
    backend = (ROOT / "backend/db/migrations" / relative).read_bytes()
    supabase = (ROOT / "supabase/migrations" / relative).read_bytes()
    assert backend == supabase
    sql = backend.decode().lower()
    assert "landed_price" in sql and "seller_concentration_hhi" in sql
    assert "hmac-sha256:v1:" in sql
    assert "market_active_supply_landed_price_backfill_incomplete" in sql
    assert "market_active_supply_unsafe_seller_identity_present" in sql
    assert "source_payload->>'landed_price'" in sql
    assert sql.index("update public.market_active_supply_listing_observations_v1") < sql.index("alter column landed_price set not null")
    assert "captured_depth_only" not in sql  # runtime semantics, not a DB-derived total


def test_no_recurring_workflow_is_enabled():
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".github/workflows").glob("*.yml")
    ).casefold()
    assert "run_market_active_supply_snapshot" not in workflow_text


def test_missing_health_path_can_materialize_explicit_continuity_rows():
    script = (ROOT / "backend/scripts/check_market_active_supply_health.py").read_text(encoding="utf-8")
    assert '"observation_state": "RUN_MISSING"' in script
    assert '"absence_is_not_disappearance": True' in script
    assert '"automatic_schedule_enabled": False' in script
