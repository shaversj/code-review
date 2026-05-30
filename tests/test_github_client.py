import httpx
import pytest

from code_review_app.github.client import GitHubClient, ReviewCommentPlacementError
from code_review_app.review.models import Finding


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


def test_create_review_comment_wraps_placement_validation_failure(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(
            422,
            request=httpx.Request("POST", "https://api.github.com/test"),
            json={"message": "Validation Failed"},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ReviewCommentPlacementError):
        GitHubClient("token").create_review_comment("owner/repo", 5, "head", finding())


def test_create_review_comment_renders_category_as_inline_section(monkeypatch) -> None:
    captured_payload = {}

    def fake_post(*args, **kwargs):
        captured_payload.update(kwargs["json"])
        return httpx.Response(
            201,
            request=httpx.Request("POST", "https://api.github.com/test"),
            json={"id": 123},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    item = finding()
    categorized = type(item)(
        file_path=item.file_path,
        line=item.line,
        severity="high",
        title=item.title,
        behavior_at_risk=item.behavior_at_risk,
        evidence=item.evidence,
        suggested_action=item.suggested_action,
        confidence=item.confidence,
        category="security",
    )

    comment_id = GitHubClient("token").create_review_comment(
        "owner/repo", 5, "head", categorized
    )

    assert comment_id == "123"
    assert captured_payload["body"].startswith("## Security\n\n**HIGH: Issue**")


def test_has_existing_bot_review_detects_marker_for_head(monkeypatch) -> None:
    def fake_get(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.github.com/test"),
            json=[
                {
                    "commit_id": "old-head",
                    "body": "<!-- code-review-bot -->\nOld",
                },
                {
                    "commit_id": "head",
                    "body": "<!-- code-review-bot -->\nCurrent",
                },
            ],
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    assert GitHubClient("token").has_existing_bot_review("owner/repo", 5, "head")
