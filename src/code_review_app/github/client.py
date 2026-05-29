from __future__ import annotations

from typing import Protocol

import httpx

from code_review_app.review.categories import category_label
from code_review_app.review.models import Finding


BOT_REVIEW_MARKER = "<!-- code-review-bot -->"


class ReviewCommentPlacementError(Exception):
    """Raised when GitHub rejects an inline PR review comment location."""


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

    def create_pull_request_review(
        self, repo_full_name: str, pr_number: int, head_sha: str, body: str
    ) -> str:
        raise NotImplementedError

    def has_existing_bot_review(self, repo_full_name: str, pr_number: int, head_sha: str) -> bool:
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
        label = category_label(finding.category)
        body = (
            f"## {label}\n\n"
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
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 422:
                raise ReviewCommentPlacementError("GitHub rejected inline comment placement") from exc
            raise
        return str(response.json()["id"])

    def create_pull_request_review(
        self, repo_full_name: str, pr_number: int, head_sha: str, body: str
    ) -> str:
        response = httpx.post(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/reviews",
            headers=self._headers(),
            json={"commit_id": head_sha, "body": body, "event": "COMMENT"},
            timeout=20,
        )
        response.raise_for_status()
        return str(response.json()["id"])

    def has_existing_bot_review(self, repo_full_name: str, pr_number: int, head_sha: str) -> bool:
        response = httpx.get(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/reviews",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        for review in response.json():
            if str(review.get("commit_id")) != head_sha:
                continue
            if BOT_REVIEW_MARKER in str(review.get("body") or ""):
                return True
        return False
