# AI Code Reviewer

Single-tenant GitHub App service for automated pull request review.

## Local Setup

```bash
uv sync --extra dev
cp .env.example .env
```

Fill in `.env` with GitHub App and SQS settings.

## Run API

```bash
uv run uvicorn code_review_app.main:create_app --factory --reload
```

## Run Worker

```bash
uv run code-review-worker
```

## Test

```bash
uv run pytest -q
```

## Review Config

Repositories can opt into allowlisted checks with `.code-review.yml`:

```yaml
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 300
```
