from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    path: Path
    base_sha: str
    head_sha: str
    diff: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: str
    command: str
    exit_code: int
    timed_out: bool
    duration_ms: int
    output_excerpt: str
