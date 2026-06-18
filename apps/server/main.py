import asyncio
import shutil
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import GENERATED_ROOT, PROJECT_ROOT, get_runner_settings
from app.models import (
    ArchitectureSpec,
    KubernetesNamespaceActionResponse,
    KubernetesNamespaceInfo,
    KubernetesNamespaceListResponse,
    PreviewActionResponse,
    PreviewInfo,
    PreviewListResponse,
    ProjectActionResponse,
    ProjectListResponse,
    ProjectRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    RequirementsSpec,
    RunnerConfigResponse,
    WorkflowActionResponse,
    WorkflowApprovalRequest,
    WorkflowChangeRequest,
    WorkflowRequest,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowSummary,
    WorkflowStartResponse,
)
from app.persistence import (
    DEFAULT_PROJECT_ID,
    append_workflow_log,
    create_project_record,
    create_workflow_record,
    delete_project_record,
    get_project_record,
    get_workflow_record,
    init_database,
    list_project_records,
    list_workflow_records,
    replace_generated_files,
    set_preview_metadata,
    upsert_build_attempt,
    update_project_record,
    update_workflow_record,
)
from app.realtime import workflow_event_manager
from app.runners.factory import get_preview_runner, get_rancher_k8s_runner
from app.runners.rancher_k8s_runner import RancherKubernetesRunnerError
from app.services.file_writer import build_workspace_dir, validate_project_id
from app.workflow import (
    run_workflow_until_approval,
    run_workflow_after_approval,
    run_workflow_after_change_request,
)


app = FastAPI(title="Agentic OS API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_database()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "agentic-os-api",
    }


@app.get("/api/runner", response_model=RunnerConfigResponse)
async def get_runner_config():
    runner_settings = get_runner_settings()
    return RunnerConfigResponse(
        runner=runner_settings.runner,
        kubeconfigPath=runner_settings.kubeconfig_path,
        k8sContext=runner_settings.k8s_context,
        namespacePrefix=runner_settings.namespace_prefix,
        previewExposureMode=runner_settings.preview_exposure_mode,
        previewBaseDomain=runner_settings.preview_base_domain,
    )


@app.get(
    "/api/kubernetes/namespaces",
    response_model=KubernetesNamespaceListResponse,
)
async def get_kubernetes_namespaces():
    runner = get_rancher_k8s_runner()

    try:
        namespaces = await asyncio.to_thread(runner.list_namespaces)
    except RancherKubernetesRunnerError as error:
        raise _namespace_error_to_http_exception(error) from error

    return KubernetesNamespaceListResponse(
        namespaces=[
            KubernetesNamespaceInfo(
                name=namespace.name,
                status=namespace.status,
                createdAt=namespace.created_at,
            )
            for namespace in namespaces
        ]
    )


@app.post(
    "/api/kubernetes/test-namespace",
    response_model=KubernetesNamespaceActionResponse,
)
async def create_kubernetes_test_namespace():
    runner = get_rancher_k8s_runner()

    try:
        namespace = await asyncio.to_thread(runner.create_test_namespace)
    except RancherKubernetesRunnerError as error:
        raise _namespace_error_to_http_exception(error) from error

    return KubernetesNamespaceActionResponse(
        namespace=namespace.name,
        status="created",
        message="Test namespace created.",
    )


@app.delete(
    "/api/kubernetes/namespaces/{namespace}",
    response_model=KubernetesNamespaceActionResponse,
)
async def delete_kubernetes_namespace(namespace: str):
    runner = get_rancher_k8s_runner()

    try:
        await asyncio.to_thread(runner.delete_namespace, namespace)
    except RancherKubernetesRunnerError as error:
        raise _namespace_error_to_http_exception(error) from error

    return KubernetesNamespaceActionResponse(
        namespace=namespace,
        status="deleted",
        message="Namespace deletion requested.",
    )


def _validate_workflow_id(workflow_id: str) -> str:
    allowed_characters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

    if not workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID is required.")

    if any(character not in allowed_characters for character in workflow_id):
        raise HTTPException(status_code=400, detail="Invalid workflow ID.")

    return workflow_id


