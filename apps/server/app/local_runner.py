from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


class LocalRunnerError(RuntimeError):
    pass


@dataclass
class LocalRunnerResult:
    preview_url: str
    preview_port: int
    logs: list[str]


@dataclass
class RunningPreview:
    workflow_id: str
    workspace_dir: Path
    process: subprocess.Popen
    preview_url: str
    preview_port: int
    logs: list[str] = field(default_factory=list)


_running_previews: dict[str, RunningPreview] = {}


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


def _append_process_output(logs: list[str], label: str, output: str | None) -> None:
    if not output:
        return

    for line in output.splitlines():
        clean_line = line.rstrip()

        if clean_line:
            logs.append(f"[{label}] {clean_line}")


def _capture_preview_logs(preview: RunningPreview) -> None:
    if preview.process.stdout is None:
        return

    for line in preview.process.stdout:
        clean_line = line.rstrip()

        if clean_line:
            preview.logs.append(f"[preview] {clean_line}")


def _wait_for_preview(preview: RunningPreview, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""

    while time.time() < deadline:
        if preview.process.poll() is not None:
            recent_logs = "\n".join(preview.logs[-25:])

            raise LocalRunnerError(
                "Preview process exited before becoming ready.\n"
                f"Exit code: {preview.process.returncode}\n"
                f"Recent logs:\n{recent_logs}"
            )

        try:
            with urllib.request.urlopen(preview.preview_url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as error:
            last_error = str(error)

        time.sleep(0.5)

    recent_logs = "\n".join(preview.logs[-25:])

    raise LocalRunnerError(
        f"Timed out waiting for preview at {preview.preview_url}.\n"
        f"Last error: {last_error}\n"
        f"Recent logs:\n{recent_logs}"
    )


def start_preview(workflow_id: str, workspace_dir: Path) -> LocalRunnerResult:
    workspace_dir = workspace_dir.resolve()

    if not workspace_dir.exists():
        raise LocalRunnerError(f"Workspace does not exist: {workspace_dir}")

    if not (workspace_dir / "package.json").exists():
        raise LocalRunnerError(f"Missing package.json in workspace: {workspace_dir}")

    logs: list[str] = []

    package_manager_path, package_manager_name = _find_package_manager()

    logs.append(f"Using package manager: {package_manager_name}")
    logs.append(f"Installing dependencies in: {workspace_dir}")

    environment = os.environ.copy()
    environment["BROWSER"] = "none"
    environment["CI"] = "true"

    install_command = [
        package_manager_path,
        "install",
    ]

    try:
        install_result = subprocess.run(
            install_command,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            timeout=180,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise LocalRunnerError("Dependency installation timed out.") from error

    _append_process_output(logs, "install:stdout", install_result.stdout)
    _append_process_output(logs, "install:stderr", install_result.stderr)

    if install_result.returncode != 0:
        recent_logs = "\n".join(logs[-30:])

        raise LocalRunnerError(
            "Dependency installation failed.\n"
            f"Exit code: {install_result.returncode}\n"
            f"Recent logs:\n{recent_logs}"
        )

    preview_port = _get_available_port()
    preview_url = f"http://127.0.0.1:{preview_port}"

    logs.append(f"Starting Vite preview server on port {preview_port}")

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

    process = subprocess.Popen(
        dev_command,
        cwd=str(workspace_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=environment,
    )

    preview = RunningPreview(
        workflow_id=workflow_id,
        workspace_dir=workspace_dir,
        process=process,
        preview_url=preview_url,
        preview_port=preview_port,
    )

    _running_previews[workflow_id] = preview

    thread = threading.Thread(
        target=_capture_preview_logs,
        args=(preview,),
        daemon=True,
    )
    thread.start()

    _wait_for_preview(preview)

    logs.extend(preview.logs)
    logs.append(f"Preview ready: {preview_url}")

    return LocalRunnerResult(
        preview_url=preview_url,
        preview_port=preview_port,
        logs=logs,
    )


def stop_preview(workflow_id: str) -> None:
    preview = _running_previews.pop(workflow_id, None)

    if preview is None:
        return

    if preview.process.poll() is None:
        preview.process.terminate()

        try:
            preview.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            preview.process.kill()


def stop_all_previews() -> None:
    for workflow_id in list(_running_previews.keys()):
        stop_preview(workflow_id)


atexit.register(stop_all_previews)