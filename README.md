# AI Code Reviewer

Single-tenant GitHub App service for automated pull request review.

## Docker Compose Setup

```bash
docker compose up --build
```

This starts:

- `api`: FastAPI webhook service on `http://localhost:8000`
- `worker`: local review job worker
- `localstack`: local SQS emulator on `http://localhost:4566`

LocalStack creates the `code-review-jobs` queue automatically from `localstack/init/ready.d/create-sqs.sh`.

Check the API:

```bash
curl http://localhost:8000/healthz
```

Check the LocalStack queue:

```bash
aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text
```

Override local defaults by exporting environment variables before `docker compose up`:

```bash
GITHUB_WEBHOOK_SECRET=devsecret
GITHUB_ALLOWED_REPOS=owner/repo
```

## Direct Local Setup

Use this path if you want to run without Docker Compose.

```bash
uv sync --extra dev
cp .env.example .env
```

Fill in `.env` with GitHub App and SQS settings.

### Run API

```bash
uv run uvicorn code_review_app.main:create_app --factory --reload
```

### Run Worker

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
