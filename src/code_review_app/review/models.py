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


@dataclass(frozen=True)
class Lead:
    file_path: str
    line: int
    suspicion: str
    related_rule_ids: list[str]
    suggested_context: str
    status: str = "open"


@dataclass(frozen=True)
class Finding:
    file_path: str
    line: int
    severity: str
    title: str
    behavior_at_risk: str
    evidence: str
    suggested_action: str
    confidence: float
    category: str = "correctness"


@dataclass(frozen=True)
class ModelUsage:
    provider: str
    model: str
    base_url: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True)
class ReviewPipelineResult:
    leads: list[Lead]
    findings: list[Finding]
    model_usage: ModelUsage | None = None
