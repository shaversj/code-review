from pathlib import Path

from fastapi.testclient import TestClient

from code_review_app.config import Settings
from code_review_app.main import create_app


def test_create_app_exposes_health_endpoint(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )

    client = TestClient(create_app(settings))

    assert client.get("/healthz").json() == {"status": "ok"}
