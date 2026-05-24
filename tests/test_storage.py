from pathlib import Path

from code_review_app.review.models import CheckResult, Finding, Lead
from code_review_app.storage import Storage


def test_storage_creates_review_run(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()

    run = storage.create_review_run(
        repo_full_name="owner/repo",
        pr_number=12,
        base_sha="base",
        head_sha="head",
        installation_id=99,
    )

    loaded = storage.get_review_run(run["id"])
    assert loaded["repo_full_name"] == "owner/repo"
    assert loaded["status"] == "queued"
    assert loaded["stale"] == 0


def test_storage_marks_existing_run_stale_for_new_head(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    first = storage.create_review_run("owner/repo", 12, "base", "old", 99)
    second = storage.create_review_run("owner/repo", 12, "base", "new", 99)

    storage.mark_other_runs_stale("owner/repo", 12, "new")

    assert storage.get_review_run(first["id"])["stale"] == 1
    assert storage.get_review_run(second["id"])["stale"] == 0


def test_storage_updates_timestamps_and_marks_old_incomplete_runs_stale(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 12, "base", "head", 99)

    storage.update_review_run_status(run["id"], "running")
    storage.mark_incomplete_runs_stale(older_than_minutes=0)

    loaded = storage.get_review_run(run["id"])
    assert loaded["status"] == "failed"
    assert loaded["conclusion"] == "stale incomplete run"
    assert loaded["started_at"] is not None
    assert loaded["finished_at"] is not None


def test_storage_persists_review_artifacts_and_posted_comment_ids(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 12, "base", "head", 99)

    storage.save_check_results(
        run["id"],
        [
            CheckResult(
                name="unit",
                kind="tests",
                command="uv run pytest",
                exit_code=1,
                timed_out=False,
                duration_ms=20,
                output_excerpt="failed",
            )
        ],
    )
    storage.save_leads(
        run["id"],
        [
            Lead(
                file_path="app.py",
                line=4,
                suspicion="Unhandled error",
                related_rule_ids=["tests"],
                suggested_context="traceback",
                status="verified",
            )
        ],
    )
    finding_ids = storage.save_findings(
        run["id"],
        [
            Finding(
                file_path="app.py",
                line=4,
                severity="medium",
                title="Issue",
                behavior_at_risk="Risk",
                evidence="Evidence",
                suggested_action="Fix",
                confidence=0.9,
            )
        ],
    )
    storage.mark_findings_posted(run["id"], ["comment-1"])

    artifacts = storage.get_review_artifacts(run["id"])
    assert artifacts["check_runs"][0]["name"] == "unit"
    assert artifacts["leads"][0]["suspicion"] == "Unhandled error"
    assert artifacts["findings"][0]["id"] == finding_ids[0]
    assert artifacts["findings"][0]["posted_comment_id"] == "comment-1"


def test_storage_detects_existing_posted_finding(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    run = storage.create_review_run("owner/repo", 12, "base", "head", 99)
    storage.save_findings(
        run["id"],
        [
            Finding(
                file_path="app.py",
                line=4,
                severity="medium",
                title="Issue",
                behavior_at_risk="Risk",
                evidence="Evidence",
                suggested_action="Fix",
                confidence=0.9,
            )
        ],
    )
    storage.mark_findings_posted(run["id"], ["comment-1"])

    assert storage.has_posted_finding("owner/repo", 12, "head", "app.py", 4, "Issue")
