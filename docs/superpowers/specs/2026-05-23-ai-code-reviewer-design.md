# AI Code Reviewer GitHub App Design

## Purpose

Build a single-tenant GitHub App that automatically reviews pull requests for one organization. The service should catch high-value issues that normal CI and human reviewers often miss: suspicious deletions, cross-boundary drift, silent behavior changes, missing test coverage, security-sensitive mistakes, and contract violations.

The system should optimize for trust. It should post fewer comments, but each posted finding must be specific, grounded in evidence, and useful to the author.

## Scope

The first version reviews GitHub pull requests and posts findings as PR review comments.

Included:

- GitHub App webhook handling for pull request events.
- Asynchronous review jobs.
- Ephemeral sandbox checkout per review.
- Configured static analysis and test execution.
- Review profiles that encode repo-specific and domain-specific rules.
- A staged AI review pipeline: scout, deep review, verification, reporting.
- Persistence for review runs, checks, leads, findings, costs, and timings.

Not included in v1:

- Multi-tenant installation support.
- Billing.
- Auto-fixing or pushing commits.
- Arbitrary model-invented shell commands.
- Slack or incident-history mining.
- Full continuous evaluation harness.

## Architecture

```text
GitHub PR opened / synchronized / reopened
  -> Webhook service
  -> Review coordinator
  -> Job queue
  -> Review worker
  -> Ephemeral sandbox
      -> clone repository
      -> checkout base and head
      -> compute diff
      -> collect surrounding context
      -> run allowlisted static checks
      -> run allowlisted tests
  -> Profile router
  -> Lead scout agent
  -> Deep reviewer agents
  -> Evidence verifier
  -> Reporter guardrails
  -> GitHub PR review comments
```

The core design mirrors a strong human review loop: notice suspicious changes first, investigate only the promising leads, try to disprove each claim, and post only comments that survive verification.

## Components

### Webhook Service

The webhook service is a FastAPI application that receives GitHub App webhook events. It verifies the GitHub signature, filters to supported pull request actions, records an incoming event, and enqueues a review job.

Supported initial events:

- `pull_request.opened`
- `pull_request.reopened`
- `pull_request.synchronize`
- Optional manual rerun via `issue_comment` command later.

The webhook request path should return quickly. Review work happens in workers, not inside the HTTP request.

### Review Coordinator

The coordinator deduplicates and schedules review jobs. For a given repository, pull request number, and head SHA, only one active review should run. If a newer commit arrives while an older review is running, the older run should be marked stale and prevented from posting comments.

Responsibilities:

- Create `ReviewRun` records.
- Enqueue jobs.
- Cancel or mark stale older runs.
- Apply repo allowlist policy.
- Track status transitions.

### Job Queue

The queue decouples GitHub webhooks from review execution. A simple first implementation can use Redis with RQ, Celery, or Dramatiq. The queue should support retries, job timeouts, and worker concurrency limits.

The queue payload should be small:

- Repository owner/name.
- Pull request number.
- Base SHA.
- Head SHA.
- Installation ID.
- Review run ID.

### Ephemeral Sandbox

Each review runs in an isolated workspace. The sandbox checks out the repository at the pull request head, fetches the base commit, and stores artifacts under the review run.

The v1 sandbox is allowed to:

- Clone and fetch the target repository.
- Read files.
- Search files.
- Compute diffs.
- Run configured commands from trusted repo configuration.

The v1 sandbox is not allowed to:

- Run arbitrary commands invented by the model.
- Push commits.
- Access secrets beyond the GitHub App token needed for checkout.
- Mutate shared host state.

The initial implementation can use a temporary directory on a controlled worker host. Container isolation should be added before running this across untrusted repositories or with broader command permissions.

### Static Analysis And Test Runner

Checks are configured per repository. They provide evidence to the reviewer, but they do not replace AI review.

Example:

