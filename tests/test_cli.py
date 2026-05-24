from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from code_review_app.cli import build_review_pipeline, build_review_worker, process_message
from code_review_app.config import Settings
from code_review_app.review.pipeline import AnthropicReviewPipeline, DeterministicReviewPipeline
from code_review_app.storage import Storage


class FakeAuth:
    def __init__(self, app_id: int, private_key_path: Path) -> None:
        self.app_id = app_id
        self.private_key_path = private_key_path

    def create_installation_token(self, installation_id: int) -> SimpleNamespace:
        return SimpleNamespace(token=f"token-{installation_id}")

    def authenticated_clone_url(self, repo_full_name: str, token: str) -> str:
        return f"clone:{repo_full_name}:{token}"


class FakeQueue:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_message(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)


class FakeWorker:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.job: dict | None = None

    def handle_job(self, job: dict) -> None:
        self.job = job
        if self.should_fail:
            raise RuntimeError("worker failed")


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=tmp_path / "app.pem",
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
    )


def message() -> dict:
    return {
        "Body": json.dumps(
            {
                "review_run_id": 1,
                "repo_full_name": "owner/repo",
                "pr_number": 7,
                "base_sha": "base",
                "head_sha": "head",
                "installation_id": 42,
            }
        ),
        "ReceiptHandle": "receipt-1",
    }


def test_process_message_builds_worker_with_installation_token_and_deletes_after_success(
    tmp_path: Path,
) -> None:
    queue = FakeQueue()
    worker = FakeWorker()
    built: dict = {}

    def worker_factory(settings, github_token, repo_url_builder):
        built["settings"] = settings
        built["github_token"] = github_token
        built["repo_url"] = repo_url_builder({"repo_full_name": "owner/repo"})
        return worker

    process_message(
        message(),
        settings(tmp_path),
        queue,
        auth_factory=FakeAuth,
        worker_factory=worker_factory,
    )

    assert built["github_token"] == "token-42"
    assert built["repo_url"] == "clone:owner/repo:token-42"
    assert worker.job is not None
    assert queue.deleted == ["receipt-1"]


def test_process_message_leaves_message_for_redelivery_when_worker_fails(tmp_path: Path) -> None:
    queue = FakeQueue()

    def worker_factory(settings, github_token, repo_url_builder):
        return FakeWorker(should_fail=True)

    with pytest.raises(RuntimeError, match="worker failed"):
        process_message(
            message(),
            settings(tmp_path),
            queue,
            auth_factory=FakeAuth,
            worker_factory=worker_factory,
        )

    assert queue.deleted == []


def test_build_review_pipeline_defaults_to_deterministic(tmp_path: Path) -> None:
    assert isinstance(build_review_pipeline(settings(tmp_path)), DeterministicReviewPipeline)


def test_build_review_pipeline_can_use_anthropic(tmp_path: Path) -> None:
    class FakeGateway:
        def __init__(self, model: str, max_tokens: int) -> None:
            self.model = model
            self.max_tokens = max_tokens

    configured = Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=tmp_path / "app.pem",
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
        review_pipeline_provider="anthropic",
        anthropic_model="claude-test",
        anthropic_max_tokens=321,
    )

    pipeline = build_review_pipeline(configured, gateway_factory=FakeGateway)

    assert isinstance(pipeline, AnthropicReviewPipeline)
    assert pipeline.gateway.model == "claude-test"
    assert pipeline.gateway.max_tokens == 321


def test_build_review_worker_marks_stale_incomplete_runs(tmp_path: Path) -> None:
    configured = Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=tmp_path / "app.pem",
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
        stale_run_after_minutes=0,
    )
    storage = Storage(configured.database_path)
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)

    build_review_worker(configured, "token", lambda job: "clone")

    assert storage.get_review_run(run["id"])["conclusion"] == "stale incomplete run"
