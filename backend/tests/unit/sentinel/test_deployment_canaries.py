from datetime import datetime, timezone

import pytest

from backend.sentinel.checks.deployment import check_release_identity
from backend.sentinel.models import CheckOutcome, RunnerIdentity
from backend.sentinel.registry import CheckContext


NOW = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)
CTX = CheckContext(
    now=NOW,
    runner_identity=RunnerIdentity(component="sentinel_release", host="observer", build_sha="runner"),
)
EXPECTED = "a" * 40


class Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def get_for(backend_payload=None, frontend_payload=None, backend_status=200, frontend_status=200):
    def get(url, **_kwargs):
        if url.endswith("/health"):
            return Response(
                backend_payload
                if backend_payload is not None
                else {"status": "ok", "build": EXPECTED},
                backend_status,
            )
        if url.endswith("/api/sentinel/build"):
            return Response(
                frontend_payload
                if frontend_payload is not None
                else {
                    "status": "ok",
                    "build": EXPECTED,
                    "ref": "main",
                    "environment": "production",
                    "provider": "vercel",
                },
                frontend_status,
            )
        raise AssertionError(url)

    return get


def run(**overrides):
    values = dict(
        backend_base_url="https://backend.example.test",
        frontend_base_url="https://index.example.test",
        expected_sha=EXPECTED,
        expected_branch="main",
        expected_environment="production",
        http_get=get_for(),
    )
    values.update(overrides)
    return check_release_identity(CTX, **values)


def test_release_identity_is_healthy_only_when_both_surfaces_match_expected_release():
    result = run()
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["backend_build"] == EXPECTED
    assert result.observed["frontend_build"] == EXPECTED
    assert result.observed["frontend_branch"] == "main"


def test_short_explicit_sha_prefix_is_supported_for_operator_release_input():
    result = run(expected_sha=EXPECTED[:12])
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.authority_identity == EXPECTED[:12]


def test_backend_release_mismatch_fails():
    result = run(http_get=get_for(backend_payload={"status": "ok", "build": "b" * 40}))
    assert result.failure_code == "deployment_backend_release_mismatch"


def test_frontend_release_mismatch_and_branch_mismatch_fail_separately():
    mismatch = run(
        http_get=get_for(
            frontend_payload={
                "status": "ok",
                "build": "b" * 40,
                "ref": "main",
                "environment": "production",
                "provider": "vercel",
            }
        )
    )
    assert mismatch.failure_code == "deployment_frontend_release_mismatch"

    branch = run(
        http_get=get_for(
            frontend_payload={
                "status": "ok",
                "build": EXPECTED,
                "ref": "develop",
                "environment": "production",
                "provider": "vercel",
            }
        )
    )
    assert branch.failure_code == "deployment_frontend_branch_mismatch"


def test_frontend_environment_mismatch_fails():
    result = run(
        http_get=get_for(
            frontend_payload={
                "status": "ok",
                "build": EXPECTED,
                "ref": "main",
                "environment": "preview",
                "provider": "vercel",
            }
        )
    )
    assert result.failure_code == "deployment_frontend_environment_mismatch"


def test_unreachable_surface_is_structured_without_exception_message_leakage():
    def get(url, **_kwargs):
        if url.endswith("/health"):
            raise RuntimeError("secret-bearing-network-message")
        return Response({})

    result = run(http_get=get)
    assert result.failure_code == "deployment_backend_unreachable"
    assert result.evidence["backend_error_type"] == "RuntimeError"
    assert "secret-bearing-network-message" not in str(result.evidence)


def test_invalid_expected_sha_fails_closed_before_http():
    with pytest.raises(ValueError, match="expected release SHA"):
        run(expected_sha="not-a-sha", http_get=lambda *_a, **_k: pytest.fail("must not call HTTP"))
