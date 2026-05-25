from __future__ import annotations

from code_review_app.review.models import CheckResult, Finding, Lead, ReviewPipelineResult, Workspace


MAX_EVIDENCE_LINES = 3


class DeterministicReviewPipeline:
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        leads: list[Lead] = []
        findings: list[Finding] = []
        for check in checks:
            if check.exit_code == 0 and not check.timed_out:
                continue
            leads.append(
                Lead(
                    file_path=".",
                    line=1,
                    suspicion=f"Configured check {check.name} did not pass.",
                    related_rule_ids=["CHECK_FAILURE"],
                    suggested_context=check.output_excerpt,
                    status="verified",
                )
            )
            findings.append(
                Finding(
                    file_path=".",
                    line=1,
                    severity="medium",
                    title=f"Configured check failed: {check.name}",
                    behavior_at_risk="The PR does not satisfy a configured repository check.",
                    evidence=self._check_evidence(check),
                    suggested_action=(
                        "Inspect the failing check output and update the PR or check configuration."
                    ),
                    confidence=0.9,
                )
            )
        return ReviewPipelineResult(leads=leads, findings=findings)

    @staticmethod
    def _check_evidence(check: CheckResult) -> str:
        lines = [line.strip() for line in check.output_excerpt.splitlines() if line.strip()]
        selected = lines[:MAX_EVIDENCE_LINES]
        output_summary = "\n".join(f"- {line}" for line in selected) or "- No output captured."
        hidden_count = max(len(lines) - len(selected), 0)
        extra = f"\n- ... {hidden_count} more line(s) omitted." if hidden_count else ""
        return (
            f"Command `{check.command}` exited with {check.exit_code}. "
            f"Showing {len(selected)} of {len(lines)} output lines:\n"
            f"{output_summary}{extra}\n"
            "Full check output is stored in SQLite."
        )


class AnthropicReviewPipeline:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        return self.gateway.review(workspace, checks)
