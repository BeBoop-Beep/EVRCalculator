from datetime import datetime, timedelta, timezone

import pytest

from backend.pricing_pipeline import ebay_quota_policy as q
from backend.pricing_pipeline.ebay_credentials import (
    CredentialsUnavailable, EbayCredentials, credential_presence, environment_of, load_ebay_credentials, parse_env_file,
)
from backend.scripts import audit_ebay_quota_and_sold_access as audit

NOW = datetime(2026, 9, 21, 16, 0, tzinfo=timezone.utc)
KEY = q.KeysetIdentity("PRODUCTION", "a" * 64)


# ----------------------------------------------------------------------------------------------- credentials
def write_env(path, **kv):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("﻿# comment\n" + "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n", encoding="utf-8")


def test_precedence_process_env_then_backend_then_frontend(tmp_path):
    write_env(tmp_path / "backend/.env", EBAY_CLIENT_ID="be-PRD-1", EBAY_CLIENT_SECRET="bs")
    write_env(tmp_path / "frontend/.env.local", EBAY_CLIENT_ID="fe-SBX-1", EBAY_CLIENT_SECRET="fs")
    env = {"EBAY_CLIENT_ID": "pe-PRD-1", "EBAY_CLIENT_SECRET": "ps"}
    assert load_ebay_credentials(env, repo_root=tmp_path).source == "process-environment"
    assert load_ebay_credentials({}, repo_root=tmp_path).source == "backend/.env"
    (tmp_path / "backend/.env").unlink()
    assert load_ebay_credentials({}, repo_root=tmp_path).source == "frontend/.env.local"


def test_vm_path_never_needs_frontend_env(tmp_path):
    write_env(tmp_path / "backend/.env", EBAY_CLIENT_ID="be-PRD-1", EBAY_CLIENT_SECRET="bs")
    write_env(tmp_path / "frontend/.env.local", EBAY_CLIENT_ID="fe-PRD-1", EBAY_CLIENT_SECRET="fs")
    assert load_ebay_credentials({}, repo_root=tmp_path, allow_frontend_fallback=False).source == "backend/.env"
    (tmp_path / "backend/.env").unlink()
    with pytest.raises(CredentialsUnavailable):
        load_ebay_credentials({}, repo_root=tmp_path, allow_frontend_fallback=False)  # fail closed, no silent dev fallback


def test_partial_pairs_are_not_accepted_and_bom_is_tolerated(tmp_path):
    write_env(tmp_path / "backend/.env", EBAY_CLIENT_ID="only-id")
    with pytest.raises(CredentialsUnavailable):
        load_ebay_credentials({}, repo_root=tmp_path, allow_frontend_fallback=False)
    write_env(tmp_path / "frontend/.env.local", EBAY_CLIENT_ID="x-PRD-1", EBAY_CLIENT_SECRET="y")
    assert parse_env_file(tmp_path / "frontend/.env.local")["EBAY_CLIENT_ID"] == "x-PRD-1"  # first key survives the BOM


def test_credentials_never_appear_in_repr_or_str_or_presence(tmp_path):
    creds = EbayCredentials("Some-App-PRD-abcdef123456", "SuperSecretValue", "backend/.env")
    for text in (repr(creds), str(creds), f"{creds}"):
        assert "SuperSecretValue" not in text and "abcdef123456" not in text
    assert creds.environment == "PRODUCTION"
    write_env(tmp_path / "backend/.env", EBAY_CLIENT_ID="a-PRD-1", EBAY_CLIENT_SECRET="zzz")
    assert set(credential_presence(tmp_path).values()) <= {"true", "false"} and "zzz" not in str(credential_presence(tmp_path))


def test_environment_detection():
    assert environment_of("App-PRD-xyz") == "PRODUCTION" and environment_of("App-SBX-xyz") == "SANDBOX" and environment_of("weird") == "UNKNOWN"


# ------------------------------------------------------------------------------------------------ quota policy
def test_usable_limit_always_leaves_an_explicit_reserve():
    assert q.usable_limit(5000) == 4500 and q.usable_limit(1000) == 900 and q.usable_limit(150) == 50
    assert q.usable_limit(50) == 0 and q.usable_limit(5000, q.QuotaPolicy(hard_cap=1000)) == 1000
    for limit in (100, 1000, 5000, 100000):
        assert q.usable_limit(limit) < limit


def decide(**over):
    base = dict(verified_limit=5000, verified_at=NOW - timedelta(hours=1), provider_state=q.PROVIDER_OK, provider_remaining=5000,
                ledger_healthy=True, ledger_reserved=0, now=NOW, expected_keyset=KEY, verified_keyset=KEY)
    base.update(over)
    return q.authorize(**base)


def test_healthy_provider_verified_quota():
    d = decide()
    assert (d.mode, d.usable_limit, d.remaining, d.may_call) == (q.HEALTHY, 4500, 4500, True)
    assert decide(ledger_reserved=4500).may_call is False and decide(ledger_reserved=4499).remaining == 1


