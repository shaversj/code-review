# Architecture

## Overview

AI Code Reviewer is a single-tenant GitHub App service for automated pull request review. The service is designed around a staged review pipeline: accept GitHub pull request events quickly, enqueue durable review jobs, inspect the pull request in an isolated workspace, run allowlisted checks, verify findings, and post guarded GitHub review comments.

The current implementation is an MVP foundation. It proves the service boundaries, persistence, SQS integration, checkout/check abstractions, reporting guardrails, and an optional Anthropic-backed review gateway.

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
LocalStack also creates `code-review-jobs-dlq` and attaches it as the dead-letter queue with `maxReceiveCount=5`.
The LocalStack service pins `localstack/localstack:4.11.1` and sets `ACTIVATE_PRO=0` because the local runtime only needs community SQS emulation. The 2026 `latest` image requires a LocalStack auth token.

## Source Layout

```text
src/code_review_app/
  ai/
    anthropic.py         Anthropic-compatible Messages API gateway for JSON review results
  config.py              environment-driven settings
  main.py                FastAPI app factory
  cli.py                 worker command entry point
  storage.py             SQLite schema and review-run persistence
  github/
    auth.py              GitHub App JWT and installation token exchange
    webhook.py           GitHub webhook signature verification and routing
    client.py            GitHub REST API wrapper for PR state and comments
  queue/
    sqs.py               SQS-compatible queue adapter
  review/
    coordinator.py       PR event to ReviewRun/SQS job orchestration
    diff.py              unified diff parser for inline comment eligibility
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

`GET /review-runs/{id}` returns the persisted review run, checks, model runs, leads, and findings for local inspection.

## Worker Flow

The worker CLI receives SQS messages and calls `ReviewWorker.handle_job`:

1. Parse the queued review job.
2. Exchange a GitHub App JWT for an installation token.
3. Build an authenticated clone URL and GitHub REST client from that installation token.
4. Mark old queued/running rows stale based on `STALE_RUN_AFTER_MINUTES`.
5. Mark the review run `running`.
6. Clone/fetch the repository and compute a base-to-head diff.
7. Load `.code-review.yml` from the checked-out repo.
8. Run configured checks through the allowlisted command runner.
9. Persist check results.
10. Pass workspace and check results to the selected review pipeline.
11. Persist leads, findings, and model usage when the selected pipeline reports it.
12. Build an index of added and right-side lines present in the pull request diff.
13. Post findings through the reporter.
14. Persist posted comment IDs.
15. Mark the review run `completed` or `failed`.

The SQS message is deleted only after `ReviewWorker.handle_job` returns successfully. Failures are left for SQS redelivery.

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
- `model_runs`
- `leads`
- `findings`

Review-run creation, lookup, stale marking, status updates, check result persistence, model usage persistence, lead persistence, finding persistence, and posted comment ID persistence are implemented.

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
- dead-letter queue name: `code-review-jobs-dlq`
- visibility timeout: `900`
- long polling wait time: `20`
- redrive max receive count: `5`

Workers request SQS system attributes and log `ApproximateReceiveCount` for retry visibility. Failed messages are not deleted, allowing SQS to retry and eventually redrive to the DLQ when configured.

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

The Docker app image includes Python, git, Node.js 24, and npm for common local checks. Missing executables are recorded as failed check results with exit code `127` instead of crashing the worker.

Check output is persisted in SQLite. GitHub-facing findings show only the first few meaningful output lines and point operators to stored artifacts for the full log.

## Review Pipeline

The default pipeline is deterministic. `DeterministicReviewPipeline` turns failed or timed-out configured checks into medium-severity findings.

The optional model-backed path is selected with `REVIEW_PIPELINE_PROVIDER=anthropic-compatible`. `AnthropicReviewGateway` uses an Anthropic-compatible Messages API and asks for a JSON object containing leads and findings. The prompt asks for at most five findings, confidence `>= 0.80`, concrete changed-code evidence, and avoids restating raw check failures without a changed-line behavioral tie. The default compatible target is MiniMax:

```text
workspace diff + check results
  -> AnthropicReviewGateway
  -> AnthropicReviewPipeline
  -> persisted leads/findings
  -> reporter
```

The model gateway receives the diff and outputs review data only. It must not create or choose shell commands. The gateway expects JSON review data, tolerates common model formatting wrappers such as Markdown fenced JSON blocks, and normalizes partial lead/finding items so missing narrative fields do not crash the worker.

For operator visibility, the model gateway logs review start, response parsing, completion, provider-reported input/output token counts, and an estimated USD cost. It also returns model usage data for persistence in `model_runs`. Cost estimation uses configured per-million token prices and should be updated if provider pricing changes.

## Reporter Guardrails

`GitHubReporter` verifies the current pull request head SHA before posting comments. If the PR head changed, it posts nothing.
Summary reviews include a hidden `<!-- code-review-bot -->` marker. If a marked bot review already exists for the same PR head SHA, the reporter skips posting another review for that head to reduce repeated-test noise.

Current behavior:

- skip stale head SHAs
- skip findings below `0.75` confidence
- skip already-posted duplicate findings for the same repo, PR, head SHA, path, line, and title
- post inline review comments only when the finding path and line are present as added lines in the pull request diff
- post issue summary comments when a finding cannot be placed inline from the local diff index
- fall back to the summary review when GitHub rejects an inline comment location with validation errors

Follow-up work should add nearest-added-line remapping for findings that point to nearby context lines and stale comment handling.

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
- `STALE_RUN_AFTER_MINUTES`
- `REVIEW_PIPELINE_PROVIDER`
- `MODEL_API_KEY`
- `MODEL_BASE_URL`
- `MODEL_NAME`
- `MODEL_MAX_TOKENS`
- `MODEL_INPUT_PRICE_PER_MILLION_TOKENS`
- `MODEL_OUTPUT_PRICE_PER_MILLION_TOKENS`

For Docker Compose, app services use `AWS_ENDPOINT_URL=http://localstack:4566` and `SQS_QUEUE_URL=http://localstack:4566/000000000000/code-review-jobs`.

Docker Compose mounts the ignored local `./.secrets` directory read-only at `/run/secrets`; the default private-key path is `/run/secrets/github-app-private-key.pem`. The private key may live inside the working directory for local development as long as it remains ignored by git and is never committed.

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
- Keep model output limited to review leads/findings. Model output must not trigger command execution.

Planned hardening:

- Container isolation for check execution.
- Secret redaction from command output before model prompts or persistence.
- SQS visibility extension during long reviews.
- Dead-letter queue redrive process.

## Known Gaps

- Inline comment positioning is basic and not diff-hunk-aware.
- Local sandboxing uses filesystem workspaces, not container isolation.
- The Anthropic path is a single JSON review gateway, not yet a multi-agent scout/reviewer/verifier workflow.
