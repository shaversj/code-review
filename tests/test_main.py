from pathlib import Path

from fastapi.testclient import TestClient

from code_review_app.config import Settings
from code_review_app.main import create_app
from code_review_app.review.models import ModelUsage
from code_review_app.storage import Storage


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


def test_create_app_exposes_review_run_detail(tmp_path: Path) -> None:
    database_path = tmp_path / "review.db"
    settings = Settings(
        database_path=database_path,
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )
    storage = Storage(database_path)
    storage.initialize()
    run = storage.create_review_run("owner/repo", 12, "base", "head", 99)
    storage.save_model_usage(
        run["id"],
        ModelUsage(
            provider="anthropic-compatible",
            model="MiniMax-M2.7",
            base_url="https://api.minimax.io/anthropic",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.001,
        ),
    )

    client = TestClient(create_app(settings))
    response = client.get(f"/review-runs/{run['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_run"]["repo_full_name"] == "owner/repo"
    assert payload["artifacts"]["model_runs"][0]["model"] == "MiniMax-M2.7"


def test_create_app_returns_404_for_missing_review_run(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=Path("key.pem"),
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )

    client = TestClient(create_app(settings))

    assert client.get("/review-runs/999").status_code == 404
