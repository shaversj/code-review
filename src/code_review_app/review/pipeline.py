from __future__ import annotations

from code_review_app.review.models import CheckResult, Finding, Lead, ReviewPipelineResult, Workspace


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
                    evidence=(
                        f"Command `{check.command}` exited with {check.exit_code}. "
                        f"Output excerpt: {check.output_excerpt}"
                    ),
                    suggested_action=(
                        "Inspect the failing check output and update the PR or check configuration."
                    ),
                    confidence=0.9,
                )
            )
        return ReviewPipelineResult(leads=leads, findings=findings)


class AnthropicReviewPipeline:
    def __init__(self, gateway) -> None:
        self.gateway = gateway

    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        return self.gateway.review(workspace, checks)