def _validate_project_id_or_400(project_id: str) -> str:
    try:
        validate_project_id(project_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return project_id


def _workspace_dir_from_relative_path(workspace_path: str) -> Path:
    generated_root = GENERATED_ROOT.resolve()
    workspace_dir = (PROJECT_ROOT / workspace_path).resolve()

    try:
        workspace_dir.relative_to(generated_root)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid workspace path.") from error

    return workspace_dir


def _resolve_workspace_dir_for_workflow(workflow: dict) -> Path:
    workspace_path = workflow.get("workspacePath")

    if isinstance(workspace_path, str) and workspace_path.strip():
        return _workspace_dir_from_relative_path(workspace_path)

    project_id = workflow.get("projectId")
    workflow_id = workflow.get("workflowId")

    if not isinstance(project_id, str) or not isinstance(workflow_id, str):
        raise HTTPException(
            status_code=404,
            detail="Generated workspace not found for this workflow.",
        )

    return build_workspace_dir(
        project_id=project_id,
        workflow_id=workflow_id,
    )


def _workspace_path_for_response(workspace_dir: Path) -> str:
    return str(workspace_dir.relative_to(PROJECT_ROOT)).replace("\\", "/")


def _namespace_error_to_http_exception(error: RancherKubernetesRunnerError) -> HTTPException:
    detail = str(error)
    lowered = detail.lower()

    if "not found" in lowered:
        return HTTPException(status_code=404, detail=detail)

    if "already exists" in lowered or "alreadyexists" in lowered:
        return HTTPException(status_code=409, detail=detail)

    if "invalid namespace" in lowered or "namespace must use the configured prefix" in lowered:
        return HTTPException(status_code=400, detail=detail)

    return HTTPException(status_code=503, detail=detail)


def _persist_workflow_event(
    workflow_id: str,
    event_type: str,
    payload: dict,
) -> None:
    # Persist only the workflow state the UI needs to restore after refresh.
    if event_type == "workflow:started":
        update_workflow_record(
            workflow_id,
            project_id=payload.get("projectId"),
            status=payload.get("status", "running"),
            approval_stage=payload.get("approvalStage"),
            current_attempt=payload.get("currentAttempt", 1),
            max_attempts=payload.get("maxAttempts", 1),
            is_retrying=payload.get("isRetrying", False),
        )
        return

    if event_type == "log":
        message = payload.get("message")

        if message:
            append_workflow_log(workflow_id, message)
        return

    if event_type == "code:generated":
        update_workflow_record(workflow_id, status="code_generated")
        files = payload.get("files") or []
        replace_generated_files(workflow_id, files)
        return

    if event_type == "agent:completed":
        agent_id = payload.get("agentId")
        output = payload.get("output")

        if agent_id == "requirements" and isinstance(output, dict):
            update_workflow_record(
                workflow_id,
                requirements=output,
            )
            return

        if agent_id == "architecture" and isinstance(output, dict):
            update_workflow_record(
                workflow_id,
                architecture=output,
            )
            return

    if event_type == "attempt:started":
        update_workflow_record(
            workflow_id,
            status="running",
            approval_stage=None,
            current_attempt=payload.get("attemptNumber", 1),
            max_attempts=payload.get("maxAttempts", 1),
            is_retrying=payload.get("isRetrying", False),
        )
        return

    if event_type == "attempt:completed":
        attempt = payload.get("attempt")

        if isinstance(attempt, dict):
            upsert_build_attempt(workflow_id, attempt)

        update_workflow_record(
            workflow_id,
            current_attempt=(
                attempt.get("attemptNumber")
                if isinstance(attempt, dict)
                else payload.get("currentAttempt", 1)
            ),
            max_attempts=payload.get("maxAttempts", 1),
            is_retrying=payload.get("willRetry", False),
        )
        return

    if event_type == "workflow:awaiting_approval":
        update_workflow_record(
            workflow_id,
            project_id=payload.get("projectId"),
            prompt=payload.get("prompt"),
            status=payload.get("status", "awaiting_approval"),
            requirements=payload.get("requirements"),
            architecture=payload.get("architecture"),
            approval_stage=payload.get("approvalStage"),
            current_attempt=payload.get("currentAttempt", 1),
            max_attempts=payload.get("maxAttempts", 1),
            is_retrying=payload.get("isRetrying", False),
        )
        return

    if event_type == "files:written":
        update_workflow_record(
            workflow_id,
            status="files_written",
            approval_stage=None,
        )
        set_preview_metadata(
            workflow_id,
            workspace_path=payload.get("workspacePath"),
        )
        return

    if event_type == "preview:ready":
        update_workflow_record(
            workflow_id,
            status="preview_ready",
            approval_stage=None,
            is_retrying=False,
        )
        set_preview_metadata(
            workflow_id,
            preview_url=payload.get("previewUrl"),
            preview_port=payload.get("previewPort"),
        )
        return

    if event_type == "preview:failed":
        update_workflow_record(
            workflow_id,
            status=payload.get("status", "preview_failed"),
            approval_stage=None,
            is_retrying=False,
        )
        set_preview_metadata(
            workflow_id,
            preview_url=None,
            preview_port=None,
        )
        return

    if event_type == "preview:stopped":
        reason = payload.get("reason")

        if reason == "restart":
            update_workflow_record(
                workflow_id,
                status="preview_restarting",
                approval_stage=None,
            )
        elif reason == "stop":
            update_workflow_record(
                workflow_id,
                status="preview_stopped",
                approval_stage=None,
            )

        set_preview_metadata(
            workflow_id,
            preview_url=None,
            preview_port=None,
        )
        return

    if event_type == "workspace:cleaned":
        update_workflow_record(
            workflow_id,
            status="workspace_cleaned",
            approval_stage=None,
        )
        set_preview_metadata(
            workflow_id,
            workspace_path=None,
            preview_url=None,
            preview_port=None,
        )
        return

    if event_type == "workflow:completed":
        update_workflow_record(
            workflow_id,
            project_id=payload.get("projectId"),
            prompt=payload.get("prompt"),
            status=payload.get("status", "completed"),
            requirements=payload.get("requirements"),
            architecture=payload.get("architecture"),
            approval_stage=payload.get("approvalStage"),
            current_attempt=payload.get("currentAttempt", 1),
            max_attempts=payload.get("maxAttempts", 1),
            is_retrying=payload.get("isRetrying", False),
        )

        files = payload.get("files") or []

        if files:
            replace_generated_files(workflow_id, files)

        set_preview_metadata(
            workflow_id,
            workspace_path=payload.get("workspacePath"),
            preview_url=payload.get("previewUrl"),
            preview_port=payload.get("previewPort"),
        )
        return

    if event_type == "workflow:failed":
        update_workflow_record(
            workflow_id,
            status="failed",
            approval_stage=None,
            is_retrying=False,
        )


async def _publish_workflow_event(
    workflow_id: str,
    event_type: str,
    payload: dict,
) -> None:
    await workflow_event_manager.publish(
        workflow_id=workflow_id,
        event_type=event_type,
        payload=payload,
    )
    _persist_workflow_event(
        workflow_id=workflow_id,
        event_type=event_type,
        payload=payload,
    )


async def _publish_log(workflow_id: str, message: str) -> None:
    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="log",
        payload={"message": message},
    )


