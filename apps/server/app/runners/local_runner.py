from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from app.runners.base_runner import (
    LogCallback,
    PreviewRunResult,
    PreviewRunner,
    PreviewRunnerError,
    RunningPreview,
    RunnerStage,
    RunnerStageEvent,
    RunnerStageStatus,
    RunnerStatus,
    StageCallback,
)


class LocalRunnerError(PreviewRunnerError):
    pass


@dataclass
class LocalRunningPreview:
    workflow_id: str
    workspace_dir: Path
    process: subprocess.Popen
    preview_url: str
    preview_port: int
    logs: list[str] = field(default_factory=list)


_running_previews: dict[str, LocalRunningPreview] = {}
_registry_lock = threading.Lock()


def _find_package_manager() -> tuple[str, str]:
    pnpm_path = shutil.which("pnpm")

    if pnpm_path:
        return pnpm_path, "pnpm"

    npm_path = shutil.which("npm")

    if npm_path:
        return npm_path, "npm"

    raise LocalRunnerError(
        "Neither pnpm nor npm was found. Install Node.js and enable pnpm first."
    )


def _get_available_port(start: int = 5178, end: int = 5999) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise LocalRunnerError("Could not find an available preview port.")


def _emit_log(
    result: PreviewRunResult,
    message: str,
    on_log: LogCallback | None,
) -> None:
    result.logs.append(message)

    if on_log is not None:
        on_log(message)


def _emit_stage(
    result: PreviewRunResult,
    stage: RunnerStage,
    status: RunnerStageStatus,
    detail: str,
    on_stage: StageCallback | None,
) -> None:
    event = RunnerStageEvent(
        stage=stage,
        status=status,
        detail=detail,
    )
    result.stage_events.append(event)

    if on_stage is not None:
        on_stage(stage, status, detail)


def _append_process_output(
    result: PreviewRunResult,
    label: str,
    output: str | None,
    on_log: LogCallback | None,
) -> None:
    if not output:
        return

    for line in output.splitlines():
        clean_line = line.rstrip()

        if clean_line:
            _emit_log(result, f"[{label}] {clean_line}", on_log)


def _capture_preview_logs(
    preview: LocalRunningPreview,
    result: PreviewRunResult,
    on_log: LogCallback | None,
) -> None:
    if preview.process.stdout is None:
        return

    for line in preview.process.stdout:
        clean_line = line.rstrip()

        if clean_line:
            _emit_log(result, f"[preview] {clean_line}", on_log)


def _register_preview(preview: LocalRunningPreview) -> None:
    with _registry_lock:
        _running_previews[preview.workflow_id] = preview


def _pop_preview(workflow_id: str) -> LocalRunningPreview | None:
    with _registry_lock:
        return _running_previews.pop(workflow_id, None)


def _remove_stale_previews() -> None:
    with _registry_lock:
        stale_workflow_ids = [
            workflow_id
            for workflow_id, preview in _running_previews.items()
            if preview.process.poll() is not None
        ]

        for workflow_id in stale_workflow_ids:
            _running_previews.pop(workflow_id, None)


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

        return

    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait(timeout=5)


def _wait_for_preview(
    preview: LocalRunningPreview,
    timeout_seconds: int = 45,
) -> tuple[bool, RunnerStatus | None, str | None]:
    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        if preview.process.poll() is not None:
            recent_logs = "\n".join(preview.logs[-25:])
            message = (
                "Preview runtime crashed before becoming ready.\n"
                f"Exit code: {preview.process.returncode}\n"
                f"Recent logs:\n{recent_logs}"
            )
            return False, "runtime_crashed", message

        try:
            with urllib.request.urlopen(preview.preview_url, timeout=1) as response:
                if response.status < 500:
                    return True, None, None
        except Exception as error:
            last_error = str(error)

        time.sleep(0.5)

    recent_logs = "\n".join(preview.logs[-25:])
    message = (
        f"Timed out waiting for preview at {preview.preview_url}.\n"
        f"Last error: {last_error}\n"
        f"Recent logs:\n{recent_logs}"
    )
    return False, "timeout", message


