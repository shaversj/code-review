from __future__ import annotations

from fastapi import FastAPI

from code_review_app.config import Settings, get_settings
from code_review_app.github.webhook import create_webhook_router
from code_review_app.queue.sqs import SqsQueue
from code_review_app.review.coordinator import ReviewCoordinator
from code_review_app.storage import Storage


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    storage = Storage(resolved.database_path)
    storage.initialize()
    queue = SqsQueue.from_region(resolved.aws_region, resolved.sqs_queue_url)
    coordinator = ReviewCoordinator(storage, queue, resolved.allowed_repo_set)

    app = FastAPI(title="AI Code Reviewer")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(create_webhook_router(resolved.github_webhook_secret, coordinator))
    return app
