# AI Code Reviewer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable vertical slice of the single-tenant GitHub App code reviewer.

**Architecture:** A FastAPI webhook verifies GitHub PR events, creates SQLite-backed `ReviewRun` records, and sends SQS messages. A Python worker receives SQS messages, checks out the PR into an ephemeral workspace, runs allowlisted checks, executes a structured review pipeline, and posts guarded PR review comments. The MVP uses a deterministic pipeline first; the model-backed follow-up uses Anthropic behind a narrow model gateway.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic Settings, SQLite, boto3, PyYAML, pytest, httpx, respx. Anthropic is the selected model provider for the first model-backed review stage after the MVP foundation.

---

## File Structure

- `pyproject.toml`: project metadata, dependencies, pytest configuration, lint configuration.
- `.env.example`: required environment variable names.
- `.gitignore`: Python, local DB, sandbox, and env ignores.
- `src/code_review_app/config.py`: environment-driven settings.
- `src/code_review_app/storage.py`: SQLite schema, connection setup, and repository methods.
- `src/code_review_app/github/webhook.py`: GitHub signature verification and FastAPI route.
- `src/code_review_app/github/client.py`: GitHub App authentication and REST API wrapper.
- `src/code_review_app/queue/sqs.py`: SQS enqueue, receive, delete, and visibility extension helpers.
- `src/code_review_app/review/coordinator.py`: webhook-to-review-run orchestration.
- `src/code_review_app/review/models.py`: structured dataclasses for jobs, checks, leads, and findings.
- `src/code_review_app/sandbox/checkout.py`: clone/fetch/diff workspace management.
- `src/code_review_app/sandbox/checks.py`: repo review config parser and allowlisted command runner.
- `src/code_review_app/review/pipeline.py`: scout, reviewer, verifier, and reporter interfaces plus initial deterministic pipeline.
- `src/code_review_app/review/worker.py`: SQS message handler for review jobs.
- `src/code_review_app/main.py`: FastAPI app factory.
- `src/code_review_app/cli.py`: worker entry point.
- `tests/`: focused unit tests for each boundary.

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/code_review_app/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create project metadata and dependencies**

Create `pyproject.toml`:

```toml
[project]
name = "code-review-app"
version = "0.1.0"
description = "Single-tenant GitHub App for AI-assisted PR review"
requires-python = ">=3.12"
dependencies = [
  "boto3>=1.34",
  "fastapi>=0.115",
  "httpx>=0.27",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "pyyaml>=6.0",
  "uvicorn>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-cov>=5.0",
  "respx>=0.21",
  "ruff>=0.6",
]

[project.scripts]
code-review-worker = "code_review_app.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/code_review_app"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Add local ignore rules**

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
*.db
*.db-shm
*.db-wal
.sandboxes/
```

- [ ] **Step 3: Add environment example**

Create `.env.example`:

```bash
APP_ENV=development
DATABASE_PATH=./code-review.db
GITHUB_APP_ID=
GITHUB_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=
GITHUB_ALLOWED_REPOS=owner/repo
AWS_REGION=us-east-1
SQS_QUEUE_URL=
SQS_VISIBILITY_TIMEOUT_SECONDS=900
SANDBOX_ROOT=./.sandboxes
```

- [ ] **Step 4: Add package markers**

Create `src/code_review_app/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `tests/__init__.py`:

```python
```

- [ ] **Step 5: Install dependencies and run empty test suite**

Run:

```bash
uv sync --extra dev
uv run pytest -q
```

Expected: pytest exits successfully with no tests collected or an empty suite success.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/code_review_app/__init__.py tests/__init__.py
git commit -m "chore: scaffold Python project"
```

## Task 2: Configuration

**Files:**
- Create: `src/code_review_app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_config.py -q
```

Expected: FAIL because `code_review_app.config` does not exist.

- [ ] **Step 3: Implement settings**

Create `src/code_review_app/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    database_path: Path = Path("code-review.db")
    github_app_id: int
    github_private_key_path: Path
    github_webhook_secret: str
    github_allowed_repos: str
    aws_region: str = "us-east-1"
    sqs_queue_url: str
    sqs_visibility_timeout_seconds: int = Field(default=900, ge=30)
    sandbox_root: Path = Path(".sandboxes")

    @property
    def allowed_repo_set(self) -> set[str]:
        return {item.strip() for item in self.github_allowed_repos.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/config.py tests/test_config.py
git commit -m "feat: add application settings"
```

