import asyncio
from typing import Any, Awaitable, Callable
from uuid import uuid4

from app.agents import (
    architecture_agent,
    code_generation_agent,
    requirements_agent,
)
from app.config import GENERATED_ROOT
from app.models import (
    ArchitectureSpec,
    BuildAttempt,
    GeneratedFile,
    RequirementsSpec,
    WorkflowResponse,
)
from app.runners.base_runner import PreviewRunResult
from app.runners.factory import get_preview_runner
from app.services.file_writer import write_generated_files


PublishEvent = Callable[[str, dict[str, Any]], Awaitable[None]]
DEFAULT_MAX_ATTEMPTS = 1


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()


def _attempt_summary(
    attempt_number: int,
    status: str,
) -> str:
    if status == "preview_ready":
        return f"Attempt {attempt_number} succeeded."

    return f"Attempt {attempt_number} ended with {status}."


def _compose_change_prompt(
    prompt: str,
    scope: str,
    feedback: str,
) -> str:
    cleaned_feedback = feedback.strip()

    if not cleaned_feedback:
        return prompt

    return (
        f"{prompt}\n\n"
        f"User requested {scope} changes before approval.\n"
        f"Feedback:\n{cleaned_feedback}"
    )


async def _emit_attempt_started(
    *,
    emit: PublishEvent,
    attempt_number: int,
    max_attempts: int,
    is_retrying: bool,
) -> None:
    await emit("attempt:started", {
        "attemptNumber": attempt_number,
        "maxAttempts": max_attempts,
        "isRetrying": is_retrying,
    })


async def _emit_attempt_completed(
    *,
    emit: PublishEvent,
    attempt: BuildAttempt,
    max_attempts: int,
    will_retry: bool,
) -> None:
    await emit("attempt:completed", {
        "attempt": _model_to_dict(attempt),
        "maxAttempts": max_attempts,
        "willRetry": will_retry,
    })


async def _run_requirements_stage(
    *,
    prompt: str,
    log: Callable[[str], Awaitable[None]],
    emit: PublishEvent,
) -> RequirementsSpec:
    await emit("agent:started", {
        "agentId": "requirements",
        "name": "Requirements Agent",
        "detail": "Converting prompt into requirements",
    })
    await log("Requirements Agent started.")

    requirements = await requirements_agent(
        prompt,
        log=log,
    )

    await log("Requirements Agent completed.")
    await log(f"Detected app name: {requirements.appName}")

    await emit("agent:completed", {
        "agentId": "requirements",
        "name": "Requirements Agent",
        "detail": f"{len(requirements.features)} features extracted",
        "output": _model_to_dict(requirements),
    })
    return requirements


async def _run_architecture_stage(
    *,
    prompt: str,
    requirements: RequirementsSpec,
    log: Callable[[str], Awaitable[None]],
    emit: PublishEvent,
) -> ArchitectureSpec:
    await emit("agent:started", {
        "agentId": "architecture",
        "name": "Architecture Agent",
        "detail": "Designing frontend architecture",
    })
    await log("Architecture Agent started.")

    architecture = await architecture_agent(
        prompt=prompt,
        requirements=requirements,
        log=log,
    )

    await log("Architecture Agent completed.")
    await log(
        f"Selected frontend stack: {architecture.stack.frontend} + {architecture.stack.buildTool}"
    )

    await emit("agent:completed", {
        "agentId": "architecture",
        "name": "Architecture Agent",
        "detail": f"{len(architecture.components)} components planned",
        "output": _model_to_dict(architecture),
    })
    return architecture


async def _emit_awaiting_approval(
    *,
    project_id: str,
    workflow_id: str,
    prompt: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    logs: list[str],
    emit: PublishEvent,
) -> WorkflowResponse:
    response = WorkflowResponse(
        projectId=project_id,
        workflowId=workflow_id,
        status="awaiting_approval",
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        approvalStage="architecture",
        files=[],
        logs=logs,
        previewUrl=None,
        previewPort=None,
        workspacePath=None,
        attempts=[],
        currentAttempt=1,
        maxAttempts=DEFAULT_MAX_ATTEMPTS,
        isRetrying=False,
    )

    await emit("workflow:awaiting_approval", _model_to_dict(response))
    return response