```yaml
review:
  checks:
    static:
      - name: ruff
        command: uv run ruff check .
        timeout_seconds: 120
      - name: mypy
        command: uv run mypy .
        timeout_seconds: 180
    tests:
      - name: unit
        command: uv run pytest
        timeout_seconds: 300
```

The runner records command, exit code, timeout status, duration, and output excerpts. Long output should be truncated and stored as an artifact. Posted comments should quote only the relevant failure lines.

Command execution must be allowlisted. Review profiles may suggest which configured checks are relevant, but the model cannot create new shell commands in v1.

### Profile Router

The profile router selects a small set of review profiles for each PR. Profiles contain only review-relevant knowledge: architecture boundaries, anti-patterns, contract rules, risky migration patterns, and incident-derived lessons.

Profiles should not include setup instructions, general style advice, or rules already covered by CI.

Example:

```yaml
name: API Contract Review
description: Rules for changes that affect request, response, or client contract behavior.
path_patterns:
  - "api/**"
  - "clients/**"
rules:
  - id: API_CONTRACT_DRIFT
    severity: high
    description: >
      When one side of an API boundary changes, callers, generated clients,
      docs, and contract tests must be checked for matching updates.
    evidence: >
      Past changes to response semantics without client updates caused runtime
      failures despite passing unit tests.
    suggested_checks:
      - unit
```

Routing should prefer precision over volume. A PR should load the profiles that actually apply to the touched files and changed behavior, not the entire rule corpus.

### Lead Scout Agent

The scout reads the diff, selected profiles, and lightweight context. It does not post comments and does not decide final correctness. Its job is to produce investigation leads.

Good leads include:

- A deletion that may remove behavior depended on elsewhere.
- A changed enum or branch that may not be handled by siblings.
- A semantic change that leaves types and signatures unchanged.
- A contract change where clients or tests may not have been updated.
- A security-sensitive path that needs deeper inspection.
- A new or changed behavior that appears untested.

Scout output should be structured JSON with file, line, suspicion, relevant profile rules, and suggested context to inspect.

### Deep Reviewer Agents

Deep reviewers investigate scout leads using full repository context, diff context, selected profiles, and check results. They should verify evidence rather than generate broad advice.

The initial system can run one deep reviewer. A second reviewer can be added for high-risk PRs or high-severity leads to reduce false positives.

Reviewer responsibilities:

- Inspect surrounding files.
- Trace callers and callees where relevant.
- Compare sibling implementations.
- Connect check output to changed code.
- Produce candidate findings with evidence.
- Drop leads that are speculative or harmless.

### Evidence Verifier

The verifier tries to falsify each candidate finding. This is a separate step so that the system does not post plausible but weak claims.

A finding should be dropped when:

- The cited behavior is already handled elsewhere.
- The issue is only general advice.
- The evidence cannot be tied to changed lines.
- The issue is already reported by a configured check without additional value.
- The suggested action is unclear.
- The PR changed after analysis began.

Surviving findings should include:

- File and line.
- Severity.
- Clear title.
- Concrete behavior at risk.
- Evidence from code, diff, profile rule, or check output.
- Suggested starting point for the author.

### Reporter Guardrails

The reporter converts verified findings into GitHub review comments. It should be conservative.

Guardrails:

- Post inline comments only on changed lines when possible.
- Avoid broad summary-only comments in v1.
- Do not post a false clean review if internal analysis found unreported high-severity findings.
- Do not post stale findings if the head SHA changed.
- Collapse or resolve older bot comments on rerun when possible.
- Avoid duplicate comments across repeated reviews.
- Use direct language, not hedged speculation.

## Data Model

### ReviewRun

- `id`
- `repo_full_name`
- `pr_number`
- `base_sha`
- `head_sha`
- `installation_id`
- `status`
- `started_at`
- `finished_at`
- `latency_ms`
- `cost_estimate_cents`
- `conclusion`
- `stale`

### CheckRun