## Task 3: SQLite Storage

**Files:**
- Create: `src/code_review_app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
from pathlib import Path

from code_review_app.storage import Storage


def test_storage_creates_review_run(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()

    run = storage.create_review_run(
        repo_full_name="owner/repo",
        pr_number=12,
        base_sha="base",
        head_sha="head",
        installation_id=99,
    )

    loaded = storage.get_review_run(run["id"])
    assert loaded["repo_full_name"] == "owner/repo"
    assert loaded["status"] == "queued"
    assert loaded["stale"] == 0


def test_storage_marks_existing_run_stale_for_new_head(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    first = storage.create_review_run("owner/repo", 12, "base", "old", 99)
    second = storage.create_review_run("owner/repo", 12, "base", "new", 99)

    storage.mark_other_runs_stale("owner/repo", 12, "new")

    assert storage.get_review_run(first["id"])["stale"] == 1
    assert storage.get_review_run(second["id"])["stale"] == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_storage.py -q
```

Expected: FAIL because `Storage` does not exist.

- [ ] **Step 3: Implement SQLite storage**

Create `src/code_review_app/storage.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    base_sha TEXT NOT NULL,
                    head_sha TEXT NOT NULL,
                    installation_id INTEGER NOT NULL,
                    queue_message_id TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    latency_ms INTEGER,
                    cost_estimate_cents INTEGER DEFAULT 0,
                    conclusion TEXT,
                    stale INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS check_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    command TEXT NOT NULL,
                    exit_code INTEGER,
                    timed_out INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL,
                    output_excerpt TEXT NOT NULL,
                    artifact_path TEXT
                );

                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    suspicion TEXT NOT NULL,
                    related_rule_ids TEXT NOT NULL,
                    suggested_context TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    lead_id INTEGER REFERENCES leads(id),
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    behavior_at_risk TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    suggested_action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    posted_comment_id TEXT
                );
                """
            )

    def create_review_run(
        self,
        repo_full_name: str,
        pr_number: int,
        base_sha: str,
        head_sha: str,
        installation_id: int,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO review_runs (
                    repo_full_name, pr_number, base_sha, head_sha,
                    installation_id, status
                )
                VALUES (?, ?, ?, ?, ?, 'queued')
                """,
                (repo_full_name, pr_number, base_sha, head_sha, installation_id),
            )
            return self.get_review_run(int(cursor.lastrowid))

    def get_review_run(self, review_run_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE id = ?",
                (review_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"review run not found: {review_run_id}")
        return dict(row)

    def mark_other_runs_stale(self, repo_full_name: str, pr_number: int, head_sha: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE review_runs
                SET stale = 1
                WHERE repo_full_name = ? AND pr_number = ? AND head_sha != ?
                """,
                (repo_full_name, pr_number, head_sha),
            )

    def update_review_run_status(self, review_run_id: int, status: str, conclusion: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE review_runs SET status = ?, conclusion = ? WHERE id = ?",
                (status, conclusion, review_run_id),
            )
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/storage.py tests/test_storage.py
git commit -m "feat: add SQLite review storage"
```

## Task 4: GitHub Webhook Verification

**Files:**
- Create: `src/code_review_app/github/__init__.py`
- Create: `src/code_review_app/github/webhook.py`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: Write failing webhook tests**

Create `tests/test_webhook.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_webhook.py -q
```

Expected: FAIL because `code_review_app.github.webhook` does not exist.

- [ ] **Step 3: Implement webhook router**

Create `src/code_review_app/github/__init__.py`:

```python
```

Create `src/code_review_app/github/webhook.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_webhook.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/github tests/test_webhook.py
git commit -m "feat: verify GitHub webhook events"
```

## Task 5: SQS Queue Adapter

**Files:**
- Create: `src/code_review_app/queue/__init__.py`
- Create: `src/code_review_app/queue/sqs.py`
- Test: `tests/test_sqs_queue.py`

- [ ] **Step 1: Write failing queue tests**

Create `tests/test_sqs_queue.py`:

