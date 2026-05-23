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


def test_aws_endpoint_url_can_target_localstack() -> None:
    settings = Settings(
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        aws_endpoint_url="http://localhost.localstack.cloud:4566",
        sqs_queue_url="http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/code-review-jobs",
    )

    assert settings.aws_endpoint_url == "http://localhost.localstack.cloud:4566"
