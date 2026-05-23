from pathlib import Path

from code_review_app.config import Settings


def test_allowed_repos_are_parsed_from_csv() -> None:
    settings = Settings(
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/a, owner/b",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )

    assert settings.allowed_repo_set == {"owner/a", "owner/b"}


def test_sandbox_root_defaults_to_relative_path() -> None:
    settings = Settings(
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )

    assert settings.sandbox_root == Path(".sandboxes")