PublishWorkflowEvent = Callable[[str, dict], Awaitable[None]]
WorkflowTask = Callable[[PublishWorkflowEvent], Awaitable[None]]


async def _run_persisted_workflow_task(
    workflow_id: str,
    task: WorkflowTask,
) -> None:
    async def publish(event_type: str, payload: dict) -> None:
        await workflow_event_manager.publish(
            workflow_id=workflow_id,
            event_type=event_type,
            payload=payload,
        )
        _persist_workflow_event(
            workflow_id=workflow_id,
            event_type=event_type,
            payload=payload,
        )

    try:
        await task(publish)
    except Exception as error:
        message = str(error)

        await publish(
            event_type="log",
            payload={
                "message": f"Workflow failed: {message}",
            },
        )
        await publish(
            event_type="workflow:failed",
            payload={
                "status": "failed",
                "message": message,
            },
        )


async def run_workflow_background(
    workflow_id: str,
    project_id: str,
    prompt: str,
) -> None:
    async def task(publish: PublishWorkflowEvent) -> None:
        await run_workflow_until_approval(
            prompt=prompt,
            project_id=project_id,
            workflow_id=workflow_id,
            publish=publish,
        )

    await _run_persisted_workflow_task(workflow_id, task)


async def run_approved_workflow_background(
    workflow_id: str,
    project_id: str,
    prompt: str,
    requirements: dict,
    architecture: dict,
    approval_note: str | None,
) -> None:
    async def task(publish: PublishWorkflowEvent) -> None:
        await run_workflow_after_approval(
            prompt=prompt,
            project_id=project_id,
            workflow_id=workflow_id,
            requirements=RequirementsSpec(**requirements),
            architecture=ArchitectureSpec(**architecture),
            publish=publish,
            approval_note=approval_note,
        )

    await _run_persisted_workflow_task(workflow_id, task)


