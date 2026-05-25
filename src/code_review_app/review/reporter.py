from __future__ import annotations

import logging
from typing import Protocol

from code_review_app.github.client import GitHubClientProtocol, ReviewCommentPlacementError
from code_review_app.review.diff import DiffIndex
from code_review_app.review.models import Finding


logger = logging.getLogger(__name__)


class DuplicateStore(Protocol):
    def has_posted_finding(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        file_path: str,
        line: int,
        title: str,
    ) -> bool:
        raise NotImplementedError


class GitHubReporter:
    def __init__(
        self,
        github_client: GitHubClientProtocol,
        duplicate_store: DuplicateStore | None = None,
    ) -> None:
        self.github_client = github_client
        self.duplicate_store = duplicate_store

    def post_findings(
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        findings: list[Finding],
        inline_locations: DiffIndex | None = None,
    ) -> list[str]:
        current_head_sha = self.github_client.get_pull_request_head_sha(repo_full_name, pr_number)
        if current_head_sha != expected_head_sha:
            return []

        posted_ids: list[str] = []
        summary_findings: list[Finding] = []
        for finding in findings:
            if finding.confidence < 0.75:
                continue
            if self._is_duplicate(repo_full_name, pr_number, expected_head_sha, finding):
                continue
            if not self._is_inline_placeable(finding, inline_locations):
                summary_findings.append(finding)
                continue
            try:
                posted_ids.append(
                    self.github_client.create_review_comment(
                        repo_full_name,
                        pr_number,
                        expected_head_sha,
                        finding,
                    )
                )
            except ReviewCommentPlacementError:
                logger.info(
                    "falling back to summary review after inline placement rejection "
                    "repo=%s pr=%s path=%s line=%s",
                    repo_full_name,
                    pr_number,
                    finding.file_path,
                    finding.line,
                )
                summary_findings.append(finding)
        if summary_findings:
            posted_ids.append(
                self.github_client.create_pull_request_review(
                    repo_full_name,
                    pr_number,
                    expected_head_sha,
                    self._summary_body(summary_findings),
                )
            )
        return posted_ids

    def _is_duplicate(
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        finding: Finding,
    ) -> bool:
        if self.duplicate_store is None:
            return False
        return self.duplicate_store.has_posted_finding(
            repo_full_name,
            pr_number,
            expected_head_sha,
            finding.file_path,
            finding.line,
            finding.title,
        )

    @staticmethod
    def _is_inline_placeable(
        finding: Finding, inline_locations: DiffIndex | None = None
    ) -> bool:
        if finding.file_path in {"", "."} or finding.line <= 0:
            return False
        if inline_locations is None:
            return True
        return inline_locations.has_added_line(finding.file_path, finding.line)

    @staticmethod
    def _summary_body(findings: list[Finding]) -> str:
        lines = ["Review findings could not be placed inline:"]
        for finding in findings:
            lines.extend(
                [
                    "",
                    f"- **{finding.severity.upper()}: {finding.title}**",
                    f"  - Risk: {finding.behavior_at_risk}",
                    f"  - Evidence: {finding.evidence}",
                    f"  - Suggested action: {finding.suggested_action}",
                ]
            )
        return "\n".join(lines)
