"""Detection-only runtime provenance checks for the production scraper VM."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from backend.sentinel.models import CheckResult, Severity
from backend.sentinel.registry import CheckContext


_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _normalize_path(value: Any) -> str:
    path = str(value or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def _validate_allowed_path(value: Any) -> str:
    path = _normalize_path(value)
    if not path or path in {".", "/"} or ".." in path.split("/"):
        raise ValueError("overlay allowed paths must be explicit repository-relative paths")
    return path


def load_vm_overlay_manifest(path: str) -> Dict[str, Any]:
    raw_path = str(path or "").strip()
    if not raw_path:
        raise ValueError("VM overlay manifest path is required")
    manifest_path = Path(raw_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("VM overlay manifest must be a JSON object")
    if int(payload.get("schemaVersion") or 0) != 1:
        raise ValueError("VM overlay manifest schemaVersion must equal 1")
    approved = str(payload.get("approvedMainSha") or "").strip().lower()
    if not _FULL_SHA_RE.fullmatch(approved):
        raise ValueError("VM overlay approvedMainSha must be a full 40-character git SHA")
    expected_branch = str(payload.get("expectedBranch") or "main").strip() or "main"
    raw_allowed = payload.get("allowedPaths")
    if not isinstance(raw_allowed, list):
        raise ValueError("VM overlay allowedPaths must be a JSON array")
    allowed = tuple(sorted(set(_validate_allowed_path(item) for item in raw_allowed)))
    return {
        "schemaVersion": 1,
        "expectedBranch": expected_branch,
        "approvedMainSha": approved,
        "allowedPaths": allowed,
    }


def _default_git_runner(repo_path: str, args: Sequence[str]) -> Tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", repo_path, *list(args)],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    return int(result.returncode), str(result.stdout or ""), str(result.stderr or "")


def _git(
    repo_path: str,
    args: Sequence[str],
    *,
    git_runner: Optional[Callable[[str, Sequence[str]], Tuple[int, str, str]]] = None,
) -> Tuple[int, str, str]:
    runner = git_runner or _default_git_runner
    return runner(repo_path, args)


def _lines(value: str) -> Tuple[str, ...]:
    return tuple(line.strip() for line in str(value or "").splitlines() if line.strip())


def _status_paths(status_text: str) -> Tuple[str, ...]:
    paths = []
    for raw in str(status_text or "").splitlines():
        if not raw.strip():
            continue
        body = raw[3:] if len(raw) >= 3 else raw
        if " -> " in body:
            body = body.split(" -> ", 1)[1]
        path = _normalize_path(body.strip().strip('"'))
        if path:
            paths.append(path)
    return tuple(sorted(set(paths)))


def _path_allowed(path: str, allowed_paths: Iterable[str]) -> bool:
    normalized = _normalize_path(path)
    for allowed in allowed_paths:
        candidate = _normalize_path(allowed)
        if candidate.endswith("/"):
            if normalized.startswith(candidate):
                return True
        elif normalized == candidate:
            return True
    return False


def _failure(
    context: CheckContext,
    *,
    code: str,
    authority: str,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    evidence: Optional[Mapping[str, Any]] = None,
) -> CheckResult:
    return CheckResult.failure(
        "runtime.vm_provenance",
        failure_code=code,
        severity=Severity.CRITICAL,
        authority_identity=authority,
        expected=dict(expected),
        observed=dict(observed),
        evidence=dict(evidence or {}),
        checked_at=context.now,
    )


def check_vm_runtime_provenance(
    context: CheckContext,
    *,
    repo_path: str,
    manifest_path: str,
    git_runner: Optional[Callable[[str, Sequence[str]], Tuple[int, str, str]]] = None,
    manifest_loader: Callable[[str], Dict[str, Any]] = load_vm_overlay_manifest,
) -> CheckResult:
    """Verify production VM = approved main release + approved VM-only overlay.

    Raw SHA equality is deliberately NOT required. Local commits/worktree changes
    are permitted only when every changed path is explicitly approved by the
    overlay manifest.
    """
    resolved_repo = str(repo_path or "").strip()
    if not resolved_repo:
        raise ValueError("runtime repository path is required")
    manifest = manifest_loader(manifest_path)
    approved = str(manifest["approvedMainSha"])
    expected_branch = str(manifest["expectedBranch"])
    allowed_paths = tuple(manifest["allowedPaths"])
    expected = {
        "branch": expected_branch,
        "approved_main_sha": approved,
        "overlay_only": True,
        "allowed_path_count": len(allowed_paths),
    }

    commands = {
        "branch": ["branch", "--show-current"],
        "head": ["rev-parse", "HEAD"],
        "ancestor": ["merge-base", "--is-ancestor", approved, "HEAD"],
        "committed": ["diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{approved}..HEAD"],
        "status": ["status", "--porcelain=v1", "-uall"],
    }
    results = {}
    for key, args in commands.items():
        try:
            results[key] = _git(resolved_repo, args, git_runner=git_runner)
        except Exception as exc:
            return _failure(
                context,
                code="runtime_git_execution_failed",
                authority=approved,
                expected=expected,
                observed={"stage": key},
                evidence={"exception_type": exc.__class__.__name__},
            )

    for key in ("branch", "head", "committed", "status"):
        rc, _stdout, stderr = results[key]
        if rc != 0:
            return _failure(
                context,
                code="runtime_git_contract_unavailable",
                authority=approved,
                expected=expected,
                observed={"stage": key, "returncode": rc},
                evidence={"stderr_present": bool(str(stderr or "").strip())},
            )

    branch = str(results["branch"][1] or "").strip()
    head = str(results["head"][1] or "").strip().lower()
    if not _FULL_SHA_RE.fullmatch(head):
        return _failure(
            context,
            code="runtime_head_sha_invalid",
            authority=approved,
            expected=expected,
            observed={"head_sha": head},
        )
    committed_paths = tuple(_normalize_path(path) for path in _lines(results["committed"][1]))
    worktree_paths = _status_paths(results["status"][1])
    overlay_paths = tuple(sorted(set((*committed_paths, *worktree_paths))))
    unapproved = tuple(path for path in overlay_paths if not _path_allowed(path, allowed_paths))
    ancestor_ok = results["ancestor"][0] == 0

    observed = {
        "branch": branch,
        "head_sha": head,
        "approved_main_is_ancestor": ancestor_ok,
        "committed_overlay_paths": list(committed_paths),
        "worktree_overlay_paths": list(worktree_paths),
        "unapproved_paths": list(unapproved),
    }

    if branch != expected_branch:
        code = "runtime_branch_mismatch"
    elif not ancestor_ok:
        code = "runtime_approved_release_not_ancestor"
    elif unapproved:
        code = "runtime_overlay_unapproved_drift"
    else:
        return CheckResult.healthy(
            "runtime.vm_provenance",
            authority_identity=approved,
            expected=expected,
            observed=observed,
            checked_at=context.now,
        )

    return _failure(
        context,
        code=code,
        authority=approved,
        expected=expected,
        observed=observed,
    )