async def run_change_request_background(
    workflow_id: str,
    project_id: str,
    prompt: str,
    change_scope: str,
    change_feedback: str,
    requirements: dict | None,
) -> None:
    async def task(publish: PublishWorkflowEvent) -> None:
        await run_workflow_after_change_request(
            prompt=prompt,
            project_id=project_id,
            workflow_id=workflow_id,
            change_scope=change_scope,
            change_feedback=change_feedback,
            current_requirements=(
                RequirementsSpec(**requirements)
                if requirements is not None
                else None
            ),
            publish=publish,
        )

    await _run_persisted_workflow_task(workflow_id, task)


@app.post("/api/workflows", response_model=WorkflowStartResponse)
async def create_workflow(
    request: WorkflowRequest,
    background_tasks: BackgroundTasks,
):
    prompt = request.prompt.strip()
    project_id = _validate_project_id_or_400(request.projectId)

    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Prompt is required.",
        )

    if get_project_record(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    workflow_id = f"workflow_{uuid4().hex[:8]}"
    create_workflow_record(
        project_id=project_id,
        workflow_id=workflow_id,
        prompt=prompt,
        status="queued",
    )

    background_tasks.add_task(
        run_workflow_background,
        workflow_id,
        project_id,
        prompt,
    )

    return WorkflowStartResponse(
        projectId=project_id,
        workflowId=workflow_id,
        status="queued",
    )


@app.get("/api/projects", response_model=ProjectListResponse)
async def get_projects():
    projects = list_project_records()

    return ProjectListResponse(
        projects=[ProjectResponse(**project) for project in projects],
    )


@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(request: ProjectRequest):
    name = request.name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")

    project_id = f"project_{uuid4().hex[:8]}"
    create_project_record(
        project_id=project_id,
        name=name,
        description=(
            request.description.strip()
            if isinstance(request.description, str) and request.description.strip()
            else None
        ),
    )
    project = get_project_record(project_id)

    if project is None:
        raise HTTPException(status_code=500, detail="Project could not be created.")

    return ProjectResponse(**project)


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    _validate_project_id_or_400(project_id)
    project = get_project_record(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    return ProjectResponse(**project)


@app.patch("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, request: ProjectUpdateRequest):
    _validate_project_id_or_400(project_id)
    project = get_project_record(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    name = request.name.strip() if isinstance(request.name, str) else None
    description = (
        request.description.strip()
        if isinstance(request.description, str) and request.description.strip()
        else None
    )

    if request.name is not None and not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")

    update_kwargs: dict[str, str | None] = {}

    if request.name is not None:
        update_kwargs["name"] = name

    if request.description is not None:
        update_kwargs["description"] = description

    update_project_record(
        project_id,
        **update_kwargs,
    )
    updated_project = get_project_record(project_id)

    if updated_project is None:
        raise HTTPException(status_code=500, detail="Project could not be updated.")

    return ProjectResponse(**updated_project)


@app.delete("/api/projects/{project_id}", response_model=ProjectActionResponse)
async def delete_project(project_id: str):
    _validate_project_id_or_400(project_id)

    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(
            status_code=409,
            detail="The default project cannot be deleted.",
        )

    project = get_project_record(project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    project_workflows = list_workflow_records(project_id=project_id)
    preview_runner = get_preview_runner()

    for workflow in project_workflows:
        await asyncio.to_thread(preview_runner.stop_preview, workflow["workflowId"])

        workspace_path = workflow.get("workspacePath")

        if isinstance(workspace_path, str) and workspace_path.strip():
            workspace_dir = _workspace_dir_from_relative_path(workspace_path)

            if workspace_dir.exists():
                try:
                    await asyncio.to_thread(shutil.rmtree, workspace_dir)
                except OSError as error:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to remove workspace: {error}",
                    ) from error

    project_root_dir = (GENERATED_ROOT / project_id).resolve()

    if project_root_dir.exists():
        try:
            await asyncio.to_thread(shutil.rmtree, project_root_dir)
        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to remove project workspace folder: {error}",
            ) from error

    delete_project_record(project_id)

    return ProjectActionResponse(
        projectId=project_id,
        status="completed",
        message="Project deleted.",
    )


@app.get("/api/workflows", response_model=WorkflowListResponse)
async def get_workflows():
    workflows = list_workflow_records()

    return WorkflowListResponse(
        workflows=[WorkflowSummary(**workflow) for workflow in workflows],
    )


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found.",
        )

    return WorkflowResponse(**workflow)


@app.get(
    "/api/projects/{project_id}/workflows",
    response_model=WorkflowListResponse,
)
async def get_project_workflows(project_id: str):
    _validate_project_id_or_400(project_id)

    if get_project_record(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    workflows = list_workflow_records(project_id=project_id)

    return WorkflowListResponse(
        workflows=[WorkflowSummary(**workflow) for workflow in workflows],
    )


@app.post(
    "/api/workflows/{workflow_id}/approve",
    response_model=WorkflowActionResponse,
)
async def approve_workflow(
    workflow_id: str,
    request: WorkflowApprovalRequest,
    background_tasks: BackgroundTasks,
):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    if workflow["status"] != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail="Workflow is not waiting for approval.",
        )

    requirements = workflow.get("requirements")
    architecture = workflow.get("architecture")

    if not isinstance(requirements, dict) or not isinstance(architecture, dict):
        raise HTTPException(
            status_code=409,
            detail="Workflow is missing persisted planning state.",
        )

    background_tasks.add_task(
        run_approved_workflow_background,
        workflow_id,
        workflow["projectId"],
        workflow["prompt"],
        requirements,
        architecture,
        request.note,
    )

    return WorkflowActionResponse(
        workflowId=workflow_id,
        status="running",
        message="Architecture approved. Resuming workflow.",
    )


@app.post(
    "/api/workflows/{workflow_id}/request-changes",
    response_model=WorkflowActionResponse,
)
async def request_workflow_changes(
    workflow_id: str,
    request: WorkflowChangeRequest,
    background_tasks: BackgroundTasks,
):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    if workflow["status"] != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail="Workflow is not waiting for approval.",
        )

    feedback = request.feedback.strip()

    if not feedback:
        raise HTTPException(
            status_code=400,
            detail="Feedback is required when requesting changes.",
        )

    requirements = workflow.get("requirements")

    if request.scope == "architecture" and not isinstance(requirements, dict):
        raise HTTPException(
            status_code=409,
            detail="Workflow is missing requirements for architecture regeneration.",
        )

    background_tasks.add_task(
        run_change_request_background,
        workflow_id,
        workflow["projectId"],
        workflow["prompt"],
        request.scope,
        feedback,
        requirements if isinstance(requirements, dict) else None,
    )

    return WorkflowActionResponse(
        workflowId=workflow_id,
        status="running",
        message=f"Change request accepted. Regenerating {request.scope}.",
    )


@app.get("/api/previews", response_model=PreviewListResponse)
async def get_running_previews():
    preview_runner = get_preview_runner()
    previews = await asyncio.to_thread(preview_runner.list_previews)

    return PreviewListResponse(
        previews=[
            PreviewInfo(
                workflowId=preview.workflow_id,
                previewUrl=preview.preview_url,
                previewPort=preview.preview_port,
                workspacePath=_workspace_path_for_response(preview.workspace_dir),
                pid=preview.pid,
                runner=preview.runner,
                namespace=preview.namespace,
            )
            for preview in previews
        ]
    )


@app.post(
    "/api/workflows/{workflow_id}/preview/restart",
    response_model=PreviewActionResponse,
)
async def restart_workflow_preview(workflow_id: str):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workspace_dir = _resolve_workspace_dir_for_workflow(workflow)

    if not workspace_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Generated workspace not found for this workflow.",
        )

    workspace_path = _workspace_path_for_response(workspace_dir)
    preview_runner = get_preview_runner()
    stopped = await asyncio.to_thread(preview_runner.stop_preview, workflow_id)

    if stopped:
        await _publish_log(workflow_id, "Stopped existing preview before restart.")

    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="preview:stopped",
        payload={
            "message": "Restarting preview from generated workspace.",
            "reason": "restart",
        },
    )

    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="agent:started",
        payload={
            "agentId": "preview",
            "name": "Live Preview",
            "detail": "Restarting preview runtime",
        },
    )
    await _publish_log(workflow_id, "Restarting preview from generated workspace.")
    loop = asyncio.get_running_loop()

    def on_runner_log(message: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            _publish_log(workflow_id, message),
            loop,
        )
        future.result()

    def on_runner_stage(stage: str, status: str, detail: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            _publish_workflow_event(
                workflow_id=workflow_id,
                event_type="runner:stage",
                payload={
                    "stage": stage,
                    "status": status,
                    "detail": detail,
                },
            ),
            loop,
        )
        future.result()

    preview_result = await asyncio.to_thread(
        preview_runner.start_preview,
        workflow_id,
        workspace_dir,
        on_stage=on_runner_stage,
        on_log=on_runner_log,
    )

    if preview_result.status != "preview_ready":
        message = preview_result.error_message or "Preview validation failed."

        await _publish_log(
            workflow_id,
            f"Preview restart failed with status: {preview_result.status}",
        )
        await _publish_workflow_event(
            workflow_id=workflow_id,
            event_type="agent:failed",
            payload={
                "agentId": "preview",
                "name": "Live Preview",
                "detail": message,
            },
        )
        await _publish_workflow_event(
            workflow_id=workflow_id,
            event_type="preview:failed",
            payload={
                "status": preview_result.status,
                "message": message,
            },
        )

        return PreviewActionResponse(
            workflowId=workflow_id,
            status=preview_result.status,
            message=message,
            workspacePath=workspace_path,
        )

    ready_message = f"Preview restarted: {preview_result.preview_url}"

    await _publish_log(workflow_id, ready_message)
    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="agent:completed",
        payload={
            "agentId": "preview",
            "name": "Live Preview",
            "detail": f"Preview ready at {preview_result.preview_url}",
        },
    )
    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="preview:ready",
        payload={
            "previewUrl": preview_result.preview_url,
            "previewPort": preview_result.preview_port,
        },
    )

    return PreviewActionResponse(
        workflowId=workflow_id,
        status="preview_ready",
        message=ready_message,
        previewUrl=preview_result.preview_url,
        previewPort=preview_result.preview_port,
        workspacePath=workspace_path,
    )


