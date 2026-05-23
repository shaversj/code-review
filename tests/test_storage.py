from pathlib import Path

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
