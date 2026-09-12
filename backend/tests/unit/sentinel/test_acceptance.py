from backend.sentinel.acceptance import ACTIVATION_STAGES, build_acceptance_snapshot
from backend.sentinel.config import SentinelConfig


def test_default_acceptance_is_code_ready_with_zero_ai_spend_mode():
    snapshot = build_acceptance_snapshot(SentinelConfig())
    assert snapshot["code_ready"] is True
    assert snapshot["ai"]["required_for_sentinel"] is False
    assert snapshot["ai"]["zero_ai_spend_mode"] is True
    assert snapshot["ai"]["runtime"]["request_made"] is False


def test_default_acceptance_distinguishes_code_ready_from_activation_ready():
    snapshot = build_acceptance_snapshot(SentinelConfig())
    assert snapshot["status"] == "code_ready_activation_pending"
    assert snapshot["production_activation_ready"] is False


def test_activation_blockers_include_unconfigured_runtime_and_manual_gates():
    blockers = build_acceptance_snapshot(SentinelConfig())["activation"]["blockers"]
    assert "persistence_schema_ready" in blockers
    assert "state_writes_enabled" in blockers
    assert "deadman_ping_configured" in blockers
    assert "manual_alert_backlog_review_pending" in blockers
    assert "dedicated_auth_canary_account_pending" in blockers


def test_activation_stages_are_ordered_explicit_and_never_automatic():
    assert [stage.order for stage in ACTIVATION_STAGES] == list(
        range(1, len(ACTIVATION_STAGES) + 1)
    )
    assert all(stage.requires_explicit_approval for stage in ACTIVATION_STAGES)
    assert all(stage.automatic is False for stage in ACTIVATION_STAGES)


def test_final_activation_stage_explicitly_keeps_ai_disabled():
    assert ACTIVATION_STAGES[-1].key == "keep_ai_disabled"
    assert "AI off" in ACTIVATION_STAGES[-1].purpose


def test_full_runtime_inputs_do_not_bypass_manual_activation_gates():
    config = SentinelConfig(
        state_writes_enabled=True,
        persistence_schema_ready=True,
        backend_base_url="https://backend.example.test",
        frontend_base_url="https://frontend.example.test",
        expected_release_sha="a" * 40,
        runtime_repo_path="/srv/index",
        runtime_overlay_manifest_path="/srv/index/vm-overlay.json",
        watch_host="external-watcher",
        deadman_ping_url="https://heartbeat.example.test/capability",
    )
    snapshot = build_acceptance_snapshot(config)
    assert snapshot["code_ready"] is True
    assert snapshot["production_activation_ready"] is False
    assert snapshot["activation"]["inputs"]["expected_release_sha_configured"] is True
    assert "observation_burn_in_pending" in snapshot["activation"]["blockers"]


def test_recovery_is_optional_for_initial_activation_and_defaults_off():
    snapshot = build_acceptance_snapshot(SentinelConfig())
    assert snapshot["recovery"] == {
        "enabled": False,
        "execution_ready": False,
        "optional_for_initial_activation": True,
    }
    assert snapshot["code_ready"] is True


def test_unsafe_ai_configuration_blocks_whole_system_acceptance():
    snapshot = build_acceptance_snapshot(
        SentinelConfig(ai_monthly_budget_cents=1001)
    )
    assert snapshot["code_ready"] is False
    assert snapshot["status"] == "configuration_blocked"
    assert snapshot["ai"]["zero_ai_spend_mode"] is False
    assert "hard Sentinel AI ceiling" in snapshot["configuration_error"]
