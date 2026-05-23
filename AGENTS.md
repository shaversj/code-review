# AGENTS.md

## Project Overview

AI Code Reviewer is a Python service for automated pull request review. It is a single-tenant GitHub App/webhook service that records PR review runs, queues work through SQS, checks out pull request code, runs allowlisted repo checks, and posts guarded GitHub review comments.

The intended architecture is staged review:

- FastAPI webhook receives GitHub pull request events
- SQLite stores review runs and related metadata
- SQS carries review jobs
- Worker checks out the PR and runs configured checks
- Deterministic pipeline currently creates findings from failed checks
- Future Anthropic-backed scout/reviewer/verifier/reporter stages will replace or extend the deterministic pipeline

## Current Project State

- Python package: `code-review-app` version `0.1.0`
- Python runtime target: `>=3.12`
- Main framework: FastAPI + Uvicorn
- Local/prototype persistence: SQLite with WAL mode
- Queue backend: SQS-compatible API
- Local SQS development: LocalStack through Docker Compose
- Test framework: pytest
- Linting: Ruff
- Dependency manager: uv
- Docker Compose starts `api`, `worker`, and `localstack`
- LocalStack creates the `code-review-jobs` queue from `localstack/init/ready.d/create-sqs.sh`
- The worker CLI currently receives SQS messages and deletes them; full `ReviewWorker` wiring is implemented as a unit-tested boundary but not yet connected to the CLI loop
- GitHub App installation-token generation is not implemented yet
- Anthropic is the selected first model provider, but model-backed review stages are not implemented yet

## Commands

```bash
uv sync --extra dev              # Install local development dependencies
./init.sh                        # Standard verification path
uv run pytest -q                 # Run tests
uv run ruff check .              # Run lint
docker compose config --quiet    # Validate Docker Compose config
docker compose up --build        # Start API, worker, and LocalStack
docker compose down              # Stop local stack
```

Direct local API and worker:

```bash
uv run uvicorn code_review_app.main:create_app --factory --reload
uv run code-review-worker
```

Local health checks:

```bash
curl http://localhost:8000/healthz

aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text
```

## Environment Variables

Required by the app:

- `GITHUB_APP_ID`
- `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_ALLOWED_REPOS`
- `SQS_QUEUE_URL`

Common local defaults:

- `APP_ENV=development`
- `DATABASE_PATH=./code-review.db`
- `AWS_REGION=us-east-1`
- `AWS_ENDPOINT_URL=http://localhost:4566` or `http://localstack:4566` inside Compose
- `AWS_ACCESS_KEY_ID=test`
- `AWS_SECRET_ACCESS_KEY=test`
- `SQS_VISIBILITY_TIMEOUT_SECONDS=900`
- `SANDBOX_ROOT=./.sandboxes`

## Documentation Lookup

Use the `ctx7` CLI to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service. This includes FastAPI, boto3, AWS SQS, LocalStack, Docker Compose, Terraform, Anthropic, GitHub Apps, uv, pytest, Ruff, and similar tools.

Steps:

1. Resolve library:

   ```bash
   npx ctx7@latest library <name> "<user's full question>"
   ```

2. Pick the best match using exact name, relevance, snippet count, source reputation, and benchmark score.
3. Fetch docs:

   ```bash
   npx ctx7@latest docs <libraryId> "<user's full question>"
   ```

4. Answer or implement using the fetched documentation.

Do not use Context7 for refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

If a Context7 command fails with a quota error, tell the user and suggest `npx ctx7@latest login` or setting `CONTEXT7_API_KEY`.

## Startup Workflow

Before writing code:

1. Confirm working directory with `pwd`
2. Read this file completely
3. Read `README.md`
4. Review the architecture and plan docs in `docs/superpowers/`
5. Review recent commits with `git log --oneline -5`
6. Run baseline verification:

   ```bash
   ./init.sh
   ```

If baseline verification fails, repair that first before adding new scope.

## Working Rules

- Keep changes scoped to the requested feature or fix.
- Prefer existing boundaries: `github/`, `queue/`, `review/`, `sandbox/`, `storage.py`, and `config.py`.
- Use tests first for behavior changes.
- Do not claim completion without running the relevant verification commands.
- Do not let model output choose shell commands. Repo checks must come from allowlisted `.code-review.yml` entries.
- Do not add arbitrary command execution to the worker.
- Do not push code, create PRs, or modify remote infrastructure unless explicitly asked.
- Do not treat GitHub App auth or Anthropic integration as implemented; they are follow-up slices.
- Keep Docker Compose local-only. Production queue behavior should remain SQS-compatible.
- Update docs when changing local setup, environment variables, or runtime commands.

## Required Artifacts

- `README.md` — Local setup and operator commands
- `docker-compose.yml` — Local runtime for API, worker, and LocalStack
- `Dockerfile` — App image build
- `.env.example` — Environment variable template
- `init.sh` — Standard dependency sync and verification path
- `localstack/init/ready.d/create-sqs.sh` — LocalStack queue initialization
- `docs/superpowers/specs/2026-05-23-ai-code-reviewer-design.md` — Architecture spec
- `docs/superpowers/plans/2026-05-23-ai-code-reviewer-mvp.md` — MVP implementation plan
- `tests/` — Regression and contract tests

## Definition of Done

A change is done only when all relevant items are true:

- [ ] Target behavior is implemented
- [ ] Tests were added or updated for changed behavior
- [ ] `uv run pytest -q` ran successfully
- [ ] `uv run ruff check .` ran successfully
- [ ] `docker compose config --quiet` ran successfully when Compose files or env wiring changed
- [ ] README or docs were updated when commands, setup, or architecture changed
- [ ] Repository is left in a clean, restartable state

## Verification Commands

Full local verification:

```bash
./init.sh
```

For Docker runtime changes, also run:

```bash
docker compose up --build
curl http://localhost:8000/healthz
aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name code-review-jobs \
  --query QueueUrl \
  --output text
docker compose down
```

## Escalation

Ask the user or stop for review if you encounter:

- Architecture changes that affect the staged reviewer design
- New production infrastructure decisions
- GitHub App permission changes
- Sandbox security boundary changes
- Arbitrary command execution requests
- Anthropic/model prompt changes that affect review behavior
- Repeated test failures that are not explained by your current change
- Scope ambiguity between MVP plumbing and model-backed review behavior

## End of Session

Before ending a coding session:

1. Run relevant verification commands
2. Summarize what changed
3. Record any unresolved risks or next slices
4. Commit with a descriptive message once work is in a safe state
5. Leave the repo clean enough for the next session to start with the standard verification path
