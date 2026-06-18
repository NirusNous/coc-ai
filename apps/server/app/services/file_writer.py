import shutil
from pathlib import Path, PurePosixPath

from app.config import GENERATED_ROOT, PROJECT_ROOT
from app.models import FileWriteResult, GeneratedFile


class UnsafeGeneratedPathError(ValueError):
    pass


def _validate_identifier(
    value: str,
    *,
    label: str,
) -> None:
    allowed_characters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

    if not value:
        raise ValueError(f"{label} cannot be empty.")

    if any(character not in allowed_characters for character in value):
        raise ValueError(f"Invalid {label}: {value}")


def validate_project_id(project_id: str) -> None:
    _validate_identifier(project_id, label="project ID")


def _validate_workflow_id(workflow_id: str) -> None:
    _validate_identifier(workflow_id, label="workflow ID")


def build_workspace_dir(
    *,
    project_id: str,
    workflow_id: str,
) -> Path:
    validate_project_id(project_id)
    _validate_workflow_id(workflow_id)
    return (GENERATED_ROOT / project_id / workflow_id).resolve()


def _safe_target_path(workspace_dir: Path, generated_path: str) -> Path:
    normalized_path = generated_path.replace("\\", "/").strip()

    if not normalized_path:
        raise UnsafeGeneratedPathError("Generated file path cannot be empty.")

    pure_path = PurePosixPath(normalized_path)

    if pure_path.is_absolute():
        raise UnsafeGeneratedPathError(
            f"Absolute generated file paths are not allowed: {generated_path}"
        )

    for part in pure_path.parts:
        if part in ("", ".", ".."):
            raise UnsafeGeneratedPathError(
                f"Unsafe generated file path segment in: {generated_path}"
            )

        if ":" in part:
            raise UnsafeGeneratedPathError(
                f"Generated file path contains an unsafe character: {generated_path}"
            )

    # Resolve the write target and make sure it stays inside the generated workspace
    # even if the model returns a malicious or malformed path.
    target_path = (workspace_dir / Path(*pure_path.parts)).resolve()
    resolved_workspace = workspace_dir.resolve()

    try:
        target_path.relative_to(resolved_workspace)
    except ValueError as error:
        raise UnsafeGeneratedPathError(
            f"Generated file path escapes workspace: {generated_path}"
        ) from error

    return target_path


def write_generated_files(
    project_id: str,
    workflow_id: str,
    files: list[GeneratedFile],
    *,
    replace_existing: bool = False,
) -> FileWriteResult:
    validate_project_id(project_id)
    _validate_workflow_id(workflow_id)

    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)

    workspace_dir = build_workspace_dir(
        project_id=project_id,
        workflow_id=workflow_id,
    )

    if replace_existing and workspace_dir.exists():
        shutil.rmtree(workspace_dir)

    workspace_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[str] = []

    for generated_file in files:
        target_path = _safe_target_path(
            workspace_dir=workspace_dir,
            generated_path=generated_file.path,
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(generated_file.content, encoding="utf-8")

        written_files.append(
            str(target_path.relative_to(workspace_dir)).replace("\\", "/")
        )

    return FileWriteResult(
        workspacePath=str(workspace_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        writtenFiles=written_files,
    )