@app.delete(
    "/api/workflows/{workflow_id}/preview",
    response_model=PreviewActionResponse,
)
async def stop_workflow_preview(workflow_id: str):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workspace_dir = _resolve_workspace_dir_for_workflow(workflow)
    workspace_path = (
        _workspace_path_for_response(workspace_dir)
        if workspace_dir.exists()
        else None
    )

    preview_runner = get_preview_runner()
    stopped = await asyncio.to_thread(preview_runner.stop_preview, workflow_id)
    message = "Preview stopped." if stopped else "Preview was not running."

    await _publish_log(workflow_id, message)
    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="preview:stopped",
        payload={
            "message": message,
            "reason": "stop",
        },
    )

    return PreviewActionResponse(
        workflowId=workflow_id,
        status="preview_stopped",
        message=message,
        workspacePath=workspace_path,
    )


@app.delete(
    "/api/workflows/{workflow_id}/workspace",
    response_model=PreviewActionResponse,
)
async def clean_workflow_workspace(workflow_id: str):
    _validate_workflow_id(workflow_id)
    workflow = get_workflow_record(workflow_id)

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workspace_dir = _resolve_workspace_dir_for_workflow(workflow)
    preview_runner = get_preview_runner()

    stopped = await asyncio.to_thread(preview_runner.stop_preview, workflow_id)

    if stopped:
        await _publish_log(workflow_id, "Preview stopped before workspace cleanup.")
        await _publish_workflow_event(
            workflow_id=workflow_id,
            event_type="preview:stopped",
            payload={
                "message": "Preview stopped before workspace cleanup.",
                "reason": "clean",
            },
        )

    if workspace_dir.exists():
        try:
            await asyncio.to_thread(shutil.rmtree, workspace_dir)
        except OSError as error:
            message = f"Failed to clean workspace: {error}"
            await _publish_log(workflow_id, message)
            raise HTTPException(status_code=500, detail=message) from error

        message = "Workspace cleaned."
    else:
        message = "Workspace already removed."

    await _publish_log(workflow_id, message)
    await _publish_workflow_event(
        workflow_id=workflow_id,
        event_type="workspace:cleaned",
        payload={
            "message": message,
        },
    )

    return PreviewActionResponse(
        workflowId=workflow_id,
        status="workspace_cleaned",
        message=message,
        workspacePath=None,
    )


@app.websocket("/ws/workflows/{workflow_id}")
async def workflow_events_socket(websocket: WebSocket, workflow_id: str):
    await workflow_event_manager.connect(
        workflow_id=workflow_id,
        websocket=websocket,
    )

    try:
        while True:
            # Keep the connection open.
            # The frontend does not need to send anything yet.
            await websocket.receive_text()

    except WebSocketDisconnect:
        await workflow_event_manager.disconnect(
            workflow_id=workflow_id,
            websocket=websocket,
        )