```python
import json

from code_review_app.queue.sqs import SqsQueue


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.deleted: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "msg-1"}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)
        return {}


def test_enqueue_review_job_sends_json_body() -> None:
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://queue")

    message_id = queue.enqueue_review_job({"review_run_id": 1, "head_sha": "abc"})

    assert message_id == "msg-1"
    assert json.loads(client.sent[0]["MessageBody"]) == {"review_run_id": 1, "head_sha": "abc"}


def test_delete_message_uses_receipt_handle() -> None:
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://queue")

    queue.delete_message("receipt")

    assert client.deleted == [{"QueueUrl": "https://queue", "ReceiptHandle": "receipt"}]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_sqs_queue.py -q
```

Expected: FAIL because `code_review_app.queue.sqs` does not exist.

- [ ] **Step 3: Implement SQS adapter**

Create `src/code_review_app/queue/__init__.py`:

```python
```

Create `src/code_review_app/queue/sqs.py`:

```python
from __future__ import annotations

import json
from typing import Any

import boto3


class SqsQueue:
    def __init__(self, client: Any, queue_url: str) -> None:
        self.client = client
        self.queue_url = queue_url

    @classmethod
    def from_region(cls, region_name: str, queue_url: str) -> "SqsQueue":
        return cls(client=boto3.client("sqs", region_name=region_name), queue_url=queue_url)

    def enqueue_review_job(self, payload: dict[str, Any]) -> str:
        response = self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(payload, separators=(",", ":")),
        )
        return str(response["MessageId"])

    def receive_messages(self, max_messages: int = 1, wait_time_seconds: int = 20) -> list[dict[str, Any]]:
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            MessageAttributeNames=["All"],
        )
        return list(response.get("Messages", []))

    def delete_message(self, receipt_handle: str) -> None:
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)

    def extend_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=timeout_seconds,
        )
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_sqs_queue.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/queue tests/test_sqs_queue.py
git commit -m "feat: add SQS queue adapter"
```

## Task 6: Review Coordinator

**Files:**
- Create: `src/code_review_app/review/__init__.py`
- Create: `src/code_review_app/review/coordinator.py`
- Test: `tests/test_coordinator.py`

- [ ] **Step 1: Write failing coordinator tests**

Create `tests/test_coordinator.py`:

```python
from pathlib import Path

from code_review_app.review.coordinator import ReviewCoordinator
from code_review_app.storage import Storage


class FakeQueue:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def enqueue_review_job(self, payload: dict) -> str:
        self.payloads.append(payload)
        return "msg-1"


def payload(repo: str = "owner/repo") -> dict:
    return {
        "installation": {"id": 42},
        "repository": {"full_name": repo},
        "pull_request": {
            "number": 7,
            "base": {"sha": "base"},
            "head": {"sha": "head"},
        },
    }


def test_coordinator_creates_review_run_and_enqueues_job(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    queue = FakeQueue()
    coordinator = ReviewCoordinator(storage, queue, allowed_repos={"owner/repo"})

    review_run_id = coordinator.handle_pull_request_event(payload())

    assert review_run_id == 1
    assert queue.payloads == [
        {
            "review_run_id": 1,
            "repo_full_name": "owner/repo",
            "pr_number": 7,
            "base_sha": "base",
            "head_sha": "head",
            "installation_id": 42,
        }
    ]


def test_coordinator_ignores_unallowed_repo(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    queue = FakeQueue()
    coordinator = ReviewCoordinator(storage, queue, allowed_repos={"owner/repo"})

    assert coordinator.handle_pull_request_event(payload("other/repo")) is None
    assert queue.payloads == []
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_coordinator.py -q
```

Expected: FAIL because `ReviewCoordinator` does not exist.

- [ ] **Step 3: Implement coordinator**

Create `src/code_review_app/review/__init__.py`:

```python
```

Create `src/code_review_app/review/coordinator.py`:

