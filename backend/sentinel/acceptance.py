"""Whole-system acceptance and production-activation preflight for Sentinel.

This module is intentionally non-mutating.  It distinguishes code acceptance
from production activation and keeps AI optional/off.  Running the preflight
never applies schema, edits cron, suppresses alerts, deploys code, sends model
requests, or enables recovery.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from backend.sentinel.ai_budget import AI_HARD_MONTHLY_CAP_CENTS
from backend.sentinel.config import SentinelConfig
from backend.sentinel.triage import triage_runtime_summary


@dataclass(frozen=True)
class ActivationStage:
    order: int
    key: str
    purpose: str
    requires_explicit_approval: bool = True
    automatic: bool = False


ACTIVATION_STAGES: Tuple[ActivationStage, ...] = (
    ActivationStage(
        1,
        "deploy_core_persistence",
        "Generate/review/apply the core Sentinel schema migration; keep recovery and AI off.",
    ),
    ActivationStage(
        2,
        "clean_alert_backlog",
        "Snapshot historical alerts, dry-run an explicit cutoff, review it, then suppress only after approval.",
    ),
    ActivationStage(
        3,
        "activate_alert_delivery",
        "Enable dispatcher/watchdog configuration and canonical schedules; verify one controlled delivery.",
    ),
    ActivationStage(
        4,
        "start_observation_profiles",
        "Run fast/public/audit monitoring with persistent state and recovery disabled.",
    ),
    ActivationStage(
        5,
        "start_independent_watcher",
        "Run heartbeat/dead-man monitoring outside the scraper VM failure domain.",
    ),
    ActivationStage(
        6,
        "activate_release_and_vm_canaries",
        "Configure expected release SHA and approved VM overlay manifest; detection only.",
    ),
    ActivationStage(
        7,
        "activate_auth_synthetic",
        "Provision a dedicated non-human canary account and schedule authenticated navigation QA.",
    ),
    ActivationStage(
        8,
        "observation_burn_in",
        "Observe incidents/noise and validate evidence before any self-healing activation.",
    ),
    ActivationStage(
        9,
        "optional_bounded_recovery",
        "Only after separate approval, enable the two exact P6 recovery signatures and verify audit trails.",
    ),
    ActivationStage(
        10,
        "keep_ai_disabled",
        "Operate deterministic Sentinel with AI off; paid AI remains optional future work.",
    ),
)


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def _activation_inputs(config: SentinelConfig) -> Dict[str, bool]:
    return {
        "state_writes_enabled": bool(config.state_writes_enabled),
        "persistence_schema_ready": bool(config.persistence_schema_ready),
        "backend_base_url_configured": _configured(config.backend_base_url),
        "frontend_base_url_configured": _configured(config.frontend_base_url),
        "expected_release_sha_configured": _configured(config.expected_release_sha),
        "runtime_repo_path_configured": _configured(config.runtime_repo_path),
        "runtime_overlay_manifest_configured": _configured(
            config.runtime_overlay_manifest_path
        ),
        "independent_watch_host_configured": _configured(config.watch_host),
        "deadman_ping_configured": _configured(config.deadman_ping_url),
    }


def _activation_blockers(config: SentinelConfig) -> List[str]:
    inputs = _activation_inputs(config)
    blockers = [key for key, ready in inputs.items() if not ready]
    # These are intentionally human gates; static config cannot prove them.
    blockers.extend(
        [
            "manual_alert_backlog_review_pending",
            "manual_schedule_activation_verification_pending",
            "dedicated_auth_canary_account_pending",
            "observation_burn_in_pending",
        ]
    )
    return blockers


def build_acceptance_snapshot(config: SentinelConfig) -> Dict[str, Any]:
    """Return a safe non-mutating whole-system readiness snapshot."""
    configuration_error = None
    try:
        config.validate_kernel_v1()
    except RuntimeError as exc:
        configuration_error = str(exc)

    triage = None
    if configuration_error is None:
        try:
            triage = triage_runtime_summary(config)
        except RuntimeError as exc:
            configuration_error = str(exc)

    zero_ai_spend_mode = (
        configuration_error is None
        and config.ai_enabled is False
        and str(config.ai_provider or "").strip().lower() in {"", "disabled", "none"}
        and triage is not None
        and triage.get("request_made") is False
    )
    blockers = _activation_blockers(config)
    code_ready = configuration_error is None and zero_ai_spend_mode

    return {
        "status": (
            "code_ready_activation_pending"
            if code_ready
            else "configuration_blocked"
        ),
        "code_ready": code_ready,
        "production_activation_ready": code_ready and not blockers,
        "configuration_error": configuration_error,
        "ai": {
            "required_for_sentinel": False,
            "enabled": config.ai_enabled,
            "provider": config.ai_provider,
            "configured_monthly_budget_cents": config.ai_monthly_budget_cents,
            "hard_monthly_cap_cents": AI_HARD_MONTHLY_CAP_CENTS,
            "zero_ai_spend_mode": zero_ai_spend_mode,
            "runtime": triage,
        },
        "recovery": {
            "enabled": config.recovery_enabled,
            "execution_ready": config.recovery_execution_ready,
            "optional_for_initial_activation": True,
        },
        "activation": {
            "automatic": False,
            "inputs": _activation_inputs(config),
            "blockers": blockers,
            "stages": [asdict(stage) for stage in ACTIVATION_STAGES],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assert-zero-ai",
        action="store_true",
        help="Exit nonzero unless the current configuration guarantees no AI request path.",
    )
    args = parser.parse_args()

    snapshot = build_acceptance_snapshot(SentinelConfig.from_env())
    print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
    if args.assert_zero_ai and not snapshot["ai"]["zero_ai_spend_mode"]:
        return 2
    return 0 if snapshot["code_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
