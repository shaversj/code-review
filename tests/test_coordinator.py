from pathlib import Path

from code_review_app.review.coordinator import ReviewCoordinator
from code_review_app.storage import Storage


class FakeQueue:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def enqueue_review_job(self, payload: dict) -> str:
        self.payloads.append(payload)
        return "msg-1"


def payload(repo: str = "owner/repo") -> dict:
    return {
        "installation": {"id": 42},
        "repository": {"full_name": repo},
        "pull_request": {
            "number": 7,
            "base": {"sha": "base"},
            "head": {"sha": "head"},
        },
    }


def test_coordinator_creates_review_run_and_enqueues_job(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    queue = FakeQueue()
    coordinator = ReviewCoordinator(storage, queue, allowed_repos={"owner/repo"})

    review_run_id = coordinator.handle_pull_request_event(payload())

    assert review_run_id == 1
    assert queue.payloads == [
        {
            "review_run_id": 1,
            "repo_full_name": "owner/repo",
            "pr_number": 7,
            "base_sha": "base",
            "head_sha": "head",
            "installation_id": 42,
        }
    ]


def test_coordinator_ignores_unallowed_repo(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "review.db")
    storage.initialize()
    queue = FakeQueue()
    coordinator = ReviewCoordinator(storage, queue, allowed_repos={"owner/repo"})

    assert coordinator.handle_pull_request_event(payload("other/repo")) is None
    assert queue.payloads == []
