from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal


RunnerStatus = Literal[
    "preview_ready",
    "install_failed",
    "build_failed",
    "preview_failed",
    "timeout",
    "runtime_crashed",
]
RunnerStage = Literal["install", "build", "preview"]
RunnerStageStatus = Literal["started", "completed", "failed"]
StageCallback = Callable[[RunnerStage, RunnerStageStatus, str], None]
LogCallback = Callable[[str], None]


class PreviewRunnerError(RuntimeError):
    pass


@dataclass
class RunnerStageEvent:
    stage: RunnerStage
    status: RunnerStageStatus
    detail: str


@dataclass
class PreviewRunResult:
    status: RunnerStatus
    preview_url: str | None = None
    preview_port: int | None = None
    logs: list[str] = field(default_factory=list)
    error_message: str | None = None
    stage_events: list[RunnerStageEvent] = field(default_factory=list)


@dataclass
class RunningPreview:
    workflow_id: str
    workspace_dir: Path
    preview_url: str
    preview_port: int | None
    runner: str
    pid: int | None = None
    logs: list[str] = field(default_factory=list)
    namespace: str | None = None


class PreviewRunner(ABC):
    runner_id = "base"
    display_name = "Preview Runner"

    @abstractmethod
    def start_preview(
        self,
        workflow_id: str,
        workspace_dir: Path,
        *,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> PreviewRunResult:
        raise NotImplementedError

    @abstractmethod
    def list_previews(self) -> list[RunningPreview]:
        raise NotImplementedError

    def restart_preview(
        self,
        workflow_id: str,
        workspace_dir: Path,
        *,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> PreviewRunResult:
        self.stop_preview(workflow_id)
        return self.start_preview(
            workflow_id=workflow_id,
            workspace_dir=workspace_dir,
            on_stage=on_stage,
            on_log=on_log,
        )

    @abstractmethod
    def stop_preview(self, workflow_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop_all_previews(self) -> None:
        raise NotImplementedError
