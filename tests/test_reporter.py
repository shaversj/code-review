from code_review_app.review.models import Finding
from code_review_app.review.reporter import GitHubReporter


class FakeGitHubClient:
    def __init__(self, head_sha: str) -> None:
        self.head_sha = head_sha
        self.comments: list[dict] = []

    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        return self.head_sha

    def create_review_comment(
        self, repo_full_name: str, pr_number: int, head_sha: str, finding: Finding
    ) -> str:
        self.comments.append(
            {
                "repo": repo_full_name,
                "pr": pr_number,
                "head_sha": head_sha,
                "title": finding.title,
            }
        )
        return "comment-1"


def finding() -> Finding:
    return Finding(
        file_path="app.py",
        line=3,
        severity="medium",
        title="Issue",
        behavior_at_risk="Risk",
        evidence="Evidence",
        suggested_action="Fix it",
        confidence=0.8,
    )


def test_reporter_posts_when_head_sha_matches() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "head", [finding()])

    assert posted == ["comment-1"]
    assert client.comments[0]["title"] == "Issue"


def test_reporter_skips_when_head_sha_is_stale() -> None:
    client = FakeGitHubClient("new-head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "old-head", [finding()])

    assert posted == []
    assert client.comments == []
