from __future__ import annotations

from pathlib import Path
from typing import Protocol

from code_review_app.review.models import CheckResult, ReviewPipelineResult, Workspace
from code_review_app.sandbox.checks import load_review_config
from code_review_app.storage import Storage


class CheckoutProtocol(Protocol):
    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        raise NotImplementedError


class CheckRunnerProtocol(Protocol):
    def run_checks(self, repo_path: Path, config) -> list[CheckResult]:
        raise NotImplementedError


class PipelineProtocol(Protocol):
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        raise NotImplementedError


class ReporterProtocol(Protocol):
    def post_findings(
        self, repo_full_name: str, pr_number: int, expected_head_sha: str, findings: list
    ) -> list[str]:
        raise NotImplementedError


class ReviewWorker:
    def __init__(
        self,
        storage: Storage,
        checkout: CheckoutProtocol,
        checks: CheckRunnerProtocol,
        pipeline: PipelineProtocol,
        reporter: ReporterProtocol,
    ) -> None:
        self.storage = storage
        self.checkout = checkout
        self.checks = checks
        self.pipeline = pipeline
        self.reporter = reporter

    def handle_job(self, job: dict) -> None:
        review_run_id = int(job["review_run_id"])
        self.storage.update_review_run_status(review_run_id, "running")
        try:
            repo_url = f"https://github.com/{job['repo_full_name']}.git"
            workspace = self.checkout.prepare(
                repo_url=repo_url,
                review_run_id=review_run_id,
                base_sha=str(job["base_sha"]),
                head_sha=str(job["head_sha"]),
            )
            config = load_review_config(workspace.path)
            check_results = self.checks.run_checks(workspace.path, config)
            result = self.pipeline.run(workspace, check_results)
            self.reporter.post_findings(
                str(job["repo_full_name"]),
                int(job["pr_number"]),
                str(job["head_sha"]),
                result.findings,
            )
            self.storage.update_review_run_status(
                review_run_id, "completed", conclusion="reviewed"
            )
        except Exception as exc:
            self.storage.update_review_run_status(review_run_id, "failed", conclusion=str(exc))
            raise
