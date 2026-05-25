from pathlib import Path

from code_review_app.review.models import (
    CheckResult,
    Finding,
    Lead,
    ModelUsage,
    ReviewPipelineResult,
    Workspace,
)
from code_review_app.review.worker import ReviewWorker
from code_review_app.storage import Storage


class FakeCheckout:
    def __init__(self) -> None:
        self.repo_url: str | None = None

    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        self.repo_url = repo_url
        return Workspace(
            path=Path("."),
            base_sha=base_sha,
            head_sha=head_sha,
            diff="""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 one
+two
 three
""",
        )


class FakeChecks:
    def run_checks(self, repo_path: Path, config) -> list[CheckResult]:
        return [
            CheckResult(
                name="unit",
                kind="tests",
                command="uv run pytest",
                exit_code=1,
                timed_out=False,
                duration_ms=20,
                output_excerpt="failed",
            )
        ]


class FakePipeline:
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        return ReviewPipelineResult(
            leads=[
                Lead(
                    file_path="app.py",
                    line=3,
                    suspicion="Suspicion",
                    related_rule_ids=["tests"],
                    suggested_context="failed",
                    status="verified",
                )
            ],
            findings=[
                Finding(
                    file_path="app.py",
                    line=3,
                    severity="medium",
                    title="Issue",
                    behavior_at_risk="Risk",
                    evidence="Evidence",
                    suggested_action="Fix",
                    confidence=0.9,
                )
            ],
        )


class FakeModelUsagePipeline(FakePipeline):
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        result = super().run(workspace, checks)
        return ReviewPipelineResult(
            leads=result.leads,
            findings=result.findings,
            model_usage=ModelUsage(
                provider="anthropic-compatible",
                model="MiniMax-M2.7",
                base_url="https://api.minimax.io/anthropic",
                input_tokens=1000,
                output_tokens=500,
                estimated_cost_usd=0.0009,
            ),
        )


class FakeReporter:
    def __init__(self) -> None:
        self.inline_locations = None

    def post_findings(
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        findings: list,
        inline_locations=None,
    ) -> list[str]:
        self.inline_locations = inline_locations
        return ["comment-1"]


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


def test_worker_persists_review_artifacts_and_logs_progress(
    tmp_path: Path, caplog
) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)
    worker = ReviewWorker(storage, FakeCheckout(), FakeChecks(), FakePipeline(), FakeReporter())

    with caplog.at_level("INFO"):
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

    artifacts = storage.get_review_artifacts(run["id"])
    assert artifacts["check_runs"][0]["name"] == "unit"
    assert artifacts["leads"][0]["suspicion"] == "Suspicion"
    assert artifacts["findings"][0]["posted_comment_id"] == "comment-1"
    assert "review job completed" in caplog.text


def test_worker_uses_injected_repo_url_builder(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)
    checkout = FakeCheckout()
    worker = ReviewWorker(
        storage,
        checkout,
        FakeChecks(),
        FakePipeline(),
        FakeReporter(),
        repo_url_builder=lambda job: f"tokenized:{job['repo_full_name']}",
    )

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

    assert checkout.repo_url == "tokenized:owner/repo"


def test_worker_passes_diff_index_to_reporter(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)
    reporter = FakeReporter()
    worker = ReviewWorker(storage, FakeCheckout(), FakeChecks(), FakePipeline(), reporter)

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

    assert reporter.inline_locations is not None
    assert reporter.inline_locations.has_right_line("app.py", 2)
    assert reporter.inline_locations.has_added_line("app.py", 2)


def test_worker_persists_model_usage(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 7, "base", "head", 42)
    worker = ReviewWorker(
        storage,
        FakeCheckout(),
        FakeChecks(),
        FakeModelUsagePipeline(),
        FakeReporter(),
    )

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

    artifacts = storage.get_review_artifacts(run["id"])
    assert artifacts["model_runs"][0]["model"] == "MiniMax-M2.7"
    assert artifacts["model_runs"][0]["input_tokens"] == 1000
    assert artifacts["model_runs"][0]["estimated_cost_usd"] == 0.0009
