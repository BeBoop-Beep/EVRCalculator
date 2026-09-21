"""Recheck driver semantics: re-observing already-known identities must never touch
workflow state, must never turn a provider failure into a zero, must stay bounded,
and must distinguish raw provider card rows from processable card rows via the
shared scraper classification rule."""

from datetime import datetime, timedelta, timezone

from backend.services import pokemon_set_onboarding_recheck_service as service


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _row(**overrides):
    base = {
        "source_set_id": "999", "source_set_name": "Completed Empty Catalog Set",
        "status": "completed", "current_step": "final_verification",
        "provider_last_checked_at": None,
    }
    base.update(overrides)
    return base


def _processable_rows(count):
    return [
        {"productName": f"Card {i}", "condition": "Near Mint", "marketPrice": 1.0 + i}
        for i in range(count)
    ]


def _code_card_rows(count):
    return [
        {"productName": f"Code Card - Series {i}", "condition": "Near Mint", "marketPrice": 0.1}
        for i in range(count)
    ]


def test_completed_row_can_be_rechecked_without_status_or_step_in_the_payload(monkeypatch):
    """A completed, empty-catalog identity being observed again must never have
    status/current_step present in the reconcile call at all: the client-side contract
    only ever sends discovery/availability fields."""
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: [])
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 0)
    calls = []

    def fake_reconcile(**kwargs):
        calls.append(kwargs)
        return {"disposition": "observed_existing"}

    monkeypatch.setattr(service.jobs, "reconcile_discovery_v2", fake_reconcile)

    result = service.run_recheck(commit=True, limit=5)

    assert result["status"] == "ok"
    assert result["reconciled"] == 1
    assert len(calls) == 1
    assert "status" not in calls[0]
    assert "current_step" not in calls[0]
    assert calls[0]["source_set_id"] == "999"


def test_provider_evidence_changes_independently_of_workflow_row(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(3))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 3)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    assert calls[0]["card_listing_count"] == 3
    assert calls[0]["sealed_listing_count"] == 3
    # candidate_status is NOT the job's workflow status: the live RPC only accepts
    # 'detected'/'manual_review' and raises P0001 on anything else (e.g. 'completed').
    assert calls[0]["candidate_status"] == "detected"


def test_legacy_row_with_null_provider_last_checked_at_proposes_observed_existing_not_inserted(monkeypatch):
    """A row already present in pokemon_set_onboarding_jobs with provider_last_checked_at
    = NULL (never yet rechecked) must NOT forecast 'inserted': list_rechecks_v2 only
    ever returns existing jobs, so 'inserted' is impossible for a due recheck row. A
    null provider_last_checked_at means no prior provider observation exists yet, so a
    normal fresh check proposes observed_existing."""
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(provider_last_checked_at=None)],
    )
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(5))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 5)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: (_ for _ in ()).throw(AssertionError("dry-run must not write")),
    )

    result = service.run_recheck(commit=False, limit=5)

    assert result["identities"][0]["proposed_reconcile_disposition"] == "observed_existing"
    assert result["identities"][0]["proposed_reconcile_disposition"] != "inserted"


def test_stale_observation_dry_run_is_proposed_not_forced(monkeypatch):
    """A row whose provider_last_checked_at is already >= 'now' proposes
    stale_observation_ignored; actual staleness enforcement is the RPC's job, this is
    just the dry-run's best-effort forecast."""
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(provider_last_checked_at=future)],
    )
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(1))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 1)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: (_ for _ in ()).throw(AssertionError("dry-run must not write")),
    )

    result = service.run_recheck(commit=False, limit=5)

    assert result["reconciled"] == 0
    assert result["identities"][0]["proposed_reconcile_disposition"] == "stale_observation_ignored"


def test_sealed_only_availability_is_detectable(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: [])
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 4)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    assert calls[0]["card_listing_count"] == 0
    assert calls[0]["sealed_listing_count"] == 4


def test_cards_appearing_later_is_detectable(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(12))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 0)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    assert calls[0]["card_listing_count"] == 12
    assert calls[0]["sealed_listing_count"] == 0


def test_provider_failure_sends_none_never_zero(monkeypatch):
    """A provider/network failure must be sent through as None (NULL), never coerced to
    0 -- otherwise a transient outage would look identical to genuine sellout."""
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: None)
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: None)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)

    assert calls[0]["card_listing_count"] is None
    assert calls[0]["sealed_listing_count"] is None
    assert result["provider_errors"] == 1
    assert result["identities"][0]["provider_error"] == "provider_unreachable"


def test_fetch_listing_count_returns_none_on_non_200(monkeypatch):
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return _FakeResponse(status_code=500)
    assert service._fetch_listing_count(Requester(), "https://x", "label") is None


def test_fetch_listing_count_returns_none_when_no_response(monkeypatch):
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return None
    assert service._fetch_listing_count(Requester(), "https://x", "label") is None


