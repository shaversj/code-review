from __future__ import annotations

import json
import logging
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

    @staticmethod
    def receive_count(message: dict) -> int:
        return int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1))


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
        review_pipeline_provider="deterministic",
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
        "Attributes": {"ApproximateReceiveCount": "3"},
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


def test_process_message_logs_sqs_receive_count(tmp_path: Path, caplog) -> None:
    queue = FakeQueue()

    with caplog.at_level(logging.INFO):
        process_message(
            message(),
            settings(tmp_path),
            queue,
            auth_factory=FakeAuth,
            worker_factory=lambda settings, github_token, repo_url_builder: FakeWorker(),
        )

    assert "sqs_receive_count=3" in caplog.text


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


def test_build_review_pipeline_defaults_to_deterministic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        pipeline = build_review_pipeline(settings(tmp_path))

    assert isinstance(pipeline, DeterministicReviewPipeline)
    assert "selected review pipeline provider=deterministic" in caplog.text


def test_build_review_pipeline_can_use_anthropic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class FakeGateway:
        def __init__(
            self,
            api_key: str | None,
            base_url: str | None,
            model: str,
            max_tokens: int,
            input_price_per_million_tokens: float,
            output_price_per_million_tokens: float,
            provider: str,
        ) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.model = model
            self.max_tokens = max_tokens
            self.input_price_per_million_tokens = input_price_per_million_tokens
            self.output_price_per_million_tokens = output_price_per_million_tokens
            self.provider = provider

    configured = Settings(
        database_path=tmp_path / "review.db",
        github_app_id=123,
        github_private_key_path=tmp_path / "app.pem",
        github_webhook_secret="secret",
        github_allowed_repos="owner/repo",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/123/reviews",
        review_pipeline_provider="anthropic-compatible",
        model_api_key="minimax-key",
        model_base_url="https://api.minimax.io/anthropic",
        model_name="MiniMax-M2.7",
        model_max_tokens=321,
        model_input_price_per_million_tokens=0.3,
        model_output_price_per_million_tokens=1.2,
    )

    with caplog.at_level(logging.INFO):
        pipeline = build_review_pipeline(configured, gateway_factory=FakeGateway)

    assert isinstance(pipeline, AnthropicReviewPipeline)
    assert pipeline.gateway.api_key == "minimax-key"
    assert pipeline.gateway.base_url == "https://api.minimax.io/anthropic"
    assert pipeline.gateway.model == "MiniMax-M2.7"
    assert pipeline.gateway.max_tokens == 321
    assert pipeline.gateway.input_price_per_million_tokens == 0.3
    assert pipeline.gateway.output_price_per_million_tokens == 1.2
    assert pipeline.gateway.provider == "anthropic-compatible"
    assert "selected review pipeline provider=anthropic-compatible" in caplog.text
    assert "model=MiniMax-M2.7" in caplog.text


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
