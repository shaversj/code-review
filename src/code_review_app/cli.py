from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Protocol

from code_review_app.config import Settings, get_settings
from code_review_app.github.auth import GitHubAppAuth
from code_review_app.github.client import GitHubClient
from code_review_app.queue.sqs import SqsQueue
from code_review_app.review.pipeline import DeterministicReviewPipeline
from code_review_app.review.reporter import GitHubReporter
from code_review_app.review.worker import ReviewWorker
from code_review_app.sandbox.checkout import CheckoutManager
from code_review_app.sandbox.checks import CheckRunner
from code_review_app.storage import Storage


class QueueProtocol(Protocol):
    def delete_message(self, receipt_handle: str) -> None:
        raise NotImplementedError


def build_review_worker(
    settings: Settings,
    github_token: str,
    repo_url_builder: Callable[[dict], str],
) -> ReviewWorker:
    storage = Storage(settings.database_path)
    storage.initialize()
    return ReviewWorker(
        storage=storage,
        checkout=CheckoutManager(settings.sandbox_root),
        checks=CheckRunner(),
        pipeline=DeterministicReviewPipeline(),
        reporter=GitHubReporter(GitHubClient(github_token)),
        repo_url_builder=repo_url_builder,
    )


def process_message(
    message: dict,
    settings: Settings,
    queue: QueueProtocol,
    auth_factory: Callable = GitHubAppAuth,
    worker_factory: Callable = build_review_worker,
) -> None:
    job = json.loads(message["Body"])
    auth = auth_factory(settings.github_app_id, settings.github_private_key_path)
    installation_token = auth.create_installation_token(int(job["installation_id"])).token

    def repo_url_builder(job: dict) -> str:
        return auth.authenticated_clone_url(str(job["repo_full_name"]), installation_token)

    worker = worker_factory(settings, installation_token, repo_url_builder)
    worker.handle_job(job)
    queue.delete_message(message["ReceiptHandle"])


def main() -> None:
    settings = get_settings()
    queue = SqsQueue.from_region(
        settings.aws_region,
        settings.sqs_queue_url,
        endpoint_url=settings.aws_endpoint_url,
    )
    while True:
        for message in queue.receive_messages(max_messages=1, wait_time_seconds=20):
            process_message(message, settings, queue)
        time.sleep(1)
