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
