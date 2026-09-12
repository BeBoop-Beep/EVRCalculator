"""Detection-only deployment identity canaries for inDex Sentinel."""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, Mapping, Optional

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_USER_AGENT = "inDex-Sentinel/1.0"


def _bounded_text(value: Any, limit: int = 300) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    return text if len(text) <= limit else text[:limit] + "...<TRUNCATED>"


def _join(base_url: str, path: str) -> str:
    return str(base_url or "").strip().rstrip("/") + "/" + str(path or "").lstrip("/")


def _probe_json(
    base_url: str,
    path: str,
    *,
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = 12.0,
) -> Dict[str, Any]:
    url = _join(base_url, path)
    if http_get is None:
        import requests

        http_get = requests.get
    started = time.perf_counter()
    try:
        response = http_get(
            url,
            timeout=float(timeout_seconds),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
    except Exception as exc:
        return {
            "url": url,
            "status_code": None,
            "payload": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
            "error_type": exc.__class__.__name__,
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    status = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
        error_type = None
    except Exception as exc:
        payload = None
        error_type = exc.__class__.__name__
    return {
        "url": url,
        "status_code": status,
        "payload": payload,
        "elapsed_ms": elapsed_ms,
        "error_type": error_type,
    }


def _normalize_expected_sha(value: str) -> str:
    resolved = str(value or "").strip().lower()
    if not _SHA_RE.fullmatch(resolved):
        raise ValueError("expected release SHA must be 7-40 hexadecimal characters")
    return resolved


def _observed_build(payload: Mapping[str, Any]) -> str:
    return str(payload.get("build") or "").strip().lower()


def _matches_expected(observed: str, expected: str) -> bool:
    candidate = str(observed or "").strip().lower()
    return bool(candidate) and candidate.startswith(expected)


def _failure(
    context: CheckContext,
    *,
    code: str,
    expected_sha: str,
    expected_branch: str,
    expected_environment: str,
    observed: Mapping[str, Any],
    evidence: Optional[Mapping[str, Any]] = None,
) -> CheckResult:
    return CheckResult.failure(
        "deployment.release_identity",
        failure_code=code,
        severity=Severity.CRITICAL,
        authority_identity=expected_sha,
        expected={
            "release_sha": expected_sha,
            "frontend_branch": expected_branch,
            "frontend_environment": expected_environment,
        },
        observed=dict(observed),
        evidence=dict(evidence or {}),
        checked_at=context.now,
    )


def check_release_identity(
    context: CheckContext,
    *,
    backend_base_url: str,
    frontend_base_url: str,
    expected_sha: str,
    expected_branch: str = "main",
    expected_environment: str = "production",
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = 12.0,
) -> CheckResult:
    """Verify backend and frontend are serving one explicitly expected release.

    This is intended for post-deploy/release verification, not continuous polling.
    The expected SHA is operator supplied so Sentinel never guesses which release
    should be live.
    """
    resolved_expected = _normalize_expected_sha(expected_sha)
    resolved_branch = str(expected_branch or "").strip()
    resolved_environment = str(expected_environment or "").strip()
    if not str(backend_base_url or "").strip():
        raise ValueError("backend base URL is required")
    if not str(frontend_base_url or "").strip():
        raise ValueError("frontend base URL is required")

    backend = _probe_json(
        backend_base_url,
        "/health",
        http_get=http_get,
        timeout_seconds=timeout_seconds,
    )
    frontend = _probe_json(
        frontend_base_url,
        "/api/sentinel/build",
        http_get=http_get,
        timeout_seconds=timeout_seconds,
    )

    observed = {
        "backend_status_code": backend.get("status_code"),
        "frontend_status_code": frontend.get("status_code"),
        "backend_elapsed_ms": backend.get("elapsed_ms"),
        "frontend_elapsed_ms": frontend.get("elapsed_ms"),
    }
    evidence = {
        "backend_url": backend.get("url"),
        "frontend_url": frontend.get("url"),
        "backend_error_type": backend.get("error_type"),
        "frontend_error_type": frontend.get("error_type"),
    }

    if backend.get("status_code") is None:
        return _failure(
            context,
            code="deployment_backend_unreachable",
            expected_sha=resolved_expected,
            expected_branch=resolved_branch,
            expected_environment=resolved_environment,
            observed=observed,
            evidence=evidence,
        )
    if frontend.get("status_code") is None:
        return _failure(
            context,
            code="deployment_frontend_unreachable",
            expected_sha=resolved_expected,
            expected_branch=resolved_branch,
            expected_environment=resolved_environment,
            observed=observed,
            evidence=evidence,
        )
    if backend.get("status_code") != 200 or not isinstance(backend.get("payload"), dict):
        return _failure(
            context,
            code="deployment_backend_contract_invalid",
            expected_sha=resolved_expected,
            expected_branch=resolved_branch,
            expected_environment=resolved_environment,
            observed=observed,
            evidence=evidence,
        )
    if frontend.get("status_code") != 200 or not isinstance(frontend.get("payload"), dict):
        return _failure(
            context,
            code="deployment_frontend_contract_invalid",
            expected_sha=resolved_expected,
            expected_branch=resolved_branch,
            expected_environment=resolved_environment,
            observed=observed,
            evidence=evidence,
        )

    backend_payload = dict(backend["payload"])
    frontend_payload = dict(frontend["payload"])
    backend_build = _observed_build(backend_payload)
    frontend_build = _observed_build(frontend_payload)
    frontend_branch = str(frontend_payload.get("ref") or "").strip()
    frontend_environment = str(frontend_payload.get("environment") or "").strip()
    observed.update(
        {
            "backend_build": backend_build,
            "frontend_build": frontend_build,
            "frontend_branch": frontend_branch,
            "frontend_environment": frontend_environment,
            "frontend_provider": frontend_payload.get("provider"),
        }
    )

    if backend_payload.get("status") != "ok" or not backend_build:
        code = "deployment_backend_contract_invalid"
    elif frontend_payload.get("status") != "ok" or not frontend_build:
        code = "deployment_frontend_contract_invalid"
    elif not _matches_expected(backend_build, resolved_expected):
        code = "deployment_backend_release_mismatch"
    elif not _matches_expected(frontend_build, resolved_expected):
        code = "deployment_frontend_release_mismatch"
    elif backend_build != frontend_build:
        code = "deployment_cross_surface_release_mismatch"
    elif resolved_branch and frontend_branch != resolved_branch:
        code = "deployment_frontend_branch_mismatch"
    elif resolved_environment and frontend_environment != resolved_environment:
        code = "deployment_frontend_environment_mismatch"
    else:
        return CheckResult.healthy(
            "deployment.release_identity",
            authority_identity=resolved_expected,
            expected={
                "release_sha": resolved_expected,
                "frontend_branch": resolved_branch,
                "frontend_environment": resolved_environment,
            },
            observed=observed,
            checked_at=context.now,
        )

    return _failure(
        context,
        code=code,
        expected_sha=resolved_expected,
        expected_branch=resolved_branch,
        expected_environment=resolved_environment,
        observed=observed,
        evidence=evidence,
    )
