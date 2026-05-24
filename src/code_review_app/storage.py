from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from code_review_app.review.models import CheckResult, Finding, Lead


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
                """
                UPDATE review_runs
                SET
                    status = ?,
                    conclusion = ?,
                    started_at = CASE
                        WHEN ? = 'running' AND started_at IS NULL THEN CURRENT_TIMESTAMP
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN ? IN ('completed', 'failed') THEN CURRENT_TIMESTAMP
                        ELSE finished_at
                    END,
                    latency_ms = CASE
                        WHEN ? IN ('completed', 'failed') AND started_at IS NOT NULL
                        THEN CAST(
                            (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400000
                            AS INTEGER
                        )
                        ELSE latency_ms
                    END
                WHERE id = ?
                """,
                (status, conclusion, status, status, status, review_run_id),
            )

    def mark_incomplete_runs_stale(self, older_than_minutes: int) -> int:
        age_filter = ""
        params: tuple[Any, ...] = ()
        if older_than_minutes > 0:
            age_filter = """
                AND COALESCE(started_at, created_at)
                    <= datetime('now', '-' || ? || ' minutes')
            """
            params = (older_than_minutes,)

        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE review_runs
                SET
                    status = 'failed',
                    conclusion = 'stale incomplete run',
                    stale = 1,
                    finished_at = CURRENT_TIMESTAMP
                WHERE status IN ('queued', 'running')
                {age_filter}
                """,
                params,
            )
            return int(cursor.rowcount)

    def save_check_results(self, review_run_id: int, checks: list[CheckResult]) -> list[int]:
        with self.connect() as connection:
            ids: list[int] = []
            for check in checks:
                cursor = connection.execute(
                    """
                    INSERT INTO check_runs (
                        review_run_id, name, kind, command, exit_code,
                        timed_out, duration_ms, output_excerpt
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_run_id,
                        check.name,
                        check.kind,
                        check.command,
                        check.exit_code,
                        int(check.timed_out),
                        check.duration_ms,
                        check.output_excerpt,
                    ),
                )
                ids.append(int(cursor.lastrowid))
            return ids

    def save_leads(self, review_run_id: int, leads: list[Lead]) -> list[int]:
        with self.connect() as connection:
            ids: list[int] = []
            for lead in leads:
                cursor = connection.execute(
                    """
                    INSERT INTO leads (
                        review_run_id, file_path, line, suspicion,
                        related_rule_ids, suggested_context, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_run_id,
                        lead.file_path,
                        lead.line,
                        lead.suspicion,
                        json.dumps(lead.related_rule_ids),
                        lead.suggested_context,
                        lead.status,
                    ),
                )
                ids.append(int(cursor.lastrowid))
            return ids

    def save_findings(self, review_run_id: int, findings: list[Finding]) -> list[int]:
        with self.connect() as connection:
            ids: list[int] = []
            for finding in findings:
                cursor = connection.execute(
                    """
                    INSERT INTO findings (
                        review_run_id, file_path, line, severity, title,
                        behavior_at_risk, evidence, suggested_action,
                        confidence, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        review_run_id,
                        finding.file_path,
                        finding.line,
                        finding.severity,
                        finding.title,
                        finding.behavior_at_risk,
                        finding.evidence,
                        finding.suggested_action,
                        finding.confidence,
                    ),
                )
                ids.append(int(cursor.lastrowid))
            return ids

    def mark_findings_posted(self, review_run_id: int, posted_comment_ids: list[str]) -> None:
        if not posted_comment_ids:
            return
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM findings
                WHERE review_run_id = ? AND posted_comment_id IS NULL
                ORDER BY id
                LIMIT ?
                """,
                (review_run_id, len(posted_comment_ids)),
            ).fetchall()
            for row, comment_id in zip(rows, posted_comment_ids, strict=False):
                connection.execute(
                    """
                    UPDATE findings
                    SET posted_comment_id = ?, status = 'posted'
                    WHERE id = ?
                    """,
                    (comment_id, int(row["id"])),
                )

    def get_review_artifacts(self, review_run_id: int) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as connection:
            check_runs = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM check_runs WHERE review_run_id = ? ORDER BY id",
                    (review_run_id,),
                )
            ]
            leads = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM leads WHERE review_run_id = ? ORDER BY id",
                    (review_run_id,),
                )
            ]
            findings = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM findings WHERE review_run_id = ? ORDER BY id",
                    (review_run_id,),
                )
            ]
        return {"check_runs": check_runs, "leads": leads, "findings": findings}

    def has_posted_finding(
        self,
        repo_full_name: str,
        pr_number: int,
        head_sha: str,
        file_path: str,
        line: int,
        title: str,
    ) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM findings
                JOIN review_runs ON review_runs.id = findings.review_run_id
                WHERE review_runs.repo_full_name = ?
                    AND review_runs.pr_number = ?
                    AND review_runs.head_sha = ?
                    AND findings.file_path = ?
                    AND findings.line = ?
                    AND findings.title = ?
                    AND findings.posted_comment_id IS NOT NULL
                LIMIT 1
                """,
                (repo_full_name, pr_number, head_sha, file_path, line, title),
            ).fetchone()
        return row is not None
