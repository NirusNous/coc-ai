from __future__ import annotations

import atexit
import base64
import json
import os
import re
import signal
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from app.config import RunnerSettings
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


NAMESPACE_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
SANITIZE_PATTERN = re.compile(r"[^a-z0-9-]+")
STAGE_MARKER_PREFIX = "__AGENTIC_OS_STAGE__|"
PREVIEW_CONTAINER_PORT = 5173
BUILD_JOB_TIMEOUT_SECONDS = 300
PREVIEW_READY_TIMEOUT_SECONDS = 240
KUBECTL_TIMEOUT_SECONDS = 60
CONFIG_MAP_SIZE_LIMIT_BYTES = 900_000
CONFIG_MAP_NAME = "preview-source"
BUILD_JOB_NAME = "preview-build"
DEPLOYMENT_NAME = "preview-app"
SERVICE_NAME = "preview-service"
INGRESS_NAME = "preview-ingress"
EXCLUDED_WORKSPACE_PARTS = {
    ".git",
    ".next",
    ".turbo",
    ".vite",
    "__pycache__",
    "dist",
    "node_modules",
}


class RancherKubernetesRunnerError(PreviewRunnerError):
    pass


@dataclass(frozen=True)
class KubernetesNamespace:
    name: str
    status: str
    created_at: str | None = None


@dataclass
class KubernetesRunningPreview:
    workflow_id: str
    workspace_dir: Path
    namespace: str
    preview_url: str
    preview_port: int | None
    logs: list[str] = field(default_factory=list)
    port_forward_process: subprocess.Popen[str] | None = None
    port_forward_thread: threading.Thread | None = None
    preview_log_process: subprocess.Popen[str] | None = None
    preview_log_thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)


_running_previews: dict[str, KubernetesRunningPreview] = {}
_registry_lock = threading.Lock()


def _register_preview(preview: KubernetesRunningPreview) -> None:
    with _registry_lock:
        _running_previews[preview.workflow_id] = preview


def _pop_preview(workflow_id: str) -> KubernetesRunningPreview | None:
    with _registry_lock:
        return _running_previews.pop(workflow_id, None)


def _list_registered_previews() -> list[KubernetesRunningPreview]:
    with _registry_lock:
        return list(_running_previews.values())


def _sanitize_kubernetes_name(value: str, *, fallback: str = "preview") -> str:
    candidate = SANITIZE_PATTERN.sub("-", value.strip().lower())
    candidate = candidate.strip("-")

    if not candidate:
        candidate = fallback

    candidate = candidate[:63].strip("-")
    return candidate or fallback


def _validate_relative_workspace_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")

    if not normalized:
        raise RancherKubernetesRunnerError("Workspace contains an empty file path.")

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise RancherKubernetesRunnerError(
            f"Unsafe workspace path cannot be mounted into Kubernetes: {path}"
        )

    return pure_path.as_posix()


def _find_available_port(start: int = 5178, end: int = 5999) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue

    raise RancherKubernetesRunnerError("Could not find an available local port.")


def _emit_log(
    result: PreviewRunResult,
    message: str,
    on_log: LogCallback | None,
) -> None:
    result.logs.append(message)

    if on_log is None:
        return

    try:
        on_log(message)
    except Exception:
        return


def _emit_stage(
    result: PreviewRunResult,
    stage: RunnerStage,
    status: RunnerStageStatus,
    detail: str,
    on_stage: StageCallback | None,
) -> None:
    result.stage_events.append(
        RunnerStageEvent(
            stage=stage,
            status=status,
            detail=detail,
        )
    )

    if on_stage is None:
        return

    try:
        on_stage(stage, status, detail)
    except Exception:
        return


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
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


def _parse_stage_marker(
    line: str,
) -> tuple[RunnerStage, RunnerStageStatus, str] | None:
    if not line.startswith(STAGE_MARKER_PREFIX):
        return None

    _, stage, status, detail = line.split("|", 3)

    if stage not in {"install", "build", "preview"}:
        return None

    if status not in {"started", "completed", "failed"}:
        return None

    return stage, status, detail