```python
from __future__ import annotations

from typing import Protocol

from code_review_app.storage import Storage


class ReviewQueue(Protocol):
    def enqueue_review_job(self, payload: dict) -> str:
        raise NotImplementedError


class ReviewCoordinator:
    def __init__(self, storage: Storage, queue: ReviewQueue, allowed_repos: set[str]) -> None:
        self.storage = storage
        self.queue = queue
        self.allowed_repos = allowed_repos

    def handle_pull_request_event(self, payload: dict) -> int | None:
        repo_full_name = payload["repository"]["full_name"]
        if repo_full_name not in self.allowed_repos:
            return None

        pull_request = payload["pull_request"]
        run = self.storage.create_review_run(
            repo_full_name=repo_full_name,
            pr_number=int(pull_request["number"]),
            base_sha=pull_request["base"]["sha"],
            head_sha=pull_request["head"]["sha"],
            installation_id=int(payload["installation"]["id"]),
        )
        self.storage.mark_other_runs_stale(repo_full_name, int(pull_request["number"]), pull_request["head"]["sha"])

        self.queue.enqueue_review_job(
            {
                "review_run_id": run["id"],
                "repo_full_name": repo_full_name,
                "pr_number": int(pull_request["number"]),
                "base_sha": pull_request["base"]["sha"],
                "head_sha": pull_request["head"]["sha"],
                "installation_id": int(payload["installation"]["id"]),
            }
        )
        return int(run["id"])
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_coordinator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/review tests/test_coordinator.py
git commit -m "feat: enqueue review runs from PR events"
```

## Task 7: Sandbox Checkout And Diff

**Files:**
- Create: `src/code_review_app/review/models.py`
- Create: `src/code_review_app/sandbox/__init__.py`
- Create: `src/code_review_app/sandbox/checkout.py`
- Test: `tests/test_checkout.py`

- [ ] **Step 1: Write failing checkout tests**

Create `tests/test_checkout.py`:

```python
from pathlib import Path

from code_review_app.sandbox.checkout import CheckoutManager


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        self.commands.append(command)
        if command[:2] == ["git", "diff"]:
            return "diff --git a/app.py b/app.py\n+print('hello')\n"
        return ""


def test_checkout_manager_runs_expected_git_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    manager = CheckoutManager(tmp_path, runner)

    workspace = manager.prepare(
        repo_url="https://x-access-token:TOKEN@github.com/owner/repo.git",
        review_run_id=5,
        base_sha="base",
        head_sha="head",
    )

    assert workspace.path == tmp_path / "run-5"
    assert "print('hello')" in workspace.diff
    assert runner.commands[0][:2] == ["git", "clone"]
    assert ["git", "checkout", "head"] in runner.commands
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_checkout.py -q
```

Expected: FAIL because `CheckoutManager` does not exist.

- [ ] **Step 3: Implement review models and checkout manager**

Create `src/code_review_app/review/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    path: Path
    base_sha: str
    head_sha: str
    diff: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: str
    command: str
    exit_code: int
    timed_out: bool
    duration_ms: int
    output_excerpt: str
```

Create `src/code_review_app/sandbox/__init__.py`:

```python
```

Create `src/code_review_app/sandbox/checkout.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from code_review_app.review.models import Workspace


class CommandRunner(Protocol):
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        raise NotImplementedError


class SubprocessRunner:
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        completed = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout_seconds,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return completed.stdout


class CheckoutManager:
    def __init__(self, sandbox_root: Path, runner: CommandRunner | None = None) -> None:
        self.sandbox_root = sandbox_root
        self.runner = runner or SubprocessRunner()

    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        workspace_path = self.sandbox_root / f"run-{review_run_id}"
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        self.runner.run(["git", "clone", "--no-tags", repo_url, str(workspace_path)], timeout_seconds=600)
        self.runner.run(["git", "fetch", "origin", base_sha, head_sha], cwd=workspace_path, timeout_seconds=300)
        self.runner.run(["git", "checkout", head_sha], cwd=workspace_path, timeout_seconds=300)
        diff = self.runner.run(
            ["git", "diff", "--unified=80", f"{base_sha}...{head_sha}"],
            cwd=workspace_path,
            timeout_seconds=300,
        )
        return Workspace(path=workspace_path, base_sha=base_sha, head_sha=head_sha, diff=diff)
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_checkout.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/review/models.py src/code_review_app/sandbox tests/test_checkout.py
git commit -m "feat: prepare PR checkout workspace"
```

## Task 8: Review Config And Check Runner

**Files:**
- Create: `src/code_review_app/sandbox/checks.py`
- Test: `tests/test_checks.py`

