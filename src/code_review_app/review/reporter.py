from __future__ import annotations

from code_review_app.github.client import GitHubClientProtocol
from code_review_app.review.models import Finding


class GitHubReporter:
    def __init__(self, github_client: GitHubClientProtocol) -> None:
        self.github_client = github_client

    def post_findings(
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        findings: list[Finding],
    ) -> list[str]:
        current_head_sha = self.github_client.get_pull_request_head_sha(repo_full_name, pr_number)
        if current_head_sha != expected_head_sha:
            return []

        posted_ids: list[str] = []
        for finding in findings:
            if finding.confidence < 0.75:
                continue
            posted_ids.append(
                self.github_client.create_review_comment(
                    repo_full_name,
                    pr_number,
                    expected_head_sha,
                    finding,
                )
            )
        return posted_ids
