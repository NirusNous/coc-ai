from pydantic import BaseModel


class WorkflowRequest(BaseModel):
    prompt: str


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


class FileWriteResult(BaseModel):
    workspacePath: str
    writtenFiles: list[str]


class WorkflowResponse(BaseModel):
    workflowId: str
    status: str
    prompt: str
    requirements: RequirementsSpec
    architecture: ArchitectureSpec
    files: list[GeneratedFile]
    logs: list[str]
    previewUrl: str | None = None
    workspacePath: str | None = None