- `id`
- `review_run_id`
- `name`
- `kind`
- `command`
- `exit_code`
- `timed_out`
- `duration_ms`
- `output_excerpt`
- `artifact_path`

### Lead

- `id`
- `review_run_id`
- `file_path`
- `line`
- `suspicion`
- `related_rule_ids`
- `suggested_context`
- `status`

### Finding

- `id`
- `review_run_id`
- `lead_id`
- `file_path`
- `line`
- `severity`
- `title`
- `behavior_at_risk`
- `evidence`
- `suggested_action`
- `confidence`
- `status`
- `posted_comment_id`

## Error Handling

Webhook errors should be limited to signature validation, malformed payloads, and unsupported events. Review failures should be recorded on the `ReviewRun`.

Expected failure modes:

- GitHub checkout fails.
- Repo config is missing or invalid.
- Static check times out.
- Test command fails.
- Model returns invalid structured output.
- Worker exceeds timeout.
- PR head SHA changes during review.
- GitHub comment API fails.

Timeout policy:

- Overall review timeout.
- Per-command timeout.
- Per-agent soft timeout.
- Per-agent hard timeout.

On soft timeout, an agent should stop investigating, drop speculative leads, and return only already-verified findings. On hard timeout before reporting, the run should finish with a failed status and post no comments. On hard timeout during reporting, the run should record which comments were posted and mark the remaining findings as unposted.

## Security

The service is single-tenant, but it still needs strict boundaries.

Controls:

- Verify every GitHub webhook signature.
- Use GitHub App installation tokens with least privilege.
- Allowlist repositories.
- Run only configured commands.
- Redact secrets from command output before storing or prompting models.
- Store minimal artifacts.
- Do not expose sandbox filesystem paths in public comments.
- Do not let model output directly choose shell commands.
- Keep model prompts free of credentials.

Recommended GitHub permissions:

- Pull requests: read/write.
- Contents: read.
- Metadata: read.
- Checks: read if needed.
- Issues: read/write only if supporting issue comment commands.

## Metrics

The core production signal is whether humans act on posted findings. For v1, collect enough data to measure quality later.

Metrics:

- Reviews started, completed, failed, and stale.
- Time from PR event to comments posted.
- Cost estimate per review.
- Number of leads created.
- Number of leads dropped.
- Number of findings posted.
- Comment deduplication rate.
- Check pass/fail/timeout rate.
- Author action rate when detectable.

## Evaluation Plan

The first eval set should be small and real. Use historical PRs where a human caught a meaningful issue, an incident was caused by review miss, or a risky pattern is known.

Each eval case should include:

- Repository fixture or snapshot.
- Base and head SHAs.
- Expected issue description.
- Expected file or area.
- Acceptable evidence.
- False positive notes.

The eval harness should run the full staged pipeline and report:

- Did the system find the expected issue?
- Did it avoid known false positives?
- How much did the review cost?
- How long did it take?
- Which stage dropped or created the decisive lead?

## Initial Implementation Order

1. Create the GitHub App webhook service and signature verification.
2. Add persistent `ReviewRun` storage and a queue.
3. Implement checkout and diff collection in an ephemeral workspace.
4. Add repo review config parsing and allowlisted check execution.
5. Add review profile loading and routing.
6. Implement scout structured output.
7. Implement deep reviewer structured output.
8. Implement evidence verification.
9. Implement reporter guardrails and GitHub inline comments.
10. Add metrics and basic eval fixtures.

## V1 Defaults

- Use PostgreSQL for persistent state.
- Use Redis Queue for asynchronous jobs.
- Use a small model gateway interface so review stages are model-agnostic from the start.
- Use temporary-directory sandbox workspaces on a controlled worker host for the first implementation.
- Run one deep reviewer by default.
- Add a second deep reviewer only for high-severity leads once the single-reviewer path is working.
- On rerun, post comments only for the current head SHA and avoid deleting old comments until stale-comment handling is explicitly implemented.
