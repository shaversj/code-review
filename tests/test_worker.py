from pathlib import Path

from code_review_app.review.models import CheckResult, ReviewPipelineResult, Workspace
from code_review_app.review.worker import ReviewWorker
from code_review_app.storage import Storage


class FakeCheckout:
    def prepare(self, repo_url: str, review_run_id: int, base_sha: str, head_sha: str) -> Workspace:
        return Workspace(path=Path("."), base_sha=base_sha, head_sha=head_sha, diff="+x")


class FakeChecks:
    def run_checks(self, repo_path: Path, config) -> list[CheckResult]:
        return []


class FakePipeline:
    def run(self, workspace: Workspace, checks: list[CheckResult]) -> ReviewPipelineResult:
        return ReviewPipelineResult(leads=[], findings=[])


class FakeReporter:
    def post_findings(
        self, repo_full_name: str, pr_number: int, expected_head_sha: str, findings: list
    ) -> list[str]:
        return []


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
