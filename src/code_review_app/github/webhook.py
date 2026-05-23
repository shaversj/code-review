from __future__ import annotations

import hashlib
import hmac
import json
from typing import Protocol

from fastapi import APIRouter, Header, HTTPException, Request, status


SUPPORTED_PULL_REQUEST_ACTIONS = {"opened", "reopened", "synchronize"}


class PullRequestCoordinator(Protocol):
    def handle_pull_request_event(self, payload: dict) -> int | None:
        raise NotImplementedError


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if signature_header is None or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    actual = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, actual)


def create_webhook_router(secret: str, coordinator: PullRequestCoordinator) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
    async def github_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(default=None),
        x_github_event: str | None = Header(default=None),
    ) -> dict[str, int | None | str]:
        body = await request.body()
        if not verify_signature(secret, body, x_hub_signature_256):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

        if x_github_event != "pull_request":
            return {"status": "ignored"}

        payload = json.loads(body)
        if payload.get("action") not in SUPPORTED_PULL_REQUEST_ACTIONS:
            return {"status": "ignored"}

        review_run_id = coordinator.handle_pull_request_event(payload)
        return {"review_run_id": review_run_id}

    return router
