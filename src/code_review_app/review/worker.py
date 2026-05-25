from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Protocol

from code_review_app.review.diff import DiffIndex
from code_review_app.review.models import CheckResult, ReviewPipelineResult, Workspace
from code_review_app.sandbox.checks import load_review_config
from code_review_app.storage import Storage


logger = logging.getLogger(__name__)


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
        self,
        repo_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        findings: list,
        inline_locations: DiffIndex | None = None,
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
        repo_url_builder: Callable[[dict], str] | None = None,
    ) -> None:
        self.storage = storage
        self.checkout = checkout
        self.checks = checks
        self.pipeline = pipeline
        self.reporter = reporter
        self.repo_url_builder = repo_url_builder or self.default_repo_url

    def handle_job(self, job: dict) -> None:
        review_run_id = int(job["review_run_id"])
        logger.info("review job received", extra={"review_run_id": review_run_id})
        self.storage.update_review_run_status(review_run_id, "running")
        try:
            repo_url = self.repo_url_builder(job)
            logger.info("preparing workspace", extra={"review_run_id": review_run_id})
            workspace = self.checkout.prepare(
                repo_url=repo_url,
                review_run_id=review_run_id,
                base_sha=str(job["base_sha"]),
                head_sha=str(job["head_sha"]),
            )
            config = load_review_config(workspace.path)
            logger.info("running configured checks", extra={"review_run_id": review_run_id})
            check_results = self.checks.run_checks(workspace.path, config)
            self.storage.save_check_results(review_run_id, check_results)
            logger.info("running review pipeline", extra={"review_run_id": review_run_id})
            result = self.pipeline.run(workspace, check_results)
            self.storage.save_leads(review_run_id, result.leads)
            self.storage.save_findings(review_run_id, result.findings)
            if result.model_usage is not None:
                self.storage.save_model_usage(review_run_id, result.model_usage)
            logger.info("posting review findings", extra={"review_run_id": review_run_id})
            inline_locations = DiffIndex.from_unified_diff(workspace.diff)
            logger.info(
                "computed inline comment locations files=%s added_lines=%s right_side_lines=%s",
                inline_locations.file_count,
                inline_locations.added_line_count,
                inline_locations.right_line_count,
                extra={"review_run_id": review_run_id},
            )
            posted_comment_ids = self.reporter.post_findings(
                str(job["repo_full_name"]),
                int(job["pr_number"]),
                str(job["head_sha"]),
                result.findings,
                inline_locations,
            )
            self.storage.mark_findings_posted(review_run_id, posted_comment_ids)
            self.storage.update_review_run_status(
                review_run_id, "completed", conclusion="reviewed"
            )
            logger.info("review job completed", extra={"review_run_id": review_run_id})
        except Exception as exc:
            self.storage.update_review_run_status(review_run_id, "failed", conclusion=str(exc))
            logger.exception("review job failed", extra={"review_run_id": review_run_id})
            raise

    @staticmethod
    def default_repo_url(job: dict) -> str:
        return f"https://github.com/{job['repo_full_name']}.git"