- [ ] **Step 1: Write failing check runner tests**

Create `tests/test_checks.py`:

```python
from pathlib import Path

from code_review_app.sandbox.checks import CheckRunner, load_review_config


class FakeRunner:
    def run(self, command: list[str], cwd: Path | None = None, timeout_seconds: int = 300) -> str:
        assert command == ["uv", "run", "pytest"]
        return "1 passed"


def test_load_review_config_reads_checks(tmp_path: Path) -> None:
    config_path = tmp_path / ".code-review.yml"
    config_path.write_text(
        """
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 120
""",
        encoding="utf-8",
    )

    config = load_review_config(tmp_path)

    assert config.checks[0].name == "unit"
    assert config.checks[0].command == ["uv", "run", "pytest"]


def test_check_runner_returns_result(tmp_path: Path) -> None:
    config_path = tmp_path / ".code-review.yml"
    config_path.write_text(
        """
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 120
""",
        encoding="utf-8",
    )
    config = load_review_config(tmp_path)

    results = CheckRunner(FakeRunner()).run_checks(tmp_path, config)

    assert results[0].name == "unit"
    assert results[0].exit_code == 0
    assert results[0].output_excerpt == "1 passed"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_checks.py -q
```

Expected: FAIL because `sandbox.checks` does not exist.

- [ ] **Step 3: Implement config parser and check runner**

Create `src/code_review_app/sandbox/checks.py`:

```python
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from code_review_app.review.models import CheckResult
from code_review_app.sandbox.checkout import CommandRunner, SubprocessRunner


@dataclass(frozen=True)
class CheckCommand:
    name: str
    kind: str
    command: list[str]
    timeout_seconds: int


@dataclass(frozen=True)
class ReviewConfig:
    checks: list[CheckCommand]


def load_review_config(repo_path: Path) -> ReviewConfig:
    path = repo_path / ".code-review.yml"
    if not path.exists():
        return ReviewConfig(checks=[])

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    checks: list[CheckCommand] = []
    check_groups = raw.get("review", {}).get("checks", {})
    for kind, entries in check_groups.items():
        for entry in entries or []:
            checks.append(
                CheckCommand(
                    name=str(entry["name"]),
                    kind=str(kind),
                    command=shlex.split(str(entry["command"])),
                    timeout_seconds=int(entry.get("timeout_seconds", 300)),
                )
            )
    return ReviewConfig(checks=checks)


class CheckRunner:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

    def run_checks(self, repo_path: Path, config: ReviewConfig) -> list[CheckResult]:
        results: list[CheckResult] = []
        for check in config.checks:
            started = time.monotonic()
            timed_out = False
            exit_code = 0
            try:
                output = self.runner.run(check.command, cwd=repo_path, timeout_seconds=check.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = 124
                output = str(exc)
            except subprocess.CalledProcessError as exc:
                exit_code = int(exc.returncode)
                output = str(exc.stdout or exc)
            duration_ms = int((time.monotonic() - started) * 1000)
            results.append(
                CheckResult(
                    name=check.name,
                    kind=check.kind,
                    command=" ".join(check.command),
                    exit_code=exit_code,
                    timed_out=timed_out,
                    duration_ms=duration_ms,
                    output_excerpt=output[:4000],
                )
            )
        return results
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_checks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/sandbox/checks.py tests/test_checks.py
git commit -m "feat: run allowlisted review checks"
```

## Task 9: Deterministic Review Pipeline Contracts

**Files:**
- Modify: `src/code_review_app/review/models.py`
- Create: `src/code_review_app/review/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

Create `tests/test_pipeline.py`:

```python
from pathlib import Path

from code_review_app.review.models import CheckResult, Workspace
from code_review_app.review.pipeline import DeterministicReviewPipeline


def test_pipeline_creates_finding_for_failing_check() -> None:
    workspace = Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+print('x')")
    checks = [
        CheckResult(
            name="unit",
            kind="tests",
            command="uv run pytest",
            exit_code=1,
            timed_out=False,
            duration_ms=20,
            output_excerpt="tests/test_app.py::test_app FAILED",
        )
    ]

    result = DeterministicReviewPipeline().run(workspace, checks)

    assert result.findings[0].title == "Configured check failed: unit"
    assert result.findings[0].severity == "medium"
    assert "uv run pytest" in result.findings[0].evidence
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_pipeline.py -q
```

Expected: FAIL because `DeterministicReviewPipeline` does not exist.

- [ ] **Step 3: Add lead/finding models**

Append to `src/code_review_app/review/models.py`:

```python

