from uuid import uuid4

from app.agents import architecture_agent, code_generation_agent, requirements_agent
from app.models import WorkflowResponse
from app.services.file_writer import write_generated_files


class WorkflowEngine:
    async def run(self, prompt: str) -> WorkflowResponse:
        workflow_id = f"workflow_{uuid4().hex[:8]}"

        logs: list[str] = []

        logs.append(f"Workflow {workflow_id} started.")
        logs.append("Requirements Agent started.")

        requirements = requirements_agent(prompt)

        logs.append("Requirements Agent completed.")
        logs.append(f"App name: {requirements.appName}")
        logs.append("Architecture Agent started.")

        architecture = architecture_agent(
            prompt=prompt,
            requirements=requirements,
        )

        logs.append("Architecture Agent completed.")
        logs.append(
            f"Selected stack: {architecture.stack.frontend} + {architecture.stack.buildTool}"
        )
        logs.append("Code Generation Agent started.")

        files = code_generation_agent(
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
        )

        logs.append(f"Code Generation Agent completed. Generated {len(files)} files.")
        logs.append("File Writer started.")

        file_write_result = write_generated_files(
            workflow_id=workflow_id,
            files=files,
        )

        logs.append("File Writer completed.")
        logs.append(f"Workspace created: {file_write_result.workspacePath}")

        for written_file in file_write_result.writtenFiles:
            logs.append(f"Wrote file: {written_file}")

        logs.append("Phase 3 complete. Files are now written to disk.")

        return WorkflowResponse(
            workflowId=workflow_id,
            status="files_written",
            prompt=prompt,
            requirements=requirements,
            architecture=architecture,
            files=files,
            logs=logs,
            previewUrl=None,
            workspacePath=file_write_result.workspacePath,
        )