def _stream_process_output(
    *,
    process: subprocess.Popen[str],
    result: PreviewRunResult,
    label: str,
    stop_event: threading.Event,
    on_log: LogCallback | None,
    on_stage: StageCallback | None = None,
) -> None:
    if process.stdout is None:
        return

    try:
        for line in process.stdout:
            if stop_event.is_set():
                break

            clean_line = line.rstrip()

            if not clean_line:
                continue

            marker = _parse_stage_marker(clean_line)

            if marker is not None:
                stage, status, detail = marker
                _emit_stage(result, stage, status, detail, on_stage)
                continue

            _emit_log(result, f"[{label}] {clean_line}", on_log)
    finally:
        try:
            process.stdout.close()
        except Exception:
            pass


def _build_shell_scripts() -> dict[str, str]:
    build_script = """#!/bin/sh
set -eu
mkdir -p /app
cp -R /config/files/. /app/
cd /app
corepack enable >/dev/null 2>&1 || true
if pnpm install --reporter append-only; then
  echo "__AGENTIC_OS_STAGE__|install|completed|Dependency installation completed in Kubernetes build job."
else
  echo "__AGENTIC_OS_STAGE__|install|failed|Dependency installation failed in Kubernetes build job."
  exit 1
fi
echo "__AGENTIC_OS_STAGE__|build|started|Building generated app in Kubernetes build job."
if pnpm run build; then
  echo "__AGENTIC_OS_STAGE__|build|completed|Generated app build completed in Kubernetes build job."
else
  echo "__AGENTIC_OS_STAGE__|build|failed|Generated app build failed in Kubernetes build job."
  exit 1
fi
"""

    preview_script = """#!/bin/sh
set -eu
mkdir -p /app
cp -R /config/files/. /app/
cd /app
corepack enable >/dev/null 2>&1 || true
pnpm install --reporter append-only
pnpm run build
exec pnpm run dev -- --host 0.0.0.0 --port 5173 --strictPort
"""

    return {
        "build-job.sh": build_script,
        "preview.sh": preview_script,
    }


