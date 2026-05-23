from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from code_review_app.review.models import Workspace


class CommandRunner(Protocol):
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        raise NotImplementedError


class SubprocessRunner:
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        completed = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout_seconds,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return completed.stdout


class CheckoutManager:
    def __init__(self, sandbox_root: Path, runner: CommandRunner | None = None) -> None:
        self.sandbox_root = sandbox_root
        self.runner = runner or SubprocessRunner()

    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        workspace_path = self.sandbox_root / f"run-{review_run_id}"
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        self.runner.run(
            ["git", "clone", "--no-tags", repo_url, str(workspace_path)], timeout_seconds=600
        )
        self.runner.run(
            ["git", "fetch", "origin", base_sha, head_sha],
            cwd=workspace_path,
            timeout_seconds=300,
        )
        self.runner.run(["git", "checkout", head_sha], cwd=workspace_path, timeout_seconds=300)
        diff = self.runner.run(
            ["git", "diff", "--unified=80", f"{base_sha}...{head_sha}"],
            cwd=workspace_path,
            timeout_seconds=300,
        )
        return Workspace(path=workspace_path, base_sha=base_sha, head_sha=head_sha, diff=diff)
