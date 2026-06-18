export type WorkflowStatus =
  | "idle"
  | "submitting"
  | "queued"
  | "running"
  | "awaiting_approval"
  | "code_generated"
  | "files_written"
  | "install_failed"
  | "build_failed"
  | "preview_failed"
  | "timeout"
  | "runtime_crashed"
  | "preview_restarting"
  | "preview_ready"
  | "preview_stopped"
  | "workspace_cleaned"
  | "completed"
  | "failed";

export type AgentId =
  | "requirements"
  | "architecture"
  | "code"
  | "build"
  | "debug"
  | "patch"
  | "files"
  | "preview";

export type AgentStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface AgentEvent {
  id: AgentId;
  name: string;
  status: AgentStatus;
  detail: string;
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
  styling: string;
  buildTool: string;
  stateManagement: string;
}

export interface ComponentSpec {
  name: string;
  responsibility: string;
}

export interface FieldSpec {
  name: string;
  type: string;
  required: boolean;
}

export interface DataModelSpec {
  name: string;
  fields: FieldSpec[];
}

export interface ArchitectureSpec {
  stack: StackSpec;
  components: ComponentSpec[];
  dataModels: DataModelSpec[];
}

export interface GeneratedFile {
  path: string;
  content: string;
}

export interface BuildAttempt {
  attemptNumber: number;
  status: WorkflowStatus;
  summary: string;
  failureType?: RunnerFailureStatus | null;
  debugSummary?: string | null;
  logs: string[];
}

export interface WorkflowResponse {
  projectId?: string | null;
  workflowId: string;
  status: WorkflowStatus;
  prompt: string;
  requirements?: RequirementsSpec | null;
  architecture?: ArchitectureSpec | null;
  approvalStage?: ApprovalStage | null;
  files: GeneratedFile[];
  logs: string[];
  previewUrl?: string | null;
  previewPort?: number | null;
  workspacePath?: string | null;
  attempts: BuildAttempt[];
  currentAttempt: number;
  maxAttempts: number;
  isRetrying: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface WorkflowStartResponse {
  projectId: string;
  workflowId: string;
  status: "queued";
}

export type ApprovalStage = "architecture";
export type ChangeRequestScope = "requirements" | "architecture";

export interface WorkflowActionResponse {
  workflowId: string;
  status: WorkflowStatus | "running";
  message: string;
}

export type PreviewAction = "stopping" | "restarting" | "cleaning";
export type RunnerStage = "install" | "build" | "preview";
export type RunnerStageStatus = "started" | "completed" | "failed";
export type RunnerFailureStatus =
  | "install_failed"
  | "build_failed"
  | "preview_failed"
  | "timeout"
  | "runtime_crashed";

export interface PreviewInfo {
  workflowId: string;
  previewUrl: string;
  previewPort?: number | null;
  workspacePath: string;
  pid?: number | null;
  runner?: string | null;
  namespace?: string | null;
}

export interface PreviewListResponse {
  previews: PreviewInfo[];
}

export interface WorkflowSummary {
  projectId?: string | null;
  workflowId: string;
  prompt: string;
  status: WorkflowStatus;
  workspacePath?: string | null;
  previewUrl?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowHistoryResponse {
  workflows: WorkflowSummary[];
}

export interface ProjectResponse {
  projectId: string;
  name: string;
  description?: string | null;
  workflowCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectListResponse {
  projects: ProjectResponse[];
}

export interface PreviewActionResponse {
  workflowId: string;
  status:
    | "preview_ready"
    | "preview_stopped"
    | "workspace_cleaned"
    | RunnerFailureStatus;
  message: string;
  previewUrl?: string | null;
  previewPort?: number | null;
  workspacePath?: string | null;
}

interface WorkflowSocketEventBase<
  EventType extends string,
  Payload extends object
> {
  id: string;
  workflowId: string;
  type: EventType;
  timestamp: string;
  payload: Payload;
}

export type WorkflowSocketEvent =
  | WorkflowSocketEventBase<
      "workflow:started",
      {
        workflowId: string;
        projectId?: string;
        status: "running";
        currentAttempt?: number;
        maxAttempts?: number;
        isRetrying?: boolean;
        approvalStage?: ApprovalStage | null;
      }
    >
  | WorkflowSocketEventBase<
      "workflow:awaiting_approval",
      WorkflowResponse
    >
  | WorkflowSocketEventBase<
      "log",
      {
        message: string;
      }
    >
  | WorkflowSocketEventBase<
      "agent:started",
      {
        agentId: AgentId;
        name: string;
        detail: string;
      }
    >
  | WorkflowSocketEventBase<
      "agent:completed",
      {
        agentId: "requirements";
        name: string;
        detail: string;
        output: RequirementsSpec;
      }
    >
  | WorkflowSocketEventBase<
      "agent:completed",
      {
        agentId: "architecture";
        name: string;
        detail: string;
        output: ArchitectureSpec;
      }
    >
  | WorkflowSocketEventBase<
      "agent:completed",
      {
        agentId: "code" | "debug" | "patch" | "files" | "preview";
        name: string;
        detail: string;
      }
    >
  | WorkflowSocketEventBase<
      "agent:failed",
      {
        agentId: AgentId;
        name: string;
        detail: string;
      }
    >
  | WorkflowSocketEventBase<
      "attempt:started",
      {
        attemptNumber: number;
        maxAttempts: number;
        isRetrying: boolean;
      }
    >
  | WorkflowSocketEventBase<
      "attempt:completed",
      {
        attempt: BuildAttempt;
        maxAttempts: number;
        willRetry: boolean;
      }
    >
  | WorkflowSocketEventBase<
      "attempt:retrying",
      {
        attemptNumber: number;
        nextAttemptNumber: number;
        maxAttempts: number;
        message: string;
        debugSummary: string;
      }
    >
  | WorkflowSocketEventBase<
      "code:generated",
      {
        files: GeneratedFile[];
      }
    >
  | WorkflowSocketEventBase<
      "files:written",
      {
        workspacePath: string;
        writtenFiles: string[];
      }
    >
  | WorkflowSocketEventBase<
      "runner:stage",
      {
        attemptNumber?: number;
        stage: RunnerStage;
        status: RunnerStageStatus;
        detail: string;
      }
    >
  | WorkflowSocketEventBase<
      "preview:ready",
      {
        previewUrl: string;
        previewPort?: number;
        attemptNumber?: number;
      }
    >
  | WorkflowSocketEventBase<
      "preview:failed",
      {
        status: RunnerFailureStatus;
        message: string;
        attemptNumber?: number;
      }
    >
  | WorkflowSocketEventBase<
      "preview:stopped",
      {
        message: string;
        reason: "stop" | "restart" | "clean";
      }
    >
  | WorkflowSocketEventBase<
      "workspace:cleaned",
      {
        message: string;
      }
    >
  | WorkflowSocketEventBase<"workflow:completed", WorkflowResponse>
  | WorkflowSocketEventBase<
      "workflow:failed",
      {
        status: "failed";
        message: string;
      }
    >;
