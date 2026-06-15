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
  content?: string;
}

export interface WorkflowResponse {
  workflowId: string;
  status: string;
  prompt: string;
  previewUrl?: string;
  files?: GeneratedFile[];
}