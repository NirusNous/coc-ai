from uuid import uuid4

from app.agents import (
    architecture_agent,
    code_generation_agent,
    requirements_agent,
)
from app.models import WorkflowResponse
from app.services.file_writer import write_generated_files
from app.config import GENERATED_ROOT
from app.local_runner import LocalRunnerError, start_preview


def run_mock_workflow(prompt: str) -> WorkflowResponse:
    workflow_id = f"workflow_{uuid4().hex[:8]}"

    logs: list[str] = []

    logs.append(f"Workflow {workflow_id} started.")
    logs.append("Requirements Agent started.")

    requirements = requirements_agent(prompt)

    logs.append("Requirements Agent completed.")
    logs.append(f"Detected app name: {requirements.appName}")
    logs.append("Architecture Agent started.")

    architecture = architecture_agent(
        prompt=prompt,
        requirements=requirements,
    )

    logs.append("Architecture Agent completed.")
    logs.append(f"Selected frontend stack: {architecture.stack.frontend} + {architecture.stack.language}")
    logs.append("Code Generation Agent started.")

    files = code_generation_agent(
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
    )

    logs.append("Code Generation Agent completed.")
    logs.append(f"Generated {len(files)} files.")
    logs.append("Phase 2 complete. Files are not written to disk yet.")

    file_write_result = write_generated_files(
        workflow_id=workflow_id,
        files=files,
    )

    logs.append("File Writer completed.")
    logs.append(f"Workspace created: {file_write_result.workspacePath}")

    for written_file in file_write_result.writtenFiles:
        logs.append(f"Wrote file: {written_file}")

    logs.append("Local Runner started.")

    preview_url: str | None = None
    preview_port: int | None = None
    status = "files_written"

    try:
        runner_result = start_preview(
            workflow_id=workflow_id,
            workspace_dir=GENERATED_ROOT / workflow_id,
        )

        preview_url = runner_result.preview_url
        preview_port = runner_result.preview_port
        status = "preview_ready"

        logs.extend(runner_result.logs)
        logs.append("Local Runner completed.")
        logs.append(f"Preview URL: {preview_url}")

    except LocalRunnerError as error:
        status = "failed"
        logs.append("Local Runner failed.")
        logs.append(str(error))


    return WorkflowResponse(
        workflowId=workflow_id,
        status=status,
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        files=files,
        logs=logs,
        previewUrl=preview_url,
        previewPort=preview_port,
        workspacePath=file_write_result.workspacePath,
    )