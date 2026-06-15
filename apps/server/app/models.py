from pydantic import BaseModel, Field


class WorkflowRequest(BaseModel):
    prompt: str = Field(min_length=1)


class GeneratedFile(BaseModel):
    path: str
    content: str


class RequirementsSpec(BaseModel):
    appName: str
    summary: str
    features: list[str]
    constraints: list[str]


class StackSpec(BaseModel):
    frontend: str
    language: str
    buildTool: str
    styling: str
    stateManagement: str


class ComponentSpec(BaseModel):
    name: str
    responsibility: str


class DataFieldSpec(BaseModel):
    name: str
    type: str
    required: bool


class DataModelSpec(BaseModel):
    name: str
    fields: list[DataFieldSpec]


class ArchitectureSpec(BaseModel):
    stack: StackSpec
    components: list[ComponentSpec]
    dataModels: list[DataModelSpec]


class WorkflowResponse(BaseModel):
    workflowId: str
    status: str
    prompt: str
    requirements: RequirementsSpec
    architecture: ArchitectureSpec
    files: list[GeneratedFile]
    logs: list[str]
    previewUrl: str | None = None