def test_fetch_listing_count_counts_result_rows():
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return _FakeResponse(payload={"result": [{"a": 1}, {"a": 2}, {"a": 3}]})
    assert service._fetch_listing_count(Requester(), "https://x", "label") == 3


def test_fetch_listing_rows_returns_none_on_non_200():
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return _FakeResponse(status_code=500)
    assert service._fetch_listing_rows(Requester(), "https://x", "label") is None


def test_fetch_listing_rows_returns_none_when_no_response():
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return None
    assert service._fetch_listing_rows(Requester(), "https://x", "label") is None


def test_fetch_listing_rows_returns_raw_rows():
    class Requester:
        def safe_request(self, method, url, label, **kwargs):
            return _FakeResponse(payload={"result": [{"productName": "A"}, {"productName": "B"}]})
    rows = service._fetch_listing_rows(Requester(), "https://x", "label")
    assert len(rows) == 2


def test_job_limit_bounds_the_db_read(monkeypatch):
    seen = {}

    def fake_list(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(service.jobs, "list_rechecks_v2", fake_list)
    service.run_recheck(commit=False, limit=7)
    assert seen["limit"] == 7


def test_provider_request_budget_is_independent_of_row_count(monkeypatch):
    """Even if the DB returns more due rows than the budget allows, provider requests
    stop once the ceiling is hit -- an explicit second bound distinct from --limit."""
    rows = [_row(source_set_id=str(100 + i), source_set_name=f"Set {i}") for i in range(5)]
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: rows)
    fetch_calls = []
    monkeypatch.setattr(
        service, "_fetch_listing_rows",
        lambda requester, url, label: fetch_calls.append(url) or [],
    )
    monkeypatch.setattr(
        service, "_fetch_listing_count",
        lambda requester, url, label: fetch_calls.append(url) or 1,
    )
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2", lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5, max_provider_requests=4)

    assert result["due_checked"] == 2
    assert len(fetch_calls) == 4


def test_dry_run_never_calls_reconcile(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(1))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 1)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: (_ for _ in ()).throw(AssertionError("dry-run must not mutate the DB")),
    )

    result = service.run_recheck(commit=False, limit=5)

    assert result["dry_run"] is True
    assert result["reconciled"] == 0
    assert result["identities"][0]["card_listing_count"] == 1


def test_unresolvable_identity_id_is_reported_without_provider_calls(monkeypatch):
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(source_set_id="unresolved:abc123")],
    )
    monkeypatch.setattr(
        service, "_fetch_listing_rows",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch for unresolvable id")),
    )
    monkeypatch.setattr(
        service, "_fetch_listing_count",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch for unresolvable id")),
    )
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2", lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)

    assert result["identities"][0]["provider_error"] == "unresolvable_identity"
    assert result["identities"][0]["card_listing_count"] is None


def test_candidate_status_is_always_a_value_the_live_rpc_accepts(monkeypatch):
    """reconcile_pokemon_set_onboarding_discovery_v2 raises P0001 'candidate_status must
    be detected or manual_review' for anything else -- confirmed against production.
    A recheck row's own workflow status (completed/waiting/manual_review/ignored/...)
    must never be forwarded as candidate_status."""
    for workflow_status in ("completed", "waiting", "ignored", "retry", None):
        monkeypatch.setattr(
            service.jobs, "list_rechecks_v2", lambda **k: [_row(status=workflow_status)],
        )
        monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(1))
        monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 1)
        calls = []
        monkeypatch.setattr(
            service.jobs, "reconcile_discovery_v2",
            lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
        )

        service.run_recheck(commit=True, limit=5)

        assert calls[0]["candidate_status"] in ("detected", "manual_review"), workflow_status


# --- Card quality evidence: raw vs processable, code cards, provider unknown -----


def test_first_partner_collection_2026_three_code_card_rows_yield_code_cards_only(monkeypatch):
    """Reproduces the live First Partner Collection 2026 case: raw_card_listing_count
    stays 3 (unchanged existing field), but the new evidence shows all 3 are code
    cards and zero are processable."""
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _code_card_rows(3))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 9)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    discovery_json = calls[0]["discovery_json"]
    assert calls[0]["card_listing_count"] == 3  # existing field: RAW count, unchanged
    assert discovery_json["raw_card_listing_count"] == 3
    assert discovery_json["processable_card_listing_count"] == 0
    assert discovery_json["excluded_code_card_count"] == 3
    assert discovery_json["excluded_missing_required_count"] == 0
    assert discovery_json["card_catalog_status"] == "code_cards_only"


