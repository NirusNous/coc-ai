from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.config import DATABASE_PATH


_UNSET = object()
DEFAULT_PROJECT_ID = "project_default"
DEFAULT_PROJECT_NAME = "Default Project"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return any(row["name"] == column_name for row in rows)


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_definition: str,
) -> None:
    column_name = column_definition.split()[0]

    if _column_exists(connection, table_name, column_name):
        return

    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"
    )


def _ensure_default_project(connection: sqlite3.Connection) -> None:
    timestamp = _now_iso()
    connection.execute(
        """
        INSERT INTO projects (
            project_id,
            name,
            description,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO NOTHING
        """,
        (
            DEFAULT_PROJECT_ID,
            DEFAULT_PROJECT_NAME,
            "Auto-created local project for existing workflows.",
            timestamp,
            timestamp,
        ),
    )


def init_database() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                project_id TEXT,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL,
                requirements_json TEXT,
                architecture_json TEXT,
                approval_stage TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS generated_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                path TEXT NOT NULL,
                content TEXT NOT NULL,
                sort_index INTEGER NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workflow_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS preview_metadata (
                workflow_id TEXT PRIMARY KEY,
                workspace_path TEXT,
                preview_url TEXT,
                preview_port INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workflow_attempts (
                workflow_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                failure_type TEXT,
                debug_summary TEXT,
                logs_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (workflow_id, attempt_number),
                FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(
            connection,
            "workflows",
            "project_id TEXT",
        )
        _ensure_column(
            connection,
            "workflows",
            "current_attempt INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            connection,
            "workflows",
            "max_attempts INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            connection,
            "workflows",
            "is_retrying INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "workflows",
            "approval_stage TEXT",
        )
        _ensure_default_project(connection)
        connection.execute(
            """
            UPDATE workflows
            SET project_id = ?
            WHERE project_id IS NULL OR TRIM(project_id) = ''
            """,
            (DEFAULT_PROJECT_ID,),
        )


def create_workflow_record(
    project_id: str,
    workflow_id: str,
    prompt: str,
    status: str,
    *,
    current_attempt: int = 1,
    max_attempts: int = 1,
    is_retrying: bool = False,
) -> None:
    timestamp = _now_iso()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO workflows (
                workflow_id,
                project_id,
                prompt,
                status,
                current_attempt,
                max_attempts,
                is_retrying,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                project_id,
                prompt,
                status,
                current_attempt,
                max_attempts,
                1 if is_retrying else 0,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO preview_metadata (
                workflow_id,
                updated_at
            )
            VALUES (?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                updated_at = excluded.updated_at
            """,
            (workflow_id, timestamp),
        )


def update_workflow_record(
    workflow_id: str,
    *,
    project_id: str | object = _UNSET,
    prompt: str | object = _UNSET,
    status: str | object = _UNSET,
    requirements: dict | None | object = _UNSET,
    architecture: dict | None | object = _UNSET,
    approval_stage: str | None | object = _UNSET,
    current_attempt: int | object = _UNSET,
    max_attempts: int | object = _UNSET,
    is_retrying: bool | object = _UNSET,
) -> None:
    assignments: list[str] = ["updated_at = ?"]
    values: list[object] = [_now_iso()]

    if prompt is not _UNSET:
        assignments.append("prompt = ?")
        values.append(prompt)

    if project_id is not _UNSET:
        assignments.append("project_id = ?")
        values.append(project_id)

    if status is not _UNSET:
        assignments.append("status = ?")
        values.append(status)

    if requirements is not _UNSET:
        assignments.append("requirements_json = ?")
        values.append(
            None if requirements is None else json.dumps(requirements)
        )

    if architecture is not _UNSET:
        assignments.append("architecture_json = ?")
        values.append(
            None if architecture is None else json.dumps(architecture)
        )

    if approval_stage is not _UNSET:
        assignments.append("approval_stage = ?")
        values.append(approval_stage)

    if current_attempt is not _UNSET:
        assignments.append("current_attempt = ?")
        values.append(current_attempt)

    if max_attempts is not _UNSET:
        assignments.append("max_attempts = ?")
        values.append(max_attempts)

    if is_retrying is not _UNSET:
        assignments.append("is_retrying = ?")
        values.append(1 if is_retrying else 0)

    values.append(workflow_id)

    with _connect() as connection:
        connection.execute(
            f"""
            UPDATE workflows
            SET {", ".join(assignments)}
            WHERE workflow_id = ?
            """,
            values,
        )


def replace_generated_files(
    workflow_id: str,
    files: list[dict],
) -> None:
    with _connect() as connection:
        connection.execute(
            "DELETE FROM generated_files WHERE workflow_id = ?",
            (workflow_id,),
        )
        connection.executemany(
            """
            INSERT INTO generated_files (
                workflow_id,
                path,
                content,
                sort_index
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    workflow_id,
                    file["path"],
                    file["content"],
                    index,
                )
                for index, file in enumerate(files)
            ],
        )


def append_workflow_log(workflow_id: str, message: str) -> None:
    timestamp = _now_iso()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO workflow_logs (
                workflow_id,
                message,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (workflow_id, message, timestamp),
        )
        connection.execute(
            """
            UPDATE workflows
            SET updated_at = ?
            WHERE workflow_id = ?
            """,
            (timestamp, workflow_id),
        )


def upsert_build_attempt(workflow_id: str, attempt: dict) -> None:
    timestamp = _now_iso()

    with _connect() as connection:
        existing_row = connection.execute(
            """
            SELECT created_at
            FROM workflow_attempts
            WHERE workflow_id = ? AND attempt_number = ?
            """,
            (
                workflow_id,
                attempt["attemptNumber"],
            ),
        ).fetchone()

        created_at = (
            existing_row["created_at"]
            if existing_row is not None
            else timestamp
        )

        connection.execute(
            """
            INSERT INTO workflow_attempts (
                workflow_id,
                attempt_number,
                status,
                summary,
                failure_type,
                debug_summary,
                logs_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, attempt_number) DO UPDATE SET
                status = excluded.status,
                summary = excluded.summary,
                failure_type = excluded.failure_type,
                debug_summary = excluded.debug_summary,
                logs_json = excluded.logs_json,
                updated_at = excluded.updated_at
            """,
            (
                workflow_id,
                attempt["attemptNumber"],
                attempt["status"],
                attempt["summary"],
                attempt.get("failureType"),
                attempt.get("debugSummary"),
                json.dumps(attempt.get("logs") or []),
                created_at,
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE workflows
            SET updated_at = ?
            WHERE workflow_id = ?
            """,
            (timestamp, workflow_id),
        )


def set_preview_metadata(
    workflow_id: str,
    *,
    workspace_path: str | None | object = _UNSET,
    preview_url: str | None | object = _UNSET,
    preview_port: int | None | object = _UNSET,
) -> None:
    timestamp = _now_iso()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT workspace_path, preview_url, preview_port
            FROM preview_metadata
            WHERE workflow_id = ?
            """,
            (workflow_id,),
        ).fetchone()

        current_workspace_path = row["workspace_path"] if row is not None else None
        current_preview_url = row["preview_url"] if row is not None else None
        current_preview_port = row["preview_port"] if row is not None else None

        next_workspace_path = (
            current_workspace_path if workspace_path is _UNSET else workspace_path
        )
        next_preview_url = (
            current_preview_url if preview_url is _UNSET else preview_url
        )
        next_preview_port = (
            current_preview_port if preview_port is _UNSET else preview_port
        )

        connection.execute(
            """
            INSERT INTO preview_metadata (
                workflow_id,
                workspace_path,
                preview_url,
                preview_port,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                workspace_path = excluded.workspace_path,
                preview_url = excluded.preview_url,
                preview_port = excluded.preview_port,
                updated_at = excluded.updated_at
            """,
            (
                workflow_id,
                next_workspace_path,
                next_preview_url,
                next_preview_port,
                timestamp,
            ),
        )


def create_project_record(
    project_id: str,
    name: str,
    description: str | None = None,
) -> None:
    timestamp = _now_iso()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO projects (
                project_id,
                name,
                description,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                name,
                description,
                timestamp,
                timestamp,
            ),
        )


def update_project_record(
    project_id: str,
    *,
    name: str | object = _UNSET,
    description: str | None | object = _UNSET,
) -> None:
    assignments: list[str] = ["updated_at = ?"]
    values: list[object] = [_now_iso()]

    if name is not _UNSET:
        assignments.append("name = ?")
        values.append(name)

    if description is not _UNSET:
        assignments.append("description = ?")
        values.append(description)

    values.append(project_id)

    with _connect() as connection:
        connection.execute(
            f"""
            UPDATE projects
            SET {", ".join(assignments)}
            WHERE project_id = ?
            """,
            values,
        )


def delete_project_record(project_id: str) -> None:
    with _connect() as connection:
        connection.execute(
            "DELETE FROM workflows WHERE project_id = ?",
            (project_id,),
        )
        connection.execute(
            "DELETE FROM projects WHERE project_id = ?",
            (project_id,),
        )


def list_project_records() -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                projects.project_id,
                projects.name,
                projects.description,
                projects.created_at,
                projects.updated_at,
                COUNT(workflows.workflow_id) AS workflow_count
            FROM projects
            LEFT JOIN workflows
                ON workflows.project_id = projects.project_id
            GROUP BY
                projects.project_id,
                projects.name,
                projects.description,
                projects.created_at,
                projects.updated_at
            ORDER BY projects.updated_at DESC, projects.created_at DESC
            """
        ).fetchall()

    return [
        {
            "projectId": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "workflowCount": row["workflow_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def get_project_record(project_id: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                projects.project_id,
                projects.name,
                projects.description,
                projects.created_at,
                projects.updated_at,
                COUNT(workflows.workflow_id) AS workflow_count
            FROM projects
            LEFT JOIN workflows
                ON workflows.project_id = projects.project_id
            WHERE projects.project_id = ?
            GROUP BY
                projects.project_id,
                projects.name,
                projects.description,
                projects.created_at,
                projects.updated_at
            """,
            (project_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "projectId": row["project_id"],
        "name": row["name"],
        "description": row["description"],
        "workflowCount": row["workflow_count"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_workflow_records(project_id: str | None = None) -> list[dict]:
    with _connect() as connection:
        if project_id is None:
            rows = connection.execute(
                """
            SELECT
                workflows.workflow_id,
                workflows.project_id,
                workflows.prompt,
                workflows.status,
                workflows.created_at,
                workflows.updated_at,
                preview_metadata.workspace_path,
                preview_metadata.preview_url
            FROM workflows
            LEFT JOIN preview_metadata
                ON preview_metadata.workflow_id = workflows.workflow_id
            ORDER BY workflows.updated_at DESC, workflows.created_at DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
            SELECT
                workflows.workflow_id,
                workflows.project_id,
                workflows.prompt,
                workflows.status,
                workflows.created_at,
                workflows.updated_at,
                preview_metadata.workspace_path,
                preview_metadata.preview_url
            FROM workflows
            LEFT JOIN preview_metadata
                ON preview_metadata.workflow_id = workflows.workflow_id
            WHERE workflows.project_id = ?
            ORDER BY workflows.updated_at DESC, workflows.created_at DESC
                """,
                (project_id,),
            ).fetchall()

    return [
        {
            "projectId": row["project_id"],
            "workflowId": row["workflow_id"],
            "prompt": row["prompt"],
            "status": row["status"],
            "workspacePath": row["workspace_path"],
            "previewUrl": row["preview_url"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def get_workflow_record(workflow_id: str) -> dict | None:
    with _connect() as connection:
        workflow_row = connection.execute(
            """
            SELECT
                workflows.workflow_id,
                workflows.project_id,
                workflows.prompt,
                workflows.status,
                workflows.requirements_json,
                workflows.architecture_json,
                workflows.approval_stage,
                workflows.current_attempt,
                workflows.max_attempts,
                workflows.is_retrying,
                workflows.created_at,
                workflows.updated_at,
                preview_metadata.workspace_path,
                preview_metadata.preview_url,
                preview_metadata.preview_port
            FROM workflows
            LEFT JOIN preview_metadata
                ON preview_metadata.workflow_id = workflows.workflow_id
            WHERE workflows.workflow_id = ?
            """,
            (workflow_id,),
        ).fetchone()

        if workflow_row is None:
            return None

        file_rows = connection.execute(
            """
            SELECT path, content
            FROM generated_files
            WHERE workflow_id = ?
            ORDER BY sort_index ASC, id ASC
            """,
            (workflow_id,),
        ).fetchall()

        log_rows = connection.execute(
            """
            SELECT message
            FROM workflow_logs
            WHERE workflow_id = ?
            ORDER BY id ASC
            """,
            (workflow_id,),
        ).fetchall()

        attempt_rows = connection.execute(
            """
            SELECT
                attempt_number,
                status,
                summary,
                failure_type,
                debug_summary,
                logs_json
            FROM workflow_attempts
            WHERE workflow_id = ?
            ORDER BY attempt_number ASC
            """,
            (workflow_id,),
        ).fetchall()

    requirements_json = workflow_row["requirements_json"]
    architecture_json = workflow_row["architecture_json"]

    return {
        "projectId": workflow_row["project_id"],
        "workflowId": workflow_row["workflow_id"],
        "status": workflow_row["status"],
        "prompt": workflow_row["prompt"],
        "requirements": (
            json.loads(requirements_json)
            if requirements_json is not None
            else None
        ),
        "architecture": (
            json.loads(architecture_json)
            if architecture_json is not None
            else None
        ),
        "approvalStage": workflow_row["approval_stage"],
        "files": [
            {
                "path": row["path"],
                "content": row["content"],
            }
            for row in file_rows
        ],
        "logs": [row["message"] for row in log_rows],
        "previewUrl": workflow_row["preview_url"],
        "previewPort": workflow_row["preview_port"],
        "workspacePath": workflow_row["workspace_path"],
        "attempts": [
            {
                "attemptNumber": row["attempt_number"],
                "status": row["status"],
                "summary": row["summary"],
                "failureType": row["failure_type"],
                "debugSummary": row["debug_summary"],
                "logs": json.loads(row["logs_json"]),
            }
            for row in attempt_rows
        ],
        "currentAttempt": workflow_row["current_attempt"],
        "maxAttempts": workflow_row["max_attempts"],
        "isRetrying": bool(workflow_row["is_retrying"]),
        "createdAt": workflow_row["created_at"],
        "updatedAt": workflow_row["updated_at"],
    }
