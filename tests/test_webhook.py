import hashlib
import hmac

from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_review_app.github.webhook import create_webhook_router


class FakeCoordinator:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def handle_pull_request_event(self, payload: dict) -> int | None:
        self.payloads.append(payload)
        return 123


def signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_accepts_valid_pull_request_event() -> None:
    body = b'{"action":"opened","repository":{"full_name":"owner/repo"}}'
    coordinator = FakeCoordinator()
    app = FastAPI()
    app.include_router(create_webhook_router("secret", coordinator))
    client = TestClient(app)

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature("secret", body),
            "X-GitHub-Event": "pull_request",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"review_run_id": 123}
    assert coordinator.payloads[0]["action"] == "opened"


def test_webhook_rejects_invalid_signature() -> None:
    coordinator = FakeCoordinator()
    app = FastAPI()
    app.include_router(create_webhook_router("secret", coordinator))
    client = TestClient(app)

    response = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=bad", "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 401