def test_legitimate_card_rows_yield_positive_processable_count(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _processable_rows(5))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 0)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    discovery_json = calls[0]["discovery_json"]
    assert discovery_json["raw_card_listing_count"] == 5
    assert discovery_json["processable_card_listing_count"] == 5
    assert discovery_json["excluded_code_card_count"] == 0
    assert discovery_json["card_catalog_status"] == "ok"


def test_mixed_code_and_real_cards_yields_mixed_status(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(
        service, "_fetch_listing_rows",
        lambda requester, url, label: _code_card_rows(2) + _processable_rows(3),
    )
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 0)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    discovery_json = calls[0]["discovery_json"]
    assert discovery_json["raw_card_listing_count"] == 5
    assert discovery_json["processable_card_listing_count"] == 3
    assert discovery_json["excluded_code_card_count"] == 2
    assert discovery_json["card_catalog_status"] == "mixed"


def test_provider_failure_reports_unknown_card_catalog_status_not_zero(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: None)
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: None)
    calls = []
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **kwargs: calls.append(kwargs) or {"disposition": "observed_existing"},
    )

    service.run_recheck(commit=True, limit=5)

    discovery_json = calls[0]["discovery_json"]
    assert discovery_json["card_catalog_status"] == "unknown"
    assert discovery_json["raw_card_listing_count"] is None
    assert discovery_json["processable_card_listing_count"] is None
    assert discovery_json["excluded_code_card_count"] is None
    assert discovery_json["excluded_missing_required_count"] is None


def test_empty_raw_catalog_is_distinct_from_unknown():
    assert service._card_quality_evidence([])["card_catalog_status"] == "empty"
    assert service._card_quality_evidence(None)["card_catalog_status"] == "unknown"


def test_dry_run_computes_card_quality_evidence_with_no_db_mutation(monkeypatch):
    monkeypatch.setattr(service.jobs, "list_rechecks_v2", lambda **k: [_row()])
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: _code_card_rows(3))
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 9)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: (_ for _ in ()).throw(AssertionError("dry-run must not mutate the DB")),
    )

    result = service.run_recheck(commit=False, limit=5)

    assert result["dry_run"] is True
    assert result["reconciled"] == 0
    discovery_json = result["identities"][0]["discovery_json"]
    assert discovery_json["card_catalog_status"] == "code_cards_only"
    assert discovery_json["raw_card_listing_count"] == 3
    assert discovery_json["processable_card_listing_count"] == 0

def test_positive_card_catalog_appearing_from_unknown_is_refresh_worthy(monkeypatch):
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(
            provider_card_listing_count=None,
            provider_sealed_listing_count=12,
            provider_discovery_json={},
        )],
    )
    monkeypatch.setattr(
        service, "_fetch_listing_rows",
        lambda requester, url, label: _processable_rows(30),
    )
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 12)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)
    item = result["identities"][0]

    assert item["previous_card_listing_count"] is None
    assert item["card_listing_count_changed"] is True
    assert item["sealed_listing_count_changed"] is False
    assert item["availability_changed"] is True
    assert item["discovery_json"]["availability_changed"] is True


def test_first_observed_zero_does_not_trigger_refresh(monkeypatch):
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(
            provider_card_listing_count=None,
            provider_sealed_listing_count=12,
            provider_discovery_json={},
        )],
    )
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: [])
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 12)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)
    item = result["identities"][0]

    assert item["card_listing_count"] == 0
    assert item["card_listing_count_changed"] is False
    assert item["availability_changed"] is False


def test_code_cards_becoming_processable_triggers_refresh_even_when_raw_count_is_same(monkeypatch):
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(
            provider_card_listing_count=3,
            provider_sealed_listing_count=9,
            provider_discovery_json={"processable_card_listing_count": 0},
        )],
    )
    monkeypatch.setattr(
        service, "_fetch_listing_rows",
        lambda requester, url, label: _processable_rows(3),
    )
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: 9)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)
    item = result["identities"][0]

    assert item["card_listing_count_changed"] is False
    assert item["processable_cards_became_available"] is True
    assert item["availability_changed"] is True


def test_provider_failure_never_marks_availability_changed(monkeypatch):
    monkeypatch.setattr(
        service.jobs, "list_rechecks_v2",
        lambda **k: [_row(
            provider_card_listing_count=4,
            provider_sealed_listing_count=8,
            provider_discovery_json={"processable_card_listing_count": 4},
        )],
    )
    monkeypatch.setattr(service, "_fetch_listing_rows", lambda requester, url, label: None)
    monkeypatch.setattr(service, "_fetch_listing_count", lambda requester, url, label: None)
    monkeypatch.setattr(
        service.jobs, "reconcile_discovery_v2",
        lambda **k: {"disposition": "observed_existing"},
    )

    result = service.run_recheck(commit=True, limit=5)
    item = result["identities"][0]

    assert item["availability_changed"] is False
    assert item["card_listing_count_changed"] is False
    assert item["sealed_listing_count_changed"] is False