@dataclass(frozen=True)
class Lead:
    file_path: str
    line: int
    suspicion: str
    related_rule_ids: list[str]
    suggested_context: str
    status: str = "open"


@dataclass(frozen=True)
class Finding:
    file_path: str
    line: int
    severity: str
    title: str
    behavior_at_risk: str
    evidence: str
    suggested_action: str
    confidence: float


@dataclass(frozen=True)
class ReviewPipelineResult:
    leads: list[Lead]
    findings: list[Finding]
```

- [ ] **Step 4: Implement deterministic pipeline**

Create `src/code_review_app/review/pipeline.py`:

```python
from __future__ import annotations

from code_review_app.review.models import CheckResult, Finding, Lead, ReviewPipelineResult, Workspace


class DeterministicReviewPipeline:
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        leads: list[Lead] = []
        findings: list[Finding] = []
        for check in checks:
            if check.exit_code == 0 and not check.timed_out:
                continue
            leads.append(
                Lead(
                    file_path=".",
                    line=1,
                    suspicion=f"Configured check {check.name} did not pass.",
                    related_rule_ids=["CHECK_FAILURE"],
                    suggested_context=check.output_excerpt,
                    status="verified",
                )
            )
            findings.append(
                Finding(
                    file_path=".",
                    line=1,
                    severity="medium",
                    title=f"Configured check failed: {check.name}",
                    behavior_at_risk="The PR does not satisfy a configured repository check.",
                    evidence=(
                        f"Command `{check.command}` exited with {check.exit_code}. "
                        f"Output excerpt: {check.output_excerpt}"
                    ),
                    suggested_action="Inspect the failing check output and update the PR or check configuration.",
                    confidence=0.9,
                )
            )
        return ReviewPipelineResult(leads=leads, findings=findings)
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/code_review_app/review/models.py src/code_review_app/review/pipeline.py tests/test_pipeline.py
git commit -m "feat: add review pipeline contracts"
```

## Task 10: GitHub Client And Reporter

**Files:**
- Create: `src/code_review_app/github/client.py`
- Create: `src/code_review_app/review/reporter.py`
- Test: `tests/test_reporter.py`

- [ ] **Step 1: Write failing reporter tests**

Create `tests/test_reporter.py`:

```python
from code_review_app.review.models import Finding
from code_review_app.review.reporter import GitHubReporter


class FakeGitHubClient:
    def __init__(self, head_sha: str) -> None:
        self.head_sha = head_sha
        self.comments: list[dict] = []

    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        return self.head_sha

    def create_review_comment(self, repo_full_name: str, pr_number: int, head_sha: str, finding: Finding) -> str:
        self.comments.append(
            {
                "repo": repo_full_name,
                "pr": pr_number,
                "head_sha": head_sha,
                "title": finding.title,
            }
        )
        return "comment-1"


def finding() -> Finding:
    return Finding(
        file_path="app.py",
        line=3,
        severity="medium",
        title="Issue",
        behavior_at_risk="Risk",
        evidence="Evidence",
        suggested_action="Fix it",
        confidence=0.8,
    )


def test_reporter_posts_when_head_sha_matches() -> None:
    client = FakeGitHubClient("head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "head", [finding()])

    assert posted == ["comment-1"]
    assert client.comments[0]["title"] == "Issue"


def test_reporter_skips_when_head_sha_is_stale() -> None:
    client = FakeGitHubClient("new-head")
    reporter = GitHubReporter(client)

    posted = reporter.post_findings("owner/repo", 5, "old-head", [finding()])

    assert posted == []
    assert client.comments == []
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_reporter.py -q
```

Expected: FAIL because `GitHubReporter` does not exist.

- [ ] **Step 3: Implement GitHub client skeleton and reporter**

Create `src/code_review_app/github/client.py`:

```python
from __future__ import annotations

from typing import Protocol

import httpx

from code_review_app.review.models import Finding


class GitHubClientProtocol(Protocol):
    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        raise NotImplementedError

    def create_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        finding: Finding,
    ) -> str:
        raise NotImplementedError


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pull_request_head_sha(self, repo_full_name: str, pr_number: int) -> str:
        response = httpx.get(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return str(response.json()["head"]["sha"])

    def create_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        finding: Finding,
    ) -> str:
        body = (
            f"**{finding.severity.upper()}: {finding.title}**\n\n"
            f"{finding.behavior_at_risk}\n\n"
            f"Evidence: {finding.evidence}\n\n"
            f"Suggested action: {finding.suggested_action}"
        )
        response = httpx.post(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/comments",
            headers=self._headers(),
            json={
                "body": body,
                "commit_id": head_sha,
                "path": finding.file_path,
                "line": finding.line,
                "side": "RIGHT",
            },
            timeout=20,
        )
        response.raise_for_status()
        return str(response.json()["id"])
