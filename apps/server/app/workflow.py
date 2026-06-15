from uuid import uuid4

from app.agents import (
    architecture_agent,
    code_generation_agent,
    requirements_agent,
)
from app.models import WorkflowResponse


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

    return WorkflowResponse(
        workflowId=workflow_id,
        status="completed",
        prompt=prompt,
        requirements=requirements,
        architecture=architecture,
        files=files,
        logs=logs,
        previewUrl=None,
    )