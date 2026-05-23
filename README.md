# AI Code Reviewer

Single-tenant GitHub App service for automated pull request review.

## Local Setup

```bash
uv sync --extra dev
cp .env.example .env
```

Fill in `.env` with GitHub App and SQS settings.

## LocalStack SQS

For local SQS development, run LocalStack and point the AWS SDK at it:

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=http://localhost.localstack.cloud:4566

docker run --rm -it -p 4566:4566 localstack/localstack
```

In another shell, create the queue:

```bash
aws --endpoint-url="$AWS_ENDPOINT_URL" sqs create-queue \
  --queue-name code-review-jobs \
  --attributes VisibilityTimeout=900,ReceiveMessageWaitTimeSeconds=20

aws --endpoint-url="$AWS_ENDPOINT_URL" sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text
```

Use the returned queue URL in `.env`:

```bash
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost.localstack.cloud:4566
SQS_QUEUE_URL=http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/code-review-jobs
```

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