class RancherKubernetesPreviewRunner(PreviewRunner):
    runner_id = "rancher_k8s"
    display_name = "RancherKubernetesRunner"

    def __init__(self, settings: RunnerSettings):
        self.settings = settings

    def _build_namespace_name(self, workflow_id: str) -> str:
        prefix = _sanitize_kubernetes_name(
            self.settings.namespace_prefix,
            fallback="agentic-os",
        )
        workflow_slug = _sanitize_kubernetes_name(
            workflow_id,
            fallback="workflow",
        )
        max_workflow_length = max(1, 63 - len(prefix) - 1)
        namespace = f"{prefix}-{workflow_slug[:max_workflow_length].strip('-')}"
        return self._validate_managed_namespace(namespace)

    def _workflow_label(self, workflow_id: str) -> str:
        return _sanitize_kubernetes_name(workflow_id, fallback="workflow")

    def _resource_labels(
        self,
        workflow_id: str,
        component: str,
    ) -> dict[str, str]:
        workflow_label = self._workflow_label(workflow_id)
        return {
            "app.kubernetes.io/name": "agentic-os-preview",
            "app.kubernetes.io/instance": workflow_label,
            "app.kubernetes.io/component": component,
            "agentic-os/workflow-id": workflow_label,
        }

    def _build_kubectl_command(self, *args: str) -> list[str]:
        if shutil.which("kubectl") is None:
            raise RancherKubernetesRunnerError(
                "kubectl was not found on PATH. Install kubectl before using the Rancher/Kubernetes runner."
            )

        command = ["kubectl"]

        if self.settings.kubeconfig_path:
            command.extend(["--kubeconfig", self.settings.kubeconfig_path])

        if self.settings.k8s_context:
            command.extend(["--context", self.settings.k8s_context])

        command.extend(args)
        return command

    def _run_kubectl(
        self,
        *args: str,
        input_text: str | None = None,
        timeout_seconds: int = KUBECTL_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        command = self._build_kubectl_command(*args)

        try:
            result = subprocess.run(
                command,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RancherKubernetesRunnerError(
                f"kubectl command timed out after {timeout_seconds} seconds."
            ) from error

        if result.returncode != 0:
            detail_source = result.stderr.strip() or result.stdout.strip()
            detail_lines = [
                line.strip()
                for line in detail_source.splitlines()
                if line.strip()
            ]
            detail = detail_lines[-1] if detail_lines else "Unknown kubectl error."
            raise RancherKubernetesRunnerError(detail)

        return result

    def _start_kubectl_process(
        self,
        *args: str,
    ) -> subprocess.Popen[str]:
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }

        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        try:
            return subprocess.Popen(
                self._build_kubectl_command(*args),
                **popen_kwargs,
            )
        except OSError as error:
            raise RancherKubernetesRunnerError(
                f"Failed to start kubectl process: {error}"
            ) from error

    def _read_kubectl_json(self, *args: str) -> dict[str, Any]:
        result = self._run_kubectl(*args, "-o", "json")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RancherKubernetesRunnerError(
                "kubectl returned invalid JSON."
            ) from error

    def _apply_manifest(self, manifest: dict[str, Any]) -> None:
        self._run_kubectl(
            "apply",
            "-f",
            "-",
            input_text=json.dumps(manifest),
            timeout_seconds=120,
        )

    def _validate_namespace(self, namespace: str) -> str:
        candidate = namespace.strip().lower()

        if not candidate:
            raise RancherKubernetesRunnerError("Namespace is required.")

        if not NAMESPACE_PATTERN.fullmatch(candidate):
            raise RancherKubernetesRunnerError(
                "Invalid namespace. Use lowercase letters, numbers, and single hyphens only."
            )

        return candidate

    def _validate_managed_namespace(self, namespace: str) -> str:
        candidate = self._validate_namespace(namespace)
        prefix = f"{self.settings.namespace_prefix}-"

        if candidate != self.settings.namespace_prefix and not candidate.startswith(prefix):
            raise RancherKubernetesRunnerError(
                f"Namespace must use the configured prefix '{self.settings.namespace_prefix}'."
            )

        return candidate

    def _namespace_exists(self, namespace: str) -> bool:
        command = self._build_kubectl_command("get", "namespace", namespace, "-o", "name")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=KUBECTL_TIMEOUT_SECONDS,
            check=False,
        )

        if result.returncode == 0:
            return True

        detail = (result.stderr or result.stdout).lower()

        if "notfound" in detail or "not found" in detail:
            return False

        raise RancherKubernetesRunnerError(
            result.stderr.strip() or result.stdout.strip() or "Failed to inspect namespace."
        )

    def _wait_for_namespace_deletion(
        self,
        namespace: str,
        timeout_seconds: int = 120,
    ) -> None:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            if not self._namespace_exists(namespace):
                return

            time.sleep(2)

        raise RancherKubernetesRunnerError(
            f"Timed out waiting for namespace {namespace} to delete."
        )

    def _delete_namespace_if_exists(
        self,
        namespace: str,
        *,
        wait: bool,
    ) -> bool:
        if not self._namespace_exists(namespace):
            return False

        self._run_kubectl(
            "delete",
            "namespace",
            namespace,
            "--wait=false",
            timeout_seconds=120,
        )

        if wait:
            self._wait_for_namespace_deletion(namespace)

        return True

    def _collect_workspace_files(
        self,
        workspace_dir: Path,
    ) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
        data: dict[str, str] = {}
        binary_data: dict[str, str] = {}
        items: list[dict[str, str]] = []
        size_bytes = 0
        index = 0

        for source_path in sorted(workspace_dir.rglob("*")):
            if not source_path.is_file():
                continue

            relative_path = source_path.relative_to(workspace_dir)

            if any(part in EXCLUDED_WORKSPACE_PARTS for part in relative_path.parts):
                continue

            relative_posix_path = _validate_relative_workspace_path(
                relative_path.as_posix()
            )

            key = f"file-{index:04d}"
            items.append({
                "key": key,
                "path": f"files/{relative_posix_path}",
            })

            try:
                text_content = source_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw_bytes = source_path.read_bytes()
                binary_data[key] = base64.b64encode(raw_bytes).decode("ascii")
                size_bytes += len(raw_bytes)
            else:
                data[key] = text_content
                size_bytes += len(text_content.encode("utf-8"))

            index += 1

        if index == 0:
            raise RancherKubernetesRunnerError(
                f"No source files were found in workspace {workspace_dir}."
            )

        if size_bytes > CONFIG_MAP_SIZE_LIMIT_BYTES:
            raise RancherKubernetesRunnerError(
                "Generated workspace is too large to mount through a ConfigMap for Kubernetes preview."
            )

        for script_name, script_content in _build_shell_scripts().items():
            data[script_name] = script_content
            items.append({
                "key": script_name,
                "path": script_name,
            })

        return data, binary_data, items

    def _build_source_config_map(
        self,
        workflow_id: str,
        namespace: str,
        workspace_dir: Path,
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        data, binary_data, items = self._collect_workspace_files(workspace_dir)
        manifest: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": CONFIG_MAP_NAME,
                "namespace": namespace,
                "labels": self._resource_labels(workflow_id, "source"),
            },
            "data": data,
        }

        if binary_data:
            manifest["binaryData"] = binary_data

        return manifest, items

    def _build_source_volume(self, items: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "name": "source-config",
            "configMap": {
                "name": CONFIG_MAP_NAME,
                "items": items,
            },
        }

    def _build_job_manifest(
        self,
        workflow_id: str,
        namespace: str,
        volume_items: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": BUILD_JOB_NAME,
                "namespace": namespace,
                "labels": self._resource_labels(workflow_id, "build"),
            },
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": BUILD_JOB_TIMEOUT_SECONDS,
                "ttlSecondsAfterFinished": 3600,
                "template": {
                    "metadata": {
                        "labels": self._resource_labels(workflow_id, "build"),
                    },
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "build",
                                "image": "node:20-alpine",
                                "command": ["/bin/sh", "/config/build-job.sh"],
                                "volumeMounts": [
                                    {
                                        "name": "source-config",
                                        "mountPath": "/config",
                                        "readOnly": True,
                                    },
                                ],
                            }
                        ],
                        "volumes": [
                            self._build_source_volume(volume_items),
                        ],
                    },
                },
            },
        }

    def _build_preview_manifests(
        self,
        workflow_id: str,
        namespace: str,
        volume_items: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        preview_labels = self._resource_labels(workflow_id, "preview")
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": DEPLOYMENT_NAME,
                "namespace": namespace,
                "labels": preview_labels,
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": preview_labels,
                },
                "template": {
                    "metadata": {
                        "labels": preview_labels,
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "preview",
                                "image": "node:20-alpine",
                                "command": ["/bin/sh", "/config/preview.sh"],
                                "ports": [
                                    {
                                        "containerPort": PREVIEW_CONTAINER_PORT,
                                        "name": "http",
                                    }
                                ],
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": "/",
                                        "port": PREVIEW_CONTAINER_PORT,
                                    },
                                    "initialDelaySeconds": 2,
                                    "periodSeconds": 3,
                                    "failureThreshold": 60,
                                },
                                "volumeMounts": [
                                    {
                                        "name": "source-config",
                                        "mountPath": "/config",
                                        "readOnly": True,
                                    },
                                ],
                            }
                        ],
                        "volumes": [
                            self._build_source_volume(volume_items),
                        ],
                    },
                },
            },
        }
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": SERVICE_NAME,
                "namespace": namespace,
                "labels": preview_labels,
            },
            "spec": {
                "selector": preview_labels,
                "ports": [
                    {
                        "name": "http",
                        "port": PREVIEW_CONTAINER_PORT,
                        "targetPort": PREVIEW_CONTAINER_PORT,
                    }
                ],
            },
        }
        manifests = [deployment, service]

        if self.settings.preview_exposure_mode == "ingress":
            base_domain = (self.settings.preview_base_domain or "").strip()

            if not base_domain:
                raise RancherKubernetesRunnerError(
                    "PREVIEW_BASE_DOMAIN is required when PREVIEW_EXPOSURE_MODE=ingress."
                )

            host = f"{namespace}.{base_domain}"
            ingress = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "Ingress",
                "metadata": {
                    "name": INGRESS_NAME,
                    "namespace": namespace,
                    "labels": preview_labels,
                },
                "spec": {
                    "rules": [
                        {
                            "host": host,
                            "http": {
                                "paths": [
                                    {
                                        "path": "/",
                                        "pathType": "Prefix",
                                        "backend": {
                                            "service": {
                                                "name": SERVICE_NAME,
                                                "port": {
                                                    "number": PREVIEW_CONTAINER_PORT,
                                                },
                                            }
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
            manifests.append(ingress)

        return manifests

    def _wait_for_pod_name(
        self,
        namespace: str,
        selector: str,
        *,
        timeout_seconds: int = 90,
    ) -> str:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            payload = self._read_kubectl_json(
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                selector,
            )
            items = payload.get("items") or []

            if items:
                metadata = items[0].get("metadata") or {}
                pod_name = metadata.get("name")

                if pod_name:
                    return pod_name

            time.sleep(2)

        raise RancherKubernetesRunnerError(
            f"Timed out waiting for pod in namespace {namespace} with selector {selector}."
        )

    def _start_log_stream(
        self,
        *,
        namespace: str,
        pod_name: str,
        result: PreviewRunResult,
        label: str,
        stop_event: threading.Event,
        on_log: LogCallback | None,
        on_stage: StageCallback | None = None,
    ) -> tuple[subprocess.Popen[str], threading.Thread]:
        process = self._start_kubectl_process(
            "logs",
            "-f",
            f"pod/{pod_name}",
            "-n",
            namespace,
        )
        thread = threading.Thread(
            target=_stream_process_output,
            kwargs={
                "process": process,
                "result": result,
                "label": label,
                "stop_event": stop_event,
                "on_log": on_log,
                "on_stage": on_stage,
            },
            daemon=True,
        )
        thread.start()
        return process, thread

    def _infer_build_failure_status(self, result: PreviewRunResult) -> RunnerStatus:
        for event in reversed(result.stage_events):
            if event.status == "failed":
                if event.stage == "install":
                    return "install_failed"

                if event.stage == "build":
                    return "build_failed"

        started_stages = {
            event.stage
            for event in result.stage_events
            if event.status == "started"
        }
        completed_stages = {
            event.stage
            for event in result.stage_events
            if event.status == "completed"
        }

        if "install" in started_stages and "install" not in completed_stages:
            return "install_failed"

        return "build_failed"

    def _describe_pod_state(
        self,
        namespace: str,
        pod_name: str,
    ) -> str | None:
        payload = self._read_kubectl_json(
            "get",
            "pod",
            pod_name,
            "-n",
            namespace,
        )
        status = payload.get("status") or {}
        container_statuses = status.get("containerStatuses") or []

        for container_status in container_statuses:
            state = container_status.get("state") or {}
            waiting = state.get("waiting")

            if waiting:
                reason = waiting.get("reason") or "Waiting"
                message = waiting.get("message")
                return f"{reason}: {message}" if message else reason

            terminated = state.get("terminated")

            if terminated:
                reason = terminated.get("reason") or "Terminated"
                message = terminated.get("message")
                exit_code = terminated.get("exitCode")
                if message:
                    return f"{reason} (exit {exit_code}): {message}"
                return f"{reason} (exit {exit_code})"

            last_state = container_status.get("lastState") or {}
            last_terminated = last_state.get("terminated")

            if last_terminated:
                reason = last_terminated.get("reason") or "Terminated"
                message = last_terminated.get("message")
                exit_code = last_terminated.get("exitCode")
                if message:
                    return f"{reason} (exit {exit_code}): {message}"
                return f"{reason} (exit {exit_code})"

        phase = status.get("phase")
        return str(phase) if phase else None

    def _wait_for_build_job(
        self,
        namespace: str,
        result: PreviewRunResult,
        on_stage: StageCallback | None,
        on_log: LogCallback | None,
    ) -> bool:
        deadline = time.time() + BUILD_JOB_TIMEOUT_SECONDS

        while time.time() < deadline:
            payload = self._read_kubectl_json(
                "get",
                "job",
                BUILD_JOB_NAME,
                "-n",
                namespace,
            )
            status = payload.get("status") or {}

            if status.get("succeeded", 0) > 0:
                return True

            if status.get("failed", 0) > 0:
                failure_status = self._infer_build_failure_status(result)
                detail = f"Kubernetes build job failed with status {failure_status}."
                pod_name = self._wait_for_pod_name(
                    namespace,
                    f"job-name={BUILD_JOB_NAME}",
                    timeout_seconds=30,
                )
                pod_state = self._describe_pod_state(namespace, pod_name)

                if pod_state:
                    detail = f"{detail} Pod state: {pod_state}"

                result.status = failure_status
                result.error_message = detail
                _emit_log(result, detail, on_log)
                _emit_stage(
                    result,
                    "install" if failure_status == "install_failed" else "build",
                    "failed",
                    detail,
                    on_stage,
                )
                return False

            time.sleep(2)

        detail = "Timed out waiting for the Kubernetes build job to finish."
        result.status = "timeout"
        result.error_message = detail
        _emit_log(result, detail, on_log)
        _emit_stage(result, "build", "failed", detail, on_stage)
        return False

    def _start_port_forward(
        self,
        namespace: str,
        local_port: int,
        result: PreviewRunResult,
        stop_event: threading.Event,
        on_log: LogCallback | None,
    ) -> tuple[subprocess.Popen[str], threading.Thread]:
        process = self._start_kubectl_process(
            "port-forward",
            f"service/{SERVICE_NAME}",
            f"{local_port}:{PREVIEW_CONTAINER_PORT}",
            "-n",
            namespace,
            "--address",
            "127.0.0.1",
        )
        thread = threading.Thread(
            target=_stream_process_output,
            kwargs={
                "process": process,
                "result": result,
                "label": "port-forward",
                "stop_event": stop_event,
                "on_log": on_log,
            },
            daemon=True,
        )
        thread.start()
        return process, thread

    def _wait_for_preview_url(
        self,
        *,
        namespace: str,
        pod_name: str,
        preview_url: str,
        result: PreviewRunResult,
        on_stage: StageCallback | None,
        on_log: LogCallback | None,
        port_forward_process: subprocess.Popen[str] | None = None,
    ) -> bool:
        if self.settings.preview_exposure_mode == "ingress":
            deadline = time.time() + PREVIEW_READY_TIMEOUT_SECONDS

            while time.time() < deadline:
                payload = self._read_kubectl_json(
                    "get",
                    "deployment",
                    DEPLOYMENT_NAME,
                    "-n",
                    namespace,
                )
                status = payload.get("status") or {}

                if status.get("availableReplicas", 0) > 0:
                    return True

                pod_state = self._describe_pod_state(namespace, pod_name)

                if pod_state and "CrashLoopBackOff" in pod_state:
                    detail = f"Preview deployment crashed before becoming ready. {pod_state}"
                    result.status = "runtime_crashed"
                    result.error_message = detail
                    _emit_log(result, detail, on_log)
                    _emit_stage(result, "preview", "failed", detail, on_stage)
                    return False

                time.sleep(2)

            detail = "Timed out waiting for the Kubernetes Ingress preview to become ready."
            result.status = "timeout"
            result.error_message = detail
            _emit_log(result, detail, on_log)
            _emit_stage(result, "preview", "failed", detail, on_stage)
            return False

        deadline = time.time() + PREVIEW_READY_TIMEOUT_SECONDS
        last_error = ""

        while time.time() < deadline:
            if port_forward_process is not None and port_forward_process.poll() is not None:
                detail = (
                    "kubectl port-forward exited before the preview became ready."
                )
                result.status = "preview_failed"
                result.error_message = detail
                _emit_log(result, detail, on_log)
                _emit_stage(result, "preview", "failed", detail, on_stage)
                return False

            try:
                with urllib.request.urlopen(preview_url, timeout=1) as response:
                    if response.status < 500:
                        return True
            except Exception as error:
                last_error = str(error)

            pod_state = self._describe_pod_state(namespace, pod_name)

            if pod_state and "CrashLoopBackOff" in pod_state:
                detail = f"Preview deployment crashed before becoming ready. {pod_state}"
                result.status = "runtime_crashed"
                result.error_message = detail
                _emit_log(result, detail, on_log)
                _emit_stage(result, "preview", "failed", detail, on_stage)
                return False

            time.sleep(2)

        detail = (
            f"Timed out waiting for preview at {preview_url}. "
            f"Last error: {last_error or 'unavailable'}"
        )
        result.status = "timeout"
        result.error_message = detail
        _emit_log(result, detail, on_log)
        _emit_stage(result, "preview", "failed", detail, on_stage)
        return False

    def _remove_stale_previews(self) -> None:
        for preview in _list_registered_previews():
            port_forward_process = preview.port_forward_process

            if port_forward_process is not None and port_forward_process.poll() is not None:
                with _registry_lock:
                    _running_previews.pop(preview.workflow_id, None)
                continue

            try:
                if not self._namespace_exists(preview.namespace):
                    with _registry_lock:
                        _running_previews.pop(preview.workflow_id, None)
            except RancherKubernetesRunnerError:
                continue

    def list_namespaces(self) -> list[KubernetesNamespace]:
        result = self._run_kubectl("get", "namespaces", "-o", "json")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RancherKubernetesRunnerError(
                "kubectl returned invalid namespace JSON."
            ) from error

        items = payload.get("items", [])
        namespaces: list[KubernetesNamespace] = []

        for item in items:
            metadata = item.get("metadata") or {}
            status = item.get("status") or {}
            namespaces.append(
                KubernetesNamespace(
                    name=metadata.get("name", ""),
                    status=status.get("phase", "Unknown"),
                    created_at=metadata.get("creationTimestamp"),
                )
            )

        return namespaces

    def create_test_namespace(self, namespace: str | None = None) -> KubernetesNamespace:
        if namespace is None:
            suffix = uuid4().hex[:8]
            namespace = f"{self.settings.namespace_prefix}-test-{suffix}"

        namespace = self._validate_managed_namespace(namespace)
        result = self._run_kubectl(
            "create",
            "namespace",
            namespace,
            "-o",
            "json",
        )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RancherKubernetesRunnerError(
                "kubectl returned invalid namespace creation JSON."
            ) from error

        metadata = payload.get("metadata") or {}
        status = payload.get("status") or {}
        return KubernetesNamespace(
            name=metadata.get("name", namespace),
            status=status.get("phase", "Active"),
            created_at=metadata.get("creationTimestamp"),
        )

    def delete_namespace(self, namespace: str) -> None:
        namespace = self._validate_managed_namespace(namespace)
        self._run_kubectl(
            "delete",
            "namespace",
            namespace,
            "--wait=false",
            timeout_seconds=120,
        )

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
        namespace = self._build_namespace_name(workflow_id)
        preview: KubernetesRunningPreview | None = None

        self._remove_stale_previews()

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
            deleted_existing = self._delete_namespace_if_exists(
                namespace,
                wait=True,
            )

            if deleted_existing:
                _emit_log(
                    result,
                    f"Deleted existing namespace {namespace} before preview startup.",
                    on_log,
                )

            self._run_kubectl(
                "create",
                "namespace",
                namespace,
                timeout_seconds=120,
            )
            _emit_log(result, f"Created namespace {namespace}.", on_log)

            config_map_manifest, volume_items = self._build_source_config_map(
                workflow_id,
                namespace,
                workspace_dir,
            )
            self._apply_manifest(config_map_manifest)
            _emit_log(
                result,
                f"Mounted generated source files into ConfigMap {CONFIG_MAP_NAME}.",
                on_log,
            )

            _emit_stage(
                result,
                "install",
                "started",
                "Starting Kubernetes build job: dependency installation.",
                on_stage,
            )
            _emit_log(
                result,
                "Starting Kubernetes build job for dependency installation and build validation.",
                on_log,
            )

            self._apply_manifest(
                self._build_job_manifest(workflow_id, namespace, volume_items)
            )

            build_pod_name = self._wait_for_pod_name(
                namespace,
                f"job-name={BUILD_JOB_NAME}",
            )
            build_log_process, build_log_thread = self._start_log_stream(
                namespace=namespace,
                pod_name=build_pod_name,
                result=result,
                label="k8s-build",
                stop_event=threading.Event(),
                on_log=on_log,
                on_stage=on_stage,
            )

            try:
                if not self._wait_for_build_job(
                    namespace,
                    result,
                    on_stage,
                    on_log,
                ):
                    return result
            finally:
                try:
                    build_log_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _terminate_process_tree(build_log_process)
                build_log_thread.join(timeout=2)

            _emit_stage(
                result,
                "preview",
                "started",
                "Creating Kubernetes preview deployment.",
                on_stage,
            )
            _emit_log(result, "Creating Kubernetes preview deployment.", on_log)

            preview_manifests = self._build_preview_manifests(
                workflow_id,
                namespace,
                volume_items,
            )
            self._apply_manifest({
                "apiVersion": "v1",
                "kind": "List",
                "items": preview_manifests,
            })

            preview_pod_name = self._wait_for_pod_name(
                namespace,
                "app.kubernetes.io/component=preview",
            )

            preview = KubernetesRunningPreview(
                workflow_id=workflow_id,
                workspace_dir=workspace_dir,
                namespace=namespace,
                preview_url="",
                preview_port=None,
                logs=result.logs,
            )

            (
                preview.preview_log_process,
                preview.preview_log_thread,
            ) = self._start_log_stream(
                namespace=namespace,
                pod_name=preview_pod_name,
                result=result,
                label="k8s-preview",
                stop_event=preview.stop_event,
                on_log=on_log,
            )

            if self.settings.preview_exposure_mode == "ingress":
                host = f"{namespace}.{self.settings.preview_base_domain}"
                preview.preview_url = f"http://{host}"
            else:
                local_port = _find_available_port()
                preview.preview_port = local_port
                preview.preview_url = f"http://127.0.0.1:{local_port}"
                (
                    preview.port_forward_process,
                    preview.port_forward_thread,
                ) = self._start_port_forward(
                    namespace,
                    local_port,
                    result,
                    preview.stop_event,
                    on_log,
                )

            _register_preview(preview)

            if not self._wait_for_preview_url(
                namespace=namespace,
                pod_name=preview_pod_name,
                preview_url=preview.preview_url,
                result=result,
                on_stage=on_stage,
                on_log=on_log,
                port_forward_process=preview.port_forward_process,
            ):
                self.stop_preview(workflow_id)
                return result

            result.status = "preview_ready"
            result.preview_url = preview.preview_url
            result.preview_port = preview.preview_port
            _emit_log(result, f"Preview ready: {preview.preview_url}", on_log)
            _emit_stage(
                result,
                "preview",
                "completed",
                f"Preview ready at {preview.preview_url}",
                on_stage,
            )
            return result
        except RancherKubernetesRunnerError as error:
            message = str(error)
            result.error_message = message

            if result.status == "preview_failed":
                result.status = "preview_failed"

            _emit_log(result, message, on_log)
            return result
        except Exception as error:
            message = f"Unexpected Kubernetes runner failure: {error}"
            result.error_message = message
            _emit_log(result, message, on_log)
            return result
        finally:
            if result.status != "preview_ready":
                try:
                    self._delete_namespace_if_exists(namespace, wait=False)
                except RancherKubernetesRunnerError:
                    pass

                if preview is not None:
                    preview.stop_event.set()
                    if preview.preview_log_process is not None:
                        _terminate_process_tree(preview.preview_log_process)
                    if preview.port_forward_process is not None:
                        _terminate_process_tree(preview.port_forward_process)
                    with _registry_lock:
                        _running_previews.pop(workflow_id, None)

    def list_previews(self) -> list[RunningPreview]:
        self._remove_stale_previews()

        return [
            RunningPreview(
                workflow_id=preview.workflow_id,
                workspace_dir=preview.workspace_dir,
                preview_url=preview.preview_url,
                preview_port=preview.preview_port,
                runner=self.runner_id,
                pid=(
                    preview.port_forward_process.pid
                    if preview.port_forward_process is not None
                    else (
                        preview.preview_log_process.pid
                        if preview.preview_log_process is not None
                        else None
                    )
                ),
                logs=preview.logs,
                namespace=preview.namespace,
            )
            for preview in _list_registered_previews()
        ]

    def stop_preview(self, workflow_id: str) -> bool:
        preview = _pop_preview(workflow_id)
        namespace = self._build_namespace_name(workflow_id)
        stopped = False

        if preview is not None:
            preview.stop_event.set()

            if preview.port_forward_process is not None:
                _terminate_process_tree(preview.port_forward_process)
                stopped = True

            if preview.preview_log_process is not None:
                _terminate_process_tree(preview.preview_log_process)
                stopped = True

        try:
            if self._delete_namespace_if_exists(namespace, wait=False):
                stopped = True
        except RancherKubernetesRunnerError:
            pass

        return stopped

    def stop_all_previews(self) -> None:
        for preview in _list_registered_previews():
            self.stop_preview(preview.workflow_id)


_RANCHER_K8S_PREVIEW_RUNNER: RancherKubernetesPreviewRunner | None = None


def get_rancher_k8s_preview_runner(
    settings: RunnerSettings,
) -> RancherKubernetesPreviewRunner:
    global _RANCHER_K8S_PREVIEW_RUNNER

    if (
        _RANCHER_K8S_PREVIEW_RUNNER is None
        or _RANCHER_K8S_PREVIEW_RUNNER.settings != settings
    ):
        _RANCHER_K8S_PREVIEW_RUNNER = RancherKubernetesPreviewRunner(settings)

    return _RANCHER_K8S_PREVIEW_RUNNER


def _stop_all_registered_previews() -> None:
    for preview in _list_registered_previews():
        try:
            runner_settings = getattr(
                _RANCHER_K8S_PREVIEW_RUNNER,
                "settings",
                None,
            )

            if runner_settings is None:
                continue

            get_rancher_k8s_preview_runner(runner_settings).stop_preview(
                preview.workflow_id
            )
        except Exception:
            continue


atexit.register(_stop_all_registered_previews)
