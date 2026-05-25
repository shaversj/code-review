# AI Code Reviewer

Single-tenant GitHub App service for automated pull request review.

## Docker Compose Setup

Store your GitHub App private key in the ignored local `.secrets` directory before starting the stack:

```bash
mkdir -p .secrets
cp /path/to/downloaded-private-key.pem .secrets/github-app-private-key.pem
chmod 600 .secrets/github-app-private-key.pem
```

The `.secrets/` directory and `*.pem` files are intentionally ignored by git. The PEM can live inside the working directory for Docker Compose convenience, but it must never be staged or committed. You can confirm it is ignored with:

```bash
git check-ignore -v .secrets/github-app-private-key.pem
git status --short
```

```bash
docker compose up --build
```

This starts:

- `api`: FastAPI webhook service on `http://localhost:8000`
- `worker`: local review job worker
- `localstack`: local SQS emulator on `http://localhost:4566`

LocalStack creates the `code-review-jobs` queue automatically from `localstack/init/ready.d/create-sqs.sh`.

The Compose file pins LocalStack to `localstack/localstack:4.11.1` and sets `ACTIVATE_PRO=0`. LocalStack's 2026 `latest` image requires a `LOCALSTACK_AUTH_TOKEN`, while this project only needs local SQS emulation.

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
GITHUB_APP_ID=123456
GITHUB_WEBHOOK_SECRET=devsecret
GITHUB_ALLOWED_REPOS=owner/repo
```

The default review pipeline is deterministic and only turns failed configured checks into findings. To use MiniMax through its Anthropic-compatible API, set:

```bash
REVIEW_PIPELINE_PROVIDER=anthropic-compatible
MODEL_API_KEY=your-minimax-api-key
MODEL_BASE_URL=https://api.minimax.io/anthropic
MODEL_NAME=MiniMax-M2.7
MODEL_MAX_TOKENS=4000
```

The worker marks queued or running review runs older than `STALE_RUN_AFTER_MINUTES` as failed stale runs during startup. Set `STALE_RUN_AFTER_MINUTES=0` only for local cleanup.

## Direct Local Setup

Use this path if you want to run without Docker Compose.

```bash
uv sync --extra dev
cp .env.example .env
```

Fill in `.env` with GitHub App and SQS settings.

For direct local runs, set `GITHUB_PRIVATE_KEY_PATH` to a host-visible path such as `./.secrets/github-app-private-key.pem`. For Docker Compose, use the container-visible `/run/secrets/...` path.

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
./init.sh
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
