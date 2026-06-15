export type WorkflowStatus =
  | "idle"
  | "submitting"
  | "started"
  | "preview_ready"
  | "completed"
  | "failed";

export type AgentStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface AgentEvent {
  id: string;
  name: string;
  status: AgentStatus;
  detail: string;
}

export interface GeneratedFile {
  path: string;
  content: string;
}

export interface RequirementsSpec {
  appName: string;
  summary: string;
  features: string[];
  constraints: string[];
}

export interface StackSpec {
  frontend: string;
  language: string;
  buildTool: string;
  styling: string;
  stateManagement: string;
}

export interface ComponentSpec {
  name: string;
  responsibility: string;
}

export interface DataFieldSpec {
  name: string;
  type: string;
  required: boolean;
}

export interface DataModelSpec {
  name: string;
  fields: DataFieldSpec[];
}

export interface ArchitectureSpec {
  stack: StackSpec;
  components: ComponentSpec[];
  dataModels: DataModelSpec[];
}

export interface WorkflowResponse {
  workflowId: string;
  status: string;
  prompt: string;
  requirements: RequirementsSpec;
  architecture: ArchitectureSpec;
  files: GeneratedFile[];
  logs: string[];
  previewUrl?: string | null;
}