async def _run_generation_and_preview(
    *,
    prompt: str,
    project_id: str,
    workflow_id: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    publish: PublishEvent | None,
    initial_logs: list[str] | None = None,
) -> WorkflowResponse:
    logs = list(initial_logs or [])
    max_attempts = DEFAULT_MAX_ATTEMPTS
    preview_runner = get_preview_runner()

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if publish is not None:
            await publish(event_type, payload)

    async def log(message: str) -> None:
        logs.append(message)
        await emit("log", {"message": message})

    await emit("agent:started", {
        "agentId": "code",
        "name": "Code Generation Agent",
        "detail": "Generating React source files",
    })
    await log("Code Generation Agent started.")

    try:
        files = await code_generation_agent(
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
            log=log,
        )
    except Exception as error:
        detail = str(error)
        await log(f"Code Generation Agent failed: {detail}")
        await emit("agent:failed", {
            "agentId": "code",
            "name": "Code Generation Agent",
            "detail": detail,
        })
        raise

    await log("Code Generation Agent completed.")
    await log(f"Generated {len(files)} files.")

    await emit("agent:completed", {
        "agentId": "code",
        "name": "Code Generation Agent",
        "detail": f"{len(files)} files generated",
    })

    await emit("code:generated", {
        "files": [_model_to_dict(file) for file in files],
    })

    await emit("agent:started", {
        "agentId": "files",
        "name": "File Writer",
        "detail": "Writing generated files to disk",
    })
    await log("File Writer started.")

    file_write_result = write_generated_files(
        project_id=project_id,
        workflow_id=workflow_id,
        files=files,
    )

    await log("File Writer completed.")
    await log(f"Workspace created: {file_write_result.workspacePath}")

    for written_file in file_write_result.writtenFiles:
        await log(f"Wrote file: {written_file}")

    await emit("agent:completed", {
        "agentId": "files",
        "name": "File Writer",
        "detail": f"Files written to {file_write_result.workspacePath}",
    })

    await emit("files:written", {
        "workspacePath": file_write_result.workspacePath,
        "writtenFiles": file_write_result.writtenFiles,
    })

    workspace_dir = GENERATED_ROOT / project_id / workflow_id
    current_files: list[GeneratedFile] = files
    attempts: list[BuildAttempt] = []

    # Each attempt delegates install/build/preview execution to the active runner
    # so the workflow layer can stay agnostic to local versus Kubernetes preview.
    async def run_preview_attempt(
        attempt_number: int,
    ) -> PreviewRunResult:
        await _emit_attempt_started(
            emit=emit,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            is_retrying=attempt_number > 1,
        )

        await emit("agent:started", {
            "agentId": "preview",
            "name": "Live Preview",
            "detail": f"Attempt {attempt_number}/{max_attempts}: validating install, build, and preview startup",
        })

        await log(
            f"{preview_runner.display_name} attempt {attempt_number}/{max_attempts} started."
        )
        await log("Running dependency install, build, and preview validation.")

        loop = asyncio.get_running_loop()

        def on_runner_log(message: str) -> None:
            future = asyncio.run_coroutine_threadsafe(log(message), loop)
            future.result()

        def on_runner_stage(stage: str, status: str, detail: str) -> None:
            future = asyncio.run_coroutine_threadsafe(
                emit(
                    "runner:stage",
                    {
                        "attemptNumber": attempt_number,
                        "stage": stage,
                        "status": status,
                        "detail": detail,
                    },
                ),
                loop,
            )
            future.result()

        return await asyncio.to_thread(
            preview_runner.start_preview,
            workflow_id=workflow_id,
            workspace_dir=workspace_dir,
            on_stage=on_runner_stage,
            on_log=on_runner_log,
        )

    attempt_number = 1
    preview_result = await run_preview_attempt(attempt_number)

    if preview_result.status == "preview_ready":
        await log(f"{preview_runner.display_name} completed.")
        await log(f"Preview ready: {preview_result.preview_url}")

        success_attempt = BuildAttempt(
            attemptNumber=attempt_number,
            status="preview_ready",
            summary=_attempt_summary(attempt_number, "preview_ready"),
            logs=preview_result.logs,
        )
        attempts.append(success_attempt)
        await _emit_attempt_completed(
            emit=emit,
            attempt=success_attempt,
            max_attempts=max_attempts,
            will_retry=False,
        )

        await emit("agent:completed", {
            "agentId": "preview",
            "name": "Live Preview",
            "detail": f"Preview ready at {preview_result.preview_url}",
        })

        await emit("preview:ready", {
            "previewUrl": preview_result.preview_url,
            "previewPort": preview_result.preview_port,
            "attemptNumber": attempt_number,
        })

        response = WorkflowResponse(
            projectId=project_id,
            workflowId=workflow_id,
            status="preview_ready",
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
            approvalStage=None,
            files=current_files,
            logs=logs,
            previewUrl=preview_result.preview_url,
            previewPort=preview_result.preview_port,
            workspacePath=file_write_result.workspacePath,
            attempts=attempts,
            currentAttempt=attempt_number,
            maxAttempts=max_attempts,
            isRetrying=False,
        )

        await emit("workflow:completed", _model_to_dict(response))
        return response

    detail = preview_result.error_message or "Preview validation failed."
    await log(
        f"{preview_runner.display_name} failed with status: {preview_result.status}"
    )
    await emit("agent:failed", {
        "agentId": "preview",
        "name": "Live Preview",
        "detail": detail,
    })

    failed_attempt = BuildAttempt(
        attemptNumber=attempt_number,
        status=preview_result.status,
        summary=_attempt_summary(attempt_number, preview_result.status),
        failureType=preview_result.status,
        logs=preview_result.logs,
    )
    attempts.append(failed_attempt)
    await _emit_attempt_completed(
        emit=emit,
        attempt=failed_attempt,
        max_attempts=max_attempts,
        will_retry=False,
    )

    await emit("preview:failed", {
        "status": preview_result.status,
        "message": detail,
        "attemptNumber": attempt_number,
    })

    response = WorkflowResponse(
        projectId=project_id,
        workflowId=workflow_id,
        status=preview_result.status,
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        approvalStage=None,
        files=current_files,
        logs=logs,
        previewUrl=None,
        previewPort=None,
        workspacePath=file_write_result.workspacePath,
        attempts=attempts,
        currentAttempt=attempt_number,
        maxAttempts=max_attempts,
        isRetrying=False,
    )

    await emit("workflow:completed", _model_to_dict(response))
    return response