```

Create `src/code_review_app/review/reporter.py`:

```python
from __future__ import annotations

from code_review_app.github.client import GitHubClientProtocol
from code_review_app.review.models import Finding


class GitHubReporter:
    def __init__(self, github_client: GitHubClientProtocol) -> None:
        self.github_client = github_client

    def post_findings(
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        findings: list[Finding],
    ) -> list[str]:
        current_head_sha = self.github_client.get_pull_request_head_sha(repo_full_name, pr_number)
        if current_head_sha != expected_head_sha:
            return []

        posted_ids: list[str] = []
        for finding in findings:
            if finding.confidence < 0.75:
                continue
            posted_ids.append(
                self.github_client.create_review_comment(
                    repo_full_name,
                    pr_number,
                    expected_head_sha,
                    finding,
                )
            )
        return posted_ids
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_reporter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/github/client.py src/code_review_app/review/reporter.py tests/test_reporter.py
git commit -m "feat: post guarded GitHub review comments"
```

## Task 11: Worker Job Handler

**Files:**
- Create: `src/code_review_app/review/worker.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Write failing worker test**

Create `tests/test_worker.py`:

```python
from pathlib import Path

from code_review_app.review.models import CheckResult, ReviewPipelineResult, Workspace
from code_review_app.review.worker import ReviewWorker
from code_review_app.storage import Storage


class FakeCheckout:
    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        return Workspace(path=Path("."), base_sha=base_sha, head_sha=head_sha, diff="+x")


class FakeChecks:
    def run_checks(self, repo_path: Path, config) -> list[CheckResult]:
        return []


class FakePipeline:
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        return ReviewPipelineResult(leads=[], findings=[])


class FakeReporter:
    def post_findings(self, repo_full_name: str, pr_number: int, expected_head_sha: str, findings: list) -> list[str]:
        return []


def test_worker_completes_review_run(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)
    worker = ReviewWorker(storage, FakeCheckout(), FakeChecks(), FakePipeline(), FakeReporter())

    worker.handle_job(
        {
            "review_run_id": run["id"],
            "repo_full_name": "owner/repo",
            "pr_number": 7,
            "base_sha": "base",
            "head_sha": "head",
            "installation_id": 42,
        }
    )

    assert storage.get_review_run(run["id"])["status"] == "completed"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_worker.py -q
```

Expected: FAIL because `ReviewWorker` does not exist.

- [ ] **Step 3: Implement worker handler**

