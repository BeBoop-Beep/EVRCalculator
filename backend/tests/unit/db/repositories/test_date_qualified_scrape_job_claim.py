from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.db.repositories import scrape_jobs_repository as repo


ROOT = Path(__file__).resolve().parents[5]
MIGRATION = ROOT / "backend/db/migrations/20260819160000_add_date_qualified_scrape_job_claim.sql"
BRIDGE = ROOT / "supabase/migrations/20260819160000_add_date_qualified_scrape_job_claim.sql"


def test_migration_bridge_is_exact_and_claim_is_atomic_date_qualified():
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())
    assert BRIDGE.read_text(encoding="utf-8") == sql
    assert "claim_next_scrape_job_for_market_date" in normalized
    assert "market_date = p_expected_market_date" in normalized
    assert "for update skip locked" in normalized
    assert "attempts = jobs.attempts + 1" in normalized
    assert normalized.index("market_date = p_expected_market_date") < normalized.index(
        "attempts = jobs.attempts + 1")
    assert "reconcile_stale_scrape_jobs(now(), p_expected_market_date)" in normalized
    assert "order by priority asc, created_at asc, id asc" in normalized


def test_wrong_date_rows_are_outside_the_claim_update_set():
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
    next_job = sql.split("with next_job as (", 1)[1].split(") update", 1)[0]
    assert "where status = 'pending'" in next_job
    assert "and market_date = p_expected_market_date" in next_job
    assert "limit 1" in next_job
    assert "update public.scrape_jobs as jobs" in sql
    assert "from next_job where jobs.id = next_job.id" in sql


def test_claim_rpc_requires_explicit_date_and_passes_it_to_database(monkeypatch):
    calls = []
    class Rpc:
        def execute(self): return SimpleNamespace(data=[])
    class Client:
        def rpc(self, name, params): calls.append((name, params)); return Rpc()
    monkeypatch.setattr(repo, "supabase", Client())
    assert repo.claim_next_scrape_job(
        worker_id="worker", lease_seconds=90, expected_market_date="2026-08-20") is None
    assert calls == [("claim_next_scrape_job_for_market_date", {
        "p_worker_id": "worker", "p_lease_seconds": 90,
        "p_expected_market_date": "2026-08-20",
    })]
    with pytest.raises(ValueError, match="expected_market_date is required"):
        repo.claim_next_scrape_job(worker_id="worker", lease_seconds=90)


@pytest.mark.parametrize(
    "expected,pending,claimed",
    [
        ("2026-08-19", ["2026-08-19"], "2026-08-19"),
        ("2026-08-20", ["2026-08-19"], None),
        ("2026-08-20", ["2026-08-19", "2026-08-20"], "2026-08-20"),
    ],
)
def test_date_qualification_state_model_does_not_consume_wrong_date_attempts(
    expected, pending, claimed,
):
    jobs = [{"market_date": day, "status": "pending", "attempts": 0} for day in pending]
    selected = next((job for job in jobs if job["status"] == "pending"
                     and job["market_date"] == expected), None)
    if selected:
        selected["status"] = "running"
        selected["attempts"] += 1
    assert (selected or {}).get("market_date") == claimed
    for job in jobs:
        if job["market_date"] != expected:
            assert job == {"market_date": job["market_date"],
                           "status": "pending", "attempts": 0}