async def run_workflow_until_approval(
    prompt: str,
    project_id: str,
    workflow_id: str | None = None,
    publish: PublishEvent | None = None,
) -> WorkflowResponse:
    workflow_id = workflow_id or f"workflow_{uuid4().hex[:8]}"
    logs: list[str] = []

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if publish is not None:
            await publish(event_type, payload)

    async def log(message: str) -> None:
        logs.append(message)
        await emit("log", {"message": message})

    await emit("workflow:started", {
        "projectId": project_id,
        "workflowId": workflow_id,
        "status": "running",
        "currentAttempt": 1,
        "maxAttempts": DEFAULT_MAX_ATTEMPTS,
        "isRetrying": False,
    })
    await log(f"Workflow {workflow_id} started.")

    requirements = await _run_requirements_stage(
        prompt=prompt,
        log=log,
        emit=emit,
    )
    architecture = await _run_architecture_stage(
        prompt=prompt,
        requirements=requirements,
        log=log,
        emit=emit,
    )

    await log("Architecture approval required before code generation.")
    return await _emit_awaiting_approval(
        project_id=project_id,
        workflow_id=workflow_id,
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        logs=logs,
        emit=emit,
    )


async def run_workflow_after_approval(
    *,
    prompt: str,
    project_id: str,
    workflow_id: str,
    requirements: RequirementsSpec,
    architecture: ArchitectureSpec,
    publish: PublishEvent | None = None,
    approval_note: str | None = None,
) -> WorkflowResponse:
    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if publish is not None:
            await publish(event_type, payload)

    await emit("workflow:started", {
        "projectId": project_id,
        "workflowId": workflow_id,
        "status": "running",
        "currentAttempt": 1,
        "maxAttempts": DEFAULT_MAX_ATTEMPTS,
        "isRetrying": False,
    })

    initial_logs = ["Architecture approved. Resuming code generation."]

    if approval_note and approval_note.strip():
        initial_logs.append(f"Approval note: {approval_note.strip()}")

    for message in initial_logs:
        await emit("log", {"message": message})

    return await _run_generation_and_preview(
        prompt=prompt,
        project_id=project_id,
        workflow_id=workflow_id,
        requirements=requirements,
        architecture=architecture,
        publish=publish,
        initial_logs=initial_logs,
    )


async def run_workflow_after_change_request(
    *,
    prompt: str,
    project_id: str,
    workflow_id: str,
    change_scope: str,
    change_feedback: str,
    current_requirements: RequirementsSpec | None,
    publish: PublishEvent | None = None,
) -> WorkflowResponse:
    logs: list[str] = []

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        if publish is not None:
            await publish(event_type, payload)

    async def log(message: str) -> None:
        logs.append(message)
        await emit("log", {"message": message})

    await emit("workflow:started", {
        "projectId": project_id,
        "workflowId": workflow_id,
        "status": "running",
        "currentAttempt": 1,
        "maxAttempts": DEFAULT_MAX_ATTEMPTS,
        "isRetrying": False,
    })

    await log(
        f"Change request received for {change_scope}: {change_feedback.strip()}"
    )

    revised_prompt = _compose_change_prompt(
        prompt,
        change_scope,
        change_feedback,
    )

    if change_scope == "requirements":
        requirements = await _run_requirements_stage(
            prompt=revised_prompt,
            log=log,
            emit=emit,
        )
    else:
        if current_requirements is None:
            raise RuntimeError(
                "Current requirements are missing. Cannot regenerate architecture only."
            )

        requirements = current_requirements
        await log("Reusing approved requirements while regenerating architecture.")

    architecture = await _run_architecture_stage(
        prompt=revised_prompt,
        requirements=requirements,
        log=log,
        emit=emit,
    )

    await log("Updated architecture is awaiting approval.")
    return await _emit_awaiting_approval(
        project_id=project_id,
        workflow_id=workflow_id,
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        logs=logs,
        emit=emit,
    )