Create `src/code_review_app/review/worker.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from code_review_app.review.models import CheckResult, ReviewPipelineResult, Workspace
from code_review_app.sandbox.checks import load_review_config
from code_review_app.storage import Storage


class CheckoutProtocol(Protocol):
    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        raise NotImplementedError


class CheckRunnerProtocol(Protocol):
    def run_checks(self, repo_path: Path, config) -> list[CheckResult]:
        raise NotImplementedError


class PipelineProtocol(Protocol):
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        raise NotImplementedError


class ReporterProtocol(Protocol):
    def post_findings(self, repo_full_name: str, pr_number: int, expected_head_sha: str, findings: list) -> list[str]:
        raise NotImplementedError


class ReviewWorker:
    def __init__(
        self,
        storage: Storage,
        checkout: CheckoutProtocol,
        checks: CheckRunnerProtocol,
        pipeline: PipelineProtocol,
        reporter: ReporterProtocol,
    ) -> None:
        self.storage = storage
        self.checkout = checkout
        self.checks = checks
        self.pipeline = pipeline
        self.reporter = reporter

    def handle_job(self, job: dict) -> None:
        review_run_id = int(job["review_run_id"])
        self.storage.update_review_run_status(review_run_id, "running")
        try:
            repo_url = f"https://github.com/{job['repo_full_name']}.git"
            workspace = self.checkout.prepare(
                repo_url=repo_url,
                review_run_id=review_run_id,
                base_sha=str(job["base_sha"]),
                head_sha=str(job["head_sha"]),
            )
            config = load_review_config(workspace.path)
            check_results = self.checks.run_checks(workspace.path, config)
            result = self.pipeline.run(workspace, check_results)
            self.reporter.post_findings(
                str(job["repo_full_name"]),
                int(job["pr_number"]),
                str(job["head_sha"]),
                result.findings,
            )
            self.storage.update_review_run_status(review_run_id, "completed", conclusion="reviewed")
        except Exception as exc:
            self.storage.update_review_run_status(review_run_id, "failed", conclusion=str(exc))
            raise
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/code_review_app/review/worker.py tests/test_worker.py
git commit -m "feat: process review jobs"
```

## Task 12: Application Entrypoints

**Files:**
- Create: `src/code_review_app/main.py`
- Create: `src/code_review_app/cli.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing app factory test**

Create `tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_main.py -q
```

Expected: FAIL because `code_review_app.main` does not exist.

- [ ] **Step 3: Implement FastAPI app factory**

Create `src/code_review_app/main.py`:

```python
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
```

- [ ] **Step 4: Implement CLI skeleton**

Create `src/code_review_app/cli.py`:

```python
from __future__ import annotations

import json
import time

from code_review_app.config import get_settings
from code_review_app.queue.sqs import SqsQueue


def main() -> None:
    settings = get_settings()
    queue = SqsQueue.from_region(settings.aws_region, settings.sqs_queue_url)
    while True:
        for message in queue.receive_messages(max_messages=1, wait_time_seconds=20):
            body = json.loads(message["Body"])
            print(f"received review job {body['review_run_id']}")
            queue.delete_message(message["ReceiptHandle"])
        time.sleep(1)
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
uv run pytest tests/test_main.py -q
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/code_review_app/main.py src/code_review_app/cli.py tests/test_main.py
git commit -m "feat: wire application entrypoints"
```

## Task 13: Developer Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README**

Create `README.md`:

```markdown
# AI Code Reviewer

Single-tenant GitHub App service for automated pull request review.

## Local setup

```bash
uv sync --extra dev
cp .env.example .env
```

Fill in `.env` with GitHub App and SQS settings.

## Run API

```bash
uv run uvicorn code_review_app.main:create_app --factory --reload
```

## Run worker

```bash
uv run code-review-worker
```

## Test

```bash
uv run pytest -q
```

## Review config

Repositories can opt into allowlisted checks with `.code-review.yml`:

```yaml
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 300
```
```

- [ ] **Step 2: Run documentation-adjacent verification**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add local development instructions"
```

## Self-Review Checklist

- Spec coverage:
  - Webhook handling: Tasks 4 and 12.
  - SQLite persistence: Task 3.
  - SQS queue: Task 5.
  - Coordinator dedupe/stale basics: Task 6.
  - Sandbox checkout and diff: Task 7.
  - Allowlisted checks: Task 8.
  - Review pipeline boundaries: Task 9.
  - GitHub comment guardrails: Task 10.
  - Worker execution: Task 11.
  - Developer workflow: Tasks 1 and 13.
- Deliberate follow-up after this MVP plan:
  - GitHub App JWT and installation token generation.
  - Persisting check runs, leads, findings, and posted comment IDs.
  - Anthropic-backed scout, reviewer, verifier, and reporter stages behind a `ModelGateway`.
  - SQS visibility extension during long reviews.
  - Dead-letter queue redrive documentation.
  - Inline comment positioning from actual diff hunks.
  - Container isolation for sandbox execution.
- Red-flag scan: no unresolved markers or unspecified implementation steps.
- Type consistency: `ReviewRun`, `Workspace`, `CheckResult`, `Lead`, `Finding`, and `ReviewPipelineResult` are defined before use.
