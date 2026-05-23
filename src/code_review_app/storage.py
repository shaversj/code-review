from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    base_sha TEXT NOT NULL,
                    head_sha TEXT NOT NULL,
                    installation_id INTEGER NOT NULL,
                    queue_message_id TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    latency_ms INTEGER,
                    cost_estimate_cents INTEGER DEFAULT 0,
                    conclusion TEXT,
                    stale INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS check_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    command TEXT NOT NULL,
                    exit_code INTEGER,
                    timed_out INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL,
                    output_excerpt TEXT NOT NULL,
                    artifact_path TEXT
                );

                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    suspicion TEXT NOT NULL,
                    related_rule_ids TEXT NOT NULL,
                    suggested_context TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_run_id INTEGER NOT NULL REFERENCES review_runs(id),
                    lead_id INTEGER REFERENCES leads(id),
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    behavior_at_risk TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    suggested_action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    posted_comment_id TEXT
                );
                """
            )

    def create_review_run(
        self,
        repo_full_name: str,
        pr_number: int,
        base_sha: str,
        head_sha: str,
        installation_id: int,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO review_runs (
                    repo_full_name, pr_number, base_sha, head_sha,
                    installation_id, status
                )
                VALUES (?, ?, ?, ?, ?, 'queued')
                """,
                (repo_full_name, pr_number, base_sha, head_sha, installation_id),
            )
            row = connection.execute(
                "SELECT * FROM review_runs WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
        if row is None:
            raise RuntimeError("inserted review run could not be loaded")
        return dict(row)

    def get_review_run(self, review_run_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM review_runs WHERE id = ?",
                (review_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"review run not found: {review_run_id}")
        return dict(row)

    def mark_other_runs_stale(self, repo_full_name: str, pr_number: int, head_sha: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE review_runs
                SET stale = 1
                WHERE repo_full_name = ? AND pr_number = ? AND head_sha != ?
                """,
                (repo_full_name, pr_number, head_sha),
            )

    def update_review_run_status(
        self, review_run_id: int, status: str, conclusion: str | None = None
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE review_runs SET status = ?, conclusion = ? WHERE id = ?",
                (status, conclusion, review_run_id),
            )
