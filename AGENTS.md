# AGENTS.md

## Purpose

This file is the agent operating guide for this repository. Keep project architecture, runtime topology, source layout, and known implementation gaps in `docs/ARCHITECTURE.md`; keep human-facing setup commands in `README.md`.

Agents should use this file to understand startup workflow, verification expectations, scope rules, and documentation lookup requirements.

## Required Reading

Before writing code:

1. Confirm working directory with `pwd`
2. Read this file completely
3. Read `README.md`
4. Read `docs/ARCHITECTURE.md`
5. Review the detailed design and plan docs in `docs/superpowers/`
6. Review recent commits with `git log --oneline -5`
7. Run baseline verification with `./init.sh`

If baseline verification fails, repair that first before adding new scope.

## Commands

Standard verification:

```bash
./init.sh
```

Common development commands:

```bash
docker compose up --build
docker compose down
uv run pytest -q
uv run ruff check .
docker compose config --quiet
```

See `README.md` for local setup, Docker Compose usage, direct local API/worker commands, and local health checks.

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

## Working Rules

- Keep changes scoped to the requested feature or fix.
- Prefer the boundaries described in `docs/ARCHITECTURE.md`.
- Use tests first for behavior changes.
- Do not claim completion without running the relevant verification commands.
- Do not let model output choose shell commands. Repo checks must come from allowlisted `.code-review.yml` entries.
- Do not add arbitrary command execution to the worker.
- Do not push code, create PRs, or modify remote infrastructure unless explicitly asked.
- Do not treat planned gaps listed in `docs/ARCHITECTURE.md` as implemented.
- Keep Docker Compose local-only. Production queue behavior should remain SQS-compatible.
- Update `README.md` when changing local setup or commands.
- Update `docs/ARCHITECTURE.md` when changing architecture, runtime topology, boundaries, configuration, security assumptions, or known gaps.

## Required Artifacts

- `README.md` — Local setup and operator commands
- `docs/ARCHITECTURE.md` — Current architecture, implementation boundaries, and known gaps
- `init.sh` — Standard dependency sync and verification path
- `docker-compose.yml` — Local runtime for API, worker, and LocalStack
- `Dockerfile` — App image build
- `.env.example` — Environment variable template
- `localstack/init/ready.d/create-sqs.sh` — LocalStack queue initialization
- `docs/superpowers/specs/2026-05-23-ai-code-reviewer-design.md` — Detailed design spec
- `docs/superpowers/plans/2026-05-23-ai-code-reviewer-mvp.md` — MVP implementation plan
- `tests/` — Regression and contract tests

## Definition of Done

A change is done only when all relevant items are true:

- [ ] Target behavior is implemented
- [ ] Tests were added or updated for changed behavior
- [ ] `./init.sh` ran successfully
- [ ] Docker runtime changes were checked with `docker compose up --build` when relevant
- [ ] README or architecture docs were updated when commands, setup, boundaries, or runtime behavior changed
- [ ] Repository is left in a clean, restartable state

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
3. Record unresolved risks or next slices in the right doc
4. Commit with a descriptive message once work is in a safe state
5. Leave the repo clean enough for the next session to start with `./init.sh`
