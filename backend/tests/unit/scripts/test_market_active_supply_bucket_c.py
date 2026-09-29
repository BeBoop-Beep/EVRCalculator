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


def test_reviewed_full_panel_dry_run_is_exact_and_bounded():
    out = preflight(target_limit=207, offer_limit=19, credit_cap=4500,
                    full_panel=True, unresolved_identity_count=207)
    assert out["target_count"] == 207
    assert out["projected_max_credits"] == 4140
    assert out["database_writes"] == out["provider_requests"] == 0
    assert out["full_panel_mode"] is True


@pytest.mark.parametrize("targets,offers,cap", [(206, 19, 4500), (207, 18, 4500), (207, 19, 4499)])
def test_full_panel_contract_cannot_be_weakened(targets, offers, cap):
    with pytest.raises(ValueError):
        preflight(target_limit=targets, offer_limit=offers, credit_cap=cap,
                  full_panel=True, unresolved_identity_count=0)


def test_vm_cron_is_phoenix_pinned_and_has_only_one_retry():
    cron = (ROOT / "infra/oracle/active-supply-panel.crontab").read_text(encoding="utf-8")
    runner = (ROOT / "infra/oracle/run_active_supply_panel.sh").read_text(encoding="utf-8")
    health_runner = (ROOT / "infra/oracle/run_active_supply_health.sh").read_text(encoding="utf-8")
    installer = (ROOT / "infra/oracle/install_active_supply_panel_cron.sh").read_text(encoding="utf-8")
    credential_installer = (ROOT / "infra/oracle/install_active_supply_credentials.sh").read_text(encoding="utf-8")
    assert "CRON_TZ=America/Phoenix" in cron
    assert "10 21 * * *" in cron and "40 21 * * *" in cron
    assert cron.count("run_active_supply_panel.sh") == 2
    assert "/tmp/pkmnprices-api.lock" in runner
    assert "/tmp/active-supply-panel.lock" in runner
    assert "/tmp/pokemon-post-scrape-publication.lock" in runner
    assert "/home/ubuntu/state/db-safety/hold.json" in runner
    assert "release.sha" in runner and "RELEASE_DRIFT_REFUSED" in runner
    assert "release.sha" in health_runner and "--record-missing" in health_runner
    assert "--apply" in installer and "VERIFY ONLY" in installer
    assert "worktree add --detach" in installer
    assert "/home/ubuntu/state/active_supply_panel/runtime/" in cron
    assert "ENV_REPO" in runner and "ENV_REPO" in health_runner
    assert "ACTIVE_SUPPLY_SELLER_HASH_KEY_INSTALL" in credential_installer
    assert "externally retained secret" in credential_installer
    assert "openssl rand" not in credential_installer
    assert "credential unchanged" in credential_installer
    assert "value=<redacted>" in credential_installer


def test_no_turnover_scarcity_or_page_two_collection():
    collector = (ROOT / "backend/scripts/run_market_active_supply_snapshot.py").read_text(encoding="utf-8")
    assert '"turnover_enabled": False' in collector
    assert '"market_scarcity_enabled": False' in collector
    assert '"page_2_requested": False' in collector
    assert "limit=offer_limit" in collector


def test_full_panel_partial_date_is_resumable_not_a_noop():
    collector = (ROOT / "backend/scripts/run_market_active_supply_snapshot.py").read_text(encoding="utf-8")
    store = (ROOT / "backend/pricing_pipeline/active_supply_store.py").read_text(encoding="utf-8")
    assert 'existing.get("status") == "COMPLETE"' in collector
    assert 'existing.get("status") == "MISSING"' in collector
    assert "existing_run=existing" in collector
    assert "full_panel_retry" in collector
    assert "prior_credits + provider.credits_charged" in collector
    assert "replace_retryable_snapshot" in collector
    assert "observed snapshot is immutable" in store


def test_retry_update_grant_is_mirrored():
    relative = "20260930030000_market_active_supply_retry_update_v1.sql"
    backend = (ROOT / "backend/db/migrations" / relative).read_bytes()
    supabase = (ROOT / "supabase/migrations" / relative).read_bytes()
    assert backend == supabase
    sql = backend.decode().lower()
    assert "grant update on public.market_active_supply_snapshots_v1 to service_role" in sql
    assert "target_failed placeholders" in sql


def test_full_panel_cap_stop_materializes_remaining_targets():
    collector = (ROOT / "backend/scripts/run_market_active_supply_snapshot.py").read_text(encoding="utf-8")
    assert "for pending in targets[target_index:]" in collector
    assert "absence must never be interpreted as" in collector.lower()
    assert "DAILY_CREDIT_CAP_WOULD_BE_EXCEEDED" in collector


def test_installers_keep_reviewed_code_separate_from_vm_env_repo():
    installer = (ROOT / "infra/oracle/install_active_supply_panel_cron.sh").read_text(encoding="utf-8")
    credential_installer = (ROOT / "infra/oracle/install_active_supply_credentials.sh").read_text(encoding="utf-8")
    assert 'SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"' in installer
    assert "ACTIVE_SUPPLY_ENV_REPO" in installer
    assert 'ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"' in installer
    assert 'PY="$ENV_REPO/.venv/bin/python"' in installer
    assert 'CODE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"' in credential_installer
    assert 'ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"' in credential_installer
    assert 'ENV_FILE="$ENV_REPO/backend/.env"' in credential_installer
