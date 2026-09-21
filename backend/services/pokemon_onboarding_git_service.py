from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


class GitSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitSettings:
    mode: str = "disabled"
    worktree_dir: Optional[Path] = None
    base_branch: str = "main"
    auto_merge: bool = False
    auto_deploy: bool = False

    @classmethod
    def from_env(cls) -> "GitSettings":
        path = os.getenv("POKEMON_ONBOARDING_WORKTREE_DIR")
        return cls(
            mode=os.getenv("POKEMON_ONBOARDING_GIT_MODE", "disabled"),
            worktree_dir=Path(path).resolve() if path else None,
            base_branch=os.getenv("POKEMON_ONBOARDING_BASE_BRANCH", "main"),
            auto_merge=os.getenv("POKEMON_ONBOARDING_AUTO_MERGE", "false").lower() == "true",
            auto_deploy=os.getenv("POKEMON_ONBOARDING_AUTO_DEPLOY", "false").lower() == "true",
        )


class GitAdapter:
    def __init__(
        self, production_checkout: Path, settings: GitSettings,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        self.production_checkout = production_checkout.resolve()
        self.settings = settings
        self.runner = runner

    def _run(self, args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return self.runner(
            list(args), cwd=str(cwd), capture_output=True, text=True, check=True,
        )

    def verify_clean(self, checkout: Optional[Path] = None) -> None:
        root = checkout or self.production_checkout
        result = self._run(["git", "status", "--porcelain"], root)
        if result.stdout.strip():
            raise GitSafetyError(f"checkout is dirty: {root}")

    def prepare_worktree(self, canonical_key: str, phase: str = "source") -> tuple[Path, str]:
        if self.settings.mode not in {"pr", "direct"}:
            raise GitSafetyError("Git source-write mode is disabled")
        if not self.settings.worktree_dir:
            raise GitSafetyError("POKEMON_ONBOARDING_WORKTREE_DIR is required")
        self.verify_clean(self.production_checkout)
        branch = (
            f"automation/onboard-pokemon-{canonical_key}"
            if phase == "source" else f"automation/{phase}-pokemon-{canonical_key}"
        )
        self._run(["git", "fetch", "origin", self.settings.base_branch], self.production_checkout)
        worktree = self.settings.worktree_dir / f"{canonical_key}-{phase}"
        if not worktree.exists():
            worktree.parent.mkdir(parents=True, exist_ok=True)
            self._run(
                ["git", "worktree", "add", "-b", branch, str(worktree),
                 f"origin/{self.settings.base_branch}"],
                self.production_checkout,
            )
        else:
            # Resuming into an existing worktree: confirm it is actually the branch
            # this canonical_key/phase maps to before reusing it, rather than silently
            # committing/pushing onto whatever happens to be checked out there.
            current = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], worktree).stdout.strip()
            if current != branch:
                raise GitSafetyError(
                    f"existing worktree {worktree} is on branch {current!r}, expected {branch!r}"
                )
        return worktree, branch

    def commit_expected_files(self, worktree: Path, paths: Sequence[Path], message: str) -> str:
        expected = sorted(str(path.relative_to(worktree)).replace("\\", "/") for path in paths)
        status = self._run(["git", "status", "--porcelain"], worktree).stdout.splitlines()
        actual = sorted(line[3:].replace("\\", "/") for line in status if len(line) >= 4)
        if not actual:
            # Nothing pending: either generation hasn't touched the worktree yet, or an
            # earlier interrupted attempt already committed exactly these files. Only
            # treat the latter as success -- verify HEAD's own changed files match
            # expected exactly before reusing it, so a resume never silently accepts an
            # unrelated commit that happens to leave the worktree clean.
            head_files = sorted(
                line for line in self._run(
                    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], worktree,
                ).stdout.splitlines() if line
            )
            if head_files == expected:
                return self._run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
            raise GitSafetyError(
                f"no pending changes to commit and HEAD does not match expected files; "
                f"expected={expected}, head_files={head_files}"
            )
        if actual != expected:
            raise GitSafetyError(f"unexpected worktree changes; expected={expected}, actual={actual}")
        self._run(["git", "add", "--", *expected], worktree)
        self._run(["git", "commit", "-m", message], worktree)
        return self._run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()

    def _find_existing_pr(self, branch: str, worktree: Path) -> Optional[dict]:
        try:
            result = self._run(
                ["gh", "pr", "list", "--head", branch, "--state", "open",
                 "--json", "url,number", "--limit", "1"],
                worktree,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        import json
        rows = json.loads(result.stdout or "[]")
        return rows[0] if rows else None

    def push_and_open_pr(self, worktree: Path, branch: str, title: str) -> dict:
        if self.settings.mode == "direct":
            # GitHub Actions may be allowed to write repository contents while the
            # repository-level "Actions may create PRs" switch remains disabled.
            # Keep the same isolated-worktree/exact-file safety, but fast-forward
            # the validated commit directly onto the configured base branch.
            # Never force: if main moved incompatibly, rebase/push fails and the
            # onboarding worker releases the job for a bounded retry.
            self._run(["git", "fetch", "origin", self.settings.base_branch], worktree)
            self._run(["git", "rebase", f"origin/{self.settings.base_branch}"], worktree)
            self._run(
                ["git", "push", "origin", f"HEAD:{self.settings.base_branch}"],
                worktree,
            )
            deployed_sha = self._run(["git", "rev-parse", "HEAD"], worktree).stdout.strip()
            if not self.settings.auto_deploy:
                return {
                    "status": "awaiting_source_deploy",
                    "source_commit_sha": deployed_sha,
                    "operator_action": (
                        f"Deploy {self.settings.base_branch}; validated onboarding source "
                        "has already been fast-forwarded to the remote branch."
                    ),
                }
            self.deploy_base_branch()
            return {"status": "deployed", "source_commit_sha": deployed_sha}

        self._run(["git", "push", "-u", "origin", branch], worktree)
        existing = self._find_existing_pr(branch, worktree)
        if existing:
            return {
                "status": "source_pr_open", "source_pr_url": existing["url"],
                "source_pr_number": existing.get("number"),
            }
        try:
            result = self._run(
                ["gh", "pr", "create", "--base", self.settings.base_branch,
                 "--head", branch, "--title", title, "--body", "Automated targeted Pokemon set onboarding."],
                worktree,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return {
                "status": "source_pr_pending",
                "operator_action": f"Push is complete. Open a PR from {branch} to {self.settings.base_branch}.",
                "error": str(exc),
            }
        url = result.stdout.strip()
        number = int(url.rstrip("/").split("/")[-1]) if url.rstrip("/").split("/")[-1].isdigit() else None
        return {"status": "source_pr_open", "source_pr_url": url, "source_pr_number": number}

    def reconcile_pr_and_optional_deploy(self, pr_url: str) -> dict:
        """Inspect/optionally merge a PR, then deploy only an already-merged PR."""
        try:
            state_result = self._run(
                ["gh", "pr", "view", pr_url, "--json", "state,mergedAt,url"], self.production_checkout,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            return {
                "status": "source_pr_pending",
                "operator_action": f"Inspect and merge {pr_url}, then deploy the configured base branch.",
                "error": str(exc),
            }
        import json
        state = json.loads(state_result.stdout)
        if not state.get("mergedAt") and self.settings.auto_merge:
            self._run(["gh", "pr", "merge", pr_url, "--merge"], self.production_checkout)
            state = json.loads(self._run(
                ["gh", "pr", "view", pr_url, "--json", "state,mergedAt,url"], self.production_checkout,
            ).stdout)
        if not state.get("mergedAt"):
            return {"status": "awaiting_source_merge", "source_pr_url": pr_url}
        if not self.settings.auto_deploy:
            return {
                "status": "awaiting_source_deploy", "source_pr_url": pr_url,
                "operator_action": (
                    f"Deploy {self.settings.base_branch} with git pull --ff-only after confirming "
                    "the production checkout is clean and critical jobs are idle."
                ),
            }
        self.deploy_base_branch()
        return {"status": "deployed", "source_pr_url": pr_url}

    def deploy_base_branch(self) -> None:
        self.verify_clean(self.production_checkout)
        probe = self.runner(
            ["pgrep", "-f", "run_next_scrape_job|run_all_v2_sets|build_pokemon.*snapshot"],
            cwd=str(self.production_checkout), capture_output=True, text=True, check=False,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            raise GitSafetyError("critical scrape/simulation/publication process is active")
        if probe.returncode not in (0, 1):
            raise GitSafetyError("could not verify critical process inactivity")
        self._run(["git", "fetch", "origin", self.settings.base_branch], self.production_checkout)
        self._run(
            ["git", "pull", "--ff-only", "origin", self.settings.base_branch],
            self.production_checkout,
        )
