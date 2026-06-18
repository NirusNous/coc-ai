from typing import Literal

from pydantic import BaseModel


class WorkflowRequest(BaseModel):
    prompt: str
    projectId: str


class WorkflowApprovalRequest(BaseModel):
    note: str | None = None


class WorkflowChangeRequest(BaseModel):
    scope: Literal["requirements", "architecture"] = "architecture"
    feedback: str


class RequirementsSpec(BaseModel):
    appName: str
    summary: str
    features: list[str]
    constraints: list[str]


class StackSpec(BaseModel):
    frontend: str
    language: str
    styling: str
    buildTool: str
    stateManagement: str


class ComponentSpec(BaseModel):
    name: str
    responsibility: str


class FieldSpec(BaseModel):
    name: str
    type: str
    required: bool


class DataModelSpec(BaseModel):
    name: str
    fields: list[FieldSpec]


class ArchitectureSpec(BaseModel):
    stack: StackSpec
    components: list[ComponentSpec]
    dataModels: list[DataModelSpec]


class GeneratedFile(BaseModel):
    path: str
    content: str


class GeneratedAppSpec(BaseModel):
    files: list[GeneratedFile]


class DebugAnalysisSpec(BaseModel):
    summary: str
    rootCause: str
    patchStrategy: list[str]


class BuildAttempt(BaseModel):
    attemptNumber: int
    status: str
    summary: str
    failureType: str | None = None
    debugSummary: str | None = None
    logs: list[str]


class FileWriteResult(BaseModel):
    workspacePath: str
    writtenFiles: list[str]


class WorkflowResponse(BaseModel):
    projectId: str | None = None
    workflowId: str
    status: str
    prompt: str
    requirements: RequirementsSpec | None = None
    architecture: ArchitectureSpec | None = None
    approvalStage: str | None = None
    files: list[GeneratedFile]
    logs: list[str]
    previewUrl: str | None = None
    previewPort: int | None = None
    workspacePath: str | None = None
    attempts: list[BuildAttempt] = []
    currentAttempt: int = 1
    maxAttempts: int = 1
    isRetrying: bool = False
    createdAt: str | None = None
    updatedAt: str | None = None


class WorkflowStartResponse(BaseModel):
    projectId: str
    workflowId: str
    status: str


class WorkflowActionResponse(BaseModel):
    workflowId: str
    status: str
    message: str


class ProjectActionResponse(BaseModel):
    projectId: str
    status: str
    message: str


class PreviewInfo(BaseModel):
    workflowId: str
    previewUrl: str
    previewPort: int | None = None
    workspacePath: str
    pid: int | None = None
    runner: str | None = None
    namespace: str | None = None


class PreviewListResponse(BaseModel):
    previews: list[PreviewInfo]


class PreviewActionResponse(BaseModel):
    workflowId: str
    status: str
    message: str
    previewUrl: str | None = None
    previewPort: int | None = None
    workspacePath: str | None = None


class WorkflowSummary(BaseModel):
    projectId: str | None = None
    workflowId: str
    prompt: str
    status: str
    workspacePath: str | None = None
    previewUrl: str | None = None
    createdAt: str
    updatedAt: str


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowSummary]


class ProjectRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    projectId: str
    name: str
    description: str | None = None
    workflowCount: int = 0
    createdAt: str
    updatedAt: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class RunnerConfigResponse(BaseModel):
    runner: str
    kubeconfigPath: str | None = None
    k8sContext: str | None = None
    namespacePrefix: str
    previewExposureMode: str
    previewBaseDomain: str | None = None


class KubernetesNamespaceInfo(BaseModel):
    name: str
    status: str
    createdAt: str | None = None


class KubernetesNamespaceListResponse(BaseModel):
    namespaces: list[KubernetesNamespaceInfo]


class KubernetesNamespaceActionResponse(BaseModel):
    namespace: str
    status: str
    message: str
