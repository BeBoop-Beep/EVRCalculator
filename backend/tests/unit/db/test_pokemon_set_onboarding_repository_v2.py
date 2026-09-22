"""v2 RPC integration: lease-token propagation, zero-row-means-lease-loss, and
non-destructive discovery reconciliation."""

from backend.db.repositories import pokemon_set_onboarding_repository as repo


class _FakeRpc:
    def __init__(self, recorder, rows, name):
        self._recorder = recorder
        self._rows = rows
        self._name = name

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeSupabase:
    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    def rpc(self, name, params):
        self._recorder["name"] = name
        self._recorder["params"] = params
        return _FakeRpc(self._recorder, self._rows, name)


def test_claim_next_v2_passes_include_waiting_and_force_retry(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1", "lease_token": "t1"}]))

    result = repo.claim_next_v2("worker-1", 900, job_id="j1", include_waiting=True, force_retry=True)

    assert recorder["name"] == "claim_next_pokemon_set_onboarding_job_v2"
    assert recorder["params"] == {
        "p_worker_id": "worker-1", "p_lease_seconds": 900,
        "p_job_id": "j1", "p_include_waiting": True, "p_force_retry": True,
    }
    assert result == {"id": "j1", "lease_token": "t1"}


def test_claim_next_v2_row_carries_lease_token(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1", "lease_token": "secret-token"}]))

    result = repo.claim_next_v2("worker-1")

    assert result["lease_token"] == "secret-token"


def test_heartbeat_v2_passes_lease_token(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1"}]))

    repo.heartbeat_v2("j1", "worker-1", "secret-token", 900)

    assert recorder["params"] == {
        "p_job_id": "j1", "p_worker_id": "worker-1", "p_lease_token": "secret-token",
        "p_lease_seconds": 900,
    }


def test_heartbeat_v2_zero_rows_means_lease_loss_not_success(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    result = repo.heartbeat_v2("j1", "worker-1", "stale-token", 900)

    assert result is None


def test_transition_v2_strict_raises_on_zero_rows(monkeypatch):
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, []))
    try:
        repo.transition_v2(
            "j1", "worker-1", "stale-token", "metadata_resolution", {"status": "ready"}, strict=True,
        )
    except repo.LeaseFencingError:
        pass
    else:
        raise AssertionError("expected LeaseFencingError on a zero-row fenced v2 transition")


def test_transition_v2_non_strict_returns_none_on_zero_rows(monkeypatch):
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, []))
    assert repo.transition_v2(
        "j1", "worker-1", "stale-token", "metadata_resolution", {"status": "ready"},
    ) is None


def test_transition_v2_passes_expected_step_and_lease_token(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1"}]))

    repo.transition_v2("j1", "worker-1", "secret-token", "market_snapshots", {"status": "ready"})

    assert recorder["params"] == {
        "p_job_id": "j1", "p_worker_id": "worker-1", "p_lease_token": "secret-token",
        "p_expected_step": "market_snapshots", "p_fields": {"status": "ready"},
    }


def test_release_for_retry_v2_is_fenced_by_lease_token_and_expected_step(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1"}]))

    repo.release_for_retry_v2(
        "j1", "worker-1", "secret-token", "market_snapshots",
        code="step_failed", message="boom", delay_seconds=60,
    )

    params = recorder["params"]
    assert params["p_lease_token"] == "secret-token"
    assert params["p_expected_step"] == "market_snapshots"
    assert params["p_fields"]["status"] == "retry"
    assert params["p_fields"]["current_step"] == "market_snapshots"
    assert params["p_fields"]["last_error_code"] == "step_failed"


def test_reconcile_discovery_v2_passes_all_fields(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(
        repo, "supabase", _FakeSupabase(recorder, [{"disposition": "inserted"}]),
    )

    result = repo.reconcile_discovery_v2(
        source_system="tcgplayer", source_set_id="999", source_set_name="Future Set",
        candidate_status="detected", discovery_json={"evidence": True},
        observed_at="2026-09-01T00:00:00+00:00", next_check_at=None,
        card_listing_count=10, sealed_listing_count=2,
    )

    assert recorder["name"] == "reconcile_pokemon_set_onboarding_discovery_v2"
    assert recorder["params"]["p_source_set_id"] == "999"
    assert recorder["params"]["p_candidate_status"] == "detected"
    assert recorder["params"]["p_card_listing_count"] == 10
    assert result == {"disposition": "inserted"}


def test_reconcile_discovery_v2_defaults_observed_at_when_omitted(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"disposition": "observed_existing"}]))

    repo.reconcile_discovery_v2(
        source_system="tcgplayer", source_set_id="999", source_set_name="Future Set",
        candidate_status="detected", discovery_json={},
    )

    assert recorder["params"]["p_observed_at"]


def test_list_rechecks_v2_passes_source_system_limit_and_as_of(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, [{"id": "j1"}]))

    result = repo.list_rechecks_v2(source_system="tcgplayer", limit=10, as_of="2026-09-01T00:00:00+00:00")

    assert recorder["params"] == {
        "p_source_system": "tcgplayer", "p_limit": 10, "p_as_of": "2026-09-01T00:00:00+00:00",
    }
    assert result == [{"id": "j1"}]


def test_list_rechecks_v2_empty_rows_returns_empty_list(monkeypatch):
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, None))
    assert repo.list_rechecks_v2() == []
