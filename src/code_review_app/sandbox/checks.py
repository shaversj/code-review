from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from code_review_app.review.models import CheckResult
from code_review_app.sandbox.checkout import CommandRunner, SubprocessRunner


@dataclass(frozen=True)
class CheckCommand:
    name: str
    kind: str
    command: list[str]
    timeout_seconds: int


@dataclass(frozen=True)
class ReviewConfig:
    checks: list[CheckCommand]


def load_review_config(repo_path: Path) -> ReviewConfig:
    path = repo_path / ".code-review.yml"
    if not path.exists():
        return ReviewConfig(checks=[])

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    checks: list[CheckCommand] = []
    check_groups = raw.get("review", {}).get("checks", {})
    for kind, entries in check_groups.items():
        for entry in entries or []:
            checks.append(
                CheckCommand(
                    name=str(entry["name"]),
                    kind=str(kind),
                    command=shlex.split(str(entry["command"])),
                    timeout_seconds=int(entry.get("timeout_seconds", 300)),
                )
            )
    return ReviewConfig(checks=checks)


class CheckRunner:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def run_checks(self, repo_path: Path, config: ReviewConfig) -> list[CheckResult]:
        results: list[CheckResult] = []
        for check in config.checks:
            started = time.monotonic()
            timed_out = False
            exit_code = 0
            try:
                output = self.runner.run(
                    check.command, cwd=repo_path, timeout_seconds=check.timeout_seconds
                )
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = 124
                output = str(exc)
            except subprocess.CalledProcessError as exc:
                exit_code = int(exc.returncode)
                output = str(exc.stdout or exc)
            except FileNotFoundError as exc:
                exit_code = 127
                missing = check.command[0] if check.command else str(exc)
                output = f"Command not found: {missing}"
            duration_ms = int((time.monotonic() - started) * 1000)
            results.append(
                CheckResult(
                    name=check.name,
                    kind=check.kind,
                    command=" ".join(check.command),
                    exit_code=exit_code,
                    timed_out=timed_out,
                    duration_ms=duration_ms,
                    output_excerpt=output[:4000],
                )
            )
        return results
