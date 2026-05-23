from pathlib import Path

from code_review_app.review.models import CheckResult, Workspace
from code_review_app.review.pipeline import DeterministicReviewPipeline


def test_pipeline_creates_finding_for_failing_check() -> None:
    workspace = Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+print('x')")
    checks = [
        CheckResult(
            name="unit",
            kind="tests",
            command="uv run pytest",
            exit_code=1,
            timed_out=False,
            duration_ms=20,
            output_excerpt="tests/test_app.py::test_app FAILED",
        )
    ]

    result = DeterministicReviewPipeline().run(workspace, checks)

    assert result.findings[0].title == "Configured check failed: unit"
    assert result.findings[0].severity == "medium"
    assert "uv run pytest" in result.findings[0].evidence
