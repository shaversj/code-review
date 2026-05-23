# Architecture

## Overview

AI Code Reviewer is a single-tenant GitHub App service for automated pull request review. The service is designed around a staged review pipeline: accept GitHub pull request events quickly, enqueue durable review jobs, inspect the pull request in an isolated workspace, run allowlisted checks, verify findings, and post guarded GitHub review comments.

The current implementation is an MVP foundation. It proves the service boundaries, persistence, SQS integration, checkout/check abstractions, and reporting guardrails. The model-backed review stages are planned but not yet implemented.

## Runtime Topology

```text
GitHub pull_request webhook
  -> FastAPI API service
  -> SQLite ReviewRun record
  -> SQS-compatible queue
  -> worker process
  -> checkout/check/review pipeline
  -> GitHub review comments
```

Local development runs the same queue shape through Docker Compose:

```text
docker compose
  -> api: FastAPI on localhost:8000
  -> worker: queue consumer
  -> localstack: SQS emulator on localhost:4566
```

LocalStack creates the `code-review-jobs` queue during startup from `localstack/init/ready.d/create-sqs.sh`.

## Source Layout

```text
src/code_review_app/
  config.py              environment-driven settings
  main.py                FastAPI app factory
  cli.py                 worker command entry point
  storage.py             SQLite schema and review-run persistence
  github/
    webhook.py           GitHub webhook signature verification and routing
    client.py            GitHub REST API wrapper for PR state and comments
  queue/
    sqs.py               SQS-compatible queue adapter
  review/
    coordinator.py       PR event to ReviewRun/SQS job orchestration
    models.py            shared review dataclasses
    pipeline.py          deterministic MVP review pipeline
    reporter.py          guarded GitHub comment posting
    worker.py            review job handler boundary
  sandbox/
    checkout.py          git clone/fetch/diff workspace preparation
    checks.py            .code-review.yml parser and allowlisted check runner
```

## Request Flow

1. GitHub sends a `pull_request` webhook to `/webhooks/github`.
2. `github.webhook` verifies `X-Hub-Signature-256` with `GITHUB_WEBHOOK_SECRET`.
3. Unsupported events and pull request actions are ignored.
4. `ReviewCoordinator` rejects repos outside `GITHUB_ALLOWED_REPOS`.
5. `Storage` creates a queued `review_runs` row in SQLite.
6. Older runs for the same repo/PR with different head SHAs are marked stale.
7. `SqsQueue` enqueues a small JSON job containing repo, PR, base SHA, head SHA, installation ID, and review run ID.

The API request returns after enqueueing. Review execution is intentionally outside the webhook request path.

## Worker Flow

The intended worker flow is implemented in `ReviewWorker.handle_job`:

1. Mark the review run `running`.
2. Clone/fetch the repository and compute a base-to-head diff.
3. Load `.code-review.yml` from the checked-out repo.
4. Run configured checks through the allowlisted command runner.
5. Pass workspace and check results to the review pipeline.
6. Post findings through the reporter.
7. Mark the review run `completed` or `failed`.

Current limitation: the `code-review-worker` CLI currently receives and deletes SQS messages, but it does not yet instantiate and call `ReviewWorker`. Wiring the CLI to the full worker boundary is a follow-up slice.

## Persistence

SQLite is the v1 persistence layer. `Storage.connect()` enables:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

The schema currently includes:

- `review_runs`
- `check_runs`
- `leads`
- `findings`

Only review-run creation, lookup, stale marking, and status updates are implemented today. Persisting check runs, leads, findings, and posted comment IDs is planned.

SQLite is suitable for the current single-tenant local/prototype shape. Move to PostgreSQL if the service needs multiple app instances, high worker concurrency, or richer analytics.

## Queue

The queue adapter targets the SQS API. In production, use AWS SQS. In local development, use LocalStack.

`SqsQueue` supports:

- `enqueue_review_job`
- `receive_messages`
- `delete_message`
- `extend_visibility`

SQS delivery is at-least-once. Worker behavior must remain idempotent using `ReviewRun.id` and `head_sha`, and comment posting must guard against stale pull request heads.

Local queue settings:

- queue name: `code-review-jobs`
- visibility timeout: `900`
- long polling wait time: `20`

## Sandbox And Checks

`CheckoutManager` prepares an ephemeral workspace:

1. Remove any previous `run-{review_run_id}` workspace.
2. `git clone --no-tags`.
3. Fetch base and head SHAs.
4. Check out the head SHA.
5. Compute a unified diff with expanded context.

`CheckRunner` only runs commands from repo-owned `.code-review.yml`:

```yaml
review:
  checks:
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 300
```

Model output must not create or choose shell commands. Future model stages may recommend configured checks, but command execution remains allowlisted.

## Review Pipeline

The current MVP pipeline is deterministic. `DeterministicReviewPipeline` turns failed or timed-out configured checks into medium-severity findings.

The intended model-backed pipeline is:

```text
Lead Scout
  -> Deep Reviewer
  -> Evidence Verifier
  -> Reporter
```

Anthropic is the selected first model provider. The model integration should sit behind a narrow gateway so review stages do not depend directly on a specific SDK call shape.

## Reporter Guardrails

`GitHubReporter` verifies the current pull request head SHA before posting comments. If the PR head changed, it posts nothing.

Current behavior:

- skip stale head SHAs
- skip findings below `0.75` confidence
- post inline review comments through GitHub's pull request comments API

Follow-up work should add diff-hunk-aware line placement, duplicate suppression, stale comment handling, and persisted posted comment IDs.

## Configuration

Settings are read from environment variables or `.env`:

- `DATABASE_PATH`
- `GITHUB_APP_ID`
- `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_ALLOWED_REPOS`
- `AWS_REGION`
- `AWS_ENDPOINT_URL`
- `SQS_QUEUE_URL`
- `SQS_VISIBILITY_TIMEOUT_SECONDS`
- `SANDBOX_ROOT`

For Docker Compose, app services use `AWS_ENDPOINT_URL=http://localstack:4566` and `SQS_QUEUE_URL=http://localstack:4566/000000000000/code-review-jobs`.

## Local Development

Primary local path:

```bash
./init.sh
docker compose up --build
```

Useful checks:

```bash
curl http://localhost:8000/healthz

aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text
```

`./init.sh` runs dependency sync, tests, Ruff, and Docker Compose config validation.

## Security Boundaries

Current rules:

- Verify every GitHub webhook signature.
- Allowlist repositories with `GITHUB_ALLOWED_REPOS`.
- Run only configured check commands.
- Do not let model output choose shell commands.
- Do not push commits or mutate remote repositories.
- Do not expose sandbox filesystem paths in public comments.
- Keep LocalStack and Docker Compose local-only.

Planned hardening:

- GitHub App JWT and installation-token exchange.
- Container isolation for check execution.
- Secret redaction from command output before model prompts or persistence.
- SQS visibility extension during long reviews.
- Dead-letter queue redrive process.

## Known Gaps

- Worker CLI is not yet wired to `ReviewWorker`.
- GitHub App installation-token generation is not yet implemented.
- Anthropic-backed scout/reviewer/verifier/reporter stages are not yet implemented.
- Check runs, leads, findings, and posted comment IDs are not yet persisted.
- Inline comment positioning is basic and not diff-hunk-aware.
- Local sandboxing uses filesystem workspaces, not container isolation.
