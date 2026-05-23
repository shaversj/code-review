from __future__ import annotations

from typing import Protocol

from code_review_app.storage import Storage


class ReviewQueue(Protocol):
    def enqueue_review_job(self, payload: dict) -> str:
        raise NotImplementedError


class ReviewCoordinator:
    def __init__(self, storage: Storage, queue: ReviewQueue, allowed_repos: set[str]) -> None:
        self.storage = storage
        self.queue = queue
        self.allowed_repos = allowed_repos

    def handle_pull_request_event(self, payload: dict) -> int | None:
        repo_full_name = payload["repository"]["full_name"]
        if repo_full_name not in self.allowed_repos:
            return None

        pull_request = payload["pull_request"]
        pr_number = int(pull_request["number"])
        head_sha = pull_request["head"]["sha"]
        run = self.storage.create_review_run(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            base_sha=pull_request["base"]["sha"],
            head_sha=head_sha,
            installation_id=int(payload["installation"]["id"]),
        )
        self.storage.mark_other_runs_stale(repo_full_name, pr_number, head_sha)

        self.queue.enqueue_review_job(
            {
                "review_run_id": run["id"],
                "repo_full_name": repo_full_name,
                "pr_number": pr_number,
                "base_sha": pull_request["base"]["sha"],
                "head_sha": head_sha,
                "installation_id": int(payload["installation"]["id"]),
            }
        )
        return int(run["id"])
