import json
from datetime import datetime, timezone

import pytest

from backend.sentinel.checks.runtime_provenance import (
    check_vm_runtime_provenance,
    load_vm_overlay_manifest,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity
from backend.sentinel.registry import CheckContext


NOW = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)
CTX = CheckContext(
    now=NOW,
    runner_identity=RunnerIdentity(component="sentinel_vm", host="vm", build_sha="runner"),
)
APPROVED = "a" * 40
HEAD = "b" * 40


def write_manifest(tmp_path, **overrides):
    payload = {
        "schemaVersion": 1,
        "expectedBranch": "main",
        "approvedMainSha": APPROVED,
        "allowedPaths": [
            "backend/constants/tcg/pokemon/vm-runtime.json",
            "backend/constants/tcg/pokemon/vm-only/",
        ],
    }
    payload.update(overrides)
    path = tmp_path / "vm-overlay.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def runner_for(*, branch="main", ancestor_rc=0, committed="", status=""):
    def run(_repo, args):
        key = tuple(args)
        if key == ("branch", "--show-current"):
            return 0, branch + "\n", ""
        if key == ("rev-parse", "HEAD"):
            return 0, HEAD + "\n", ""
        if key[:2] == ("merge-base", "--is-ancestor"):
            return ancestor_rc, "", ""
        if key[:3] == ("diff", "--name-only", "--diff-filter=ACDMRTUXB"):
            return 0, committed, ""
        if key == ("status", "--porcelain=v1", "-uall"):
            return 0, status, ""
        raise AssertionError(key)

    return run


def check(tmp_path, **runner_kwargs):
    return check_vm_runtime_provenance(
        CTX,
        repo_path="/repo",
        manifest_path=write_manifest(tmp_path),
        git_runner=runner_for(**runner_kwargs),
    )


def test_main_based_runtime_with_only_approved_overlay_is_healthy(tmp_path):
    result = check(
        tmp_path,
        committed="backend/constants/tcg/pokemon/vm-runtime.json\n",
        status=" M backend/constants/tcg/pokemon/vm-only/state.json\n",
    )
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["branch"] == "main"
    assert result.observed["approved_main_is_ancestor"] is True
    assert result.observed["unapproved_paths"] == []


def test_runtime_does_not_require_raw_head_equality_to_approved_main(tmp_path):
    result = check(tmp_path)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["head_sha"] == HEAD
    assert HEAD != APPROVED


def test_wrong_branch_fails_even_when_overlay_paths_are_approved(tmp_path):
    result = check(tmp_path, branch="develop")
    assert result.failure_code == "runtime_branch_mismatch"


def test_approved_release_must_be_ancestor_of_vm_head(tmp_path):
    result = check(tmp_path, ancestor_rc=1)
    assert result.failure_code == "runtime_approved_release_not_ancestor"


def test_unapproved_committed_or_worktree_path_fails(tmp_path):
    committed = check(tmp_path, committed="backend/secret-new-runtime-file.py\n")
    assert committed.failure_code == "runtime_overlay_unapproved_drift"
    assert committed.observed["unapproved_paths"] == ["backend/secret-new-runtime-file.py"]

    dirty = check(tmp_path, status="?? unexpected.txt\n")
    assert dirty.failure_code == "runtime_overlay_unapproved_drift"
    assert dirty.observed["unapproved_paths"] == ["unexpected.txt"]


def test_manifest_rejects_non_full_sha_and_parent_traversal(tmp_path):
    bad_sha = write_manifest(tmp_path, approvedMainSha="abc1234")
    with pytest.raises(ValueError, match="40-character"):
        load_vm_overlay_manifest(bad_sha)

    bad_path = write_manifest(tmp_path, allowedPaths=["../outside"])
    with pytest.raises(ValueError, match="repository-relative"):
        load_vm_overlay_manifest(bad_path)


def test_git_exception_is_structured_without_error_message(tmp_path):
    def boom(_repo, _args):
        raise RuntimeError("secret-bearing-git-error")

    result = check_vm_runtime_provenance(
        CTX,
        repo_path="/repo",
        manifest_path=write_manifest(tmp_path),
        git_runner=boom,
    )
    assert result.failure_code == "runtime_git_execution_failed"
    assert result.evidence["exception_type"] == "RuntimeError"
    assert "secret-bearing-git-error" not in str(result.evidence)
