from __future__ import annotations

from typing import Protocol

import httpx

from code_review_app.review.models import Finding


class GitHubClientProtocol(Protocol):
    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        raise NotImplementedError

    def create_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        finding: Finding,
    ) -> str:
        raise NotImplementedError


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        response = httpx.get(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return str(response.json()["head"]["sha"])

    def create_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        finding: Finding,
    ) -> str:
        body = (
            f"**{finding.severity.upper()}: {finding.title}**\n\n"
            f"{finding.behavior_at_risk}\n\n"
            f"Evidence: {finding.evidence}\n\n"
            f"Suggested action: {finding.suggested_action}"
        )
        response = httpx.post(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/comments",
            headers=self._headers(),
            json={
                "body": body,
                "commit_id": head_sha,
                "path": finding.file_path,
                "line": finding.line,
                "side": "RIGHT",
            },
            timeout=20,
        )
        response.raise_for_status()
        return str(response.json()["id"])
