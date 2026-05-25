from code_review_app.github.client import ReviewCommentPlacementError
from code_review_app.review.diff import DiffIndex
from code_review_app.review.models import Finding
from code_review_app.review.reporter import BOT_REVIEW_MARKER, GitHubReporter


class FakeGitHubClient:
    def __init__(
        self,
        head_sha: str,
        rejected_inline_titles: set[str] | None = None,
        existing_bot_review: bool = False,
    ) -> None:
        self.head_sha = head_sha
        self.rejected_inline_titles = rejected_inline_titles or set()
        self.existing_bot_review = existing_bot_review
        self.comments: list[dict] = []
        self.summary_comments: list[dict] = []

    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        return self.head_sha

    def create_review_comment(
        self, repo_full_name: str, pr_number: int, head_sha: str, finding: Finding
    ) -> str:
        if finding.title in self.rejected_inline_titles:
            raise ReviewCommentPlacementError("validation failed")
        self.comments.append(
            {
                "repo": repo_full_name,
                "pr": pr_number,
                "head_sha": head_sha,
                "title": finding.title,
            }
        )
        return f"comment-{len(self.comments)}"

    def create_pull_request_review(
        self, repo_full_name: str, pr_number: int, head_sha: str, body: str
    ) -> str:
        self.summary_comments.append(
            {"repo": repo_full_name, "pr": pr_number, "head_sha": head_sha, "body": body}
        )
        return "summary-1"

    def has_existing_bot_review(self, repo_full_name: str, pr_number: int, head_sha: str) -> bool:
        return self.existing_bot_review


class FakeDuplicateStore:
    def __init__(self, duplicate: bool) -> None:
        self.duplicate = duplicate

    def has_posted_finding(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        file_path: str,
        line: int,
        title: str,
    ) -> bool:
        return self.duplicate


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


def non_inline_finding(title: str) -> Finding:
    item = finding()
    return type(item)(
        file_path=".",
        line=1,
        severity=item.severity,
        title=title,
        behavior_at_risk=item.behavior_at_risk,
        evidence=item.evidence,
        suggested_action=item.suggested_action,
        confidence=item.confidence,
    )


def inline_finding(title: str) -> Finding:
    item = finding()
    return type(item)(
        file_path=item.file_path,
        line=item.line,
        severity=item.severity,
        title=title,
        behavior_at_risk=item.behavior_at_risk,
        evidence=item.evidence,
        suggested_action=item.suggested_action,
        confidence=item.confidence,
    )


def inline_finding_at(title: str, line: int) -> Finding:
    item = inline_finding(title)
    return type(item)(
        file_path=item.file_path,
        line=line,
        severity=item.severity,
        title=item.title,
        behavior_at_risk=item.behavior_at_risk,
        evidence=item.evidence,
        suggested_action=item.suggested_action,
        confidence=item.confidence,
    )


def test_reporter_posts_when_head_sha_matches() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "head", [finding()])

    assert posted == ["comment-1"]
    assert client.comments[0]["title"] == "Issue"


def test_reporter_skips_when_bot_review_already_exists_for_head() -> None:
    client = FakeGitHubClient("head", existing_bot_review=True)
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "head", [finding()])

    assert posted == []
    assert client.comments == []
    assert client.summary_comments == []


def test_reporter_skips_when_head_sha_is_stale() -> None:
    client = FakeGitHubClient("new-head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "old-head", [finding()])

    assert posted == []
    assert client.comments == []


def test_reporter_skips_duplicate_findings() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client, duplicate_store=FakeDuplicateStore(duplicate=True))

    posted = reporter.post_findings("owner/repo", 5, "head", [finding()])

    assert posted == []
    assert client.comments == []


def test_reporter_posts_summary_when_inline_location_is_not_placeable() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)
    item = non_inline_finding("Issue")

    posted = reporter.post_findings("owner/repo", 5, "head", [item])

    assert posted == ["summary-1"]
    assert client.comments == []
    assert client.summary_comments[0]["head_sha"] == "head"
    assert "Issue" in client.summary_comments[0]["body"]
    assert BOT_REVIEW_MARKER in client.summary_comments[0]["body"]


def test_reporter_groups_multiple_non_inline_findings_into_one_summary() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings(
        "owner/repo",
        5,
        "head",
        [non_inline_finding("First issue"), non_inline_finding("Second issue")],
    )

    assert posted == ["summary-1"]
    assert len(client.summary_comments) == 1
    body = client.summary_comments[0]["body"]
    assert "First issue" in body
    assert "Second issue" in body


def test_reporter_falls_back_to_summary_when_github_rejects_inline_location() -> None:
    client = FakeGitHubClient("head", rejected_inline_titles={"Rejected inline"})
    reporter = GitHubReporter(client)

    posted = reporter.post_findings(
        "owner/repo",
        5,
        "head",
        [inline_finding("Accepted inline"), inline_finding("Rejected inline")],
    )

    assert posted == ["comment-1", "summary-1"]
    assert [comment["title"] for comment in client.comments] == ["Accepted inline"]
    assert len(client.summary_comments) == 1
    assert "Rejected inline" in client.summary_comments[0]["body"]


def test_reporter_only_posts_inline_when_location_is_added_in_diff() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)
    diff_index = DiffIndex.from_unified_diff(
        """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 line one
+line two
"""
    )

    posted = reporter.post_findings(
        "owner/repo",
        5,
        "head",
        [
            inline_finding_at("Context line", 1),
            inline_finding_at("Added line", 2),
            inline_finding_at("Outside diff", 20),
        ],
        inline_locations=diff_index,
    )

    assert posted == ["comment-1", "summary-1"]
    assert [comment["title"] for comment in client.comments] == ["Added line"]
    assert "Context line" in client.summary_comments[0]["body"]
    assert "Outside diff" in client.summary_comments[0]["body"]