def test_provider_remaining_is_a_second_ceiling_after_the_reserve():
    assert decide(provider_remaining=700).remaining == 200  # 700 - 500 reserve; other consumers may share the key


@pytest.mark.parametrize("state", ["PROVIDER_USAGE_UNRESOLVED_NO_CONTENT", "PROVIDER_USAGE_ERROR", None])
def test_analytics_failure_never_means_unlimited_or_zero(state):
    d = decide(provider_state=state, provider_remaining=None, ledger_reserved=1000)
    assert d.mode == q.DEGRADED_LAST_KNOWN and d.usable_limit == 4500 and d.remaining == 3500 and d.may_call
    assert d.remaining <= d.usable_limit  # bounded by the last verified ceiling minus reserve


def test_stale_or_unknown_quota_fails_closed():
    stale = decide(provider_state="PROVIDER_USAGE_ERROR", verified_at=NOW - timedelta(hours=37))
    assert stale.mode == q.FAIL_CLOSED and stale.reason == "QUOTA_VERIFICATION_STALE" and not stale.may_call
    for over, reason in ((dict(verified_limit=None), "QUOTA_NEVER_VERIFIED"), (dict(verified_at=None), "QUOTA_NEVER_VERIFIED"),
                         (dict(verified_keyset=None), "QUOTA_NEVER_VERIFIED"), (dict(verified_limit=0), "QUOTA_NEVER_VERIFIED"),
                         (dict(verified_keyset=q.KeysetIdentity("PRODUCTION", "b" * 64)), "KEYSET_IDENTITY_CHANGED"),
                         (dict(ledger_healthy=False), "LEDGER_UNAVAILABLE")):
        d = decide(**over)
        assert d.mode == q.FAIL_CLOSED and d.reason == reason and d.remaining == 0 and not d.may_call


def test_window_follows_provider_reset_not_a_fixed_local_day():
    start, end = q.window_bounds(datetime(2026, 12, 21, 8, 0, tzinfo=timezone.utc), 86400)  # winter reset is 08:00Z, not 07:00Z
    assert end - start == timedelta(days=1) and end.hour == 8


def test_verification_from_provider_snapshot_prefers_daily_window_and_separates_pools():
    limits = [{"resource": "buy.browse", "limit": 5000, "count": 3, "remaining": 4997, "reset": "2026-09-22T07:00:00.000Z", "time_window_seconds": 86400},
              {"resource": "buy.browse.item.bulk", "limit": 5000, "count": 0, "remaining": 5000, "reset": "2026-09-22T07:00:00.000Z", "time_window_seconds": 86400},
              {"resource": "buy.marketplaceinsight", "limit": 5000, "count": 0, "remaining": 5000, "reset": "x", "time_window_seconds": 86400}]
    assert q.verification_from_provider(limits, q.BUCKET_BROWSE)["provider_reported_used"] == 3
    assert q.verification_from_provider(limits, q.BUCKET_BROWSE_BULK)["bucket"] == "buy.browse.item.bulk"
    assert q.verification_from_provider(limits, "buy.unknown") is None


# ------------------------------------------------------------------------------------------ audit normalization
def test_204_is_unresolved_never_zero_or_unlimited():
    for response in ({"status": 204, "body": None}, {"status": 200, "body": None}, {"status": 200, "body": {}}):
        summary = audit.summarize_rate_limits(response)
        assert summary["state"] == "PROVIDER_USAGE_UNRESOLVED_NO_CONTENT" and summary["limits"] == []
        assert "not zero" in summary["interpretation"] and "not unlimited" in summary["interpretation"]


def test_rate_limit_payload_is_normalized_per_resource_and_errors_are_sanitized():
    body = {"rateLimits": [{"apiContext": "buy", "apiName": "Browse", "apiVersion": "v1", "resources": [
        {"name": "buy.browse", "rates": [{"limit": 5000, "count": 1, "remaining": 4999, "reset": "2026-09-22T07:00:00.000Z", "timeWindow": 86400}]},
        {"name": "buy.browse.item.bulk", "rates": [{"limit": 5000, "count": 0, "remaining": 5000, "reset": "2026-09-22T07:00:00.000Z", "timeWindow": 86400}]}]}]}
    summary = audit.summarize_rate_limits({"status": 200, "body": body})
    assert summary["state"] == "PROVIDER_USAGE_OK" and [x["resource"] for x in summary["limits"]] == ["buy.browse", "buy.browse.item.bulk"]
    err = audit.summarize_rate_limits({"status": 500, "body": {"errors": [{"errorId": 1, "message": "boom", "secret": "nope"}]}})
    assert err["state"] == "PROVIDER_USAGE_ERROR" and "secret" not in str(err)
    assert audit._clean_errors({"errors": [{"errorId": 1100, "message": "Access denied", "token": "x"}]})[0].keys() >= {"errorId", "message"}
    assert "token" not in audit._clean_errors({"errors": [{"errorId": 1100, "token": "x"}]})[0]
