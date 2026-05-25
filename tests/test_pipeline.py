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


def test_pipeline_summarizes_long_check_output_in_finding_evidence() -> None:
    workspace = Workspace(path=Path("."), base_sha="base", head_sha="head", diff="+print('x')")
    checks = [
        CheckResult(
            name="typescript",
            kind="types",
            command="npm exec tsc -- --noEmit",
            exit_code=2,
            timed_out=False,
            duration_ms=20,
            output_excerpt="\n".join(
                [
                    "src/a.ts(1,1): error TS6133: 'a' is declared but never read.",
                    "src/b.ts(1,1): error TS6133: 'b' is declared but never read.",
                    "src/c.ts(1,1): error TS6133: 'c' is declared but never read.",
                    "src/d.ts(1,1): error TS6133: 'd' is declared but never read.",
                    "src/e.ts(1,1): error TS6133: 'e' is declared but never read.",
                ]
            ),
        )
    ]

    result = DeterministicReviewPipeline().run(workspace, checks)

    evidence = result.findings[0].evidence
    assert "5 output lines" in evidence
    assert "src/a.ts" in evidence
    assert "src/c.ts" in evidence
    assert "src/d.ts" not in evidence
    assert "Full check output is stored in SQLite" in evidence