def _run_command(
    result: PreviewRunResult,
    *,
    command: list[str],
    workspace_dir: Path,
    environment: dict[str, str],
    stage: RunnerStage,
    stage_label: str,
    started_detail: str,
    completed_detail: str,
    failure_status: RunnerStatus,
    timeout_message: str,
    on_stage: StageCallback | None,
    on_log: LogCallback | None,
    timeout_seconds: int = 180,
) -> bool:
    _emit_stage(result, stage, "started", started_detail, on_stage)
    _emit_log(result, started_detail, on_log)

    try:
        command_result = subprocess.run(
            command,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        result.status = "timeout"
        result.error_message = timeout_message
        _emit_log(result, timeout_message, on_log)
        _emit_stage(result, stage, "failed", timeout_message, on_stage)
        return False

    _append_process_output(
        result,
        f"{stage_label}:stdout",
        command_result.stdout,
        on_log,
    )
    _append_process_output(
        result,
        f"{stage_label}:stderr",
        command_result.stderr,
        on_log,
    )

    if command_result.returncode != 0:
        message = (
            f"{stage_label.capitalize()} failed with exit code {command_result.returncode}."
        )
        result.status = failure_status
        result.error_message = message
        _emit_log(result, message, on_log)
        _emit_stage(result, stage, "failed", message, on_stage)
        return False

    _emit_log(result, completed_detail, on_log)
    _emit_stage(result, stage, "completed", completed_detail, on_stage)
    return True


class LocalPreviewRunner(PreviewRunner):
    runner_id = "local"
    display_name = "LocalRunner"

    def start_preview(
        self,
        workflow_id: str,
        workspace_dir: Path,
        *,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> PreviewRunResult:
        workspace_dir = workspace_dir.resolve()
        result = PreviewRunResult(status="preview_failed")

        _remove_stale_previews()

        with _registry_lock:
            if workflow_id in _running_previews:
                message = f"Preview is already running for workflow {workflow_id}."
                result.error_message = message
                _emit_log(result, message, on_log)
                return result

        if not workspace_dir.exists():
            message = f"Workspace does not exist: {workspace_dir}"
            result.error_message = message
            _emit_log(result, message, on_log)
            return result

        if not (workspace_dir / "package.json").exists():
            message = f"Missing package.json in workspace: {workspace_dir}"
            result.error_message = message
            _emit_log(result, message, on_log)
            return result

        try:
            package_manager_path, package_manager_name = _find_package_manager()
        except LocalRunnerError as error:
            result.status = "install_failed"
            result.error_message = str(error)
            _emit_log(result, str(error), on_log)
            return result

        _emit_log(result, f"Using package manager: {package_manager_name}", on_log)

        environment = os.environ.copy()
        environment["BROWSER"] = "none"
        environment["CI"] = "true"

        if not _run_command(
            result,
            command=[package_manager_path, "install"],
            workspace_dir=workspace_dir,
            environment=environment,
            stage="install",
            stage_label="install",
            started_detail=f"Installing dependencies in {workspace_dir}",
            completed_detail="Dependency installation completed.",
            failure_status="install_failed",
            timeout_message="Dependency installation timed out.",
            on_stage=on_stage,
            on_log=on_log,
        ):
            return result

        if not _run_command(
            result,
            command=[package_manager_path, "run", "build"],
            workspace_dir=workspace_dir,
            environment=environment,
            stage="build",
            stage_label="build",
            started_detail="Building generated app.",
            completed_detail="Generated app build completed.",
            failure_status="build_failed",
            timeout_message="Generated app build timed out.",
            on_stage=on_stage,
            on_log=on_log,
        ):
            return result

        try:
            preview_port = _get_available_port()
        except LocalRunnerError as error:
            result.error_message = str(error)
            _emit_log(result, str(error), on_log)
            return result

        preview_url = f"http://127.0.0.1:{preview_port}"
        _emit_stage(
            result,
            "preview",
            "started",
            f"Starting Vite preview server on port {preview_port}",
            on_stage,
        )
        _emit_log(result, f"Starting Vite preview server on port {preview_port}", on_log)

        dev_command = [
            package_manager_path,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(preview_port),
            "--strictPort",
        ]

        popen_kwargs = {
            "cwd": str(workspace_dir),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "env": environment,
        }

        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(
                dev_command,
                **popen_kwargs,
            )
        except OSError as error:
            message = f"Failed to start Vite preview server: {error}"
            result.error_message = message
            _emit_log(result, message, on_log)
            _emit_stage(result, "preview", "failed", message, on_stage)
            return result

        preview = LocalRunningPreview(
            workflow_id=workflow_id,
            workspace_dir=workspace_dir,
            process=process,
            preview_url=preview_url,
            preview_port=preview_port,
            logs=result.logs,
        )
        _emit_log(result, f"[preview] Process started with PID {process.pid}", on_log)

        _register_preview(preview)

        thread = threading.Thread(
            target=_capture_preview_logs,
            args=(preview, result, on_log),
            daemon=True,
        )
        thread.start()

        is_ready, failure_status, failure_message = _wait_for_preview(preview)

        if not is_ready:
            self.stop_preview(workflow_id)
            result.status = failure_status or "preview_failed"
            result.error_message = failure_message or "Preview startup failed."

            if failure_message is not None:
                _emit_log(result, failure_message, on_log)

            _emit_stage(
                result,
                "preview",
                "failed",
                result.error_message,
                on_stage,
            )
            return result

        result.status = "preview_ready"
        result.preview_url = preview_url
        result.preview_port = preview_port
        _emit_log(result, f"Preview ready: {preview_url}", on_log)
        _emit_stage(
            result,
            "preview",
            "completed",
            f"Preview ready at {preview_url}",
            on_stage,
        )

        return result

    def list_previews(self) -> list[RunningPreview]:
        _remove_stale_previews()

        with _registry_lock:
            previews = list(_running_previews.values())

        return [
            RunningPreview(
                workflow_id=preview.workflow_id,
                workspace_dir=preview.workspace_dir,
                preview_url=preview.preview_url,
                preview_port=preview.preview_port,
                runner=self.runner_id,
                pid=preview.process.pid,
                logs=preview.logs,
            )
            for preview in previews
        ]

    def stop_preview(self, workflow_id: str) -> bool:
        _remove_stale_previews()
        preview = _pop_preview(workflow_id)

        if preview is None:
            return False

        _terminate_process_tree(preview.process)
        return True

    def stop_all_previews(self) -> None:
        for workflow_id in [preview.workflow_id for preview in self.list_previews()]:
            self.stop_preview(workflow_id)


_LOCAL_PREVIEW_RUNNER = LocalPreviewRunner()


def get_local_preview_runner() -> LocalPreviewRunner:
    return _LOCAL_PREVIEW_RUNNER


def start_preview(
    workflow_id: str,
    workspace_dir: Path,
    *,
    on_stage: StageCallback | None = None,
    on_log: LogCallback | None = None,
) -> PreviewRunResult:
    return _LOCAL_PREVIEW_RUNNER.start_preview(
        workflow_id=workflow_id,
        workspace_dir=workspace_dir,
        on_stage=on_stage,
        on_log=on_log,
    )


def list_previews() -> list[RunningPreview]:
    return _LOCAL_PREVIEW_RUNNER.list_previews()


def list_local_previews() -> list[LocalRunningPreview]:
    _remove_stale_previews()

    with _registry_lock:
        return list(_running_previews.values())


def restart_preview(
    workflow_id: str,
    workspace_dir: Path,
    *,
    on_stage: StageCallback | None = None,
    on_log: LogCallback | None = None,
) -> PreviewRunResult:
    return _LOCAL_PREVIEW_RUNNER.restart_preview(
        workflow_id=workflow_id,
        workspace_dir=workspace_dir,
        on_stage=on_stage,
        on_log=on_log,
    )


def stop_preview(workflow_id: str) -> bool:
    return _LOCAL_PREVIEW_RUNNER.stop_preview(workflow_id)


def stop_all_previews() -> None:
    _LOCAL_PREVIEW_RUNNER.stop_all_previews()


atexit.register(stop_all_previews)
