from pathlib import Path
from subprocess import CompletedProcess

import pytest

from backend.services.pokemon_onboarding_git_service import GitAdapter, GitSafetyError, GitSettings


def test_dirty_production_checkout_is_refused(tmp_path):
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args, 0, stdout=" M production.py\n", stderr="")
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr", worktree_dir=tmp_path / "wt"), runner)
    with pytest.raises(GitSafetyError, match="dirty"):
        adapter.prepare_worktree("futureSet")
    assert calls == [["git", "status", "--porcelain"]]


def test_disabled_mode_performs_no_git_actions(tmp_path):
    adapter = GitAdapter(
        tmp_path, GitSettings(mode="disabled"),
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("git invoked")),
    )
    with pytest.raises(GitSafetyError, match="disabled"):
        adapter.prepare_worktree("futureSet")


def _scripted_runner(script_map, calls):
    """Dispatch a fake CompletedProcess by matching the leading tokens of each command."""
    def runner(args, **kwargs):
        calls.append(args)
        for prefix, make_result in script_map:
            if list(args[:len(prefix)]) == list(prefix):
                return make_result(args)
        raise AssertionError(f"unscripted command: {args}")
    return runner


def test_prepare_worktree_reuses_existing_worktree_on_matching_branch(tmp_path, monkeypatch):
    worktree_dir = tmp_path / "wt"
    existing = worktree_dir / "futureSet-source"
    existing.mkdir(parents=True)
    calls = []
    script = [
        (["git", "status", "--porcelain"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "fetch"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "rev-parse", "--abbrev-ref", "HEAD"],
         lambda a: CompletedProcess(a, 0, stdout="automation/onboard-pokemon-futureSet\n", stderr="")),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr", worktree_dir=worktree_dir), _scripted_runner(script, calls))
    worktree, branch = adapter.prepare_worktree("futureSet")
    assert worktree == existing
    assert branch == "automation/onboard-pokemon-futureSet"
    assert ["git", "worktree", "add"] not in [c[:3] for c in calls]


def test_prepare_worktree_refuses_existing_worktree_on_wrong_branch(tmp_path):
    worktree_dir = tmp_path / "wt"
    (worktree_dir / "futureSet-source").mkdir(parents=True)
    calls = []
    script = [
        (["git", "status", "--porcelain"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "fetch"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "rev-parse", "--abbrev-ref", "HEAD"],
         lambda a: CompletedProcess(a, 0, stdout="some-unrelated-branch\n", stderr="")),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr", worktree_dir=worktree_dir), _scripted_runner(script, calls))
    with pytest.raises(GitSafetyError, match="expected"):
        adapter.prepare_worktree("futureSet")


def test_commit_expected_files_is_idempotent_when_already_committed(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    config_path = worktree / "config.py"
    calls = []
    script = [
        (["git", "status", "--porcelain"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "diff-tree"], lambda a: CompletedProcess(a, 0, stdout="config.py\n", stderr="")),
        (["git", "rev-parse", "HEAD"], lambda a: CompletedProcess(a, 0, stdout="deadbeef\n", stderr="")),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr"), _scripted_runner(script, calls))
    sha = adapter.commit_expected_files(worktree, [config_path], "Onboard futureSet")
    assert sha == "deadbeef"
    assert ["git", "commit"] not in [c[:2] for c in calls]
    assert ["git", "add"] not in [c[:2] for c in calls]


def test_commit_expected_files_raises_when_clean_but_head_does_not_match(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    config_path = worktree / "config.py"
    calls = []
    script = [
        (["git", "status", "--porcelain"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "diff-tree"], lambda a: CompletedProcess(a, 0, stdout="unrelated.py\n", stderr="")),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr"), _scripted_runner(script, calls))
    with pytest.raises(GitSafetyError, match="no pending changes"):
        adapter.commit_expected_files(worktree, [config_path], "Onboard futureSet")


def test_commit_expected_files_still_commits_when_changes_are_pending(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    config_path = worktree / "config.py"
    calls = []
    script = [
        (["git", "status", "--porcelain"], lambda a: CompletedProcess(a, 0, stdout="A  config.py\n", stderr="")),
        (["git", "add"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "commit"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["git", "rev-parse", "HEAD"], lambda a: CompletedProcess(a, 0, stdout="cafef00d\n", stderr="")),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr"), _scripted_runner(script, calls))
    sha = adapter.commit_expected_files(worktree, [config_path], "Onboard futureSet")
    assert sha == "cafef00d"
    assert ["git", "commit"] in [c[:2] for c in calls]


def test_push_and_open_pr_reuses_existing_open_pr(tmp_path):
    calls = []
    script = [
        (["git", "push"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["gh", "pr", "list"], lambda a: CompletedProcess(
            a, 0, stdout='[{"url": "https://github.com/example/repo/pull/9", "number": 9}]', stderr="",
        )),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr"), _scripted_runner(script, calls))
    result = adapter.push_and_open_pr(tmp_path, "automation/onboard-pokemon-futureSet", "Onboard futureSet")
    assert result == {
        "status": "source_pr_open", "source_pr_url": "https://github.com/example/repo/pull/9",
        "source_pr_number": 9,
    }
    assert ["gh", "pr", "create"] not in [c[:3] for c in calls]


def test_reconcile_does_not_remerge_an_already_merged_pr(tmp_path):
    calls = []
    script = [
        (["gh", "pr", "view"], lambda a: CompletedProcess(
            a, 0, stdout='{"state": "MERGED", "mergedAt": "2026-09-01T00:00:00Z", "url": "u"}', stderr="",
        )),
    ]
    adapter = GitAdapter(
        tmp_path, GitSettings(mode="pr", auto_merge=True, auto_deploy=False),
        _scripted_runner(script, calls),
    )
    result = adapter.reconcile_pr_and_optional_deploy("https://github.com/example/repo/pull/1")
    assert result["status"] == "awaiting_source_deploy"
    assert ["gh", "pr", "merge"] not in [c[:3] for c in calls]


def test_reconcile_merged_not_deployed_stays_pending_without_auto_deploy(tmp_path):
    calls = []
    script = [
        (["gh", "pr", "view"], lambda a: CompletedProcess(
            a, 0, stdout='{"state": "MERGED", "mergedAt": "2026-09-01T00:00:00Z", "url": "u"}', stderr="",
        )),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr", auto_deploy=False), _scripted_runner(script, calls))
    result = adapter.reconcile_pr_and_optional_deploy("https://github.com/example/repo/pull/1")
    assert result["status"] == "awaiting_source_deploy"
    assert not any(c[:2] == ["git", "pull"] for c in calls)


def test_push_and_open_pr_creates_pr_when_none_exists(tmp_path):
    calls = []
    script = [
        (["git", "push"], lambda a: CompletedProcess(a, 0, stdout="", stderr="")),
        (["gh", "pr", "list"], lambda a: CompletedProcess(a, 0, stdout="[]", stderr="")),
        (["gh", "pr", "create"], lambda a: CompletedProcess(
            a, 0, stdout="https://github.com/example/repo/pull/10\n", stderr="",
        )),
    ]
    adapter = GitAdapter(tmp_path, GitSettings(mode="pr"), _scripted_runner(script, calls))
    result = adapter.push_and_open_pr(tmp_path, "automation/onboard-pokemon-futureSet", "Onboard futureSet")
    assert result == {
        "status": "source_pr_open", "source_pr_url": "https://github.com/example/repo/pull/10",
        "source_pr_number": 10,
    }
